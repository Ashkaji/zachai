import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "react-oidc-context";
import { useEditor, EditorContent, FloatingMenu } from "@tiptap/react";
import { Decoration, DecorationSet } from "prosemirror-view";
import { 
  Play, 
  Pause, 
  Bold, 
  Italic, 
  Type, 
  Zap, 
  ZapOff,
  SkipForward,
  SkipBack,
  Gauge,
  Ghost,
  History
} from "lucide-react";
import Document from "@tiptap/extension-document";
import Paragraph from "@tiptap/extension-paragraph";
import Text from "@tiptap/extension-text";
import Collaboration from "@tiptap/extension-collaboration";
import CollaborationCursor from "@tiptap/extension-collaboration-cursor";
import { HocuspocusProvider } from "@hocuspocus/provider";
import * as Y from "yjs";
import { WhisperSegment, type WhisperSegmentAttrs } from "./WhisperSegmentMark";
import { BiblicalCitation } from "./BiblicalCitationMark";
import { BubbleMenuShortcut } from "./BubbleMenuShortcut";
import { AzureBubbleMenu } from "./AzureBubbleMenu";
import { BiblePreviewPopup } from "./BiblePreviewPopup";
import { HistoryPanel, type Snapshot } from "./HistoryPanel";
import {
  MAX_RECONNECT_ATTEMPTS,
  computeReconnectDelayMs,
  hasReconnectAttemptsRemaining,
  shouldRetryTicketHttpStatus,
} from "./reconnect-policy";
import { apiFetch, bearerForApi } from "../auth/api-client";
import {
  buildDocTextIndex,
  docRangeForTextSlice,
  recomputeGrammarApplyRange,
  type GrammarMatch,
  type TextSpan,
} from "./grammarUtils";
import { useNotifications } from "../shared/notifications/NotificationContext";
import {
  editorStrings,
  remoteRestoreFailureFallback,
  resolveEditorLocale,
  type EditorLocale,
} from "./editorStrings";
import "./collaboration.css";

// --- Types for Ghost Mode ---
type DiffChange = {
  type: 'add' | 'remove' | 'equal';
  value: string;
};

interface Segment {
  start: number;
  end: number;
  text: string;
}

