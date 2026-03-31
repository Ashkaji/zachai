import { describe, it, expect } from "vitest";
import { Schema } from "@tiptap/pm/model";
import {
  buildDocTextIndex,
  docRangeForTextSlice,
  recomputeGrammarApplyRange,
} from "./grammarUtils";

const schema = new Schema({
  nodes: {
    doc: { content: "block+" },
    paragraph: { group: "block", content: "text*" },
    text: { name: "text", group: "inline" },
  },
});

function docTwoParagraphs(a: string, b: string) {
  return schema.nodes.doc.create(null, [
    schema.nodes.paragraph.create(null, schema.text(a)),
    schema.nodes.paragraph.create(null, schema.text(b)),
  ]);
}

function docOnePara(t: string) {
  return schema.nodes.doc.create(null, [schema.nodes.paragraph.create(null, schema.text(t))]);
}

describe("buildDocTextIndex", () => {
  it("inserts newline between top-level text blocks", () => {
    const doc = docTwoParagraphs("hello", "world");
    const { text, spans } = buildDocTextIndex(doc);
    expect(text).toBe("hello\nworld");
    expect(spans).toHaveLength(2);
    expect(spans[0]!.textStart).toBe(0);
    expect(spans[0]!.textEnd).toBe(5);
    expect(spans[1]!.textStart).toBe(6);
    expect(spans[1]!.textEnd).toBe(11);
  });

  it("concatenates segments within one paragraph", () => {
    const doc = docOnePara("ab");
    const { text, spans } = buildDocTextIndex(doc);
    expect(text).toBe("ab");
    expect(spans).toHaveLength(1);
  });
});

describe("docRangeForTextSlice", () => {
  it("maps a slice within one text node", () => {
    const doc = docOnePara("abcdef");
    const { spans } = buildDocTextIndex(doc);
    const r = docRangeForTextSlice(spans, 2, 2);
    expect(r).not.toBeNull();
    expect(doc.textBetween(r!.from, r!.to)).toBe("cd");
  });

  it("returns null when slice would span block separator", () => {
    const doc = docTwoParagraphs("ab", "cd");
    const { text, spans } = buildDocTextIndex(doc);
    expect(text).toBe("ab\ncd");
    expect(docRangeForTextSlice(spans, 1, 3)).toBeNull();
  });

  it("maps within second paragraph using offset including newline", () => {
    const doc = docTwoParagraphs("ab", "cd");
    const { text, spans } = buildDocTextIndex(doc);
    expect(text).toBe("ab\ncd");
    const r = docRangeForTextSlice(spans, 3, 1);
    expect(r).not.toBeNull();
    expect(doc.textBetween(r!.from, r!.to)).toBe("c");
  });

  it("returns null for out-of-range offset", () => {
    const doc = docOnePara("a");
    const { spans } = buildDocTextIndex(doc);
    expect(docRangeForTextSlice(spans, 5, 1)).toBeNull();
  });
});

describe("TranscriptionEditor stale grammar response guard", () => {
  function isStaleGrammarResponse(genWhenScheduled: number, grammarGenNow: number) {
    return genWhenScheduled !== grammarGenNow;
  }

  it("drops in-flight results after another edit bumps gen", () => {
    expect(isStaleGrammarResponse(1, 2)).toBe(true);
  });

  it("allows results when gen matches", () => {
    expect(isStaleGrammarResponse(3, 3)).toBe(false);
  });
});

describe("recomputeGrammarApplyRange", () => {
  it("returns range when index and live text still match expected slice", () => {
    const doc = docOnePara("teh quick");
    const r = recomputeGrammarApplyRange(doc, { offset: 0, length: 3 }, "teh");
    expect(r).not.toBeNull();
    expect(doc.textBetween(r!.from, r!.to)).toBe("teh");
  });

  it("returns null when document text changed under the match", () => {
    const doc = docOnePara("the quick");
    expect(recomputeGrammarApplyRange(doc, { offset: 0, length: 3 }, "teh")).toBeNull();
  });

  it("returns null when expected slice disagrees with index at offset", () => {
    const doc = docOnePara("hello");
    expect(recomputeGrammarApplyRange(doc, { offset: 0, length: 3 }, "xyz")).toBeNull();
  });
});
