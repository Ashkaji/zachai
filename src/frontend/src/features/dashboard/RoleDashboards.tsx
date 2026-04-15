import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useAuth } from "react-oidc-context";
import { bearerForApi } from "../../auth/api-client";
import { Card, DataTable, Metric } from "../../shared/ui/Primitives";
import { formatIso } from "../../shared/utils/dateUtils";
import {
  fetchExpertTasks,
  fetchGoldenSetStatus,
  fetchManagerProjects,
  fetchMyAudioTasks,
  type AudioTask,
  type ExpertTask,
  type GoldenSetStatus,
  type ProjectSummary,
} from "./dashboardApi";
import { CreateManagerModal } from "./CreateManagerModal";

function DashboardInfo({ text }: { text: string }) {
  return <p style={{ margin: 0, color: "var(--color-text-muted)", fontSize: "0.9rem" }}>{text}</p>;
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
}): ReactNode {
  const { viewState, error, tasks } = input;
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
      columns={["Audio", "Projet", "Statut", "Source", "Assigne le"]}
      rows={tasks.slice(0, 12).map((t) => [
        t.filename,
        t.project_name,
        t.status,
        t.source,
        t.assigned_at ? formatIso(t.assigned_at) : "--",
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
      
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: "var(--spacing-6)" }}>
        <div>
          <p style={{ margin: 0, color: "var(--color-text-muted)", fontSize: "0.95rem" }}>
            Supervision globale de l'infrastructure et des projets ZachAI.
          </p>
        </div>
        <button onClick={() => setIsModalOpen(true)} className="za-btn za-btn--primary">
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

      <h3 style={{ fontFamily: "var(--font-headline)", fontSize: "1.25rem", fontWeight: 800, marginBottom: "var(--spacing-4)" }}>Santé Système</h3>
      <StatGrid>
        <HealthIndicator label="Charge CPU" value="42%" percent={42} />
        <HealthIndicator label="Mémoire RAM" value="6.2 / 16 GB" percent={38} />
        <HealthIndicator label="Stockage MinIO" value="1.2 / 2.0 TB" percent={60} status="warn" />
        <HealthIndicator label="PostgreSQL" value="Connecté" percent={100} />
      </StatGrid>

      <h3 style={{ fontFamily: "var(--font-headline)", fontSize: "1.25rem", fontWeight: 800, marginBottom: "var(--spacing-4)" }}>Activité Globale</h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "var(--spacing-4)", marginBottom: "var(--spacing-8)" }}>
        <Metric label="Total Projets" value={String(projects.length)} />
        <Metric label="Projets Actifs" value={String(activeProjects)} tone="success" />
        <Metric label="Heures Transcrites" value="428h" />
        <Metric label="Golden Set" value={golden ? `${golden.count}/${golden.threshold}` : "--"} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "var(--spacing-6)" }}>
        <Card title="Derniers Projets" subtitle="Surveillance des flux de production">
          <DataTable
            columns={["Nom", "Statut", "Nature", "Créé le"]}
            rows={projects.slice(0, 5).map((p) => [
              <span style={{ fontWeight: 700 }}>{p.name}</span>,
              <span style={{ 
                padding: "4px 8px", 
                borderRadius: "4px", 
                fontSize: "0.75rem", 
                fontWeight: 700,
                background: p.status === "active" ? "var(--color-primary-soft)" : "var(--color-surface-vhi)",
                color: p.status === "active" ? "var(--color-primary)" : "var(--color-text-muted)"
              }}>{p.status.toUpperCase()}</span>,
              p.nature_name,
              formatIso(p.created_at)
            ])}
          />
        </Card>

        <Card title="Logs Critiques" subtitle="Alertes temps-réel">
          <div style={{ display: "grid", gap: "12px" }}>
            {[
              { id: 1, type: "error", msg: "Worker ASR timeout on proj_42", time: "2m ago" },
              { id: 2, type: "warn", msg: "MinIO bucket 'snapshots' > 80%", time: "15m ago" },
              { id: 3, type: "error", msg: "Auth failure: invalid JWT issuer", time: "1h ago" },
            ].map(log => (
              <div key={log.id} style={{ 
                padding: "12px", 
                background: "var(--color-surface-low)", 
                borderRadius: "var(--radius-md)",
                borderLeft: `4px solid ${log.type === 'error' ? 'var(--color-error)' : '#f59e0b'}`
              }}>
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
    for (const p of projects) {
      assigned += p.audio_counts_by_status?.assigned ?? 0;
      inProgress += p.audio_counts_by_status?.in_progress ?? 0;
      transcribed += p.audio_counts_by_status?.transcribed ?? 0;
      validated += p.audio_counts_by_status?.validated ?? 0;
    }
    return { assigned, inProgress, transcribed, validated };
  }, [projects]);

  return (
    <div style={{ animation: "fade-in 0.4s ease" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: "var(--spacing-6)" }}>
        <div>
          <p style={{ margin: 0, color: "var(--color-text-muted)", fontSize: "0.95rem" }}>
            Vue d'ensemble de vos projets de transcription.
          </p>
        </div>
        {onCreateProject && (
          <button onClick={onCreateProject} className="za-btn za-btn--primary">
            + Nouveau Projet
          </button>
        )}
      </header>

      {error ? <p style={{ color: "var(--color-error)", marginBottom: "var(--spacing-4)" }}>{error}</p> : null}
      {loading ? <DashboardInfo text="Mise à jour des données..." /> : null}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "var(--spacing-5)", marginBottom: "var(--spacing-8)" }}>
        <Metric label="Projets gérés" value={String(projects.length)} />
        <Metric label="Audios en cours" value={String(totals.assigned + totals.inProgress)} />
        <Metric label="Attente Validation" value={String(totals.transcribed)} tone={totals.transcribed > 0 ? "error" : "default"} />
        <Metric label="Potentiel LoRA" value={golden ? `${Math.round((golden.count/golden.threshold)*100)}%` : "--"} tone="success" />
      </div>

      <Card title="Vos Projets" subtitle="Pipeline de production en cours">
        {projects.length === 0 ? (
          <DashboardInfo text="Aucun projet actif. Commencez par en créer un." />
        ) : (
          <DataTable
            columns={["Nom du Projet", "Nature", "Progression", "Statut", "Actions"]}
            rows={projects.map((p) => {
              const total = (p.audio_counts_by_status?.uploaded ?? 0) + (p.audio_counts_by_status?.assigned ?? 0) + (p.audio_counts_by_status?.in_progress ?? 0) + (p.audio_counts_by_status?.transcribed ?? 0) + (p.audio_counts_by_status?.validated ?? 0);
              const done = p.audio_counts_by_status?.validated ?? 0;
              const prog = total > 0 ? Math.round((done / total) * 100) : 0;
              
              return [
                <div style={{ fontWeight: 700 }}>{p.name}</div>,
                <div style={{ fontSize: "0.85rem", opacity: 0.8 }}>{p.nature_name}</div>,
                <div style={{ width: "120px" }}>
                  <div style={{ fontSize: "0.75rem", marginBottom: "4px", fontWeight: 600 }}>{prog}% ({done}/{total})</div>
                  <div style={{ height: "4px", background: "var(--color-surface-hi)", borderRadius: "2px", overflow: "hidden" }}>
                    <div style={{ width: `${prog}%`, height: "100%", background: "var(--color-primary)" }} />
                  </div>
                </div>,
                <span style={{ 
                  padding: "4px 8px", 
                  borderRadius: "4px", 
                  fontSize: "0.7rem", 
                  fontWeight: 800,
                  background: p.status === "completed" ? "var(--color-primary-soft)" : "var(--color-surface-hi)",
                  color: p.status === "completed" ? "var(--color-primary)" : "var(--color-text-muted)"
                }}>{p.status.toUpperCase()}</span>,
                onViewProject ? (
                  <button 
                    type="button" 
                    className="za-btn za-btn--ghost" 
                    style={{ padding: "6px 12px", fontSize: "0.8rem", border: "none", background: "var(--color-surface-hi)" }}
                    onClick={() => onViewProject(p.id)}
                  >
                    Détails →
                  </button>
                ) : "--"
              ];
            })}
          />
        )}
      </Card>
    </div>
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

