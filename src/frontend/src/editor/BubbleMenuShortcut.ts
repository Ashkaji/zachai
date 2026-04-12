import { Extension } from "@tiptap/core";

export const BubbleMenuShortcut = Extension.create({
  name: "bubbleMenuShortcut",

  addKeyboardShortcuts() {
    return {
      "Mod-k": () => {
        const { editor } = this;
        const { state } = editor;
        const { selection } = state;
        if (selection.empty) {
          return false;
        }

        // Emit an event that the BubbleMenu can listen to for focusing
        // Using cast to any because it's a custom event not in Tiptap types
        (editor as any).emit("focusBubbleMenu");
        
        return true;
      },
    };
  },
});
