import { useEffect, useState, useMemo } from "react";
import { useAuth } from "react-oidc-context";
import { bearerForApi } from "../../auth/api-client";
import { fetchProjectStatus, type AudioRow } from "../dashboard/dashboardApi";
import { Card, DataTable, Metric } from "../../shared/ui/Primitives";
import { formatIso } from "../../shared/utils/dateUtils";

type ProjectDetailProps = {
  projectId: number;
  onBack: () => void;
};

export function ProjectDetailManager({ projectId, onBack }: ProjectDetailProps) {
  const auth = useAuth();
  const token = useMemo(() => bearerForApi(auth.user), [auth.user]);
  const [projectStatus, setProjectStatus] = useState<string>("");
  const [audios, setAudios] = useState<AudioRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortField, setSortField] = useState<"filename" | "uploaded_at">("uploaded_at");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");

  useEffect(() => {
    if (auth.isLoading || !token || !projectId) return;
    let active = true;
    setError("");
    setLoading(true);
    fetchProjectStatus(projectId, token)
      .then((res) => {
        if (!active) return;
        setProjectStatus(res.project_status);
        setAudios(res.audios);
      })
      .catch((e: unknown) => {
        if (!active) return;
        setError(e instanceof Error ? e.message : "Erreur lors de la récupération du projet");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [auth.isLoading, token, projectId]);

  const filteredAndSortedAudios = useMemo(() => {
    let result = audios;
    if (statusFilter !== "all") {
      result = result.filter((a) => a.status === statusFilter);
    }
    
    return [...result].sort((a, b) => {
      const valA = a[sortField] || "";
      const valB = b[sortField] || "";
      if (valA < valB) return sortDirection === "asc" ? -1 : 1;
      if (valA > valB) return sortDirection === "asc" ? 1 : -1;
      return 0;
    });
  }, [audios, statusFilter, sortField, sortDirection]);

  const toggleSort = (field: "filename" | "uploaded_at") => {
    if (sortField === field) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortDirection("asc");
    }
  };

  if (auth.isLoading) {
    return <p style={{ color: "var(--color-text-muted)" }}>Chargement du projet...</p>;
  }
  if (!token) {
    return (
      <p style={{ color: "var(--color-error)" }}>
        Session indisponible. Veuillez vous reconnecter.
      </p>
    );
  }

  if (loading) return <p style={{ color: "var(--color-text-muted)" }}>Chargement du projet...</p>;
  if (error) return <p style={{ color: "var(--color-error)" }}>{error}</p>;

  return (
    <div style={{ display: "grid", gap: "var(--spacing-4)" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-3)" }}>
          <button type="button" className="za-btn za-btn--ghost" onClick={onBack}>
            &larr; Retour
          </button>
          <h2 style={{ margin: 0, fontFamily: "var(--font-headline)" }}>Détail Projet #{projectId}</h2>
        </div>
        <div style={{ display: "flex", gap: "var(--spacing-3)", alignItems: "center" }}>
          <div style={{ display: "flex", gap: "var(--spacing-2)", alignItems: "center" }}>
            <label htmlFor="sort-field" style={{ fontSize: "0.9rem", color: "var(--color-text-muted)" }}>Trier par:</label>
            <select 
              id="sort-field"
              value={sortField} 
              onChange={(e) => toggleSort(e.target.value as "filename" | "uploaded_at")}
              style={{ 
                padding: "var(--spacing-1) var(--spacing-2)", 
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--color-outline)",
                background: "var(--color-surface)",
                color: "var(--color-text)"
              }}
            >
              <option value="filename">Nom de fichier</option>
              <option value="uploaded_at">Date d'upload</option>
            </select>
            <button 
              type="button" 
              className="za-btn za-btn--ghost" 
              style={{ padding: "var(--spacing-1) var(--spacing-2)" }}
              onClick={() => setSortDirection(sortDirection === "asc" ? "desc" : "asc")}
            >
              {sortDirection === "asc" ? "↑" : "↓"}
            </button>
          </div>
          <div style={{ display: "flex", gap: "var(--spacing-2)", alignItems: "center" }}>
            <label htmlFor="status-filter" style={{ fontSize: "0.9rem", color: "var(--color-text-muted)" }}>Filtrer par statut:</label>
            <select 
              id="status-filter"
              value={statusFilter} 
              onChange={(e) => setStatusFilter(e.target.value)}
              style={{ 
                padding: "var(--spacing-1) var(--spacing-2)", 
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--color-outline)",
                background: "var(--color-surface)",
                color: "var(--color-text)"
              }}
            >
              <option value="all">Tous</option>
              <option value="uploaded">Uploadé</option>
              <option value="assigned">Assigné</option>
              <option value="in_progress">En cours</option>
              <option value="transcribed">Transcrit</option>
              <option value="validated">Validé</option>
            </select>
          </div>
        </div>
      </header>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: "var(--spacing-4)" }}>
        <Metric label="Statut Projet" value={projectStatus || "--"} tone={projectStatus === "active" ? "success" : "default"} />
        <Metric label="Total Audios" value={String(audios.length)} />
        <Metric label="Filtre actif" value={String(filteredAndSortedAudios.length)} tone={statusFilter !== "all" ? "success" : "default"} />
      </div>

      <Card title="Liste des fichiers audio" subtitle={`Affichage de ${filteredAndSortedAudios.length} fichier(s)`}>
        {audios.length === 0 ? (
          <p style={{ color: "var(--color-text-muted)", margin: 0 }}>Aucun fichier audio n'a été ajouté à ce projet.</p>
        ) : (
          <DataTable
            columns={["Fichier", "Statut", "Assigné à", "Uploadé le"]}
            rows={filteredAndSortedAudios.map((a) => [
              a.filename,
              a.status,
              a.assigned_to || "--",
              formatIso(a.uploaded_at)
            ])}
          />
        )}
      </Card>
    </div>
  );
}