export function TranscriberDashboard() {
  const auth = useAuth();
  const token = useMemo(() => bearerForApi(auth.user), [auth.user]);
  const [tasks, setTasks] = useState<AudioTask[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    let active = true;
    fetchMyAudioTasks(token).then((rows) => {
      if (active) setTasks(rows);
    }).catch(e => active && setError(e instanceof Error ? e.message : "Erreur backend"));
    return () => { active = false; };
  }, [token]);

  const transcribed = tasks.filter((t) => t.status === "transcribed").length;

  return (
    <div style={{ animation: "fade-in 0.4s ease" }}>
      <header style={{ marginBottom: "var(--spacing-6)" }}>
        <p style={{ margin: 0, color: "var(--color-text-muted)", fontSize: "0.95rem" }}>
          Vos tâches de transcription et de correction en cours.
        </p>
      </header>

      {error ? <p style={{ color: "var(--color-error)", marginBottom: "var(--spacing-4)" }}>{error}</p> : null}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "var(--spacing-4)", marginBottom: "var(--spacing-8)" }}>
        <Metric label="Assignés" value={String(tasks.length)} />
        <Metric label="Soumis" value={String(transcribed)} tone="success" />
        <Metric label="À Traiter" value={String(tasks.length - transcribed)} tone={tasks.length - transcribed > 5 ? "error" : "default"} />
        <Metric label="Productivité" value="1.2h/j" />
      </div>

      <Card title="File de Travail" subtitle="Priorité aux tâches les plus anciennes">
        {tasks.length === 0 ? (
          <DashboardInfo text="Aucune tâche assignée. Prenez une pause !" />
        ) : (
          <DataTable
            columns={["Fichier Audio", "Projet", "Statut", "Reçu le", "Action"]}
            rows={tasks.map(t => [
              <div style={{ fontWeight: 700 }}>{t.filename}</div>,
              <div style={{ fontSize: "0.85rem", opacity: 0.8 }}>{t.project_name}</div>,
              <span style={{ 
                padding: "2px 6px", 
                borderRadius: "4px", 
                fontSize: "0.7rem", 
                fontWeight: 800,
                background: t.status === "in_progress" ? "var(--color-primary-soft)" : "var(--color-surface-hi)",
                color: t.status === "in_progress" ? "var(--color-primary)" : "var(--color-text-muted)"
              }}>{t.status.toUpperCase()}</span>,
              formatIso(t.assigned_at),
              <button className="za-btn za-btn--ghost" style={{ padding: "4px 8px", fontSize: "0.75rem", border: "none", background: "var(--color-surface-hi)" }}>
                Éditer →
              </button>
            ])}
          />
        )}
      </Card>
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
  const viewState = resolveExpertDashboardViewState({ loading, error, tasksCount: tasks.length });

  return (
    <div style={{ animation: "fade-in 0.4s ease" }}>
      <header style={{ marginBottom: "var(--spacing-6)" }}>
        <p style={{ margin: 0, color: "var(--color-text-muted)", fontSize: "0.95rem" }}>
          Réconciliation des segments et validation de la qualité finale.
        </p>
      </header>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "var(--spacing-4)", marginBottom: "var(--spacing-8)" }}>
        <Metric label="Tâches LS" value={String(labelStudioTasks)} />
        <Metric label="Validés" value={String(tasks.filter(t => t.status === 'validated').length)} tone="success" />
        <Metric label="Conflits" value={String(tasks.filter(t => t.status === 'transcribed').length)} tone="error" />
        <Metric label="Qualité Moy." value="98.2%" />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "2.5fr 1fr", gap: "var(--spacing-6)" }}>
        <Card title="Réconciliation Experte" subtitle="Segments en attente de décision">
          {viewState === "loading" ? (
            <DashboardInfo text="Chargement dashboard expert..." />
          ) : viewState === "error" ? (
            <p style={{ color: "var(--color-error)", margin: 0 }}>{error}</p>
          ) : viewState === "empty" ? (
            <DashboardInfo text="Aucune tache experte pour le moment." />
          ) : (
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
                onReconcile ? (
                  <button 
                    onClick={() => onReconcile(t.audio_id)}
                    className="za-btn za-btn--ghost" 
                    style={{ padding: "4px 8px", fontSize: "0.75rem", border: "none", background: "var(--color-surface-hi)" }}
                  >
                    Réconcilier →
                  </button>
                ) : "--"
              ])}
            />
          )}
        </Card>

        <Card title="Typologie Conflits" subtitle="Analyse des erreurs récurrentes">
          <ConflictWidget data={[
            { type: "Terminologie", count: 14, color: "var(--color-primary)" },
            { type: "Ponctuation", count: 8, color: "var(--color-secondary)" },
            { type: "Identification Orateur", count: 5, color: "var(--color-success)" },
            { type: "Bruit de fond", count: 3, color: "var(--color-error)" },
          ]} />
        </Card>
      </div>
    </div>
  );
}
