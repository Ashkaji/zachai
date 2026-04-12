import { Mark, mergeAttributes } from "@tiptap/core";

export const BiblicalCitation = Mark.create({
  name: "biblicalCitation",

  addOptions() {
    return {
      HTMLAttributes: {
        class: "za-biblical-citation",
      },
    };
  },

  parseHTML() {
    return [
      {
        tag: "span",
        getAttrs: (element) =>
          (element as HTMLElement).classList.contains("za-biblical-citation") && null,
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "span",
      mergeAttributes(this.options.HTMLAttributes, HTMLAttributes),
      0,
    ];
  },
});
