import React, { useEffect, useRef } from "react";
import { BubbleMenu, Editor } from "@tiptap/react";
import { Play, CheckCircle2, BookOpen } from "lucide-react";

interface AzureBubbleMenuProps {
  editor: Editor;
  audioRef: React.RefObject<HTMLAudioElement | null>;
}

export const AzureBubbleMenu: React.FC<AzureBubbleMenuProps> = ({ editor, audioRef }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleFocusEvent = () => {
      // Use requestAnimationFrame for more reliable focus timing after Tippy renders (Story 11 review)
      requestAnimationFrame(() => {
        const firstButton = containerRef.current?.querySelector("button");
        if (firstButton instanceof HTMLElement) {
          firstButton.focus();
        }
      });
    };

    (editor as any).on("focusBubbleMenu", handleFocusEvent);
    return () => {
      (editor as any).off("focusBubbleMenu", handleFocusEvent);
    };
  }, [editor]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      editor.commands.focus();
      return;
    }

    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      const buttons = Array.from(containerRef.current?.querySelectorAll("button") || []);
      const currentIndex = buttons.indexOf(document.activeElement as HTMLButtonElement);
      if (currentIndex === -1) return;

      let nextIndex = e.key === "ArrowRight" ? currentIndex + 1 : currentIndex - 1;
      if (nextIndex < 0) nextIndex = buttons.length - 1;
      if (nextIndex >= buttons.length) nextIndex = 0;

      (buttons[nextIndex] as HTMLButtonElement).focus();
      e.preventDefault();
      e.stopPropagation();
    }
  };

  return (
    <BubbleMenu
      editor={editor}
      tippyOptions={{ 
        duration: 300,
        // Ensure it doesn't close when we focus inside it
        interactive: true,
        trigger: "manual" // We handle showing via selection + Ctrl+K
      }}
      shouldShow={({ editor }) => !editor.state.selection.empty}
    >
      <div
        ref={containerRef}
        className="za-glass za-bubble-menu"
        role="menu"
        aria-expanded="true"
        onKeyDown={handleKeyDown}
        style={{
          display: "flex",
          gap: "var(--spacing-1)",
          padding: "var(--spacing-1)",
          borderRadius: "var(--radius-sm)",
          boxShadow: "var(--glow-primary)",
        }}
      >
        <button
          role="menuitem"
          aria-label="Play Selection"
          onClick={() => {
            const { from } = editor.state.selection;
            const node = editor.state.doc.nodeAt(from);
            if (node?.marks) {
              const whisperMark = node.marks.find((m) => m.type.name === "whisperSegment");
              if (whisperMark) {
                const audio = audioRef.current;
                if (audio) {
                  audio.currentTime = whisperMark.attrs.audioStart;
                  audio.play();
                }
              }
            }
          }}
          className="za-btn za-btn--ghost"
          style={{ padding: "6px" }}
          title="Play Selection"
        >
          <Play size={16} strokeWidth={1.5} />
        </button>
        <button
          role="menuitem"
          aria-label="Validate Segment"
          onClick={() => {
            editor
              .chain()
              .focus()
              .extendMarkRange("whisperSegment")
              .updateAttributes("whisperSegment", { status: "validated" })
              .run();
          }}
          className="za-btn za-btn--ghost"
          style={{ padding: "6px" }}
          title="Validate Segment"
        >
          <CheckCircle2 size={16} strokeWidth={1.5} />
        </button>
        <button
          role="menuitem"
          aria-label="Verse Style"
          onClick={() => {
            editor.chain().focus().toggleMark("biblicalCitation").run();
          }}
          className={`za-btn za-btn--ghost ${
            editor.isActive("biblicalCitation") ? "za-btn--active" : ""
          }`}
          style={{ padding: "6px" }}
          title="Verse Style"
        >
          <BookOpen size={16} strokeWidth={1.5} />
        </button>
      </div>
    </BubbleMenu>
  );
};
