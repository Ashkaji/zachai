import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useAuth } from "react-oidc-context";
import { bearerForApi } from "../../auth/api-client";
import { Card, DataTable } from "../../shared/ui/Primitives";
import {
  MetricTile,
  StatusChip,
  PipelineBar,
  EmptyState,
  DemoBadge,
  normaliseStatus,
  statusColor,
} from "../../shared/ui/StatusUI";
import { useNotifications } from "../../shared/notifications/NotificationContext";
import { formatIso } from "../../shared/utils/dateUtils";
import {
  claimTask,
  fetchAvailableTasks,
  fetchExpertTasks,
  fetchGoldenSetStatus,
  fetchManagerProjects,
  fetchMyAudioTasks,
  toggleHelp,
  type AudioTask,
  type ExpertTask,
  type GoldenSetStatus,
  type ProjectSummary,
} from "./dashboardApi";
import { CreateManagerModal } from "./CreateManagerModal";
import { InviteTeamMemberModal } from "./InviteTeamMemberModal";

function DashboardInfo({ text }: { text: string }) {
  return <p style={{ margin: 0, color: "var(--color-text-muted)", fontSize: "0.9rem" }}>{text}</p>;
}

/** Compact search input with a leading icon and a clear button. */
function SearchBox({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "8px",
        background: "var(--color-surface-hi)",
        border: "1px solid var(--color-outline-ghost)",
        borderRadius: "var(--radius-sm)",
        padding: "7px 10px",
        minWidth: "min(280px, 100%)",
      }}
    >
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--color-text-muted)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <circle cx="11" cy="11" r="7" />
        <path d="m21 21-4.3-4.3" />
      </svg>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        style={{
          flex: 1,
          border: "none",
          outline: "none",
          background: "transparent",
          color: "var(--color-text)",
          fontFamily: "var(--font-body)",
          fontSize: "0.85rem",
          minWidth: 0,
        }}
      />
      {value ? (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label="Effacer la recherche"
          style={{ border: "none", background: "transparent", color: "var(--color-text-muted)", cursor: "pointer", fontSize: "0.9rem", lineHeight: 1, padding: 0 }}
        >
          ✕
        </button>
      ) : null}
    </div>
  );
}

export type ExpertDashboardViewState = "loading" | "error" | "empty" | "success";

export function resolveExpertDashboardViewState(input: {
  loading: boolean;
  error: string;
  tasksCount: number;
}): ExpertDashboardViewState {
  if (input.loading) return "loading";
  if (input.error) return "error";
  if (input.tasksCount === 0) return "empty";
  return "success";
}

