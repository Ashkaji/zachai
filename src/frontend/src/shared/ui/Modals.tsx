import { type ReactNode, useEffect } from "react";
import { createPortal } from "react-dom";

type ModalSize = "sm" | "md" | "lg" | "xl";

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  size?: ModalSize;
}

const sizeClasses: Record<ModalSize, string> = {
  sm: "400px",
  md: "600px",
  lg: "800px",
  xl: "1000px",
};

export function GlassModal({ isOpen, onClose, title, children, size = "md" }: ModalProps) {
  useEffect(() => {
    if (!isOpen) return;

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };

    window.addEventListener("keydown", handleEscape);
    // Prevent scrolling when modal is open
    document.body.style.overflow = "hidden";

    return () => {
      window.removeEventListener("keydown", handleEscape);
      document.body.style.overflow = "auto";
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return createPortal(
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(0, 0, 0, 0.4)",
        backdropFilter: "blur(8px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        animation: "za-fade-in 0.2s ease-out",
      }}
      onClick={onClose}
    >
      <div
        className="za-glass"
        style={{
          width: "90%",
          maxWidth: sizeClasses[size],
          maxHeight: "90vh",
          padding: "var(--spacing-6)",
          borderRadius: "var(--radius-lg)",
          border: "1px solid var(--color-outline)",
          boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.5), 0 0 20px var(--color-primary-soft)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--spacing-5)",
          overflow: "hidden",
          animation: "za-modal-slide-up 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <header
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <h3
            style={{
              margin: 0,
              fontFamily: "var(--font-headline)",
              fontSize: "1.25rem",
              fontWeight: 800,
              letterSpacing: "-0.02em",
            }}
          >
            {title}
          </h3>
          <button
            type="button"
            className="za-btn za-btn--ghost"
            onClick={onClose}
            style={{
              padding: "var(--spacing-1)",
              width: "32px",
              height: "32px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              borderRadius: "50%",
              fontSize: "1.5rem",
              lineHeight: 1,
            }}
          >
            &times;
          </button>
        </header>

        <div
          style={{
            flex: 1,
            overflowY: "auto",
            minHeight: 0,
          }}
        >
          {children}
        </div>
      </div>

      <style>{`
        @keyframes za-fade-in {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes za-modal-slide-up {
          from { transform: translateY(20px); opacity: 0; }
          to { transform: translateY(0); opacity: 1; }
        }
      `}</style>
    </div>,
    document.body
  );
}
