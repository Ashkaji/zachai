import { useEffect, useState, useMemo, useCallback } from "react";
import { useAuth } from "react-oidc-context";
import { bearerForApi } from "../../auth/api-client";
import { fetchProjectStatus, fetchProjectDetail, type AudioRow, type ProjectDetail, assignAudio, validateAudio, fetchProjectAuditTrail, type AuditLogEntry } from "../dashboard/dashboardApi";
import { Card, DataTable, Metric, Badge } from "../../shared/ui/Primitives";
import { GlassModal } from "../../shared/ui/Modals";
import { formatIso, formatDuration } from "../../shared/utils/dateUtils";
import { useBatchAction } from "../../shared/hooks/useBatchAction";

type ProjectDetailProps = {
  projectId: number;
  onBack: () => void;
};

type ModalType = "none" | "assign" | "reject" | "report" | "settings" | "audit";

export function ProjectDetailManager({ projectId, onBack }: ProjectDetailProps) {
  const auth = useAuth();
  const token = useMemo(() => bearerForApi(auth.user), [auth.user]);
  const [projectStatus, setProjectStatus] = useState<string>("");
  const [projectDetail, setProjectDetail] = useState<ProjectDetail | null>(null);
  const [audios, setAudios] = useState<AudioRow[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [auditLoading, setAuditLoading] = useState(false);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortField, setSortField] = useState<"filename" | "uploaded_at">("uploaded_at");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");

  // Bulk Selection State
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [activeModal, setActiveModal] = useState<ModalType>("none");
  const [transcripteurId, setTranscripteurId] = useState("");
  const [rejectComment, setRejectComment] = useState("");
  const [rejectMotif, setRejectMotif] = useState("");
  const [pendingActionId, setPendingActionId] = useState<number | null>(null);

  const REJECTION_MOTIFS = [
    "Qualité audio insuffisante",
    "Erreurs de transcription majeures",
    "Formatage / Ponctuation incorrecte",
    "Citations bibliques manquantes",
    "Autre (préciser...)"
  ];

  const refreshData = useCallback(() => {
    if (!token || !projectId) return;
    Promise.all([
      fetchProjectStatus(projectId, token),
      fetchProjectDetail(projectId, token)
    ])
      .then(([statusRes, detailRes]) => {
        setProjectStatus(statusRes.project_status);
        setAudios(statusRes.audios);
        setProjectDetail(detailRes);
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : "Erreur lors de la récupération du projet");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [projectId, token]);

  useEffect(() => {
    if (auth.isLoading || !token || !projectId) return;
    setLoading(true);
    refreshData();
  }, [auth.isLoading, token, projectId, refreshData]);

  // Reset selection on filter/sort change
  useEffect(() => {
    setSelectedIds(new Set());
  }, [statusFilter, sortField, sortDirection]);

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

  // Analytics Calculations
  const analytics = useMemo(() => {
    if (audios.length === 0) return { progress: 0, duration: 0, avgConfidence: 0 };
    const validatedCount = audios.filter(a => a.status === "validated").length;
    const totalDuration = audios.reduce((acc, a) => acc + (a.duration_s || 0), 0);
    return {
      progress: (validatedCount / audios.length) * 100,
      duration: totalDuration,
      avgConfidence: 0 
    };
  }, [audios]);

  // Batch Actions
  const assignBatch = useBatchAction<number>(async (id) => {
    if (!token) return;
    await assignAudio(projectId, id, transcripteurId, token);
  });

  const validateBatch = useBatchAction<number>(async (id) => {
    if (!token) return;
    await validateAudio(id, true, null, token);
  });

  const rejectBatch = useBatchAction<number>(async (id) => {
    if (!token) return;
    const finalComment = rejectMotif === "Autre (préciser...)" ? rejectComment : `[${rejectMotif}] ${rejectComment}`;
    await validateAudio(id, false, finalComment, token);
  });

  const toggleSort = (field: "filename" | "uploaded_at") => {
    if (sortField === field) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortDirection("asc");
    }
  };

  const handleToggleRow = (id: number | string) => {
    const newSelected = new Set(selectedIds);
    if (newSelected.has(id as number)) {
      newSelected.delete(id as number);
    } else {
      newSelected.add(id as number);
    }
    setSelectedIds(newSelected);
  };

  const handleToggleAll = () => {
    const visibleIds = filteredAndSortedAudios.map(a => a.id);
    const allVisibleSelected = visibleIds.every(id => selectedIds.has(id));

    const newSelected = new Set(selectedIds);
    if (allVisibleSelected) {
      visibleIds.forEach(id => newSelected.delete(id));
    } else {
      visibleIds.forEach(id => newSelected.add(id));
    }
    setSelectedIds(newSelected);
  };

  const handleQuickValidate = async (id: number) => {
    if (!token) return;
    setLoading(true);
    try {
      await validateAudio(id, true, null, token);
      refreshData();
    } catch (e: any) {
      setError(e.message || "Erreur lors de la validation");
    } finally {
      setLoading(false);
    }
  };

  const handleQuickReject = (id: number) => {
    setPendingActionId(id);
    setRejectMotif("");
    setRejectComment("");
    setActiveModal("reject");
  };

  const handleShowAudit = async () => {
    if (!token) return;
    setAuditLoading(true);
    setActiveModal("audit");
    try {
      const logs = await fetchProjectAuditTrail(projectId, token);
      setAuditLogs(logs);
    } catch (e: any) {
      setError(e.message || "Erreur lors du chargement de l'historique");
    } finally {
      setAuditLoading(false);
    }
  };

  const executeAssign = async () => {
    if (!transcripteurId) return;
    const eligibleIds = Array.from(selectedIds).filter(id => {
      const a = audios.find(aud => aud.id === id);
      return a && (a.status === "uploaded" || a.status === "assigned");
    });
    setActiveModal("report");
    await assignBatch.runBatch(eligibleIds);
    refreshData();
    setSelectedIds(new Set());
  };

  const executeValidate = async () => {
    const eligibleIds = Array.from(selectedIds).filter(id => {
      const a = audios.find(aud => aud.id === id);
      return a && a.status === "transcribed";
    });
    setActiveModal("report");
    await validateBatch.runBatch(eligibleIds);
    refreshData();
    setSelectedIds(new Set());
  };

  const executeReject = async () => {
    if (rejectMotif === "Autre (préciser...)" && !rejectComment) return;
    if (!rejectMotif) return;

    if (pendingActionId) {
      // Single reject
      setLoading(true);
      setActiveModal("none");
      try {
        const finalComment = rejectMotif === "Autre (préciser...)" ? rejectComment : `[${rejectMotif}] ${rejectComment}`;
        await validateAudio(pendingActionId, false, finalComment, token || "");
        refreshData();
      } catch (e: any) {
        setError(e.message || "Erreur lors du rejet");
      } finally {
        setLoading(false);
        setPendingActionId(null);
      }
    } else {
      // Bulk reject
      const eligibleIds = Array.from(selectedIds).filter(id => {
        const a = audios.find(aud => aud.id === id);
        return a && a.status === "transcribed";
      });
      setActiveModal("report");
      await rejectBatch.runBatch(eligibleIds);
      refreshData();
      setSelectedIds(new Set());
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

  const allVisibleSelected = filteredAndSortedAudios.length > 0 && 
    filteredAndSortedAudios.every(a => selectedIds.has(a.id));

  const currentBatch = assignBatch.status !== "idle" ? assignBatch : 
                  validateBatch.status !== "idle" ? validateBatch : 
                  rejectBatch.status !== "idle" ? rejectBatch : null;

  return (
    <div style={{ display: "grid", gap: "var(--spacing-4)", position: "relative", minHeight: "100%" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-3)" }}>
          <button type="button" className="za-btn za-btn--ghost" onClick={onBack}>
            &larr; Retour
          </button>
          <h2 style={{ margin: 0, fontFamily: "var(--font-headline)" }}>
            {projectDetail?.name || `Projet #${projectId}`}
          </h2>
          <button 
            type="button" 
            className="za-btn za-btn--ghost za-btn--sm" 
            onClick={() => setActiveModal("settings")}
            style={{ border: "1px solid var(--color-outline)" }}
          >
            Paramètres
          </button>
          <button 
            type="button" 
            className="za-btn za-btn--ghost za-btn--sm" 
            onClick={handleShowAudit}
            style={{ border: "1px solid var(--color-outline)" }}
          >
            Historique
          </button>
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
        <Metric label="Progression" value={`${analytics.progress.toFixed(1)}%`} tone={analytics.progress === 100 ? "success" : "default"} />
        <Metric label="Durée Totale" value={formatDuration(analytics.duration)} />
        <Metric label="Confiance Moy." value="--" />
      </div>

      <Card title="Liste des fichiers audio" subtitle={`Affichage de ${filteredAndSortedAudios.length} fichier(s)`}>
        {audios.length === 0 ? (
          <p style={{ color: "var(--color-text-muted)", margin: 0 }}>Aucun fichier audio n'a été ajouté à ce projet.</p>
        ) : (
          <DataTable
            selectable
            selectedIds={selectedIds}
            onToggleRow={handleToggleRow}
            onToggleAll={handleToggleAll}
            allSelected={allVisibleSelected}
            rowIds={filteredAndSortedAudios.map(a => a.id)}
            columns={["Fichier", "Statut", "Assigné à", "Uploadé le", "Actions"]}
            rows={filteredAndSortedAudios.map((a) => [
              a.filename,
              <Badge 
                key={`status-${a.id}`} 
                tone={a.status === "validated" ? "success" : a.status === "transcribed" || a.status === "in_progress" ? "primary" : "default"}
                glow={true}
                pulse={a.status === "in_progress"}
              >
                {a.status}
              </Badge>,
              a.assigned_to || "--",
              formatIso(a.uploaded_at),
              <div key={`actions-${a.id}`} style={{ display: "flex", gap: "var(--spacing-1)" }}>
                {a.status === "transcribed" && (
                  <>
                    <button 
                      type="button" 
                      className="za-btn za-btn--ghost" 
                      title="Valider"
                      onClick={() => handleQuickValidate(a.id)}
                      style={{ color: "var(--color-success)", padding: "4px" }}
                    >
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
                    </button>
                    <button 
                      type="button" 
                      className="za-btn za-btn--ghost" 
                      title="Rejeter"
                      onClick={() => handleQuickReject(a.id)}
                      style={{ color: "var(--color-error)", padding: "4px" }}
                    >
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                    </button>
                  </>
                )}
                <button type="button" className="za-btn za-btn--ghost" style={{ padding: "4px", opacity: 0.5 }} title="Détails">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
                </button>
              </div>
            ])}
          />
        )}
      </Card>

      {/* Bulk Action Bar */}
      {selectedIds.size > 0 && (
        <div style={{
          position: "fixed",
          bottom: "var(--spacing-6)",
          left: "50%",
          transform: "translateX(-50%)",
          background: "var(--color-surface-hi)",
          backdropFilter: "blur(12px)",
          border: "1px solid var(--color-primary-soft)",
          padding: "var(--spacing-3) var(--spacing-6)",
          borderRadius: "var(--radius-full)",
          boxShadow: "0 10px 30px rgba(0,0,0,0.3), 0 0 15px var(--color-glow-blue)",
          display: "flex",
          alignItems: "center",
          gap: "var(--spacing-5)",
          zIndex: 100,
          animation: "za-slide-up 0.3s ease-out"
        }}>
          <span style={{ fontWeight: 700, fontSize: "0.9rem" }}>
            {selectedIds.size} élément(s) sélectionné(s)
          </span>
          <div style={{ width: "1px", height: "24px", background: "var(--color-outline)" }} />
          <div style={{ display: "flex", gap: "var(--spacing-2)" }}>
            <button type="button" className="za-btn za-btn--primary" onClick={() => setActiveModal("assign")}>Assigner</button>
            <button type="button" className="za-btn za-btn--success" onClick={executeValidate}>Valider</button>
            <button type="button" className="za-btn za-btn--ghost" style={{ color: "var(--color-error)" }} onClick={() => setActiveModal("reject")}>Rejeter</button>
          </div>
          <button 
            type="button" 
            className="za-btn za-btn--ghost" 
            onClick={() => setSelectedIds(new Set())}
            style={{ padding: "var(--spacing-1)" }}
          >
            &times;
          </button>
        </div>
      )}

      {/* Modals */}
      <GlassModal 
        isOpen={activeModal === "assign"} 
        title="Assignation Groupée" 
        onClose={() => setActiveModal("none")}
        size="sm"
      >
        <div style={{ display: "grid", gap: "var(--spacing-4)" }}>
          <div>
            <p style={{ margin: "0 0 var(--spacing-2)" }}>
              Saisissez l'ID du Transcripteur pour les <strong>{selectedIds.size}</strong> éléments sélectionnés.
            </p>
            <div style={{ fontSize: "0.8rem", color: "var(--color-text-muted)" }}>
              Projet: {projectDetail?.name}
            </div>
          </div>
          <input 
            type="text" 
            className="za-input" 
            placeholder="ID Transcripteur (ex: user_123)" 
            value={transcripteurId}
            onChange={(e) => setTranscripteurId(e.target.value)}
            autoFocus
          />
          <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--spacing-2)" }}>
            <button className="za-btn za-btn--ghost" onClick={() => setActiveModal("none")}>Annuler</button>
            <button className="za-btn za-btn--primary" disabled={!transcripteurId} onClick={executeAssign}>Assigner</button>
          </div>
        </div>
      </GlassModal>

      <GlassModal 
        isOpen={activeModal === "reject"} 
        title={pendingActionId ? "Rejeter la transcription" : "Rejet Groupé"} 
        onClose={() => {
          setActiveModal("none");
          setPendingActionId(null);
        }}
        size="sm"
      >
        <div style={{ display: "grid", gap: "var(--spacing-4)" }}>
          <div>
            <p style={{ margin: "0 0 var(--spacing-2)" }}>
              {pendingActionId 
                ? "Pourquoi rejetez-vous cette transcription ?" 
                : `Motif du rejet pour les ${selectedIds.size} éléments sélectionnés.`}
            </p>
          </div>

          <div style={{ display: "grid", gap: "var(--spacing-1)" }}>
            <label style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--color-text-muted)" }}>MOTIF PRINCIPAL</label>
            <select 
              className="za-input"
              value={rejectMotif}
              onChange={(e) => setRejectMotif(e.target.value)}
              style={{ width: "100%" }}
            >
              <option value="">-- Sélectionner un motif --</option>
              {REJECTION_MOTIFS.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>

          <div style={{ display: "grid", gap: "var(--spacing-1)" }}>
            <label style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--color-text-muted)" }}>
              COMMENTAIRE {rejectMotif === "Autre (préciser...)" ? "(OBLIGATOIRE)" : "(OPTIONNEL)"}
            </label>
            <textarea 
              className="za-input" 
              placeholder="Précisez votre retour ici..." 
              value={rejectComment}
              onChange={(e) => setRejectComment(e.target.value)}
              rows={4}
            />
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--spacing-2)" }}>
            <button className="za-btn za-btn--ghost" onClick={() => {
              setActiveModal("none");
              setPendingActionId(null);
            }}>Annuler</button>
            <button 
              className="za-btn za-btn--error" 
              disabled={!rejectMotif || (rejectMotif === "Autre (préciser...)" && !rejectComment)} 
              onClick={executeReject}
            >
              Confirmer le rejet
            </button>
          </div>
        </div>
      </GlassModal>

      <GlassModal 
        isOpen={activeModal === "settings"} 
        title="Paramètres du Projet" 
        onClose={() => setActiveModal("none")}
        size="md"
      >
        {projectDetail && (
          <div style={{ display: "grid", gap: "var(--spacing-6)" }}>
            <div style={{ display: "grid", gap: "var(--spacing-2)" }}>
              <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--color-text-muted)", textTransform: "uppercase" }}>Informations</div>
              <div style={{ display: "grid", gridTemplateColumns: "120px 1fr", gap: "var(--spacing-2)" }}>
                <span style={{ opacity: 0.7 }}>Nom:</span>
                <span style={{ fontWeight: 600 }}>{projectDetail.name}</span>
                <span style={{ opacity: 0.7 }}>Nature:</span>
                <span style={{ fontWeight: 600 }}>{projectDetail.nature_name}</span>
                <span style={{ opacity: 0.7 }}>Créé le:</span>
                <span style={{ fontWeight: 600 }}>{formatIso(projectDetail.created_at)}</span>
              </div>
            </div>

            <div style={{ display: "grid", gap: "var(--spacing-3)" }}>
              <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--color-text-muted)", textTransform: "uppercase" }}>Labels de la Nature</div>
              <div style={{ 
                display: "flex", 
                flexWrap: "wrap", 
                gap: "var(--spacing-2)",
                background: "var(--color-surface-hi)",
                padding: "var(--spacing-4)",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--color-outline-ghost)"
              }}>
                {projectDetail.labels.map(label => (
                  <Badge 
                    key={label.id} 
                    tone="default"
                    style={{ background: label.color, color: "#fff", textShadow: "0 1px 2px rgba(0,0,0,0.3)" }}
                  >
                    {label.name}
                  </Badge>
                ))}
                {projectDetail.labels.length === 0 && (
                  <span style={{ fontSize: "0.9rem", color: "var(--color-text-muted)" }}>Aucun label configuré.</span>
                )}
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "var(--spacing-2)" }}>
              <button className="za-btn za-btn--primary" onClick={() => setActiveModal("none")}>Fermer</button>
            </div>
          </div>
        )}
      </GlassModal>

      <GlassModal
        isOpen={activeModal === "audit"}
        title="Historique du Projet"
        onClose={() => setActiveModal("none")}
        size="md"
      >
        {auditLoading ? (
          <p style={{ textAlign: "center", padding: "var(--spacing-8)", color: "var(--color-text-muted)" }}>
            Chargement de l'historique...
          </p>
        ) : (
          <div style={{ display: "grid", gap: "var(--spacing-4)", maxHeight: "60vh", overflowY: "auto", padding: "var(--spacing-2)" }}>
            {auditLogs.length === 0 ? (
              <p style={{ textAlign: "center", color: "var(--color-text-muted)" }}>Aucun événement enregistré.</p>
            ) : (
              <div style={{ position: "relative", paddingLeft: "var(--spacing-6)" }}>
                <div style={{ 
                  position: "absolute", 
                  left: "7px", 
                  top: 0, 
                  bottom: 0, 
                  width: "2px", 
                  background: "var(--color-outline-ghost)" 
                }} />
                
                {auditLogs.map((log) => (
                  <div key={log.id} style={{ position: "relative", marginBottom: "var(--spacing-6)" }}>
                    <div style={{ 
                      position: "absolute", 
                      left: "-23px", 
                      top: "4px", 
                      width: "12px", 
                      height: "12px", 
                      borderRadius: "50%", 
                      background: "var(--color-primary)",
                      boxShadow: "0 0 8px var(--color-glow-blue)",
                      border: "2px solid var(--color-surface)"
                    }} />
                    
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                      <span style={{ fontWeight: 700, fontSize: "0.9rem", color: "var(--color-primary)" }}>
                        {log.action.replace(/_/g, " ")}
                      </span>
                      <span style={{ fontSize: "0.75rem", color: "var(--color-text-muted)" }}>
                        {formatIso(log.created_at)}
                      </span>
                    </div>
                    
                    <div style={{ fontSize: "0.85rem", marginTop: "var(--spacing-1)" }}>
                      Utilisateur: <code style={{ color: "var(--color-text-dim)" }}>{log.user_id}</code>
                    </div>
                    
                    {Object.keys(log.details).length > 0 && (
                      <div style={{ 
                        marginTop: "var(--spacing-2)", 
                        padding: "var(--spacing-2) var(--spacing-3)", 
                        background: "var(--color-surface-low)", 
                        borderRadius: "var(--radius-sm)",
                        fontSize: "0.8rem",
                        border: "1px solid var(--color-outline-ghost)"
                      }}>
                        {Object.entries(log.details).map(([key, val]) => (
                          <div key={key}>
                            <span style={{ opacity: 0.6, textTransform: "capitalize" }}>{key}: </span>
                            <span style={{ fontWeight: 500 }}>{String(val)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "var(--spacing-4)" }}>
              <button className="za-btn za-btn--primary" onClick={() => setActiveModal("none")}>Fermer</button>
            </div>
          </div>
        )}
      </GlassModal>

      <GlassModal 
        isOpen={activeModal === "report"} 
        title="Opération en cours" 
        onClose={() => {
          assignBatch.reset();
          validateBatch.reset();
          rejectBatch.reset();
          setActiveModal("none");
        }}
        size="sm"
      >
        {currentBatch && (
          <div style={{ display: "grid", gap: "var(--spacing-4)" }}>
            <div style={{ fontSize: "1.25rem", fontWeight: 700, textAlign: "center" }}>
              {currentBatch.status === "processing" ? "Traitement..." : "Terminé"}
            </div>
            <div style={{ height: "8px", background: "var(--color-surface-low)", borderRadius: "4px", overflow: "hidden" }}>
              <div style={{ 
                width: `${(currentBatch.progress / currentBatch.total) * 100}%`, 
                height: "100%", 
                background: "var(--color-primary)",
                transition: "width 0.3s ease"
              }} />
            </div>
            <p style={{ textAlign: "center" }}>{currentBatch.progress} sur {currentBatch.total} traités</p>
            
            {currentBatch.status === "completed" && (
              <div style={{ marginTop: "var(--spacing-2)" }}>
                <div style={{ fontWeight: 700, marginBottom: "var(--spacing-2)" }}>Résumé :</div>
                <div style={{ color: "var(--color-success)" }}>
                  {currentBatch.results.filter(r => r.success).length} succès
                </div>
                {currentBatch.results.some(r => !r.success) && (
                  <>
                    <div style={{ color: "var(--color-error)", marginTop: "var(--spacing-1)" }}>
                      {currentBatch.results.filter(r => !r.success).length} échecs
                    </div>
                    <div style={{ display: "flex", justifyContent: "center", marginTop: "var(--spacing-4)", gap: "var(--spacing-2)" }}>
                      <button className="za-btn za-btn--ghost" onClick={() => {
                        const failedIds = currentBatch.results.filter(r => !r.success).map(r => Number(r.id));
                        currentBatch.runBatch(failedIds);
                      }}>Réessayer les échecs</button>
                      <button className="za-btn za-btn--primary" onClick={() => {
                        assignBatch.reset();
                        validateBatch.reset();
                        rejectBatch.reset();
                        setActiveModal("none");
                      }}>Fermer</button>
                    </div>
                  </>
                )}
                {!currentBatch.results.some(r => !r.success) && (
                  <div style={{ display: "flex", justifyContent: "center", marginTop: "var(--spacing-4)" }}>
                    <button className="za-btn za-btn--primary" onClick={() => {
                      assignBatch.reset();
                      validateBatch.reset();
                      rejectBatch.reset();
                      setActiveModal("none");
                    }}>Fermer</button>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </GlassModal>

      <style>{`
        @keyframes za-slide-up {
          from { transform: translate(-50%, 100%); opacity: 0; }
          to { transform: translate(-50%, 0); opacity: 1; }
        }
        .za-input {
          padding: var(--spacing-3);
          border-radius: var(--radius-md);
          border: 1px solid var(--color-outline);
          background: var(--color-surface-low);
          color: var(--color-text);
          font-family: inherit;
        }
        .za-input:focus {
          outline: 2px solid var(--color-primary);
          border-color: transparent;
        }
      `}</style>
    </div>
  );
}
