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

function sliceCoveredBySpans(spans: TextSpan[], offset: number, end: number): boolean {
  for (let i = offset; i < end; i++) {
    const covered = spans.some((s) => i >= s.textStart && i < s.textEnd);
    if (!covered) return false;
  }
  return true;
}

/** Map a UTF-16 slice in `buildDocTextIndex` text to an inclusive-exclusive ProseMirror range. */
export function docRangeForTextSlice(
  spans: TextSpan[],
  offset: number,
  length: number,
): { from: number; to: number } | null {
  if (length <= 0 || offset < 0) return null;
  const end = offset + length;
  if (!sliceCoveredBySpans(spans, offset, end)) return null;
  let fromPos: number | null = null;
  let toPos: number | null = null;
  for (const s of spans) {
    const overlapStart = Math.max(offset, s.textStart);
    const overlapEnd = Math.min(end, s.textEnd);
    if (overlapStart >= overlapEnd) continue;
    const localFrom = s.from + (overlapStart - s.textStart);
    const localTo = s.from + (overlapEnd - s.textStart);
    if (fromPos === null) fromPos = localFrom;
    toPos = localTo;
  }
  if (fromPos === null || toPos === null) return null;
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
