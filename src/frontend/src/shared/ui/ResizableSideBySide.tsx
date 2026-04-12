import { useState, useRef, useEffect, ReactNode } from "react";

interface ResizableSideBySideProps {
  left: ReactNode;
  right: ReactNode;
  initialLeftWidth?: number; // percentage 0-100
  minWidth?: number; // percentage
}

export function ResizableSideBySide({
  left,
  right,
  initialLeftWidth = 50,
  minWidth = 20,
}: ResizableSideBySideProps) {
  const [leftWidth, setLeftWidth] = useState(initialLeftWidth);
  const containerRef = useRef<HTMLDivElement>(null);
  const isResizing = useRef(false);

  const startResizing = () => {
    isResizing.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };

  const stopResizing = () => {
    isResizing.current = false;
    document.body.style.cursor = "default";
    document.body.style.userSelect = "auto";
  };

  const onMouseMove = (e: MouseEvent) => {
    if (!isResizing.current || !containerRef.current) return;

    const containerRect = containerRef.current.getBoundingClientRect();
    const newWidth = ((e.clientX - containerRect.left) / containerRect.width) * 100;

    if (newWidth >= minWidth && newWidth <= 100 - minWidth) {
      setLeftWidth(newWidth);
    }
  };

  useEffect(() => {
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", stopResizing);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", stopResizing);
    };
  }, []);

  return (
    <div
      ref={containerRef}
      style={{
        display: "flex",
        width: "100%",
        height: "100%",
        overflow: "hidden",
        position: "relative",
      }}
    >
      <div
        style={{
          width: `${leftWidth}%`,
          height: "100%",
          overflow: "auto",
        }}
      >
        {left}
      </div>

      <div
        onMouseDown={startResizing}
        style={{
          width: "8px",
          height: "100%",
          cursor: "col-resize",
          background: "transparent",
          position: "relative",
          zIndex: 10,
          flexShrink: 0,
          transition: "background 0.2s",
        }}
        className="za-resizable-handle"
      >
        <div
          style={{
            position: "absolute",
            left: "50%",
            top: "50%",
            transform: "translate(-50%, -50%)",
            width: "2px",
            height: "40px",
            background: "var(--color-primary)",
            borderRadius: "1px",
            opacity: 0.4,
            boxShadow: "var(--glow-primary)",
          }}
        />
      </div>

      <div
        style={{
          flex: 1,
          height: "100%",
          overflow: "auto",
        }}
      >
        {right}
      </div>

      <style>{`
        .za-resizable-handle:hover {
          background: rgba(var(--color-primary-rgb), 0.1) !important;
        }
        .za-resizable-handle:active {
          background: rgba(var(--color-primary-rgb), 0.2) !important;
        }
      `}</style>
    </div>
  );
}
