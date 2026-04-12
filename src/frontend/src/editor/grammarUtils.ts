import type { Node as PMNode } from "@tiptap/pm/model";

export type GrammarMatch = {
  offset: number;
  length: number;
  message: string;
  shortMessage?: string;
  ruleId?: string;
  category?: string;
  replacements: string[];
  issueType?: string;
};

export type TextSpan = {
  textStart: number;
  textEnd: number;
  from: number;
  to: number;
};

const BLOCK_SEP = "\n";

/**
 * Flatten top-level text blocks in document order, inserting BLOCK_SEP between blocks.
 * Offsets align with the string sent to LanguageTool; matches cannot span block boundaries.
 */
export function buildDocTextIndex(doc: PMNode): { text: string; spans: TextSpan[] } {
  const spans: TextSpan[] = [];
  let text = "";
  let firstBlock = true;
  doc.descendants((node, pos) => {
    if (!node.isTextblock || node.type.name === "doc") return;
    if (!firstBlock) text += BLOCK_SEP;
    firstBlock = false;
    node.forEach((child, offset) => {
      if (!child.isText || !child.text) return;
      const from = pos + 1 + offset;
      const t = child.text;
      const start = text.length;
      text += t;
      spans.push({ textStart: start, textEnd: text.length, from, to: from + t.length });
    });
  });
  return { text, spans };
}

/** 
 * Map a UTF-16 slice in `buildDocTextIndex` text to an inclusive-exclusive ProseMirror range.
 * Now handles characters not covered by spans (like BLOCK_SEP) by finding the nearest positions.
 */
export function docRangeForTextSlice(
  spans: TextSpan[],
  offset: number,
  length: number,
): { from: number; to: number } | null {
  if (length <= 0 || offset < 0 || spans.length === 0) return null;
  const end = offset + length;

  let fromPos: number | null = null;
  let toPos: number | null = null;

  for (const s of spans) {
    const overlapStart = Math.max(offset, s.textStart);
    const overlapEnd = Math.min(end, s.textEnd);
    
    if (overlapStart < overlapEnd) {
      const localFrom = s.from + (overlapStart - s.textStart);
      const localTo = s.from + (overlapEnd - s.textStart);
      if (fromPos === null || localFrom < fromPos) fromPos = localFrom;
      if (toPos === null || localTo > toPos) toPos = localTo;
    }
  }

  // If no overlap with actual text spans was found, check if it's a separator-only slice
  if (fromPos === null || toPos === null) {
    // Find the span immediately following the offset to get a fallback position
    const nextSpan = spans.find(s => s.textStart >= offset);
    if (nextSpan) {
      return { from: nextSpan.from, to: nextSpan.from };
    }
    // Fallback to the end of the last span
    const lastSpan = spans[spans.length - 1]!;
    return { from: lastSpan.to, to: lastSpan.to };
  }

  return { from: fromPos, to: toPos };
}

/**
 * Recompute PM range for a grammar match after doc changes; abort if index slice or live text
 * no longer matches what was shown when the popup opened.
 */
export function recomputeGrammarApplyRange(
  doc: PMNode,
  match: Pick<GrammarMatch, "offset" | "length">,
  expectedSlice: string,
): { from: number; to: number } | null {
  const { text, spans } = buildDocTextIndex(doc);
  const idxSlice = text.slice(match.offset, match.offset + match.length);
  if (idxSlice !== expectedSlice) return null;
  const r = docRangeForTextSlice(spans, match.offset, match.length);
  if (!r) return null;
  if (doc.textBetween(r.from, r.to) !== expectedSlice) return null;
  return r;
}
