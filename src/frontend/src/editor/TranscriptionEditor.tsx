import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "react-oidc-context";
import { useEditor, EditorContent } from "@tiptap/react";
import { Decoration, DecorationSet } from "prosemirror-view";
import Document from "@tiptap/extension-document";
import Paragraph from "@tiptap/extension-paragraph";
import Text from "@tiptap/extension-text";
import Collaboration from "@tiptap/extension-collaboration";
import CollaborationCursor from "@tiptap/extension-collaboration-cursor";
import { HocuspocusProvider } from "@hocuspocus/provider";
import * as Y from "yjs";
import { WhisperSegment, type WhisperSegmentAttrs } from "./WhisperSegmentMark";
import {
  MAX_RECONNECT_ATTEMPTS,
  computeReconnectDelayMs,
  hasReconnectAttemptsRemaining,
  shouldRetryTicketHttpStatus,
} from "./reconnect-policy";
import { apiFetch, bearerForApi } from "../auth/api-client";
import "./collaboration.css";

interface Segment {
  start: number;
  end: number;
  text: string;
}

const DEBOUNCE_MS = 800;

/** Host-side port in compose (`HOCUSPOCUS_HOST_PORT`, default 11234). Container still uses 1234. */
const DEFAULT_HOCUSPOCUS_HOST_PORT = 11234;

const DEV_FIXTURE_SEGMENTS: Segment[] = [
  { start: 0.0, end: 2.5, text: "Bonjour à tous," },
  { start: 2.5, end: 5.0, text: "bienvenue au camp biblique." },
  { start: 5.0, end: 8.0, text: "Aujourd'hui nous allons étudier le livre de la Genèse." },
];
type AudioLoadStatus = "idle" | "loading" | "ready" | "error";

function roundAudioTime(t: number): number {
  // 1ms precision is enough for click/seek boundaries and makes stringified dataset values match.
  return Math.round(t * 1000) / 1000;
}

