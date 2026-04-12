import { useState, useEffect } from "react";

interface BiblePreviewPopupProps {
  x: number;
  y: number;
  reference: string;
  token: string;
}

/** Mock function to simulate a Bible Engine API call until it's implemented. */
async function mockFetchVerse(reference: string, _token: string): Promise<string> {
  // Simulate network delay
  await new Promise((resolve) => setTimeout(resolve, 800));
  
  const mockVerses: Record<string, string> = {
    "Zacharie 1:8": "Je regardai pendant la nuit, et voici, un homme était monté sur un cheval roux, et se tenait parmi des myrtes dans un lieu ombragé ; il y avait derrière lui des chevaux roux, fauves, et blancs.",
    "Genèse 1:1": "Au commencement, Dieu créa les cieux et la terre.",
    "Jean 3:16": "Car Dieu a tant aimé le monde qu'il a donné son Fils unique, afin que quiconque croit en lui ne périsse point, mais qu'il ait la vie éternelle.",
  };

  return mockVerses[reference] || "Texte du verset non trouvé dans la base de données locale (Simulation).";
}

export function BiblePreviewPopup({ x, y, reference, token }: BiblePreviewPopupProps) {
  const [text, setText] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    mockFetchVerse(reference, token)
      .then((res) => {
        if (!cancelled) {
          setText(res);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError("Erreur lors de la récupération du verset.");
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [reference, token]);

  return (
    <div
      className="za-glass za-card-glow"
      style={{
        position: "fixed",
        left: Math.min(x, typeof window !== "undefined" ? window.innerWidth - 320 : x),
        top: y + 12,
        zIndex: 1000,
        width: "300px",
        padding: "var(--spacing-5)",
        borderRadius: "var(--radius-lg)",
        fontSize: "0.95rem",
        lineHeight: "1.5",
        animation: "za-pop-in 0.2s ease-out",
      }}
    >
      <div style={{ 
        fontSize: "0.7rem", 
        fontWeight: 800, 
        textTransform: "uppercase", 
        color: "var(--color-primary)", 
        marginBottom: "var(--spacing-3)",
        letterSpacing: "0.05em",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center"
      }}>
        <span>📖 Citation Biblique</span>
        <span style={{ opacity: 0.6 }}>{reference}</span>
      </div>

      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          <div className="za-pulse" style={{ height: "12px", width: "100%", background: "var(--color-surface-vhi)", borderRadius: "4px" }} />
          <div className="za-pulse" style={{ height: "12px", width: "80%", background: "var(--color-surface-vhi)", borderRadius: "4px" }} />
          <div className="za-pulse" style={{ height: "12px", width: "90%", background: "var(--color-surface-vhi)", borderRadius: "4px" }} />
        </div>
      ) : error ? (
        <div style={{ color: "var(--color-error)", fontSize: "0.85rem" }}>{error}</div>
      ) : (
        <div style={{ color: "var(--color-text)", fontStyle: "italic" }}>
          "{text}"
        </div>
      )}

      <style>{`
        @keyframes za-pop-in {
          from { opacity: 0; transform: translateY(4px) scale(0.98); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }
      `}</style>
    </div>
  );
}