const DEBOUNCE_MS = 800;
/** Story 5.5 — grammar proxy debounce (PRD ~500ms). */
const GRAMMAR_DEBOUNCE_MS = 500;

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
  const { notify } = useNotifications();
  const [editorLocale] = useState<EditorLocale>(() => resolveEditorLocale());
  const editorCopy = useMemo(() => editorStrings(editorLocale), [editorLocale]);
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
  const [audioPlaybackSpeed, setAudioPlaybackSpeed] = useState(1);
  const [isPlaying, setIsPlaying] = useState(false);
  const recoverAudioFromCacheRef = useRef<(() => void) | null>(null);

  const audioUrlCacheRef = useRef<
    Map<number, { url: string; expiresIn: number; fetchedAtMs: number }>
  >(new Map());

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

  const grammarMatchesRef = useRef<GrammarMatch[]>([]);
  const grammarGenRef = useRef(0);
  const grammarTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const grammarAbortRef = useRef<AbortController | null>(null);
  const grammarEnabledRef = useRef(true);
  const [grammarNote, setGrammarNote] = useState("");
  const [grammarEnabled, setGrammarEnabled] = useState(true);
  const [ecoMode, setEcoMode] = useState(false);
  
  // Story 12.2 — Ghost Mode
  const [ghostMode, setGhostMode] = useState(false);
  const [originalContent, setOriginalContent] = useState<string>("");
  const ghostModeRef = useRef(false);
  const originalContentRef = useRef("");
  const diffResultRef = useRef<DiffChange[]>([]);
  const workerRef = useRef<Worker | null>(null);

  // Performance — Memoize document indexing (Issue 05)
  const docIndexRef = useRef<{ text: string; spans: TextSpan[] }>({ text: "", spans: [] });

  const [grammarPopup, setGrammarPopup] = useState<{
    x: number;
    y: number;
    match: GrammarMatch;
    expectedSlice: string;
  } | null>(null);

  const [biblePopup, setBiblePopup] = useState<{
    x: number;
    y: number;
    reference: string;
  } | null>(null);

  // Story 12.2 — Snapshots
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [isTimelineOpen, setIsTimelineOpen] = useState(false);
  const [isLoadingSnapshot, setIsLoadingSnapshot] = useState(false);
  const [activeSnapshotId, setActiveSnapshotId] = useState<string | null>(null);

  // Story 12.3: Restoration State
  const [isRestoring, setIsRestoring] = useState(false);
  const [showRestoreConfirm, setShowRestoreConfirm] = useState(false);
  const [snapshotToRestore, setSnapshotToRestore] = useState<string | null>(null);
  /** Set when another collaborator triggers restoration (Hocuspocus stateless). */
  const [remoteRestoringBy, setRemoteRestoringBy] = useState<string | null>(null);
  /** Story 13.1: remote collaborator restore failure (distinct from success overlay). */
  const [remoteRestoreFailureMessage, setRemoteRestoreFailureMessage] = useState<string | null>(null);
  const localRestoreRequestActiveRef = useRef(false);
  const suppressRemoteRestoreFailureRef = useRef(false);
  /** Story 14.1: Track the latest active restore operation to pair signals correctly. */
  const activeRestoreIdRef = useRef<string | null>(null);

  const handleRestoreSnapshot = async (snapId: string) => {
    if (!audioId || !token) return;
    
    setIsRestoring(true);
    setShowRestoreConfirm(false);
    setRemoteRestoreFailureMessage(null);
    activeRestoreIdRef.current = null;
    localRestoreRequestActiveRef.current = true;
    
    try {
      const resp = await apiFetch(`/v1/snapshots/${encodeURIComponent(snapId)}/restore`, token, {
        method: "POST",
      });
      
      const body = await resp.json().catch(() => ({ error: "Invalid server response format" }));
      if (!resp.ok) {
        let msg: string = editorCopy.restoreFailureDefault;
        const d = body.detail;
        if (typeof d === "object" && d !== null && "error" in d) {
          msg = String((d as { error: string }).error);
        } else if (typeof d === "string") {
          msg = d;
        } else if (body.error) {
          msg = String(body.error);
        }
        throw new Error(msg);
      }

      // initiator tracks their own restore_id to pair signals
      if (body.restore_id) {
        activeRestoreIdRef.current = body.restore_id;
      }
      
      // Force reconnect to get new state from Hocuspocus
      provider?.disconnect();
      provider?.connect();
      
      notify({ tier: "informational", title: editorCopy.restoreSuccessTitle, body: editorCopy.restoreSuccessMessage });
      setStatus(editorCopy.restoreSuccessMessage);
      setRemoteRestoreFailureMessage(null);
      setIsTimelineOpen(false);
      setActiveSnapshotId(null);
      setGhostMode(false);
    } catch (err) {
      console.error("restore_error", err);
      const msg = err instanceof Error ? err.message : String(err);
      notify({ tier: "critical", title: editorCopy.restoreFailureTitle, body: msg });
      setStatus(`${editorCopy.restoreFailureTitle}: ${msg}`);
      suppressRemoteRestoreFailureRef.current = true;
      window.setTimeout(() => {
        suppressRemoteRestoreFailureRef.current = false;
      }, 3500);
    } finally {
      setIsRestoring(false);
      localRestoreRequestActiveRef.current = false;
    }
  };

  const fetchSnapshots = useCallback(async () => {
    if (!audioId || !token) return;
    try {
      const resp = await apiFetch(`/v1/audio-files/${audioId}/snapshots`, token);
      if (resp.ok) {
        const data = await resp.json();
        setSnapshots(data);
      }
    } catch (err) {
      console.error("Failed to fetch snapshots", err);
    }
  }, [audioId, token]);

  useEffect(() => {
    fetchSnapshots();
  }, [fetchSnapshots]);

  useEffect(() => {
    setRemoteRestoringBy(null);
  }, [audioId]);

  const handleSelectSnapshot = async (snapId: string) => {
    if (!token) return;
    setIsLoadingSnapshot(true);
    setActiveSnapshotId(snapId);
    setStatus("Fetching snapshot state…");
    try {
      const resp = await apiFetch(`/v1/snapshots/${snapId}/yjs`, token);
      if (resp.ok) {
        const buffer = await resp.arrayBuffer();
        const yjsData = new Uint8Array(buffer);
        const tempDoc = new Y.Doc();
        Y.applyUpdate(tempDoc, yjsData);
        // Tiptap collab uses 'default' XML fragment name
        const text = tempDoc.getText("default").toString();
        
        setOriginalContent(text);
        originalContentRef.current = text;
        setGhostMode(true);
        setStatus(`Comparing against snapshot ${snapId.slice(0, 8)}…`);
        triggerDiff();
      } else {
        setStatus(`Failed to fetch snapshot Yjs: ${resp.status}`);
      }
    } catch (err) {
      console.error("Failed to fetch snapshot Yjs", err);
      setStatus("Error loading snapshot binary");
    } finally {
      setIsLoadingSnapshot(false);
    }
  };

  const handleHoverSnapshot = async (snapId: string | null) => {
    // Story 12.2 AC 3: Hover preview
    if (snapId) {
      const snap = snapshots.find(s => s.snapshot_id === snapId);
      if (snap) {
        setStatus(`Preview: ${snap.source} snapshot from ${new Date(snap.created_at).toLocaleTimeString()}`);
      }
    } else {
      setStatus("");
    }
  };

  // Initialize Worker
  useEffect(() => {
    workerRef.current = new Worker(new URL('./ghostModeWorker.ts', import.meta.url), { type: 'module' });
    workerRef.current.onmessage = (e) => {
      const { result } = e.data;
      diffResultRef.current = result;
      paintAllDecorations();
    };
    return () => workerRef.current?.terminate();
  }, []);

  const triggerDiff = useCallback(() => {
    if (!ghostModeRef.current || !workerRef.current || !editorRef.current) return;
    const { text } = docIndexRef.current;
    workerRef.current.postMessage({
      oldStr: originalContentRef.current,
      newStr: text,
      requestId: Date.now()
    });
  }, []);

  // Sync refs and trigger initial diff
  useEffect(() => {
    ghostModeRef.current = ghostMode;
    if (ghostMode && !originalContent) {
      if (editorRef.current) {
        const { text } = docIndexRef.current;
        setOriginalContent(text);
        originalContentRef.current = text;
      }
    }
    if (ghostMode) triggerDiff();
    else {
      diffResultRef.current = [];
      paintAllDecorations();
    }
  }, [ghostMode, triggerDiff]);

  // Task 2: Sync ecoMode to root class for CSS conditional styling
  useEffect(() => {
    if (ecoMode) {
      document.documentElement.classList.add("za-eco-mode");
    } else {
      document.documentElement.classList.remove("za-eco-mode");
    }
  }, [ecoMode]);

  const grammarMessageFromResponse = useCallback(
    (
      resp: Response,
      data: { error?: string } | { detail?: { error?: string; matches?: unknown } | string },
    ) => {
      const raw = data as { detail?: { error?: string; matches?: unknown } | string; error?: string };
      const det = raw.detail;
      let msg = `HTTP ${resp.status}`;
      if (typeof det === "string") msg = det;
      else if (det && typeof det === "object" && "error" in det && det.error) msg = String(det.error);
      else if (raw.error) msg = String(raw.error);
      return msg;
    },
    [],
  );

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

        hp.on("stateless", ({ payload }: { payload: string }) => {
          try {
            const data = JSON.parse(payload) as {
              type?: string;
              user_name?: string | null;
              document_id?: number;
              code?: string;
              message?: string;
              restore_id?: string;
            };
            if (data.type === "zachai:document_restoring") {
              setRemoteRestoringBy(
                typeof data.user_name === "string" && data.user_name.trim()
                  ? data.user_name.trim()
                  : "Another collaborator",
              );
            } else if (data.type === "zachai:document_restored") {
              setRemoteRestoringBy(null);
              // Only clear if no restore_id (legacy) or if it matches the latest operation we know about.
              // This prevents clearing a valid failure message from a different operation.
              if (!data.restore_id || activeRestoreIdRef.current === data.restore_id) {
                setRemoteRestoreFailureMessage(null);
              }
            } else if (data.type === "zachai:document_restore_failed") {
              const docId =
                typeof data.document_id === "number" && Number.isFinite(data.document_id)
                  ? data.document_id
                  : null;
              if (docId !== null && docId !== audioId) return;
              setRemoteRestoringBy(null);
              
              if (data.restore_id) {
                activeRestoreIdRef.current = data.restore_id;
              }

              if (localRestoreRequestActiveRef.current || suppressRemoteRestoreFailureRef.current) {
                return;
              }
              const code =
                typeof data.code === "string" && data.code.trim() ? data.code.trim() : "UNKNOWN";
              const custom =
                typeof data.message === "string" && data.message.trim() ? data.message.trim() : null;
              
              setRemoteRestoreFailureMessage(
                custom ?? remoteRestoreFailureFallback(code, editorLocale),
              );
            }
          } catch {
            /* ignore */
          }
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
  }, [audioId, token, ydoc, editorLocale]);

  const editor = useEditor(
    {
      extensions: [
        Document,
        Paragraph,
        Text,
        WhisperSegment,
        BiblicalCitation,
        BubbleMenuShortcut,
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

  const paintAllDecorations = useCallback(() => {
    const ed = editorRef.current;
    if (!ed) return;
    ed.view.setProps({
      decorations: (state) => {
        const decos: Decoration[] = [];
        const { spans } = docIndexRef.current;
        
        // 1. Grammar/Spelling (Story 11.4)
        if (grammarEnabledRef.current) {
          for (const m of grammarMatchesRef.current) {
            const r = docRangeForTextSlice(spans, m.offset, m.length);
            if (!r) continue;
            const cls =
              m.issueType === "spelling"
                ? "zachai-grammar-spelling"
                : "zachai-grammar-style";
            decos.push(Decoration.inline(r.from, r.to, { class: cls }));
          }
        }

        // 2. Karaoke Highlight (Story 5.3)
        const activeKey = activeIntervalKeyRef.current;
        if (activeKey) {
          const parts = activeKey.split("-");
          if (parts.length >= 2) {
            const audioStart = Number(parts[0]);
            const audioEnd = Number(parts[1]);
            if (Number.isFinite(audioStart) && Number.isFinite(audioEnd)) {
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
                      decos.push(
                        Decoration.inline(from, to, { class: "zachai-karaoke-active" }),
                      );
                    }
                  }
                }
              });
            }
          }
        }

        // 3. Ghost Mode Diff (Story 12.2)
        if (ghostModeRef.current && diffResultRef.current.length > 0) {
          let currentOffset = 0;
          for (const part of diffResultRef.current) {
            if (part.type === 'equal') {
              currentOffset += part.value.length;
            } else if (part.type === 'add') {
              const r = docRangeForTextSlice(spans, currentOffset, part.value.length);
              if (r) {
                decos.push(Decoration.inline(r.from, r.to, { class: "zachai-ghost-added" }));
              }
              currentOffset += part.value.length;
            } else if (part.type === 'remove') {
              const r = docRangeForTextSlice(spans, currentOffset, 1);
              if (r) {
                // Removal marker (widget decoration) — "Spectral Blue" (Story 12.2 AC 2.3)
                const widget = document.createElement("span");
                widget.className = "zachai-ghost-deleted-marker";
                widget.style.color = "rgba(0, 120, 212, 0.4)";
                widget.style.textDecoration = "line-through";
                widget.innerText = part.value;
                decos.push(Decoration.widget(r.from, widget));
              }
            }
          }
        }

        return DecorationSet.create(state.doc, decos);
      },
    });
  }, []);

  useEffect(() => {
    grammarEnabledRef.current = grammarEnabled;
    if (!grammarEnabled) {
      if (grammarTimerRef.current) clearTimeout(grammarTimerRef.current);
      if (grammarAbortRef.current) {
        grammarAbortRef.current.abort();
        grammarAbortRef.current = null;
      }
      grammarGenRef.current += 1;
      grammarMatchesRef.current = [];
      setGrammarNote("");
      setGrammarPopup(null);
      paintAllDecorations();
    } else if (token && editor) {
      grammarGenRef.current += 1;
      grammarMatchesRef.current = [];
      paintAllDecorations();
      if (grammarTimerRef.current) clearTimeout(grammarTimerRef.current);
      grammarTimerRef.current = setTimeout(() => {
        const ed = editor;
        const tok = token;
        if (!ed || !tok || !grammarEnabledRef.current) return;
        const { text } = docIndexRef.current;
        if (!text.trim()) {
          setGrammarNote("");
          return;
        }
        const gen = grammarGenRef.current;
        const lang =
          (import.meta.env.VITE_GRAMMAR_LANGUAGE as string | undefined)?.trim() || "fr";
        if (grammarAbortRef.current) grammarAbortRef.current.abort();
        const controller = new AbortController();
        grammarAbortRef.current = controller;
        void (async () => {
          try {
            const resp = await apiFetch("/v1/proxy/grammar", tok, {
              method: "POST",
              body: JSON.stringify({ text, language: lang }),
              signal: controller.signal,
            });
            let data: { matches?: GrammarMatch[]; error?: string };
            try {
              data = (await resp.json()) as { matches?: GrammarMatch[]; error?: string };
            } catch {
              if (gen !== grammarGenRef.current) return;
              grammarMatchesRef.current = [];
              paintAllDecorations();
              setGrammarNote("Grammar check failed");
              return;
            }
            if (gen !== grammarGenRef.current) return;
            if (resp.ok || resp.status === 429) {
              grammarMatchesRef.current = data.matches ?? [];
              paintAllDecorations();
              setGrammarNote(resp.status === 429 ? grammarMessageFromResponse(resp, data) : data.error ? String(data.error) : "");
            } else {
              grammarMatchesRef.current = [];
              paintAllDecorations();
              setGrammarNote(grammarMessageFromResponse(resp, data));
            }
          } catch {
            if (controller.signal.aborted) return;
            if (gen === grammarGenRef.current) {
              grammarMatchesRef.current = [];
              paintAllDecorations();
              setGrammarNote("Grammar check unavailable");
            }
          } finally {
            if (grammarAbortRef.current === controller) grammarAbortRef.current = null;
          }
        })();
      }, GRAMMAR_DEBOUNCE_MS);
    }
  }, [grammarEnabled, paintAllDecorations, token, editor, grammarMessageFromResponse]);

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
      activeIntervalKeyRef.current = interval?.key ?? null;
      paintAllDecorations();
    },
    [paintAllDecorations],
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
      if (recoverAudioFromCacheRef.current) {
        const retry = recoverAudioFromCacheRef.current;
        recoverAudioFromCacheRef.current = null;
        retry();
        return;
      }
      setAudioLoadStatus("error");
      setAudioError("Audio failed to load. Text editing will still work.");
      stopKaraokeLoop();
      applyKaraokeDecoration(null);
    };

    audio.onplaying = () => {
      setAudioLoadStatus((s) => (s === "idle" ? "ready" : s));
      setIsPlaying(true);
      startKaraokeLoop();
    };

    audio.onpause = () => {
      setIsPlaying(false);
      stopKaraokeLoop();
      // Keep the highlight at the last computed timestamp (no doc mutation).
      if (audio && !Number.isNaN(audio.currentTime)) {
        updateKaraokeHighlightForTime(audio.currentTime);
      }
    };

    audio.onended = () => {
      setIsPlaying(false);
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

    const isCacheUsable = (c: { url: string; expiresIn: number; fetchedAtMs: number }) => {
      const safetyMs = 30_000;
      return Date.now() < c.fetchedAtMs + c.expiresIn * 1000 - safetyMs;
    };

    let retriedFromAudioError = false;

    const run = async (allowRetryOnCachedFailure: boolean, triedCached: boolean) => {
      const cached = audioUrlCacheRef.current.get(audioId);
      if (cached && isCacheUsable(cached)) {
        setAudioLoadStatus("loading");
        setAudioError("");
        recoverAudioFromCacheRef.current = () => {
          if (retriedFromAudioError || cancelled) return;
          retriedFromAudioError = true;
          audioUrlCacheRef.current.delete(audioId);
          void run(false, false);
        };
        audio.src = cached.url;
        audio.load();
        return;
      }
      if (cached && !isCacheUsable(cached)) {
        audioUrlCacheRef.current.delete(audioId);
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
        audioUrlCacheRef.current.set(audioId, {
          url: data.presigned_url,
          expiresIn,
          fetchedAtMs: Date.now(),
        });
        audio.src = data.presigned_url;
        audio.load();
      } catch (e) {
        if (cancelled) return;
        if (triedCached && allowRetryOnCachedFailure) {
          audioUrlCacheRef.current.delete(audioId);
          await run(false, false);
          return;
        }
        setAudioLoadStatus("error");
        setAudioError(String(e));
        setStatus(`Audio error: ${String(e)}`);
        stopKaraokeLoop();
        applyKaraokeDecoration(null);
      }
    };

    void run(true, Boolean(audioUrlCacheRef.current.get(audioId)));

    return () => {
      cancelled = true;
      recoverAudioFromCacheRef.current = null;
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

  // Click: grammar suggestions (Story 5.5) take precedence over whisper seek (Story 5.3).
  useEffect(() => {
    const container = editorContainerRef.current;
    if (!container) return;

    const onClick = (ev: MouseEvent) => {
      const target = ev.target as HTMLElement | null;
      if (target?.closest?.("#zachai-grammar-popup, .za-bible-popup")) return;

      // Reset popups
      setGrammarPopup(null);
      setBiblePopup(null);

      // 1. Bible Citation detection (Story 11.4 AC 2.1)
      const bibleEl = target?.closest?.(".za-biblical-citation") as HTMLElement | null;
      if (bibleEl) {
        setBiblePopup({
          x: ev.clientX,
          y: ev.clientY,
          reference: bibleEl.innerText.trim(),
        });
        return;
      }

      // 2. Grammar Suggestion detection (Story 5.5)
      if (grammarEnabledRef.current) {
        const gEl = target?.closest?.(".zachai-grammar-spelling, .zachai-grammar-style");
        if (gEl) {
          const ed = editorRef.current;
          if (!ed) return;
          const coords = { left: ev.clientX, top: ev.clientY };
          const posInfo = ed.view.posAtCoords(coords);
          if (posInfo == null) return;
          const pos = posInfo.pos;
          const { text, spans } = docIndexRef.current;
          for (const m of grammarMatchesRef.current) {
            const r = docRangeForTextSlice(spans, m.offset, m.length);
            if (r && pos >= r.from && pos < r.to) {
              ev.preventDefault();
              ev.stopPropagation();
              const expectedSlice = text.slice(m.offset, m.offset + m.length);
              setGrammarPopup({
                x: ev.clientX,
                y: ev.clientY,
                match: m,
                expectedSlice,
              });
              return;
            }
          }
        }
      }

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

      audio.currentTime = start;

      const roundedStart = roundAudioTime(start);
      const roundedEnd = Number.isNaN(end) ? roundAudioTime(start) : roundAudioTime(end);
      const key = `${roundedStart}-${roundedEnd}`;
      const interval = intervalByKeyRef.current.get(key) ?? null;
      if (interval) applyKaraokeDecoration(interval);
      else updateKaraokeHighlightForTime(start);

      audio.play().catch(() => {
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
    if (!grammarPopup && !biblePopup) return;
    const onDown = (e: MouseEvent) => {
      const gEl = document.getElementById("zachai-grammar-popup");
      const bEl = document.getElementById("zachai-bible-popup");
      if (gEl?.contains(e.target as Node) || bEl?.contains(e.target as Node)) return;
      setGrammarPopup(null);
      setBiblePopup(null);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [grammarPopup, biblePopup]);

  useEffect(() => {
    if (!editor) return;
    const handler = () => {
      // Memoize document indexing (Issue 05)
      docIndexRef.current = buildDocTextIndex(editor.state.doc);

      debouncedSubmit();
      rebuildWhisperSegmentIndex();

      if (grammarEnabledRef.current && token) {
        setGrammarPopup(null);
        grammarGenRef.current += 1;
        grammarMatchesRef.current = [];
        paintAllDecorations();
        if (grammarTimerRef.current) clearTimeout(grammarTimerRef.current);
        grammarTimerRef.current = setTimeout(() => {
          const ed = editorRef.current;
          const tok = token;
          if (!ed || !tok || !grammarEnabledRef.current) return;
          const { text } = docIndexRef.current;
          if (!text.trim()) {
            setGrammarNote("");
            return;
          }
          const gen = grammarGenRef.current;
          const lang =
            (import.meta.env.VITE_GRAMMAR_LANGUAGE as string | undefined)?.trim() || "fr";
          if (grammarAbortRef.current) grammarAbortRef.current.abort();
          const controller = new AbortController();
          grammarAbortRef.current = controller;
          void (async () => {
            try {
              const resp = await apiFetch("/v1/proxy/grammar", tok, {
                method: "POST",
                body: JSON.stringify({ text, language: lang }),
                signal: controller.signal,
              });
              let data: { matches?: GrammarMatch[]; error?: string };
              try {
                data = (await resp.json()) as { matches?: GrammarMatch[]; error?: string };
              } catch {
                if (gen !== grammarGenRef.current) return;
                grammarMatchesRef.current = [];
                paintAllDecorations();
                setGrammarNote("Grammar check failed");
                return;
              }
              if (gen !== grammarGenRef.current) return;
              if (resp.ok || resp.status === 429) {
                grammarMatchesRef.current = data.matches ?? [];
                paintAllDecorations();
                setGrammarNote(resp.status === 429 ? grammarMessageFromResponse(resp, data) : data.error ? String(data.error) : "");
              } else {
                grammarMatchesRef.current = [];
                paintAllDecorations();
                setGrammarNote(grammarMessageFromResponse(resp, data));
              }
            } catch {
              if (controller.signal.aborted) return;
              if (gen === grammarGenRef.current) {
                grammarMatchesRef.current = [];
                paintAllDecorations();
                setGrammarNote("Grammar check unavailable");
              }
            } finally {
              if (grammarAbortRef.current === controller) grammarAbortRef.current = null;
            }
          })();
        }, GRAMMAR_DEBOUNCE_MS);
      }

      const audio = audioRef.current;
      if (audio && audioLoadStatus === "ready") {
        updateKaraokeHighlightForTime(audio.currentTime);
      }
    };
    editor.on("update", handler);
    // Initial indexing
    docIndexRef.current = buildDocTextIndex(editor.state.doc);

    return () => {
      editor.off("update", handler);
      if (pendingRef.current) clearTimeout(pendingRef.current);
      if (grammarTimerRef.current) clearTimeout(grammarTimerRef.current);
      if (grammarAbortRef.current) {
        grammarAbortRef.current.abort();
        grammarAbortRef.current = null;
      }
    };
  }, [
    editor,
    token,
    debouncedSubmit,
    audioLoadStatus,
    rebuildWhisperSegmentIndex,
    updateKaraokeHighlightForTime,
    paintAllDecorations,
    grammarMessageFromResponse,
  ]);

  const applyGrammarReplacement = useCallback(
    (replacement: string) => {
      const ed = editorRef.current;
      if (!ed || !grammarPopup) return;
      const range = recomputeGrammarApplyRange(
        ed.state.doc,
        grammarPopup.match,
        grammarPopup.expectedSlice,
      );
      if (!range) {
        setGrammarPopup(null);
        return;
      }
      ed.chain()
        .focus()
        .insertContentAt({ from: range.from, to: range.to }, replacement)
        .run();
      setGrammarPopup(null);
      grammarMatchesRef.current = [];
      grammarGenRef.current += 1;
      paintAllDecorations();
    },
    [grammarPopup, paintAllDecorations],
  );

  const togglePlay = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) audio.play();
    else audio.pause();
  };

  const seekRelative = (seconds: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = Math.max(0, Math.min(audio.duration, audio.currentTime + seconds));
  };

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
    <div className="za-workspace-container" style={{ display: "flex", flexDirection: "row", padding: 0 }}>
      {/* Story 13.1 — remote restore failed (collaborators); not the same UX as success */}
      {remoteRestoreFailureMessage && (
        <div role="alert" className="za-card za-glass za-restore-failure-banner">
          <div style={{ flex: 1 }}>
            <strong className="za-restore-failure-banner__title">
              {editorCopy.restoreFailureTitle}
            </strong>
            <span className="za-restore-failure-banner__message">{remoteRestoreFailureMessage}</span>
          </div>
          <button
            type="button"
            className="za-button za-button-subtle"
            style={{ flexShrink: 0 }}
            onClick={() => {
              suppressRemoteRestoreFailureRef.current = false;
              setRemoteRestoreFailureMessage(null);
            }}
          >
            {editorCopy.restoreFailureDismiss}
          </button>
        </div>
      )}
      {/* Restoration Overlay (Story 12.3 — collaborators + local) */}
      {(isRestoring || remoteRestoringBy) && (
        <div 
          className="za-glass"
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 9999,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'rgba(0, 0, 0, 0.7)',
            backdropFilter: 'blur(8px)',
            color: 'white',
          }}
        >
          <div className="za-spinner" style={{ width: '48px', height: '48px', marginBottom: '1.5rem' }} />
          <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '0.5rem' }}>{editorCopy.restorationOverlayTitle}</h2>
          <p style={{ opacity: 0.9, maxWidth: 420, textAlign: "center", padding: "0 1rem" }}>
            {editorCopy.restorationOverlayWait}
            <br />
            Document being restored by{" "}
            <strong>{isRestoring ? displayName : remoteRestoringBy}</strong>
            …
          </p>
        </div>
      )}

      {/* Restoration Confirmation Modal (Story 12.3 AC 2.1) */}
      {showRestoreConfirm && (
        <div 
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 1000,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'rgba(0, 0, 0, 0.5)',
          }}
        >
          <div 
            className="za-card za-glass" 
            style={{ 
              width: '400px', 
              padding: 'var(--spacing-6)', 
              border: '1px solid #e54242',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)'
            }}
          >
            <h3 style={{ color: '#e54242', marginTop: 0, marginBottom: 'var(--spacing-4)', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Zap size={20} /> Danger Zone
            </h3>
            <p style={{ fontSize: '0.9rem', lineHeight: 1.5, marginBottom: 'var(--spacing-6)' }}>
              This will overwrite all current changes. This action cannot be undone (except by another
              restore).
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--spacing-3)' }}>
              <button 
                onClick={() => setShowRestoreConfirm(false)} 
                className="za-btn za-btn--ghost"
              >
                Cancel
              </button>
              <button 
                onClick={() => snapshotToRestore && handleRestoreSnapshot(snapshotToRestore)} 
                className="za-btn"
                style={{ background: '#e54242', color: 'white' }}
              >
                Confirm Restoration
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Sidebar Toggle (Left edge hover or static) */}
      
      {/* Main Workspace Area */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", padding: "var(--spacing-8) 5%", transition: "all 0.3s ease" }}>
        
        {/* Header / Toolbar Section */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "var(--spacing-6)",
            padding: "var(--spacing-4)",
            borderRadius: "var(--radius-md)",
          }}
          className="za-glass za-card-glow"
        >
          <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-4)" }}>
            <div style={{ display: "flex", flexDirection: "column" }}>
              <span style={{ fontWeight: 700, fontSize: "1.1rem" }}>Audio #{audioId}</span>
              <span style={{ fontSize: "0.75rem", color: "var(--color-text-muted)" }}>
                {status || "Syncing..."}
              </span>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-2)" }}>
            <button
              type="button"
              className={`za-btn ${isTimelineOpen ? "za-btn--primary" : "za-btn--ghost"}`}
              title="Version History (Snapshots)"
              onClick={() => setIsTimelineOpen(!isTimelineOpen)}
            >
              <History size={18} />
            </button>

            <button
              type="button"
              className={`za-btn ${ghostMode ? "za-btn--primary" : "za-btn--ghost"}`}
              title="Toggle Ghost Mode (Visual Diff)"
              onClick={() => setGhostMode((v) => !v)}
            >
              <Ghost size={18} />
            </button>

            <button
              type="button"
              className="za-btn za-btn--ghost"
              title={ecoMode ? "Disable Eco-Mode" : "Enable Eco-Mode (Better Performance)"}
              onClick={() => setEcoMode(!ecoMode)}
              style={{ color: ecoMode ? "var(--color-primary)" : "inherit" }}
            >
              {ecoMode ? <ZapOff size={18} /> : <Zap size={18} />}
            </button>
            
            <button
              type="button"
              className={`za-btn ${grammarEnabled ? "za-btn--primary" : "za-btn--ghost"}`}
              title="Toggle grammar highlights"
              onClick={() => setGrammarEnabled((v) => !v)}
            >
              <Type size={18} />
            </button>
          </div>
        </div>

        {/* Main Editor Canvas */}
        <div
          style={{
            position: "relative",
            flex: 1,
          }}
          ref={editorContainerRef}
        >
          {editor && (
            <>
              <AzureBubbleMenu editor={editor} audioRef={audioRef} />

              <FloatingMenu editor={editor} tippyOptions={{ duration: 300 }}>
                <div className="za-glass za-card-glow" style={{ 
                  display: "flex", 
                  gap: "var(--spacing-1)", 
                  padding: "var(--spacing-1)",
                  borderRadius: "var(--radius-sm)" 
                }}>
                  <button
                    onClick={() => {/* editor.chain().focus().toggleBold().run() */}}
                    className="za-btn za-btn--ghost"
                    style={{ padding: "6px" }}
                  >
                    <Bold size={16} />
                  </button>
                  <button
                    onClick={() => {/* editor.chain().focus().toggleItalic().run() */}}
                    className="za-btn za-btn--ghost"
                    style={{ padding: "6px" }}
                  >
                    <Italic size={16} />
                  </button>
                </div>
              </FloatingMenu>
            </>
          )}

          <EditorContent editor={editor} className="za-editor-canvas" />

          {/* Bible Popup (Story 11.4) */}
          {biblePopup && token && (
            <div id="zachai-bible-popup" className="za-bible-popup">
              <BiblePreviewPopup
                x={biblePopup.x}
                y={biblePopup.y}
                reference={biblePopup.reference}
                token={token}
              />
            </div>
          )}

          {/* Grammar Popup (from Story 5.5) */}
          {grammarPopup && (
            <div
              id="zachai-grammar-popup"
              role="dialog"
              className="za-glass za-card-glow"
              style={{
                position: "fixed",
                left: Math.min(grammarPopup.x, typeof window !== "undefined" ? window.innerWidth - 260 : grammarPopup.x),
                top: grammarPopup.y + 8,
                zIndex: 50,
                maxWidth: 260,
                padding: "var(--spacing-3)",
                borderRadius: "var(--radius-md)",
                fontSize: "0.8125rem",
              }}
            >
              <div style={{ marginBottom: "var(--spacing-2)", fontWeight: 600 }}>
                {grammarPopup.match.shortMessage || grammarPopup.match.message || "Suggestion"}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-1)" }}>
                {(grammarPopup.match.replacements?.length
                  ? grammarPopup.match.replacements
                  : []
                ).slice(0, 5).map((rep, idx) => (
                  <button
                    key={`${rep}-${idx}`}
                    type="button"
                    onClick={() => applyGrammarReplacement(rep)}
                    className="za-btn za-btn--ghost"
                    style={{ textAlign: "left", fontSize: "0.8rem" }}
                  >
                    {rep}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Audio Bottom Dock (Task 5) */}
        <div
          style={{
            position: "fixed",
            bottom: "var(--spacing-6)",
            left: "50%",
            transform: "translateX(-50%)",
            width: "90%",
            maxWidth: "800px",
            display: "flex",
            alignItems: "center",
            gap: "var(--spacing-4)",
            padding: "var(--spacing-3) var(--spacing-6)",
            borderRadius: "999px",
            zIndex: 100,
          }}
          className="za-glass za-card-glow"
        >
          <div style={{ display: "flex", gap: "var(--spacing-2)" }}>
            <button onClick={() => seekRelative(-5)} className="za-btn za-btn--ghost">
              <SkipBack size={20} />
            </button>
            <button onClick={togglePlay} className="za-btn za-btn--primary" style={{ borderRadius: "50%", width: "44px", height: "44px", display: "flex", alignItems: "center", justifyContent: "center", padding: 0 }}>
              {isPlaying ? <Pause size={22} fill="currentColor" /> : <Play size={22} fill="currentColor" style={{ marginLeft: "2px" }} />}
            </button>
            <button onClick={() => seekRelative(5)} className="za-btn za-btn--ghost">
              <SkipForward size={20} />
            </button>
          </div>

          {/* Stylized Waveform Placeholder */}
          <div style={{ flex: 1, height: "32px", display: "flex", alignItems: "center", gap: "2px" }}>
            {Array.from({ length: 40 }).map((_, i) => (
              <div 
                key={i} 
                style={{ 
                  flex: 1, 
                  height: `${20 + Math.sin(i * 0.5) * 15}%`, 
                  background: "var(--color-primary)",
                  opacity: 0.3 + (i % 5) * 0.1,
                  borderRadius: "1px"
                }} 
              />
            ))}
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-2)" }}>
            <Gauge size={18} className="color-text-muted" />
            <select 
              value={audioPlaybackSpeed} 
              onChange={(e) => {
                const val = parseFloat(e.target.value);
                setAudioPlaybackSpeed(val);
                if (audioRef.current) audioRef.current.playbackRate = val;
              }}
              className="za-select"
              style={{ width: "auto", padding: "4px 8px" }}
            >
              <option value="0.5">0.5x</option>
              <option value="1">1.0x</option>
              <option value="1.25">1.25x</option>
              <option value="1.5">1.5x</option>
              <option value="2">2.0x</option>
            </select>
          </div>
        </div>

        {/* Footer Info */}
        <div style={{ 
          marginTop: "var(--spacing-8)", 
          fontSize: "0.75rem", 
          color: "var(--color-text-muted)",
          textAlign: "center",
          paddingBottom: "80px" // Space for the dock
        }}>
          <span>{audioStatusLine}</span>
          {collabLine && <span style={{ marginLeft: "1rem" }}>{collabLine}</span>}
          {grammarNote && <span style={{ marginLeft: "1rem", color: "var(--color-secondary)" }}>{grammarNote}</span>}
        </div>
      </div>

      {/* Version History Sidebar (Story 12.2) */}
      <HistoryPanel 
        isOpen={isTimelineOpen}
        onClose={() => setIsTimelineOpen(false)}
        snapshots={snapshots}
        onSelectSnapshot={handleSelectSnapshot}
        onHoverSnapshot={handleHoverSnapshot}
        onRestoreSnapshot={(snapId) => {
          setSnapshotToRestore(snapId);
          setShowRestoreConfirm(true);
        }}
        isLoading={isLoadingSnapshot}
        activeSnapshotId={activeSnapshotId}
        ghostMode={ghostMode}
        onClearDiff={() => {
          setGhostMode(false);
          setOriginalContent("");
          setActiveSnapshotId(null);
        }}
      />
    </div>
  );
}