function collabWsBase(): string {
  const fromEnv = import.meta.env.VITE_HOCUSPOCUS_URL as string | undefined;
  if (fromEnv?.trim()) {
    return fromEnv.replace(/\/$/, "");
  }
  if (typeof window === "undefined") {
    return `ws://localhost:${DEFAULT_HOCUSPOCUS_HOST_PORT}`;
  }
  const { protocol, hostname } = window.location;
  const scheme = protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${hostname}:${DEFAULT_HOCUSPOCUS_HOST_PORT}`;
}

const ZACHAI_SEED_META = "zachai_meta";

/** Stable hue for awareness cursor from user id (AC7). */
function awarenessColorFromId(id: string): string {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  const hue = h % 360;
  return `hsl(${hue} 62% 42%)`;
}

function segmentsToEditorJson(segments: Segment[]) {
  return {
    type: "doc",
    content: [
      {
        type: "paragraph",
        content: segments.flatMap((seg, i) => {
          const nodes = [
            {
              type: "text",
              text: seg.text,
              marks: [
                {
                  type: "whisperSegment",
                  attrs: {
                    audioStart: seg.start,
                    audioEnd: seg.end,
                    sourceText: seg.text,
                  } satisfies WhisperSegmentAttrs,
                },
              ],
            },
          ];
          if (i < segments.length - 1) {
            nodes.push({ type: "text", text: " ", marks: [] });
          }
          return nodes;
        }),
      },
    ],
  };
}

function collectMarkedSegments(
  editor: ReturnType<typeof useEditor>,
): { attrs: WhisperSegmentAttrs; currentText: string }[] {
  if (!editor) return [];
  const results: { attrs: WhisperSegmentAttrs; currentText: string }[] = [];
  const doc = editor.state.doc;
  doc.descendants((node) => {
    if (!node.isText || !node.marks.length) return;
    for (const mark of node.marks) {
      if (mark.type.name === "whisperSegment") {
        const attrs = mark.attrs as WhisperSegmentAttrs;
        const text = node.text ?? "";
        const existing = results.find(
          (r) =>
            r.attrs.audioStart === attrs.audioStart &&
            r.attrs.audioEnd === attrs.audioEnd &&
            r.attrs.sourceText === attrs.sourceText,
        );
        if (existing) {
          existing.currentText += text;
        } else {
          results.push({ attrs: { ...attrs }, currentText: text });
        }
      }
    }
  });
  return results;
}

export function TranscriptionEditor() {
  const auth = useAuth();
  const token = useMemo(() => bearerForApi(auth.user), [auth.user]);
  const audioIdParam = new URLSearchParams(window.location.search).get("audio_id");
  const audioId =
    audioIdParam && /^\d+$/.test(audioIdParam) ? parseInt(audioIdParam, 10) : null;

  const ydoc = useMemo(() => new Y.Doc(), []);

  const [provider, setProvider] = useState<HocuspocusProvider | null>(null);
  const [synced, setSynced] = useState(false);
  const [status, setStatus] = useState<string>("");
  const [collabLine, setCollabLine] = useState<string>("");
  const pendingRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSentRef = useRef<Map<string, string>>(new Map());
  const seededRef = useRef(false);

  // Story 5.3 — audio playback + karaoke highlight state
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const editorRef = useRef<ReturnType<typeof useEditor> | null>(null);
  const editorContainerRef = useRef<HTMLDivElement | null>(null);

  const [audioLoadStatus, setAudioLoadStatus] = useState<AudioLoadStatus>("idle");
  const [audioError, setAudioError] = useState<string>("");

  const audioUrlCacheRef = useRef<Map<number, { url: string; expiresIn: number }>>(new Map());

  type WhisperIntervalIndex = {
    audioStart: number;
    audioEnd: number;
    key: string;
    ranges: Array<{ from: number; to: number }>;
  };
  const intervalsRef = useRef<WhisperIntervalIndex[]>([]);
  const intervalByKeyRef = useRef<Map<string, WhisperIntervalIndex>>(new Map());
  const activeIntervalKeyRef = useRef<string | null>(null);
  const rafIdRef = useRef<number | null>(null);

  const displayName = useMemo(() => {
    const p = auth.user?.profile as
      | { preferred_username?: string; name?: string; sub?: string }
      | undefined;
    return p?.preferred_username ?? p?.name ?? p?.sub ?? "Collaborator";
  }, [auth.user?.profile]);

  const awarenessColor = useMemo(() => {
    const p = auth.user?.profile as { sub?: string } | undefined;
    return awarenessColorFromId(p?.sub ?? displayName);
  }, [auth.user?.profile, displayName]);

  useEffect(() => {
    if (!audioId || !token) {
      setProvider(null);
      setSynced(false);
      setCollabLine("");
      return;
    }

    let cancelled = false;
    const hpRef: { current: HocuspocusProvider | null } = { current: null };
    let reconnectAttempts = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let reconnectPending = false;

    const cleanupProvider = () => {
      hpRef.current?.destroy();
      hpRef.current = null;
      setProvider(null);
      setSynced(false);
    };

    const scheduleReconnect = (reason: string) => {
      if (cancelled || reconnectPending) return;
      if (!hasReconnectAttemptsRemaining(reconnectAttempts)) {
        setCollabLine(`${reason} — reconnect stopped after ${MAX_RECONNECT_ATTEMPTS} attempts`);
        return;
      }
      reconnectPending = true;
      const waitMs = computeReconnectDelayMs(reconnectAttempts);
      reconnectAttempts += 1;
      setCollabLine(`${reason} — reconnecting in ${Math.round(waitMs / 1000)}s…`);
      reconnectTimer = setTimeout(() => {
        reconnectPending = false;
        void connectWithFreshTicket();
      }, waitMs);
    };

    const connectWithFreshTicket = async () => {
      if (cancelled) return;

      setCollabLine("Minting collaboration ticket…");
      setSynced(false);
      seededRef.current = false;

      try {
        cleanupProvider();
        const tr = await apiFetch("/v1/editor/ticket", token, {
          method: "POST",
          body: JSON.stringify({ document_id: audioId, permissions: ["read", "write"] }),
        });
        if (!tr.ok) {
          let hint = "";
          try {
            const errBody = (await tr.clone().json()) as { detail?: unknown; error?: string };
            const d = errBody?.detail ?? errBody?.error;
            hint = d != null ? ` — ${typeof d === "string" ? d : JSON.stringify(d)}` : "";
          } catch {
            /* ignore */
          }
          if (shouldRetryTicketHttpStatus(tr.status)) {
            scheduleReconnect(`Ticket HTTP ${tr.status}${hint}`);
          } else {
            setCollabLine(`Ticket HTTP ${tr.status}${hint}`);
          }
          return;
        }
        const { ticket_id } = (await tr.json()) as { ticket_id: string };
        if (cancelled) return;

        const url = collabWsBase();
        const hp = new HocuspocusProvider({
          url,
          name: String(audioId),
          token: ticket_id,
          document: ydoc,
        });
        hpRef.current = hp;

        hp.on("synced", () => {
          if (!cancelled) {
            reconnectAttempts = 0;
            setSynced(true);
          }
        });
        hp.on("authenticationFailed", () => {
          if (cancelled) return;
          cleanupProvider();
          scheduleReconnect("Hocuspocus auth failed");
        });
        hp.on("close", (ev: { event?: CloseEvent }) => {
          if (cancelled) return;
          const code = ev?.event?.code;
          cleanupProvider();
          scheduleReconnect(code ? `Disconnected (code ${code})` : "Disconnected");
        });

        if (!cancelled) {
          setProvider(hp);
          setCollabLine(`CRDT sync → ${url} (room ${audioId})`);
        }
      } catch (e) {
        if (!cancelled) scheduleReconnect(`Collaboration error: ${String(e)}`);
      }
    };
    void connectWithFreshTicket();

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      cleanupProvider();
    };
  }, [audioId, token, ydoc]);

  const editor = useEditor(
    {
      extensions: [
        Document,
        Paragraph,
        Text,
        WhisperSegment,
        Collaboration.configure({
          document: ydoc,
        }),
        ...(provider
          ? [
              CollaborationCursor.configure({
                provider,
                user: {
                  name: displayName,
                  color: awarenessColor,
                },
              }),
            ]
          : []),
      ],
      content: "<p></p>",
      editable: true,
    },
    [provider, displayName, awarenessColor, ydoc],
  );

  useEffect(() => {
    editorRef.current = editor;
  }, [editor]);

  const rebuildWhisperSegmentIndex = useCallback(() => {
    const ed = editorRef.current;
    if (!ed) return;

    const indexMap = new Map<string, WhisperIntervalIndex>();
    const doc = ed.state.doc;

    doc.descendants((node, pos) => {
      if (!node.isText || !node.marks?.length) return;

      for (const mark of node.marks) {
        if (mark.type.name !== "whisperSegment") continue;
        const attrs = mark.attrs as WhisperSegmentAttrs;

        const audioStart = roundAudioTime(attrs.audioStart);
        const audioEnd = roundAudioTime(attrs.audioEnd);
        const key = `${audioStart}-${audioEnd}`;

        const from = pos;
        const to = pos + node.nodeSize;

        const entry =
          indexMap.get(key) ??
          ({
            audioStart,
            audioEnd,
            key,
            ranges: [],
          } as WhisperIntervalIndex);
        entry.ranges.push({ from, to });
        indexMap.set(key, entry);
      }
    });

    const intervals = Array.from(indexMap.values()).sort(
      (a, b) => a.audioStart - b.audioStart,
    );

    intervalsRef.current = intervals;
    intervalByKeyRef.current = new Map(intervals.map((it) => [it.key, it]));
  }, []);

  const applyKaraokeDecoration = useCallback(
    (interval: WhisperIntervalIndex | null) => {
      const ed = editorRef.current;
      if (!ed) return;

      if (!interval) {
        activeIntervalKeyRef.current = null;
        ed.view.setProps({
          decorations: (state) => DecorationSet.create(state.doc, []),
        });
        return;
      }

      if (activeIntervalKeyRef.current === interval.key) return;
      activeIntervalKeyRef.current = interval.key;
      const activeKey = interval.key;
      ed.view.setProps({
        decorations: (state) => {
          const [startRaw, endRaw] = activeKey.split("-");
          const audioStart = Number(startRaw);
          const audioEnd = Number(endRaw);
          if (!Number.isFinite(audioStart) || !Number.isFinite(audioEnd)) {
            return DecorationSet.create(state.doc, []);
          }

          const decorations: Decoration[] = [];
          state.doc.descendants((node, pos) => {
            if (!node.isText || !node.marks?.length) return;
            for (const mark of node.marks) {
              if (mark.type.name !== "whisperSegment") continue;
              const attrs = mark.attrs as WhisperSegmentAttrs;
              if (
                roundAudioTime(attrs.audioStart) === audioStart &&
                roundAudioTime(attrs.audioEnd) === audioEnd
              ) {
                const from = pos;
                const to = pos + node.nodeSize;
                if (from >= 0 && to > from && to <= state.doc.content.size) {
                  decorations.push(
                    Decoration.inline(from, to, { class: "zachai-karaoke-active" }),
                  );
                }
              }
            }
          });
          return DecorationSet.create(state.doc, decorations);
        },
      });
    },
    [],
  );

  const updateKaraokeHighlightForTime = useCallback(
    (time: number) => {
      const intervals = intervalsRef.current;
      if (!intervals.length) return;

      const t = roundAudioTime(time);

      // Find the rightmost segment with audioStart <= t, then validate t < audioEnd.
      let lo = 0;
      let hi = intervals.length - 1;
      let best = -1;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        const midInterval = intervals[mid];
        if (midInterval && midInterval.audioStart <= t) {
          best = mid;
          lo = mid + 1;
        } else {
          hi = mid - 1;
        }
      }

      const candidate = best >= 0 ? intervals[best] : null;
      const active =
        candidate && t >= candidate.audioStart && t < candidate.audioEnd
          ? candidate
          : null;

      applyKaraokeDecoration(active);
    },
    [applyKaraokeDecoration],
  );

  const stopKaraokeLoop = useCallback(() => {
    if (rafIdRef.current != null) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
  }, []);

  const startKaraokeLoop = useCallback(() => {
    if (rafIdRef.current != null) return;

    const step = () => {
      rafIdRef.current = null;

      const audio = audioRef.current;
      const ed = editorRef.current;
      if (!audio || !ed) return;
      if (audio.paused || audio.ended) return;

      updateKaraokeHighlightForTime(audio.currentTime);
      rafIdRef.current = requestAnimationFrame(step);
    };

    rafIdRef.current = requestAnimationFrame(step);
  }, [updateKaraokeHighlightForTime]);

  // Initialize the dedicated audio element once and wire karaoke highlight updates.
  useEffect(() => {
    const audio = new Audio();
    audio.preload = "auto";
    audioRef.current = audio;

    audio.onloadedmetadata = () => {
      setAudioLoadStatus("ready");
      setAudioError("");
    };

    audio.onerror = () => {
      setAudioLoadStatus("error");
      setAudioError("Audio failed to load. Text editing will still work.");
      stopKaraokeLoop();
      applyKaraokeDecoration(null);
    };

    audio.onplaying = () => {
      setAudioLoadStatus((s) => (s === "idle" ? "ready" : s));
      startKaraokeLoop();
    };

    audio.onpause = () => {
      stopKaraokeLoop();
      // Keep the highlight at the last computed timestamp (no doc mutation).
      if (audio && !Number.isNaN(audio.currentTime)) {
        updateKaraokeHighlightForTime(audio.currentTime);
      }
    };

    audio.onended = () => {
      stopKaraokeLoop();
      applyKaraokeDecoration(null);
    };

    return () => {
      stopKaraokeLoop();
      applyKaraokeDecoration(null);
      audio.pause();
      audio.src = "";
      audioRef.current = null;
    };
  }, [
    applyKaraokeDecoration,
    startKaraokeLoop,
    stopKaraokeLoop,
    updateKaraokeHighlightForTime,
  ]);

  // Fetch the normalized audio presigned URL exactly once per audioId (cache + safe abort).
  useEffect(() => {
    if (!audioId || !token || !synced) return;
    const audio = audioRef.current;
    if (!audio) return;

    let cancelled = false;
    const controller = new AbortController();

    const run = async () => {
      const cached = audioUrlCacheRef.current.get(audioId);
      if (cached) {
        setAudioLoadStatus("loading");
        setAudioError("");
        audio.src = cached.url;
        audio.load();
        return;
      }

      setAudioLoadStatus("loading");
      setAudioError("");
      setStatus("Loading normalized audio…");

      try {
        const resp = await apiFetch(`/v1/audio-files/${audioId}/media`, token, {
          method: "GET",
          signal: controller.signal,
        });
        if (!resp.ok) {
          let hint = "";
          try {
            const errBody = (await resp.json()) as { detail?: unknown; error?: string };
            const d = errBody?.detail ?? errBody?.error;
            hint = d != null ? (typeof d === "string" ? d : JSON.stringify(d)) : "";
          } catch {
            /* ignore */
          }
          throw new Error(`HTTP ${resp.status}${hint ? ` — ${hint}` : ""}`);
        }
        const data = (await resp.json()) as { presigned_url: string; expires_in?: number };

        if (cancelled) return;

        const expiresIn = typeof data.expires_in === "number" ? data.expires_in : 3600;
        audioUrlCacheRef.current.set(audioId, { url: data.presigned_url, expiresIn });
        audio.src = data.presigned_url;
        audio.load();
      } catch (e) {
        if (cancelled) return;
        setAudioLoadStatus("error");
        setAudioError(String(e));
        setStatus(`Audio error: ${String(e)}`);
        stopKaraokeLoop();
        applyKaraokeDecoration(null);
      }
    };

    void run();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [
    audioId,
    token,
    synced,
    applyKaraokeDecoration,
    startKaraokeLoop,
    stopKaraokeLoop,
    updateKaraokeHighlightForTime,
  ]);

  // Click → seek (text → audio) via DOM event delegation.
  useEffect(() => {
    const container = editorContainerRef.current;
    if (!container) return;

    const onClick = (ev: MouseEvent) => {
      const target = ev.target as HTMLElement | null;
      const span = target?.closest?.("span[data-whisper-segment]") as HTMLElement | null;
      if (!span) return;

      const startStr = span.dataset.audioStart;
      const endStr = span.dataset.audioEnd;
      if (!startStr) return;

      const start = parseFloat(startStr);
      const end = endStr != null ? parseFloat(endStr) : NaN;
      if (Number.isNaN(start)) return;

      const audio = audioRef.current;
      if (!audio) return;

      // Seek immediately, and update the karaoke highlight right away (even before the next rAF tick).
      audio.currentTime = start;

      const roundedStart = roundAudioTime(start);
      const roundedEnd = Number.isNaN(end) ? roundAudioTime(start) : roundAudioTime(end);
      const key = `${roundedStart}-${roundedEnd}`;
      const interval = intervalByKeyRef.current.get(key) ?? null;
      if (interval) applyKaraokeDecoration(interval);
      else updateKaraokeHighlightForTime(start);

      // Playback: ignore failures (autoplay policy / not yet loaded); highlight still updates.
      audio
        .play()
        .catch(() => {
          /* no-op */
        });
    };

    container.addEventListener("click", onClick);
    return () => container.removeEventListener("click", onClick);
  }, [applyKaraokeDecoration, updateKaraokeHighlightForTime]);

  useEffect(() => {
    if (!editor || !synced || !audioId || !token || seededRef.current) return;

    const run = async () => {
      if (!editor.isEmpty) {
        seededRef.current = true;
        setStatus("Document loaded from collaboration server");
        return;
      }
      await new Promise((r) => setTimeout(r, 50 + Math.random() * 120));
      if (!editor.isEmpty || seededRef.current) {
        seededRef.current = true;
        return;
      }
      const meta = ydoc.getMap(ZACHAI_SEED_META);
      let claimed = false;
      ydoc.transact(() => {
        if (meta.get("transcription_seeded")) return;
        meta.set("transcription_seeded", true);
        claimed = true;
      });
      if (!claimed) {
        seededRef.current = true;
        setStatus("Initial transcription loaded by another collaborator");
        return;
      }
      try {
        setStatus("Loading transcription after sync…");
        const resp = await apiFetch(`/v1/audio-files/${audioId}/transcription`, token);
        if (!resp.ok) {
          setStatus(`Transcription HTTP ${resp.status} — using dev fixture if empty`);
        }
        const data = resp.ok
          ? ((await resp.json()) as { segments: Segment[] })
          : { segments: [] };
        const segs = data.segments.length > 0 ? data.segments : DEV_FIXTURE_SEGMENTS;
        if (!editor.isEmpty) {
          seededRef.current = true;
          setStatus("Document loaded from collaboration server");
          return;
        }
        if (!seededRef.current) {
          editor.commands.setContent(segmentsToEditorJson(segs));
          seededRef.current = true;
          setStatus(
            data.segments.length > 0
              ? `${data.segments.length} segments (initial seed)`
              : "Dev fixture (no server segments yet)",
          );
        }
      } catch (e) {
        ydoc.transact(() => meta.delete("transcription_seeded"));
        setStatus(`Transcription fetch error: ${String(e)}`);
      }
    };
    void run();
  }, [editor, synced, audioId, token, ydoc]);

  const submitCorrections = useCallback(async () => {
    if (!audioId || !token || !editor) return;
    const segments = collectMarkedSegments(editor);
    let sent = 0;
    for (const seg of segments) {
      const key = `${seg.attrs.audioStart}-${seg.attrs.audioEnd}-${seg.attrs.sourceText}`;
      if (
        seg.currentText === seg.attrs.sourceText ||
        lastSentRef.current.get(key) === seg.currentText
      ) {
        continue;
      }
      try {
        const resp = await apiFetch(
          "/v1/golden-set/frontend-correction",
          token,
          {
            method: "POST",
            body: JSON.stringify({
              audio_id: audioId,
              segment_start: seg.attrs.audioStart,
              segment_end: seg.attrs.audioEnd,
              original_text: seg.attrs.sourceText,
              corrected_text: seg.currentText,
              client_mutation_id: `${audioId}-${seg.attrs.audioStart}-${seg.attrs.audioEnd}-${seg.currentText}`,
            }),
          },
        );
        if (resp.ok) {
          lastSentRef.current.set(key, seg.currentText);
          sent++;
        }
      } catch {
        /* network error — will retry on next debounce cycle */
      }
    }
    if (sent > 0) {
      setStatus(`${sent} correction(s) submitted`);
    }
  }, [audioId, token, editor]);

  const debouncedSubmit = useMemo(() => {
    return () => {
      if (pendingRef.current) clearTimeout(pendingRef.current);
      pendingRef.current = setTimeout(() => {
        submitCorrections();
      }, DEBOUNCE_MS);
    };
  }, [submitCorrections]);

  useEffect(() => {
    if (!editor) return;
    const handler = () => {
      debouncedSubmit();
      rebuildWhisperSegmentIndex();

      const audio = audioRef.current;
      if (audio && audioLoadStatus === "ready") {
        updateKaraokeHighlightForTime(audio.currentTime);
      }
    };
    editor.on("update", handler);
    return () => {
      editor.off("update", handler);
      if (pendingRef.current) clearTimeout(pendingRef.current);
    };
  }, [
    editor,
    debouncedSubmit,
    audioLoadStatus,
    rebuildWhisperSegmentIndex,
    updateKaraokeHighlightForTime,
  ]);

  const audioStatusLine =
    audioLoadStatus === "loading"
      ? "Audio: loading…"
      : audioLoadStatus === "ready"
        ? "Audio ready"
        : audioLoadStatus === "error"
          ? `Audio error: ${audioError || "unknown error"}`
          : "";

  if (!audioId) {
    return (
      <div style={{ padding: "1rem", color: "#666" }}>
        <p>
          Pass <code>?audio_id=N</code> to load transcription segments for an
          assigned audio file.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "0.5rem",
          fontSize: "0.875rem",
          color: "#666",
        }}
      >
        <span>Audio #{audioId}</span>
        <span>
          {status}
          {audioStatusLine ? ` · ${audioStatusLine}` : ""}
          {collabLine ? ` · ${collabLine}` : ""}
        </span>
      </div>
      <div
        style={{
          border: "1px solid #ddd",
          borderRadius: "6px",
          padding: "1rem",
          minHeight: "200px",
          lineHeight: "1.8",
          fontSize: "1rem",
        }}
        ref={editorContainerRef}
      >
        <EditorContent editor={editor} />
      </div>
      <p
        style={{
          marginTop: "0.5rem",
          fontSize: "0.75rem",
          color: "#999",
        }}
      >
        Corrections are auto-saved {DEBOUNCE_MS}ms after you stop typing. Real-time sync targets
        &lt;50ms on LAN; manual check: two browsers, same <code>?audio_id=</code>, both signed in,
        edit and verify cursors.
      </p>
    </div>
  );
}
