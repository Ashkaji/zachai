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
        background: "var(--color-surface-low)",
        borderRadius: "var(--radius-lg)",
        padding: "var(--spacing-5)",
        // No-Line Rule: Border removed, tonal separation used
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
        // No-Line Rule: Border removed
      }}
    >
      <div style={{ color: "var(--color-text-muted)", fontSize: "0.75rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</div>
      <div style={{ marginTop: "var(--spacing-2)", fontSize: "1.75rem", fontWeight: 800, color: tone === "default" ? "var(--color-text)" : toneColor, fontFamily: "var(--font-headline)" }}>{value}</div>
    </div>
  );
}

export function Badge({
  children,
  tone = "default",
  glow = false,
  pulse = false,
  style,
}: {
  children: ReactNode;
  tone?: "default" | "primary" | "success" | "error";
  glow?: boolean;
  pulse?: boolean;
  style?: React.CSSProperties;
}) {
  const styles = {
    default: { bg: "var(--color-surface-vhi)", text: "var(--color-text-muted)", glow: "0 0 8px rgba(128, 128, 128, 0.2)" },
    primary: { bg: "var(--color-primary-soft)", text: "var(--color-primary)", glow: "0 0 12px var(--color-glow-blue)" },
    success: { bg: "rgba(47, 138, 99, 0.15)", text: "var(--color-success)", glow: "0 0 12px var(--color-success)" },
    error: { bg: "rgba(255, 113, 108, 0.15)", text: "var(--color-error)", glow: "0 0 12px var(--color-error)" },
  };

  const current = styles[tone];

  return (
    <span
      className={pulse ? "za-pulse" : ""}
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "4px 10px",
        borderRadius: "var(--radius-sm)",
        fontSize: "0.75rem",
        fontWeight: 700,
        background: current.bg,
        color: current.text,
        textTransform: "uppercase",
        letterSpacing: "0.02em",
        boxShadow: glow ? current.glow : undefined,
        ...style,
      }}
    >
      {children}
      <style>{`
        @keyframes za-pulse {
          0% { opacity: 0.8; transform: scale(1); }
          50% { opacity: 1; transform: scale(1.02); }
          100% { opacity: 0.8; transform: scale(1); }
        }
        .za-pulse {
          animation: za-pulse 2s infinite ease-in-out;
        }
      `}</style>
    </span>
  );
}

export function DataTable({
  columns,
  rows,
  selectable,
  selectedIds,
  onToggleAll,
  onToggleRow,
  allSelected,
  rowIds,
}: {
  columns: string[];
  rows: ReactNode[][];
  selectable?: boolean;
  selectedIds?: Set<number | string>;
  onToggleAll?: () => void;
  onToggleRow?: (id: number | string) => void;
  allSelected?: boolean;
  rowIds?: (number | string)[];
}) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 0 }}>
        <thead>
          <tr>
            {selectable && (
              <th
                style={{
                  width: "48px",
                  padding: "12px 16px",
                  background: "var(--color-surface-hi)",
                  borderBottom: "2px solid var(--color-bg)",
                }}
              >
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={() => onToggleAll?.()}
                  style={{ cursor: "pointer" }}
                />
              </th>
            )}
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
                  borderBottom: "2px solid var(--color-bg)",
                }}
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => {
          const rowId = (rowIds ? rowIds[rowIndex] : rowIndex) ?? rowIndex;
          const isSelected = selectedIds?.has(rowId);
          return (
          <tr
          key={`row-${rowIndex}`}
          className="za-row-hover"
          style={{
            transition: "background 0.2s ease",
            background: isSelected ? "var(--color-primary-soft)" : undefined,
          }}
          >
          {selectable && (
            <td
              style={{
                padding: "16px",
                borderBottom: "1px solid var(--color-surface-low)",
              }}
            >
              <input
                type="checkbox"
                checked={isSelected}
                onChange={() => onToggleRow?.(rowId)}
                style={{ cursor: "pointer" }}
              />
            </td>
          )}

                {row.map((cell, cellIndex) => (
                  <td
                    key={`cell-${rowIndex}-${cellIndex}`}
                    style={{
                      padding: "16px",
                      fontSize: "0.9rem",
                      borderBottom: "1px solid var(--color-surface-low)",
                    }}
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            );
          })}
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
