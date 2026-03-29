import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "react-oidc-context";
import { useEditor, EditorContent } from "@tiptap/react";
import Document from "@tiptap/extension-document";
import Paragraph from "@tiptap/extension-paragraph";
import Text from "@tiptap/extension-text";
import { WhisperSegment, type WhisperSegmentAttrs } from "./WhisperSegmentMark";
import { apiFetch } from "../auth/api-client";

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

  const [status, setStatus] = useState<string>("");
  const [loaded, setLoaded] = useState(false);
  const pendingRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSentRef = useRef<Map<string, string>>(new Map());

  const editor = useEditor({
    extensions: [Document, Paragraph, Text, WhisperSegment],
    content: "<p></p>",
    editable: true,
  });

  const loadTranscription = useCallback(async () => {
    if (!audioId || !token || loaded) return;
    try {
      const resp = await apiFetch(`/v1/audio-files/${audioId}/transcription`, token);
      if (resp.ok) {
        const data = (await resp.json()) as { segments: Segment[] };
        const segs = data.segments.length > 0 ? data.segments : DEV_FIXTURE_SEGMENTS;
        editor?.commands.setContent(segmentsToEditorJson(segs));
        setLoaded(true);
        setStatus(
          data.segments.length > 0
            ? `${data.segments.length} segments loaded`
            : "Dev fixture loaded (no server segments yet)",
        );
      } else {
        setStatus(`Failed to load transcription (HTTP ${resp.status})`);
      }
    } catch (err) {
      setStatus(`Network error: ${String(err)}`);
    }
  }, [audioId, token, loaded, editor]);

  useEffect(() => {
    loadTranscription();
  }, [loadTranscription]);

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
        <span>{status}</span>
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
        Corrections are auto-saved {DEBOUNCE_MS}ms after you stop typing.
      </p>
    </div>
  );
}
