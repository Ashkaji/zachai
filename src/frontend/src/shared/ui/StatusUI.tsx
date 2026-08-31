import type { CSSProperties, ReactNode } from "react";

/**
 * Foundation UI built on the pipeline status tokens (--st-*) from theme.css.
 * One hue per production stage, used consistently across every screen.
 */

export type PipelineStatus =
  | "uploaded"
  | "assigned"
  | "in_progress"
  | "transcribed"
  | "validated"
  | "critical";

type StatusMeta = { token: string; label: string };

const STATUS_META: Record<PipelineStatus, StatusMeta> = {
  uploaded: { token: "--st-uploaded", label: "Déposé" },
  assigned: { token: "--st-assigned", label: "Assigné" },
  in_progress: { token: "--st-progress", label: "En cours" },
  transcribed: { token: "--st-transcribed", label: "À valider" },
  validated: { token: "--st-validated", label: "Validé" },
  critical: { token: "--st-critical", label: "Erreur" },
};

/** Normalise a raw backend status string to a known PipelineStatus. */
export function normaliseStatus(raw: string | null | undefined): PipelineStatus {
  const key = (raw ?? "").toLowerCase().replace(/[\s-]+/g, "_");
  if (key in STATUS_META) return key as PipelineStatus;
  if (key === "in_progress" || key === "inprogress") return "in_progress";
  if (key === "error" || key === "failed") return "critical";
  return "uploaded";
}

export function statusColor(status: PipelineStatus): string {
  return `var(${STATUS_META[status].token})`;
}

export function statusLabel(status: PipelineStatus): string {
  return STATUS_META[status].label;
}

/** A dot + label chip. Single source of truth for status display. */
export function StatusChip({
  status,
  label,
  style,
}: {
  status: PipelineStatus | string;
  label?: string;
  style?: CSSProperties;
}) {
  const s = typeof status === "string" && !(status in STATUS_META) ? normaliseStatus(status) : (status as PipelineStatus);
  const color = statusColor(s);
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "7px",
        padding: "4px 11px 4px 9px",
        borderRadius: "100px",
        fontSize: "0.72rem",
        fontWeight: 700,
        color,
        background: `color-mix(in srgb, ${color} 15%, transparent)`,
        whiteSpace: "nowrap",
        ...style,
      }}
    >
      <span
        aria-hidden
        style={{
          width: "7px",
          height: "7px",
          borderRadius: "50%",
          background: color,
          boxShadow: `0 0 0 3px color-mix(in srgb, ${color} 18%, transparent)`,
        }}
      />
      {label ?? statusLabel(s)}
    </span>
  );
}

/** A small readiness dot (e.g. normalisation state). */
export function ReadyDot({ status, title }: { status: PipelineStatus | string; title?: string }) {
  const s = typeof status === "string" && !(status in STATUS_META) ? normaliseStatus(status) : (status as PipelineStatus);
  return (
    <span
      title={title}
      style={{ width: "9px", height: "9px", borderRadius: "50%", display: "inline-block", background: statusColor(s) }}
    />
  );
}

type Tone = "default" | "positive" | "attention";

