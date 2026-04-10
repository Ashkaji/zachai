import type { ReactNode } from "react";

export function Card({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <section
      className="za-card-glow"
      style={{
        background: "var(--color-surface)",
        border: "1px solid var(--color-outline-ghost)",
        borderRadius: "var(--radius-lg)",
        padding: "var(--spacing-5)",
      }}
    >
      <div style={{ marginBottom: "var(--spacing-4)" }}>
        <h3
          style={{
            margin: 0,
            fontFamily: "var(--font-headline)",
            fontSize: "1rem",
            fontWeight: 800,
          }}
        >
          {title}
        </h3>
        {subtitle ? (
          <p style={{ margin: "var(--spacing-1) 0 0", color: "var(--color-text-muted)", fontSize: "0.85rem" }}>{subtitle}</p>
        ) : null}
      </div>
      {children}
    </section>
  );
}

export function Metric({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "success" | "error";
}) {
  const toneColor =
    tone === "success" ? "var(--color-success)" : tone === "error" ? "var(--color-error)" : "var(--color-primary)";
  return (
    <div
      style={{
        padding: "var(--spacing-4)",
        borderRadius: "var(--radius-md)",
        background: "var(--color-surface-hi)",
        border: "1px solid var(--color-outline-ghost)",
      }}
    >
      <div style={{ color: "var(--color-text-muted)", fontSize: "0.75rem", fontWeight: 600, textTransform: "uppercase", tracking: "0.05em" }}>{label}</div>
      <div style={{ marginTop: "var(--spacing-2)", fontSize: "1.75rem", fontWeight: 800, color: tone === "default" ? "var(--color-text)" : toneColor, fontFamily: "var(--font-headline)" }}>{value}</div>
    </div>
  );
}

export function DataTable({
  columns,
  rows,
}: {
  columns: string[];
  rows: ReactNode[][];
}) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 0 }}>
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column}
                style={{
                  textAlign: "left",
                  padding: "12px 16px",
                  color: "var(--color-text-muted)",
                  background: "var(--color-surface-hi)",
                  fontSize: "0.75rem",
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                  borderBottom: "1px solid var(--color-outline-ghost)",
                }}
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr 
              key={`row-${rowIndex}`} 
              className="za-row-hover"
              style={{ transition: "background 0.2s ease" }}
            >
              {row.map((cell, cellIndex) => (
                <td 
                  key={`cell-${rowIndex}-${cellIndex}`} 
                  style={{ 
                    padding: "16px", 
                    borderBottom: "1px solid var(--color-outline-ghost)",
                    fontSize: "0.9rem",
                  }}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <style>{`
        .za-row-hover:hover {
          background: var(--color-surface-hi);
        }
      `}</style>
    </div>
  );
}