export function ExpertDashboardStateContent(input: {
  viewState: ExpertDashboardViewState;
  error: string;
  tasks: ExpertTask[];
  onReconcile?: (id: number) => void;
}): ReactNode {
  const { viewState, error, tasks, onReconcile } = input;
  if (viewState === "loading") {
    return <DashboardInfo text="Chargement dashboard expert..." />;
  }
  if (viewState === "error") {
    return <p style={{ color: "var(--color-error)", margin: 0 }}>{error}</p>;
  }
  if (viewState === "empty") {
    return <DashboardInfo text="Aucune tache experte pour le moment." />;
  }
  return (
    <DataTable
      columns={["Audio", "Projet", "Statut", "Source", "Action"]}
      rows={tasks.slice(0, 12).map((t) => [
        <div style={{ fontWeight: 700 }}>{t.filename}</div>,
        t.project_name,
        <span style={{ 
          padding: "2px 6px", 
          borderRadius: "4px", 
          fontSize: "0.7rem", 
          fontWeight: 800,
          background: t.status === "validated" ? "var(--color-primary-soft)" : "var(--color-surface-hi)",
          color: t.status === "validated" ? "var(--color-primary)" : "var(--color-text-muted)"
        }}>{t.status.toUpperCase()}</span>,
        t.source,
        <div style={{ display: "flex", gap: "var(--spacing-2)" }}>
          {onReconcile && (
            <button 
              onClick={() => onReconcile(t.audio_id)}
              className="za-btn za-btn--ghost" 
              style={{ padding: "4px 8px", fontSize: "0.75rem", border: "none", background: "var(--color-surface-hi)" }}
            >
              Réconcilier →
            </button>
          )}
          {t.source === "label_studio" && t.label_studio_url && t.label_studio_project_id && (
            <a
              href={`${t.label_studio_url}/projects/${t.label_studio_project_id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="za-btn za-btn--ghost"
              style={{ 
                padding: "4px 8px", 
                fontSize: "0.75rem", 
                border: "1px solid var(--color-outline-ghost)", 
                background: "transparent",
                textDecoration: "none",
                display: "inline-flex",
                alignItems: "center"
              }}
              title="Ouvrir dans Label Studio"
            >
              Label Studio →
            </a>
          )}
        </div>
      ])}
    />
  );
}

// --- Common Components for Azure Flow ---

function StatGrid({ children }: { children: ReactNode }) {
  return (
    <div style={{ 
      display: "grid", 
      gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", 
      gap: "var(--spacing-6)",
      marginBottom: "var(--spacing-8)"
    }}>
      {children}
    </div>
  );
}

function HealthIndicator({ label, value, percent, status = "ok" }: { label: string, value: string, percent: number, status?: "ok" | "warn" | "error" }) {
  const color = status === "ok" ? "var(--color-success)" : status === "warn" ? "#f59e0b" : "var(--color-error)";
  return (
    <div style={{ 
      background: "var(--color-surface-hi)", 
      padding: "var(--spacing-5)", 
      borderRadius: "var(--radius-md)",
      border: "1px solid var(--color-outline-ghost)"
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "var(--spacing-3)" }}>
        <span style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--color-text-muted)", textTransform: "uppercase" }}>{label}</span>
        <span style={{ fontSize: "0.85rem", fontWeight: 800, color }}>{value}</span>
      </div>
      <div style={{ height: "6px", background: "var(--color-surface-vhi)", borderRadius: "3px", overflow: "hidden" }}>
        <div style={{ width: `${percent}%`, height: "100%", background: color, transition: "width 0.5s ease" }} />
      </div>
    </div>
  );
}

// --- Admin Dashboard ---

export function AdminDashboard() {
  const auth = useAuth();
  const token = useMemo(() => bearerForApi(auth.user), [auth.user]);
  const [golden, setGolden] = useState<GoldenSetStatus | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [error, setError] = useState("");
  const [isModalOpen, setIsModalOpen] = useState(false);

  useEffect(() => {
    if (!token) return;
    let active = true;
    Promise.all([fetchGoldenSetStatus(token), fetchManagerProjects(token)])
      .then(([g, p]) => {
        if (!active) return;
        setGolden(g);
        setProjects(p);
      })
      .catch((e: unknown) => {
        if (!active) return;
        setError(e instanceof Error ? e.message : "Erreur backend");
      });
    return () => {
      active = false;
    };
  }, [token]);

  const activeProjects = projects.filter((p) => p.status === "active").length;

  return (
    <div style={{ animation: "fade-in 0.4s ease" }}>
      <style>{`
        @keyframes fade-in { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
      `}</style>

      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: "var(--spacing-4)", flexWrap: "wrap", marginBottom: "var(--spacing-6)" }}>
        <p style={{ margin: 0, color: "var(--color-text-muted)", fontSize: "0.9rem" }}>
          Supervision globale de l'infrastructure et des projets ZachAI.
        </p>
        <button type="button" onClick={() => setIsModalOpen(true)} className="za-btn za-btn--primary">
          + Créer Manager
        </button>
      </header>

      {error ? <p style={{ color: "var(--color-error)", marginBottom: "var(--spacing-4)" }}>{error}</p> : null}

      <CreateManagerModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        token={token ?? ""}
        onSuccess={() => setError("")}
      />

      {/* Real activity — actual data from the API */}
      <SectionTitle>Activité globale</SectionTitle>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "var(--spacing-4)", marginBottom: "var(--spacing-8)" }}>
        <MetricTile label="Total projets" value={projects.length} />
        <MetricTile label="Projets actifs" value={activeProjects} tone="positive" />
        <MetricTile label="Golden set" value={golden ? `${golden.count}/${golden.threshold}` : "—"} />
        <MetricTile label="Heures transcrites" value="—" demo />
      </div>

      {/* Demo-only: infrastructure health is not wired to real metrics yet */}
      <SectionTitle badge>Santé système</SectionTitle>
      <p style={{ margin: "0 0 var(--spacing-4)", fontSize: "0.8rem", color: "var(--color-text-muted)" }}>
        Placeholders d'interface — pas encore branchés sur des métriques réelles (Prometheus).
      </p>
      <StatGrid>
        <HealthIndicator label="Charge CPU" value="42%" percent={42} />
        <HealthIndicator label="Mémoire RAM" value="6.2 / 16 GB" percent={38} />
        <HealthIndicator label="Stockage MinIO" value="1.2 / 2.0 TB" percent={60} status="warn" />
        <HealthIndicator label="PostgreSQL" value="Connecté" percent={100} />
      </StatGrid>

      <div style={{ height: "var(--spacing-8)" }} />

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "var(--spacing-6)" }}>
        <Card title="Derniers projets" subtitle="Flux de production">
          {projects.length === 0 ? (
            <EmptyState title="Aucun projet" description="Les projets créés par les managers apparaîtront ici." />
          ) : (
            <DataTable
              columns={["Nom", "Statut", "Nature", "Créé le"]}
              rows={projects.slice(0, 5).map((p) => [
                <span style={{ fontWeight: 700 }}>{p.name}</span>,
                <ProjectStatusPill status={p.status} />,
                p.nature_name,
                formatIso(p.created_at),
              ])}
            />
          )}
        </Card>

        <Card title="Alertes" subtitle="Flux d'alertes système">
          <div style={{ marginBottom: "var(--spacing-3)" }}><DemoBadge /></div>
          <div style={{ display: "grid", gap: "12px" }}>
            {[
              { id: 1, type: "error", msg: "Worker ASR timeout on proj_42", time: "il y a 2 min" },
              { id: 2, type: "warn", msg: "MinIO bucket 'snapshots' > 80%", time: "il y a 15 min" },
              { id: 3, type: "error", msg: "Auth failure: invalid JWT issuer", time: "il y a 1 h" },
            ].map((log) => (
              <div
                key={log.id}
                style={{
                  padding: "12px",
                  background: "var(--color-surface-low)",
                  borderRadius: "var(--radius-md)",
                  borderLeft: `4px solid ${log.type === "error" ? "var(--st-critical)" : "var(--st-transcribed)"}`,
                }}
              >
                <div style={{ fontSize: "0.8rem", fontWeight: 700, marginBottom: "4px" }}>{log.msg}</div>
                <div style={{ fontSize: "0.7rem", color: "var(--color-text-muted)" }}>{log.time}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

/** Section heading with an optional DÉMO badge. */
function SectionTitle({ children, badge = false }: { children: ReactNode; badge?: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-3)", marginBottom: "var(--spacing-4)" }}>
      <h3 style={{ margin: 0, fontFamily: "var(--font-headline)", fontSize: "1.2rem", fontWeight: 800, letterSpacing: "-0.02em" }}>
        {children}
      </h3>
      {badge ? <DemoBadge /> : null}
    </div>
  );
}

// --- Manager Dashboard ---

export function ManagerDashboard({ 
  onCreateProject, 
  onViewProject, 
  refreshKey = 0 
}: { 
  onCreateProject?: () => void; 
  onViewProject?: (id: number) => void;
  refreshKey?: number 
}) {
  const auth = useAuth();
  const token = useMemo(() => bearerForApi(auth.user), [auth.user]);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [golden, setGolden] = useState<GoldenSetStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [isInviteModalOpen, setIsInviteModalOpen] = useState(false);
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!token) return;
    let active = true;
    setLoading(true);
    Promise.all([fetchManagerProjects(token), fetchGoldenSetStatus(token)])
      .then(([p, g]) => {
        if (!active) return;
        setProjects(p);
        setGolden(g);
      })
      .catch((e: unknown) => {
        if (!active) return;
        setError(e instanceof Error ? e.message : "Erreur backend");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [token, refreshKey]);

  const totals = useMemo(() => {
    let assigned = 0, inProgress = 0, transcribed = 0, validated = 0;
    const safeProjects = projects || [];
    for (const p of safeProjects) {
      if (!p) continue;
      assigned += p.audio_counts_by_status?.assigned ?? 0;
      inProgress += p.audio_counts_by_status?.in_progress ?? 0;
      transcribed += p.audio_counts_by_status?.transcribed ?? 0;
      validated += p.audio_counts_by_status?.validated ?? 0;
    }
    return { assigned, inProgress, transcribed, validated };
  }, [projects]);

  const safeProjectsCount = (projects || []).length;

  const q = query.trim().toLowerCase();
  const visibleProjects = (projects || []).filter(
    (p) => p && (!q || p.name.toLowerCase().includes(q) || (p.nature_name || "").toLowerCase().includes(q)),
  );

  return (
    <div style={{ animation: "fade-in 0.4s ease" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: "var(--spacing-4)", flexWrap: "wrap", marginBottom: "var(--spacing-6)" }}>
        <p style={{ margin: 0, color: "var(--color-text-muted)", fontSize: "0.9rem" }}>
          Vue d'ensemble de vos projets de transcription.
        </p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-3)", alignItems: "center" }}>
          <SearchBox value={query} onChange={setQuery} placeholder="Rechercher un projet…" />
          <button type="button" onClick={() => setIsInviteModalOpen(true)} className="za-btn za-btn--ghost">
            + Inviter un membre
          </button>
          {onCreateProject ? (
            <button type="button" onClick={onCreateProject} className="za-btn za-btn--primary">
              + Nouveau Projet
            </button>
          ) : null}
        </div>
      </header>

      <InviteTeamMemberModal
        isOpen={isInviteModalOpen}
        onClose={() => setIsInviteModalOpen(false)}
        token={token ?? ""}
        onSuccess={() => {
          setError("");
        }}
      />

      {error ? <p style={{ color: "var(--color-error)", marginBottom: "var(--spacing-4)" }}>{error}</p> : null}
      {loading ? <DashboardInfo text="Mise à jour des données..." /> : null}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "var(--spacing-4)", marginBottom: "var(--spacing-8)" }}>
        <MetricTile label="Projets gérés" value={safeProjectsCount} />
        <MetricTile label="Audios en cours" value={totals.assigned + totals.inProgress} />
        <MetricTile label="Attente validation" value={totals.transcribed} tone={totals.transcribed > 0 ? "attention" : "default"} />
        <MetricTile label="Potentiel LoRA" value={golden ? `${Math.round((golden.count / golden.threshold) * 100)}%` : "—"} tone="positive" />
      </div>

      <Card title="Vos projets" subtitle="Pipeline de production en cours">
        {safeProjectsCount === 0 ? (
          <EmptyState
            icon={<span style={{ fontSize: "1.1rem" }}>＋</span>}
            title="Aucun projet"
            description="Commencez par créer un projet : nature, labels d'annotation, puis dépôt des audios."
            action={
              onCreateProject ? (
                <button type="button" onClick={onCreateProject} className="za-btn za-btn--primary">
                  + Nouveau projet
                </button>
              ) : undefined
            }
          />
        ) : visibleProjects.length === 0 ? (
          <EmptyState title="Aucun résultat" description={`Aucun projet ne correspond à « ${query} ».`} />
        ) : (
          <div style={{ display: "grid", gap: "var(--spacing-4)" }}>
            {visibleProjects.map((p) => {
              const counts = p.audio_counts_by_status;
              const total =
                (counts?.uploaded ?? 0) +
                (counts?.assigned ?? 0) +
                (counts?.in_progress ?? 0) +
                (counts?.transcribed ?? 0) +
                (counts?.validated ?? 0);
              const done = counts?.validated ?? 0;
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => onViewProject?.(p.id)}
                  style={{
                    textAlign: "left",
                    cursor: "pointer",
                    border: "1px solid var(--color-outline-ghost)",
                    background: "var(--color-surface-hi)",
                    borderRadius: "var(--radius-md)",
                    padding: "var(--spacing-4) var(--spacing-5)",
                    display: "grid",
                    gap: "var(--spacing-3)",
                    font: "inherit",
                    color: "inherit",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-3)" }}>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontWeight: 800, fontFamily: "var(--font-headline)", fontSize: "1rem", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {p.name}
                      </div>
                      <div style={{ fontSize: "0.78rem", color: "var(--color-text-muted)" }}>
                        {p.nature_name} · {done}/{total} validés
                      </div>
                    </div>
                    <ProjectStatusPill status={p.status} />
                    <span style={{ color: "var(--color-text-muted)", flex: "none" }} aria-hidden>›</span>
                  </div>
                  <PipelineBar
                    counts={{
                      uploaded: counts?.uploaded ?? 0,
                      assigned: counts?.assigned ?? 0,
                      in_progress: counts?.in_progress ?? 0,
                      transcribed: counts?.transcribed ?? 0,
                      validated: counts?.validated ?? 0,
                    }}
                  />
                </button>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}

/** Lifecycle pill for a project (active / completed / draft …). */
function ProjectStatusPill({ status }: { status: string }) {
  const s = (status || "").toLowerCase();
  const color =
    s === "completed" ? "var(--st-validated)" : s === "active" ? "var(--st-progress)" : "var(--color-text-muted)";
  const label = s === "completed" ? "Terminé" : s === "active" ? "Actif" : s === "draft" ? "Brouillon" : status;
  return (
    <span
      style={{
        flex: "none",
        fontSize: "0.7rem",
        fontWeight: 700,
        padding: "3px 10px",
        borderRadius: "100px",
        color,
        background: `color-mix(in srgb, ${color} 14%, transparent)`,
      }}
    >
      {label}
    </span>
  );
}

// --- Transcriber & Expert (Layout Upgrades) ---

function ConflictWidget({ data }: { data: { type: string, count: number, color: string }[] }) {
  return (
    <div style={{ display: "grid", gap: "12px" }}>
      {data.map((item) => (
        <div key={item.type}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", marginBottom: "4px", fontWeight: 600 }}>
            <span>{item.type}</span>
            <span>{item.count}</span>
          </div>
          <div style={{ height: "4px", background: "var(--color-surface-hi)", borderRadius: "2px" }}>
            <div style={{ width: `${(item.count / 20) * 100}%`, height: "100%", background: item.color, borderRadius: "2px" }} />
          </div>
        </div>
      ))}
    </div>
  );
}

/** Compact deterministic waveform glyph for a task row. */
function Waveform({ color, seed }: { color: string; seed: number }) {
  const bars = Array.from({ length: 14 }, (_, i) => {
    const h = 4 + Math.abs(Math.sin(seed * 0.7 + i * 1.3)) * 26;
    return { x: 2 + i * 6, h, y: (34 - h) / 2 };
  });
  return (
    <svg width="84" height="34" viewBox="0 0 84 34" style={{ flex: "none", opacity: 0.85 }} aria-hidden>
      <g fill={color}>
        {bars.map((b, i) => (
          <rect key={i} x={b.x} y={b.y} width="3" height={b.h} rx="1.5" />
        ))}
      </g>
    </svg>
  );
}

export function TranscriberDashboard({ onEditTask }: { onEditTask?: (audioId: number) => void }) {
  const auth = useAuth();
  const token = useMemo(() => bearerForApi(auth.user), [auth.user]);
  const { notify } = useNotifications();
  const [tasks, setTasks] = useState<AudioTask[]>([]);
  const [availableTasks, setAvailableTasks] = useState<AudioTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [helpFor, setHelpFor] = useState<AudioTask | null>(null);
  const [helpDraft, setHelpDraft] = useState("");
  const [query, setQuery] = useState("");

  const refreshTasks = async (t: string) => {
    setLoading(true);
    try {
      const [mine, available] = await Promise.all([
        fetchMyAudioTasks(t),
        fetchAvailableTasks(t)
      ]);
      setTasks(mine);
      setAvailableTasks(available);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors du chargement des tâches");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!token) return;
    refreshTasks(token);
  }, [token]);

  const handleClaim = async (audioId: number) => {
    if (!token) return;
    try {
      await claimTask(audioId, token);
      await refreshTasks(token);
      notify({ tier: "informational", title: "Tâche récupérée", body: "Elle est maintenant dans vos assignations." });
    } catch (e) {
      notify({ tier: "critical", title: "Récupération impossible", body: e instanceof Error ? e.message : "Erreur inconnue" });
    }
  };

  // Cancelling help needs no message; requesting it opens the modal below.
  const cancelHelp = async (audioId: number) => {
    if (!token) return;
    try {
      await toggleHelp(audioId, false, null, token);
      await refreshTasks(token);
    } catch (e) {
      notify({ tier: "critical", title: "Action impossible", body: e instanceof Error ? e.message : "Erreur inconnue" });
    }
  };

  const submitHelp = async () => {
    if (!token || !helpFor) return;
    const audioId = helpFor.audio_id;
    setHelpFor(null);
    try {
      await toggleHelp(audioId, true, helpDraft.trim() || null, token);
      setHelpDraft("");
      await refreshTasks(token);
      notify({ tier: "informational", title: "Entraide demandée", body: "Vos collègues du périmètre sont notifiés." });
    } catch (e) {
      notify({ tier: "critical", title: "Demande impossible", body: e instanceof Error ? e.message : "Erreur inconnue" });
    }
  };

  const transcribed = tasks.filter((t) => t.status === "transcribed").length;
  const toDo = tasks.length - transcribed;

  // Search across both lists by filename or project name.
  const q = query.trim().toLowerCase();
  const matches = (t: AudioTask) =>
    !q || t.filename.toLowerCase().includes(q) || t.project_name.toLowerCase().includes(q);
  const filteredTasks = tasks.filter(matches);
  const filteredAvailable = availableTasks.filter(matches);

  // Group assignments by project so a transcriber working across several
  // projects can navigate them instead of scanning one flat list.
  const groupedTasks = Array.from(
    filteredTasks
      .reduce((map, t) => {
        const g = map.get(t.project_id) ?? { name: t.project_name, items: [] as AudioTask[] };
        g.items.push(t);
        map.set(t.project_id, g);
        return map;
      }, new Map<number, { name: string; items: AudioTask[] }>())
      .values(),
  );

  const renderTaskRow = (t: AudioTask, first: boolean) => {
    const status = normaliseStatus(t.status);
    return (
      <div
        key={t.audio_id}
        style={{
          display: "flex",
          alignItems: "center",
          gap: "14px",
          padding: "13px 4px",
          borderTop: first ? "none" : "1px solid var(--color-outline-ghost)",
        }}
      >
        <Waveform color={statusColor(status)} seed={t.audio_id} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: "0.9rem", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {t.filename}
          </div>
          {t.help_requested && (
            <div style={{ fontSize: "0.7rem", color: "var(--st-transcribed)", fontWeight: 700, marginTop: "2px" }}>
              ⚑ Entraide demandée{t.help_message ? ` : ${t.help_message}` : ""}
            </div>
          )}
        </div>
        <div style={{ display: "flex", gap: "8px", alignItems: "center", flex: "none" }}>
          <StatusChip status={status} />
          <button
            onClick={() => onEditTask?.(t.audio_id)}
            className="za-btn za-btn--primary"
            style={{ padding: "6px 12px", fontSize: "0.78rem" }}
          >
            {status === "assigned" ? "Commencer →" : status === "transcribed" ? "Revoir →" : "Reprendre →"}
          </button>
          <button
            onClick={() => (t.help_requested ? cancelHelp(t.audio_id) : (setHelpFor(t), setHelpDraft("")))}
            className="za-btn za-btn--ghost"
            style={{
              padding: "6px 10px",
              fontSize: "0.78rem",
              color: t.help_requested ? "var(--st-transcribed)" : "var(--color-text-muted)",
            }}
            title={t.help_requested ? "Annuler la demande d'aide" : "Demander de l'aide à un collègue"}
          >
            {t.help_requested ? "Aide ✓" : "Aide"}
          </button>
        </div>
      </div>
    );
  };

  return (
    <div style={{ animation: "fade-in 0.4s ease" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: "var(--spacing-4)", flexWrap: "wrap", marginBottom: "var(--spacing-6)" }}>
        <p style={{ margin: 0, color: "var(--color-text-muted)", fontSize: "0.9rem" }}>
          Transcription &amp; correction en cours.
        </p>
        <SearchBox value={query} onChange={setQuery} placeholder="Rechercher un audio ou un projet…" />
      </header>

      {error ? <p style={{ color: "var(--color-error)", marginBottom: "var(--spacing-4)" }}>{error}</p> : null}
      {loading ? <DashboardInfo text="Mise à jour des flux..." /> : null}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "var(--spacing-4)", marginBottom: "var(--spacing-8)" }}>
        <MetricTile label="Assignées" value={tasks.length} />
        <MetricTile label="Libre service" value={availableTasks.length} tone={availableTasks.length > 0 ? "positive" : "default"} />
        <MetricTile label="À traiter" value={toDo} tone={toDo > 5 ? "attention" : "default"} />
        <MetricTile label="Productivité" value="—" demo />
      </div>

      <div style={{ display: "grid", gap: "var(--spacing-8)" }}>
        <Card title="Mes assignations" subtitle={`Tâches directement confiées · ${tasks.length}`}>
          {tasks.length === 0 ? (
            <EmptyState
              title="Aucune tâche assignée"
              description="Dès qu'un manager vous confie un audio, il apparaît ici prêt à être repris."
            />
          ) : filteredTasks.length === 0 ? (
            <EmptyState
              title="Aucun résultat"
              description={`Rien ne correspond à « ${query} ». Essayez un autre terme.`}
            />
          ) : (
            <div style={{ display: "grid", gap: "var(--spacing-5)" }}>
              {groupedTasks.map((group) => (
                <div key={group.name}>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                      padding: "0 4px 8px",
                      fontFamily: "var(--font-headline)",
                      fontWeight: 800,
                      fontSize: "0.82rem",
                      color: "var(--color-text-muted)",
                      textTransform: "uppercase",
                      letterSpacing: "0.04em",
                    }}
                  >
                    <span style={{ width: "8px", height: "8px", borderRadius: "2px", background: "var(--color-primary)", flex: "none" }} />
                    {group.name}
                    <span style={{ color: "var(--color-text-muted)", fontWeight: 700 }}>· {group.items.length}</span>
                  </div>
                  {group.items.map((t, i) => renderTaskRow(t, i === 0))}
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Libre service (périmètre)" subtitle="Audios prêts que vous pouvez récupérer">
          {availableTasks.length === 0 ? (
            <EmptyState
              title="Rien à récupérer pour l'instant"
              description="Les audios apparaissent ici une fois normalisés (traitement FFmpeg) et tant qu'ils ne sont pas encore assignés."
            />
          ) : filteredAvailable.length === 0 ? (
            <EmptyState
              title="Aucun résultat"
              description={`Rien ne correspond à « ${query} ». Essayez un autre terme.`}
            />
          ) : (
            <div style={{ display: "grid" }}>
              {filteredAvailable.map((t, i) => (
                <div
                  key={t.audio_id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "14px",
                    padding: "13px 4px",
                    borderTop: i === 0 ? "none" : "1px solid var(--color-outline-ghost)",
                  }}
                >
                  <Waveform color="var(--st-progress)" seed={t.audio_id} />
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontWeight: 700, fontSize: "0.9rem", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {t.filename}
                    </div>
                    <div style={{ fontSize: "0.76rem", color: "var(--color-text-muted)" }}>
                      {t.project_name} · prêt {formatIso(t.assigned_at || (t as any).uploaded_at)}
                    </div>
                  </div>
                  <button
                    onClick={() => handleClaim(t.audio_id)}
                    className="za-btn za-btn--primary"
                    style={{ padding: "6px 12px", fontSize: "0.78rem", flex: "none" }}
                  >
                    Récupérer
                  </button>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {helpFor && (
        <div
          role="dialog"
          aria-modal="true"
          onClick={() => setHelpFor(null)}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(5,7,12,0.55)",
            display: "grid",
            placeItems: "center",
            padding: "24px",
            zIndex: 50,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: "100%",
              maxWidth: "420px",
              background: "var(--color-surface-hi)",
              border: "1px solid var(--color-outline)",
              borderRadius: "var(--radius-md)",
              padding: "20px",
              display: "grid",
              gap: "12px",
            }}
          >
            <div>
              <div style={{ fontFamily: "var(--font-headline)", fontWeight: 800, fontSize: "1rem" }}>Demander de l'aide</div>
              <div style={{ fontSize: "0.8rem", color: "var(--color-text-muted)", marginTop: "2px" }}>
                {helpFor.filename}
              </div>
            </div>
            <textarea
              className="za-textarea"
              autoFocus
              value={helpDraft}
              onChange={(e) => setHelpDraft(e.target.value)}
              placeholder="Décrivez brièvement votre besoin (optionnel)…"
              style={{ maxWidth: "none" }}
            />
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px" }}>
              <button className="za-btn za-btn--ghost" onClick={() => setHelpFor(null)}>Annuler</button>
              <button className="za-btn za-btn--primary" onClick={submitHelp}>Envoyer la demande</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function ExpertDashboard({ onReconcile }: { onReconcile?: (audioId: number) => void }) {
  const auth = useAuth();
  const token = useMemo(() => bearerForApi(auth.user), [auth.user]);
  const [tasks, setTasks] = useState<ExpertTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    let active = true;
    setLoading(true);
    fetchExpertTasks(token).then(rows => {
      if (active) setTasks(rows);
    }).catch(e => active && setError(e instanceof Error ? e.message : "Erreur backend")).finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [token]);

  const labelStudioTasks = tasks.filter((t) => t.source === "label_studio").length;
  const internalTasks = tasks.length - labelStudioTasks;
  const validated = tasks.filter((t) => t.status === "validated").length;
  const pending = tasks.filter((t) => t.status === "transcribed").length;
  const viewState = resolveExpertDashboardViewState({ loading, error, tasksCount: tasks.length });

  return (
    <div style={{ animation: "fade-in 0.4s ease" }}>
      <header style={{ marginBottom: "var(--spacing-6)" }}>
        <p style={{ margin: 0, color: "var(--color-text-muted)", fontSize: "0.9rem" }}>
          Réconciliation des segments et validation de la qualité finale.
        </p>
        <p style={{ margin: "var(--spacing-2) 0 0 0", color: "var(--color-text-muted)", fontSize: "0.8rem" }}>
          Deux surfaces de travail : <strong>réconciliation interne</strong> (comparaison machine / humain) et
          <strong> Label Studio</strong> (annotation fine). Connectez-vous à Label Studio avec vos identifiants experts.
        </p>
      </header>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "var(--spacing-4)", marginBottom: "var(--spacing-8)" }}>
        <MetricTile label="À réconcilier" value={pending} tone={pending > 0 ? "attention" : "default"} />
        <MetricTile label="Validés" value={validated} tone="positive" />
        <MetricTile label="Tâches Label Studio" value={labelStudioTasks} />
        <MetricTile label="Qualité moyenne" value="—" demo />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "2.5fr 1fr", gap: "var(--spacing-6)" }}>
        <Card title="File de réconciliation" subtitle={`Segments en attente de décision · ${internalTasks} interne · ${labelStudioTasks} Label Studio`}>
          {viewState === "loading" ? (
            <DashboardInfo text="Chargement du dashboard expert…" />
          ) : viewState === "error" ? (
            <p style={{ color: "var(--color-error)", margin: 0 }}>{error}</p>
          ) : viewState === "empty" ? (
            <EmptyState
              title="Rien à réconcilier"
              description="Les segments transcrits en attente d'arbitrage apparaîtront ici, avec leur source."
            />
          ) : (
            <DataTable
              columns={["Audio", "Projet", "Statut", "Source", "Action"]}
              rows={tasks.slice(0, 12).map((t) => [
                <div style={{ fontWeight: 700 }}>{t.filename}</div>,
                t.project_name,
                <StatusChip status={t.status} />,
                <SourcePill source={t.source} />,
                <div style={{ display: "flex", gap: "var(--spacing-2)" }}>
                  {onReconcile && (
                    <button
                      type="button"
                      onClick={() => onReconcile(t.audio_id)}
                      className="za-btn za-btn--primary"
                      style={{ padding: "5px 11px", fontSize: "0.75rem" }}
                    >
                      Réconcilier →
                    </button>
                  )}
                  {t.source === "label_studio" && t.label_studio_url && t.label_studio_project_id && (
                    <a
                      href={`${t.label_studio_url}/projects/${t.label_studio_project_id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="za-btn za-btn--ghost"
                      style={{ padding: "5px 11px", fontSize: "0.75rem", textDecoration: "none", display: "inline-flex", alignItems: "center" }}
                      title="Ouvrir dans Label Studio"
                    >
                      Label Studio →
                    </a>
                  )}
                </div>,
              ])}
            />
          )}
        </Card>

        <Card title="Typologie des conflits" subtitle="Erreurs récurrentes">
          <div style={{ marginBottom: "var(--spacing-3)" }}><DemoBadge /></div>
          <ConflictWidget data={[
            { type: "Terminologie", count: 14, color: "var(--st-progress)" },
            { type: "Ponctuation", count: 8, color: "var(--st-assigned)" },
            { type: "Identification orateur", count: 5, color: "var(--st-validated)" },
            { type: "Bruit de fond", count: 3, color: "var(--st-critical)" },
          ]} />
        </Card>
      </div>
    </div>
  );
}

/** Badge distinguishing an internal reconciliation task from a Label Studio one. */
function SourcePill({ source }: { source: string }) {
  const isLs = source === "label_studio";
  const color = isLs ? "var(--st-transcribed)" : "var(--st-progress)";
  return (
    <span
      style={{
        fontSize: "0.68rem",
        fontWeight: 700,
        padding: "3px 9px",
        borderRadius: "100px",
        color,
        background: `color-mix(in srgb, ${color} 14%, transparent)`,
        whiteSpace: "nowrap",
      }}
    >
      {isLs ? "Label Studio" : "Interne"}
    </span>
  );
}