/** Metric card with optional trend and a "demo" badge for non-wired figures. */
export function MetricTile({
  label,
  value,
  trend,
  tone = "default",
  demo = false,
  spark,
}: {
  label: string;
  value: ReactNode;
  trend?: { direction: "up" | "down"; text: string };
  tone?: Tone;
  demo?: boolean;
  spark?: number[];
}) {
  const valueColor =
    tone === "positive"
      ? "var(--st-validated)"
      : tone === "attention"
        ? "var(--st-transcribed)"
        : "var(--color-text)";
  const trendColor = trend?.direction === "up" ? "var(--st-validated)" : "var(--st-critical)";

  return (
    <div
      style={{
        position: "relative",
        overflow: "hidden",
        padding: "var(--spacing-4) var(--spacing-4)",
        borderRadius: "var(--radius-md)",
        background: "var(--color-surface-hi)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "8px",
          color: "var(--color-text-muted)",
          fontSize: "0.72rem",
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.05em",
        }}
      >
        <span>{label}</span>
        {demo ? <DemoBadge /> : null}
      </div>
      <div
        style={{
          marginTop: "3px",
          fontSize: "1.7rem",
          fontWeight: 800,
          color: demo ? "var(--color-text-muted)" : valueColor,
          fontFamily: "var(--font-headline)",
          letterSpacing: "-0.02em",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {value}
      </div>
      {trend ? (
        <div style={{ marginTop: "2px", fontSize: "0.72rem", fontWeight: 700, color: trendColor }}>
          {trend.direction === "up" ? "▲" : "▼"} {trend.text}
        </div>
      ) : null}
      {spark && spark.length > 1 ? <Sparkline points={spark} color={valueColor} /> : null}
    </div>
  );
}

export function DemoBadge() {
  return (
    <span
      title="Donnée de démonstration — non branchée sur une source réelle"
      style={{
        fontSize: "0.58rem",
        fontWeight: 800,
        letterSpacing: "0.06em",
        padding: "1px 6px",
        borderRadius: "100px",
        color: "var(--color-text-muted)",
        border: "1px solid var(--color-outline)",
      }}
    >
      DÉMO
    </span>
  );
}

function Sparkline({ points, color }: { points: number[]; color: string }) {
  const max = Math.max(...points, 1);
  const min = Math.min(...points, 0);
  const range = max - min || 1;
  const w = 62;
  const h = 26;
  const step = w / (points.length - 1);
  const d = points
    .map((p, i) => `${(i * step).toFixed(1)},${(h - ((p - min) / range) * h).toFixed(1)}`)
    .join(" ");
  return (
    <svg
      width={w}
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      fill="none"
      style={{ position: "absolute", right: "12px", bottom: "10px", opacity: 0.85 }}
      aria-hidden
    >
      <polyline points={d} stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export type StatusCounts = Partial<Record<PipelineStatus, number>>;

const PIPELINE_ORDER: PipelineStatus[] = ["uploaded", "assigned", "in_progress", "transcribed", "validated"];

/** Segmented progress bar coloured by status, with an optional counted legend. */
export function PipelineBar({ counts, legend = true }: { counts: StatusCounts; legend?: boolean }) {
  const total = PIPELINE_ORDER.reduce((sum, s) => sum + (counts[s] ?? 0), 0);
  return (
    <div>
      <div
        style={{
          display: "flex",
          height: "9px",
          borderRadius: "100px",
          overflow: "hidden",
          background: "var(--color-surface-vhi)",
        }}
      >
        {total > 0 &&
          PIPELINE_ORDER.map((s) => {
            const c = counts[s] ?? 0;
            if (c === 0) return null;
            return <span key={s} style={{ width: `${(c / total) * 100}%`, background: statusColor(s) }} />;
          })}
      </div>
      {legend ? (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "12px",
            marginTop: "8px",
            fontSize: "0.72rem",
            color: "var(--color-text-muted)",
          }}
        >
          {PIPELINE_ORDER.map((s) => (
            <span key={s} style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
              <span style={{ width: "9px", height: "9px", borderRadius: "3px", background: statusColor(s) }} />
              {statusLabel(s)} · {counts[s] ?? 0}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/** Empty state with icon, title, guidance and optional action. */
export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div style={{ textAlign: "center", padding: "30px 20px" }}>
      <div
        style={{
          width: "44px",
          height: "44px",
          borderRadius: "12px",
          background: "var(--color-primary-soft)",
          color: "var(--color-primary)",
          display: "grid",
          placeItems: "center",
          margin: "0 auto 12px",
        }}
      >
        {icon ?? <CheckIcon />}
      </div>
      <div style={{ fontFamily: "var(--font-headline)", fontWeight: 700, fontSize: "0.95rem" }}>{title}</div>
      {description ? (
        <div
          style={{
            fontSize: "0.8rem",
            color: "var(--color-text-muted)",
            maxWidth: "44ch",
            margin: "5px auto 0",
            lineHeight: 1.5,
          }}
        >
          {description}
        </div>
      ) : null}
      {action ? <div style={{ marginTop: "16px" }}>{action}</div> : null}
    </div>
  );
}

function CheckIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}
