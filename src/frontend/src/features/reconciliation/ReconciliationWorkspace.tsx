import { useState, useEffect, useRef } from "react";
import { ResizableSideBySide } from "../../shared/ui/ResizableSideBySide";
import { useAuth } from "react-oidc-context";
import { bearerForApi } from "../../auth/api-client";

interface ReconciliationWorkspaceProps {
  audioId: number;
  onBack: () => void;
}

/**
 * Simple word-level diff.
 * Returns an array of elements representing additions, deletions, and unchanged text.
 */
function renderDiff(original: string, corrected: string) {
  const words1 = original.split(/\s+/);
  const words2 = corrected.split(/\s+/);
  
  // Very basic word comparison. For production, use diff-match-patch or similar.
  const elements: JSX.Element[] = [];
  
  const maxLength = Math.max(words1.length, words2.length);
  
  for (let i = 0; i < maxLength; i++) {
    const w1 = words1[i];
    const w2 = words2[i];
    
    if (w1 === w2) {
      elements.push(<span key={i}>{w1} </span>);
    } else {
      if (w1 && !w2) {
        // Deletion (only in original)
        // Not shown in the 'corrected' view render unless we want a merged view
      } else if (!w1 && w2) {
        // Addition
        elements.push(<span key={i} style={{ background: "rgba(34, 197, 94, 0.2)", color: "var(--color-success)", fontWeight: 600, padding: "0 2px", borderRadius: "2px" }}>{w2} </span>);
      } else {
        // Change
        elements.push(<span key={i} style={{ background: "rgba(59, 130, 246, 0.2)", color: "var(--color-primary)", fontWeight: 600, padding: "0 2px", borderRadius: "2px" }}>{w2} </span>);
      }
    }
  }
  
  return elements;
}

export function ReconciliationWorkspace({ audioId, onBack }: ReconciliationWorkspaceProps) {
  const auth = useAuth();
  const token = bearerForApi(auth.user);
  const [syncScroll, setSyncScroll] = useState(true);
  
  const leftRef = useRef<HTMLDivElement>(null);
  const rightRef = useRef<HTMLDivElement>(null);
  const isScrolling = useRef<"left" | "right" | null>(null);

  useEffect(() => {
    // Logic using token and audioId will go here when API is integrated
    if (!token || !audioId) return;
  }, [token, audioId]);

  useEffect(() => {
    if (!syncScroll) return;

    const handleScroll = (source: "left" | "right") => () => {
      if (isScrolling.current && isScrolling.current !== source) return;
      
      const target = source === "left" ? rightRef.current : leftRef.current;
      const src = source === "left" ? leftRef.current : rightRef.current;
      
      if (src && target) {
        isScrolling.current = source;
        const scrollPct = src.scrollTop / (src.scrollHeight - src.clientHeight);
        target.scrollTop = scrollPct * (target.scrollHeight - target.clientHeight);
        
        // Reset after a short delay
        setTimeout(() => {
          isScrolling.current = null;
        }, 50);
      }
    };

    const left = leftRef.current;
    const right = rightRef.current;

    left?.addEventListener("scroll", handleScroll("left"));
    right?.addEventListener("scroll", handleScroll("right"));

    return () => {
      left?.removeEventListener("scroll", handleScroll("left"));
      right?.removeEventListener("scroll", handleScroll("right"));
    };
  }, [syncScroll]);

  // Mock data for demonstration
  const originalText = "Le prophète Zacharie a reçu une vision pendant la nuit. Il a vu un homme monté sur un cheval roux, se tenant parmi des myrtes. ".repeat(15);
  const correctedText = "Le prophète Zacharie reçut une vision pendant la nuit. Il vit un homme monté sur un coursier roux, se tenant parmi des myrtes. ".repeat(15);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        gap: "var(--spacing-4)",
        animation: "fade-in 0.4s ease",
      }}
    >
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <button onClick={onBack} className="za-btn za-btn--ghost" style={{ border: "none" }}>
          ← Retour au Dashboard
        </button>
        <div style={{ display: "flex", gap: "16px", alignItems: "center" }}>
          <label style={{ fontSize: "0.85rem", fontWeight: 600, cursor: "pointer", display: "flex", alignItems: "center", gap: "8px", color: "var(--color-text-muted)" }}>
            <input 
              type="checkbox" 
              checked={syncScroll} 
              onChange={(e) => setSyncScroll(e.target.checked)} 
              style={{ width: "16px", height: "16px" }}
            />
            Synchroniser le défilement
          </label>
          <button className="za-btn za-btn--primary" style={{ boxShadow: "var(--glow-primary)" }}>
            Valider le Golden Set
          </button>
        </div>
      </header>

      <div className="za-glass" style={{ flex: 1, borderRadius: "var(--radius-lg)", overflow: "hidden", display: "flex", flexDirection: "column", boxShadow: "0 8px 32px rgba(0,0,0,0.2)" }}>
        <div style={{ display: "flex", background: "var(--color-surface-hi)", borderBottom: "none" }}>
           <div style={{ flex: 1, padding: "14px 24px", fontSize: "0.7rem", fontWeight: 800, textTransform: "uppercase", color: "var(--color-text-muted)", letterSpacing: "0.05em" }}>
             Whisper (A-Raw)
           </div>
           <div style={{ width: "8px" }} />
           <div style={{ flex: 1, padding: "14px 24px", fontSize: "0.7rem", fontWeight: 800, textTransform: "uppercase", color: "var(--color-primary)", letterSpacing: "0.05em" }}>
             Correction (B-User)
           </div>
        </div>
        
        <div style={{ flex: 1, minHeight: 0 }}>
          <ResizableSideBySide
            left={
              <div ref={leftRef} style={{ height: "100%", overflow: "auto", padding: "40px", lineHeight: "1.8", fontSize: "1.15rem", fontFamily: "var(--font-body)", color: "var(--color-text-muted)" }}>
                {originalText}
              </div>
            }
            right={
              <div ref={rightRef} style={{ height: "100%", overflow: "auto", padding: "40px", lineHeight: "1.8", fontSize: "1.15rem", fontFamily: "var(--font-body)" }}>
                {renderDiff(originalText, correctedText)}
              </div>
            }
          />
        </div>
      </div>
      
      <style>{`
        @keyframes fade-in { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
      `}</style>
    </div>
  );
}
