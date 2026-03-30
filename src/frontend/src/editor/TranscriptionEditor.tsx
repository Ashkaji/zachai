import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "react-oidc-context";
import { useEditor, EditorContent } from "@tiptap/react";
import Document from "@tiptap/extension-document";
import Paragraph from "@tiptap/extension-paragraph";
import Text from "@tiptap/extension-text";
import Collaboration from "@tiptap/extension-collaboration";
import CollaborationCursor from "@tiptap/extension-collaboration-cursor";
import { HocuspocusProvider } from "@hocuspocus/provider";
import * as Y from "yjs";
import { WhisperSegment, type WhisperSegmentAttrs } from "./WhisperSegmentMark";
import { apiFetch } from "../auth/api-client";
import "./collaboration.css";

interface Segment {
  start: number;
  end: number;
  text: string;
}

const DEBOUNCE_MS = 800;

const DEV_FIXTURE_SEGMENTS: Segment[] = [
  { start: 0.0, end: 2.5, text: "Bonjour à tous," },
  { start: 2.5, end: 5.0, text: "bienvenue au camp biblique." },
  { start: 5.0, end: 8.0, text: "Aujourd'hui nous allons étudier le livre de la Genèse." },
];

function collabWsBase(): string {
  const fromEnv = import.meta.env.VITE_HOCUSPOCUS_URL as string | undefined;
  if (fromEnv?.trim()) {
    return fromEnv.replace(/\/$/, "");
  }
  if (typeof window === "undefined") {
    return "ws://localhost:1234";
  }
  const { protocol, hostname } = window.location;
  const scheme = protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${hostname}:1234`;
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
  const token = auth.user?.access_token ?? "";
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

    (async () => {
      setCollabLine("Minting collaboration ticket…");
      setSynced(false);
      seededRef.current = false;
      try {
        const tr = await apiFetch("/v1/editor/ticket", token, {
          method: "POST",
          body: JSON.stringify({ document_id: audioId, permissions: ["read", "write"] }),
        });
        if (!tr.ok) {
          setCollabLine(`Ticket HTTP ${tr.status}`);
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
          if (!cancelled) setSynced(true);
        });
        hp.on("authenticationFailed", () => {
          if (!cancelled) setCollabLine("Hocuspocus authentication failed (ticket invalid or consumed)");
        });
        hp.on("close", (ev: { event?: CloseEvent }) => {
          if (cancelled) return;
          const code = ev?.event?.code;
          setCollabLine(code ? `Disconnected (code ${code})` : "Disconnected");
        });

        if (!cancelled) {
          setProvider(hp);
          setCollabLine(`CRDT sync → ${url} (room ${audioId})`);
        }
      } catch (e) {
        if (!cancelled) setCollabLine(`Collaboration error: ${String(e)}`);
      }
    })();

    return () => {
      cancelled = true;
      hpRef.current?.destroy();
      hpRef.current = null;
      setProvider(null);
      setSynced(false);
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
    const handler = () => debouncedSubmit();
    editor.on("update", handler);
    return () => {
      editor.off("update", handler);
      if (pendingRef.current) clearTimeout(pendingRef.current);
    };
  }, [editor, debouncedSubmit]);

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
