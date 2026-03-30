import { Mark, mergeAttributes } from "@tiptap/core";

export interface WhisperSegmentAttrs {
  audioStart: number;
  audioEnd: number;
  sourceText: string;
}

/**
 * Custom Tiptap Mark that binds a text span to a Whisper segment's time bounds.
 *
 * Each marked range carries the original Whisper transcript (`sourceText`) plus
 * the audio time window (`audioStart`, `audioEnd`). When the user edits text
 * inside this range the editor captures the diff and posts it to the Golden Set.
 *
 * Mark splitting behaviour: when the user types in the middle of a marked range,
 * ProseMirror may split the mark into two adjacent marks that share the same
 * `audioStart`/`audioEnd`. The `TranscriptionEditor` component detects this by
 * comparing attributes and treats contiguous spans with the same time bounds as
 * a single logical segment.
 */
export const WhisperSegment = Mark.create({
  name: "whisperSegment",

  addAttributes() {
    return {
      audioStart: { default: 0 },
      audioEnd: { default: 0 },
      sourceText: { default: "" },
    };
  },

  parseHTML() {
    return [{ tag: 'span[data-whisper-segment]' }];
  },

  renderHTML({ HTMLAttributes }) {
    const attrs = HTMLAttributes as WhisperSegmentAttrs & { [key: string]: unknown };
    const { audioStart, audioEnd, sourceText: _sourceText, ...rest } = attrs;
    return [
      "span",
      mergeAttributes(rest, {
        "data-whisper-segment": "",
        "data-audio-start": audioStart,
        "data-audio-end": audioEnd,
        class: "zachai-whisper-segment",
      }),
      0,
    ];
  },
});
