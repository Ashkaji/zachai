import { useEffect, useState, useMemo, useCallback, useRef } from "react";
import { useAuth } from "react-oidc-context";
import { bearerForApi } from "../../auth/api-client";
import {
  fetchProjectStatus,
  fetchProjectDetail,
  type AudioRow,
  type ProjectDetail,
  assignAudio,
  listUsers,
  type User,
  deleteAudio,
  retryNormalization,
  deleteProject,
} from "../dashboard/dashboardApi";
import { 
  registerAudio, 
  requestAudioUpload 
} from "../project-wizard/projectApi";
import { Card, DataTable, Metric, Badge } from "../../shared/ui/Primitives";
import { formatIso, formatDuration } from "../../shared/utils/dateUtils";
import { useBatchAction } from "../../shared/hooks/useBatchAction";

type ProjectDetailManagerProps = {
  projectId: number;
  onBack: () => void;
};

// --- Sub-component: MultiUserSelect (Chip-based searchable select) ---

function MultiUserSelect({ 
  users, 
  selectedIds, 
  onChange 
}: { 
  users: User[], 
  selectedIds: string[], 
  onChange: (ids: string[]) => void 
}) {
  const [search, setSearch] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const filteredUsers = useMemo(() => {
    const s = search.toLowerCase();
    return users.filter(u => 
      !selectedIds.includes(u.id) && 
      (u.username.toLowerCase().includes(s) || 
       (u.firstName || "").toLowerCase().includes(s) || 
       (u.lastName || "").toLowerCase().includes(s))
    );
  }, [users, selectedIds, search]);

  const selectedUsers = useMemo(() => 
    selectedIds.map(id => users.find(u => u.id === id)).filter(Boolean) as User[]
  , [selectedIds, users]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div ref={containerRef} style={{ position: "relative", width: "100%" }}>
      <div 
        style={{ 
          display: "flex", 
          flexWrap: "wrap", 
          gap: "6px", 
          padding: "8px", 
          background: "var(--color-surface-hi)", 
          borderRadius: "8px",
          border: "1px solid var(--color-outline)",
          minHeight: "44px",
          cursor: "text"
        }}
        onClick={() => setIsOpen(true)}
      >
        {selectedUsers.map(u => (
          <div 
            key={u.id} 
            style={{ 
              display: "flex", 
              alignItems: "center", 
              gap: "6px", 
              background: "var(--color-primary-soft)", 
              color: "var(--color-primary)",
              padding: "2px 8px",
              borderRadius: "4px",
              fontSize: "0.85rem",
              fontWeight: 600
            }}
          >
            {u.firstName || u.lastName ? `${u.firstName} ${u.lastName}` : u.username}
            <button
              onClick={(e) => {
                e.stopPropagation();
                onChange(selectedIds.filter(id => id !== u.id));
              }}
              style={{ 
                border: "none", 
                background: "none", 
                color: "inherit", 
                cursor: "pointer", 
                padding: "0 2px",
                display: "flex",
                alignItems: "center",
                opacity: 0.7
              }}
              title="Retirer"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
            </button>
          </div>
        ))}
        <input
          type="text"
          placeholder={selectedIds.length === 0 ? "Rechercher des collaborateurs..." : ""}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onFocus={() => setIsOpen(true)}
          style={{ 
            border: "none", 
            background: "none", 
            outline: "none", 
            flex: 1, 
            minWidth: "120px", 
            color: "inherit",
            fontSize: "0.85rem"
          }}
        />
      </div>

      {isOpen && filteredUsers.length > 0 && (
        <div style={{ 
          position: "absolute", 
          top: "100%", 
          left: 0, 
          right: 0, 
          zIndex: 300, 
          background: "var(--color-surface-hi)", 
          borderRadius: "8px", 
          boxShadow: "0 10px 25px rgba(0,0,0,0.4)",
          marginTop: "4px",
          maxHeight: "200px",
          overflowY: "auto",
          border: "1px solid var(--color-outline-ghost)"
        }}>
          {filteredUsers.map(u => (
            <div 
              key={u.id}
              onClick={() => {
                onChange([...selectedIds, u.id]);
                setSearch("");
                setIsOpen(false);
              }}
              style={{ 
                padding: "10px 15px", 
                cursor: "pointer",
                display: "flex",
                flexDirection: "column",
                borderBottom: "1px solid var(--color-outline-ghost)"
              }}
              className="za-row-hover"
            >
              <span style={{ fontWeight: 600 }}>{u.firstName || u.lastName ? `${u.firstName} ${u.lastName}` : u.username}</span>
              <span style={{ fontSize: "0.75rem", opacity: 0.6 }}>@{u.username}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// --- Main Component ---

export function ProjectDetailManager({ projectId, onBack }: ProjectDetailManagerProps) {
  const auth = useAuth();
  const token = useMemo(() => bearerForApi(auth.user), [auth.user]);
  const [projectStatus, setProjectStatus] = useState<string>("");
  const [projectDetail, setProjectDetail] = useState<ProjectDetail | null>(null);
  const [audios, setAudios] = useState<AudioRow[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeModal, setActiveModal] = useState<"none" | "import" | "assign" | "report" | "delete-project">("none");
  const [importFiles, setImportFiles] = useState<File[]>([]);
  const [importing, setImporting] = useState(false);
  const [importProgress, setImportProgress] = useState(0);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [transcripteurIds, setTranscripteurIds] = useState<string[]>([]);
  const [audioActionLoading, setAudioActionLoading] = useState<number | null>(null);
  const [deleteProjectLoading, setDeleteProjectLoading] = useState(false);

  const assignBatch = useBatchAction<number>(async (id) => {
    if (!token) return;
    await assignAudio(projectId, id, transcripteurIds, token);
  });

  const uploadToMinio = (url: string, file: File, onProgress: (p: number) => void): Promise<void> => {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("PUT", url);
      xhr.setRequestHeader("Content-Type", file.type || "audio/mpeg");
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          onProgress(Math.floor((e.loaded / e.total) * 100));
        }
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) resolve();
        else reject(new Error(`MinIO Error: ${xhr.status}`));
      };
      xhr.onerror = () => reject(new Error("Network error during MinIO upload"));
      xhr.send(file);
    });
  };

  const handleImportFiles = async () => {
    if (!token || !importFiles || importFiles.length === 0) return;
    setImporting(true);
    setImportProgress(0);
    let done = 0;
    try {
      for (const file of importFiles) {
        const req = await requestAudioUpload(token, projectId, {
          filename: file.name,
          content_type: file.type || "audio/mpeg"
        });
        await uploadToMinio(req.presigned_url, file, (p) => {
          const currentTotalProgress = Math.floor(((done + (p / 100)) / importFiles.length) * 100);
          setImportProgress(currentTotalProgress);
        });
        await registerAudio(token, projectId, req.object_key);
        done++;
        setImportProgress(Math.floor((done / importFiles.length) * 100));
      }
      setImportFiles([]);
      setActiveModal("none");
      refreshData();
    } catch (e: any) {
      setError(e.message || "Erreur pendant l'importation");
    } finally {
      setImporting(false);
      setImportProgress(0);
    }
  };

  const executeAssign = async () => {
    setActiveModal("report");
    await assignBatch.runBatch(Array.from(selectedIds));
    refreshData();
    setSelectedIds(new Set());
    setTranscripteurIds([]);
  };

  const handleRetryNormalization = async (audioId: number) => {
    if (!token) return;
    setAudioActionLoading(audioId);
    try {
      await retryNormalization(projectId, audioId, token);
      refreshData();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de la relance de normalisation");
    } finally {
      setAudioActionLoading(null);
    }
  };

  const handleDeleteAudio = async (audioId: number, filename: string) => {
    if (!token) return;
    if (!window.confirm(`Supprimer « ${filename} » ? Cette action est irréversible.`)) return;
    setAudioActionLoading(audioId);
    try {
      await deleteAudio(projectId, audioId, token);
      refreshData();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de la suppression de l'audio");
    } finally {
      setAudioActionLoading(null);
    }
  };

  const handleDeleteProject = async () => {
    if (!token) return;
    setDeleteProjectLoading(true);
    try {
      await deleteProject(projectId, token);
      onBack();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de la suppression du projet");
      setDeleteProjectLoading(false);
      setActiveModal("none");
    }
  };

  const refreshData = useCallback(() => {
    if (!token || projectId === null || projectId === undefined) return;
    setLoading(true);
    Promise.all([
      fetchProjectStatus(projectId, token),
      fetchProjectDetail(projectId, token),
      listUsers(token)
    ])
      .then(([statusRes, detailRes, userItems]) => {
        setProjectStatus(statusRes.project_status);
        setAudios(statusRes.audios || []);
        setProjectDetail(detailRes);
        setUsers(userItems || []);
        setError("");
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : "Erreur lors de la récupération du projet");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [projectId, token]);

  useEffect(() => {
    if (auth.isLoading || !token) return;
    refreshData();
  }, [auth.isLoading, token, refreshData]);

  const analytics = useMemo(() => {
    const safeAudios = audios || [];
    if (safeAudios.length === 0) return { progress: 0, duration: 0 };
    const validatedCount = safeAudios.filter(a => a && a.status === "validated").length;
    const totalDuration = safeAudios.reduce((acc, a) => acc + ((a && a.duration_s) || 0), 0);
    return {
      progress: (validatedCount / safeAudios.length) * 100,
      duration: totalDuration
    };
  }, [audios]);

  const assignedUsersInfo = useMemo(() => {
    const counts: Record<string, number> = {};
    const safeAudios = audios || [];
    safeAudios.forEach(a => {
      if (a && a.assigned_to) {
        const ids = a.assigned_to.split(",").filter(Boolean);
        ids.forEach(id => {
          counts[id] = (counts[id] || 0) + 1;
        });
      }
    });
    return Object.entries(counts).map(([userId, count]) => {
      const u = (users || []).find(user => user && user.id === userId);
      return {
        id: userId,
        username: u?.username || userId,
        count
      };
    });
  }, [audios, users]);

  if (loading) return <div style={{ padding: "2rem" }}>Chargement des détails du projet ({projectId})...</div>;
  if (error) return <div style={{ padding: "2rem", color: "var(--color-error)" }}>Erreur: {error} <button onClick={refreshData}>Réessayer</button></div>;

  return (
    <div style={{ display: "grid", gap: "var(--spacing-6)", animation: "fade-in 0.3s ease" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-4)" }}>
          <button onClick={onBack} className="za-btn za-btn--ghost" style={{ border: "none" }}>
            &larr; Retour
          </button>
          <h2 style={{ margin: 0, fontFamily: "var(--font-headline)", fontWeight: 800 }}>
            {projectDetail?.name || `Projet #${projectId}`}
          </h2>
          <Badge tone={projectStatus === "active" ? "success" : "default"}>{projectStatus}</Badge>
        </div>
        <div style={{ display: "flex", gap: "var(--spacing-3)" }}>
          <button
            type="button"
            className="za-btn za-btn--ghost"
            style={{ color: "var(--color-error)", border: "1px solid var(--color-error)" }}
            onClick={() => setActiveModal("delete-project")}
          >
            Supprimer le projet
          </button>
          <button
            type="button"
            className="za-btn za-btn--primary"
            onClick={() => setActiveModal("import")}
          >
            + Ajouter Audios
          </button>
        </div>
      </header>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "var(--spacing-4)" }}>
        <Metric label="Fichiers" value={String(audios.length)} />
        <Metric label="Progression" value={`${analytics.progress.toFixed(0)}%`} tone="success" />
        <Metric label="Assignés" value={String(new Set(audios.flatMap(a => (a.assigned_to || "").split(",").filter(Boolean))).size)} />
        <Metric label="Durée Totale" value={formatDuration(analytics.duration)} />
      </div>

      {assignedUsersInfo.length > 0 && (
        <Card title="Équipe du projet" subtitle="Collaborateurs travaillant sur ce projet">
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-3)" }}>
            {assignedUsersInfo.map(u => (
              <div key={u.id} style={{ 
                display: "flex", 
                alignItems: "center", 
                gap: "var(--spacing-2)", 
                background: "var(--color-surface-hi)", 
                padding: "8px 12px", 
                borderRadius: "var(--radius-full)",
                border: "1px solid var(--color-outline-ghost)"
              }}>
                <div style={{ 
                  width: "24px", 
                  height: "24px", 
                  borderRadius: "50%", 
                  background: "var(--color-primary-soft)", 
                  color: "var(--color-primary)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "0.75rem",
                  fontWeight: 800
                }}>
                  {u.username.substring(0, 1).toUpperCase()}
                </div>
                <div style={{ display: "flex", flexDirection: "column" }}>
                  <span style={{ fontSize: "0.85rem", fontWeight: 700 }}>{u.username}</span>
                </div>
                <Badge tone="primary" style={{ marginLeft: "4px" }}>{u.count} audios</Badge>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card title="Fichiers Audio" subtitle={`${audios.length} fichiers dans ce projet`}>
        {audios.length === 0 ? (
          <p style={{ color: "var(--color-text-muted)" }}>Aucun fichier.</p>
        ) : (
          <DataTable
            selectable
            selectedIds={selectedIds}
            onToggleRow={(id) => {
              const newSelected = new Set(selectedIds);
              if (newSelected.has(id as number)) newSelected.delete(id as number);
              else newSelected.add(id as number);
              setSelectedIds(newSelected);
            }}
            onToggleAll={() => {
              const allIds = audios.map(a => a.id);
              if (selectedIds.size === allIds.length) setSelectedIds(new Set());
              else setSelectedIds(new Set(allIds));
            }}
            allSelected={selectedIds.size > 0 && selectedIds.size === audios.length}
            columns={["Fichier", "Statut", "Prêt", "Assigné à"]}
            rowIds={audios.map(a => a.id)}
            rows={audios.map(a => {
              const assignedIdsList = (a.assigned_to || "").split(",").filter(Boolean);
              const isNormalized = !!a.normalized_path && !a.validation_error;

              return [
                <div key={`file-${a.id}`} style={{ fontWeight: 600 }}>{a.filename}</div>,
                <Badge key={`status-${a.id}`} tone={a.status === "validated" ? "success" : a.status === "transcribed" ? "primary" : "default"}>
                  {a.status}
                </Badge>,
                <span
                  key={`norm-${a.id}`}
                  title={
                    a.validation_error
                      ? `Erreur de normalisation : ${a.validation_error}`
                      : isNormalized
                      ? "Audio normalisé, prêt pour assignation"
                      : "En attente de normalisation (worker FFmpeg)"
                  }
                  style={{
                    display: "inline-block",
                    width: "10px",
                    height: "10px",
                    borderRadius: "50%",
                    background: a.validation_error
                      ? "var(--color-error)"
                      : isNormalized
                      ? "var(--color-success)"
                      : "var(--color-text-muted)",
                    flexShrink: 0,
                  }}
                />,
                <div key={`assign-${a.id}`} style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: "4px" }}>
                  {assignedIdsList.length === 0 ? (
                    <span style={{ color: "var(--color-text-muted)", fontSize: "0.85rem" }}>--</span>
                  ) : (
                    assignedIdsList.map(id => {
                      const u = users.find(user => user.id === id);
                      const name = u ? (u.firstName || u.lastName ? `${u.firstName} ${u.lastName}` : u.username) : id;
                      return (
                        <span key={id} style={{ 
                          background: "var(--color-surface-vhi)", 
                          padding: "2px 6px", 
                          borderRadius: "4px", 
                          fontSize: "0.75rem",
                          fontWeight: 600,
                          border: "1px solid var(--color-outline-ghost)"
                        }}>
                          {name}
                        </span>
                      );
                    })
                  )}
                  <button
                    type="button"
                    className="za-btn za-btn--ghost"
                    style={{ padding: "4px", opacity: 0.6 }}
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedIds(new Set([a.id]));
                      setTranscripteurIds(assignedIdsList);
                      setActiveModal("assign");
                    }}
                    title="Modifier l'assignation"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
                  </button>
                  {a.validation_error && (
                    <button
                      type="button"
                      className="za-btn za-btn--ghost"
                      style={{ padding: "4px 8px", fontSize: "0.7rem", color: "var(--color-primary)", border: "1px solid var(--color-primary)", opacity: audioActionLoading === a.id ? 0.5 : 1 }}
                      disabled={audioActionLoading === a.id}
                      onClick={(e) => { e.stopPropagation(); handleRetryNormalization(a.id); }}
                      title="Relancer la normalisation FFmpeg"
                    >
                      {audioActionLoading === a.id ? "..." : "Retry"}
                    </button>
                  )}
                  {!["transcribed", "validated"].includes(a.status) && (
                    <button
                      type="button"
                      className="za-btn za-btn--ghost"
                      style={{ padding: "4px", color: "var(--color-error)", opacity: audioActionLoading === a.id ? 0.5 : 0.7 }}
                      disabled={audioActionLoading === a.id}
                      onClick={(e) => { e.stopPropagation(); handleDeleteAudio(a.id, a.filename); }}
                      title="Supprimer cet audio"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"></path><path d="M10 11v6"></path><path d="M14 11v6"></path><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"></path></svg>
                    </button>
                  )}
                </div>
              ];
            })}
          />
        )}
      </Card>

      {/* Bulk Action Bar */}
      {selectedIds.size > 0 && activeModal === "none" && (
        <div style={{
          position: "fixed",
          bottom: "var(--spacing-6)",
          left: "50%",
          transform: "translateX(-50%)",
          background: "var(--color-surface-hi)",
          padding: "var(--spacing-3) var(--spacing-6)",
          borderRadius: "var(--radius-full)",
          boxShadow: "0 10px 30px rgba(0,0,0,0.3)",
          display: "flex",
          alignItems: "center",
          gap: "var(--spacing-5)",
          zIndex: 100,
          border: "1px solid var(--color-primary-soft)"
        }}>
          <span style={{ fontWeight: 700 }}>{selectedIds.size} sélectionnés</span>
          <button className="za-btn za-btn--primary za-btn--sm" onClick={() => {
            setTranscripteurIds([]); // Start fresh for bulk
            setActiveModal("assign");
          }}>Assigner à...</button>
          <button className="za-btn za-btn--ghost za-btn--sm" onClick={() => setSelectedIds(new Set())}>Annuler</button>
        </div>
      )}

      {/* MODALS */}
      {activeModal === "import" && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 200 }}>
          <div className="za-glass" style={{ padding: "2rem", borderRadius: "1rem", width: "400px" }}>
            <h3 style={{ marginTop: 0 }}>Ajouter des audios</h3>
            <input 
              type="file" 
              multiple 
              accept="audio/*" 
              onChange={(e) => setImportFiles(Array.from(e.target.files || []))}
              disabled={importing}
              style={{ marginBottom: "1rem" }}
            />
            {importing && (
              <div style={{ marginBottom: "1rem" }}>
                <div style={{ height: "4px", background: "var(--color-surface-low)", borderRadius: "2px" }}>
                  <div style={{ width: `${importProgress}%`, height: "100%", background: "var(--color-primary)" }} />
                </div>
                <p style={{ fontSize: "0.8rem", textAlign: "center" }}>En cours... {importProgress}%</p>
              </div>
            )}
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px" }}>
              <button className="za-btn za-btn--ghost" onClick={() => setActiveModal("none")} disabled={importing}>Annuler</button>
              <button className="za-btn za-btn--primary" onClick={handleImportFiles} disabled={importing || importFiles.length === 0}>Lancer l'import</button>
            </div>
          </div>
        </div>
      )}

      {activeModal === "assign" && (() => {
        const selectedAudios = audios.filter(a => selectedIds.has(a.id));
        const notReady = selectedAudios.filter(a => !a.normalized_path || !!a.validation_error);
        return (
          <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 200 }}>
            <div className="za-glass" style={{ padding: "2rem", borderRadius: "1rem", width: "500px", maxHeight: "80vh", display: "flex", flexDirection: "column" }}>
              <h3 style={{ marginTop: 0 }}>Assignation des collaborateurs</h3>
              <p style={{ fontSize: "0.9rem", color: "var(--color-text-muted)", marginBottom: "1rem" }}>
                Recherchez et ajoutez les personnes pour ces {selectedIds.size} audio(s).
              </p>

              {notReady.length > 0 && (
                <div style={{ marginBottom: "1rem", padding: "10px 12px", background: "rgba(255,80,0,0.12)", border: "1px solid rgba(255,80,0,0.3)", borderRadius: "6px", fontSize: "0.82rem" }}>
                  <strong style={{ color: "var(--color-error)" }}>⚠️ {notReady.length} audio(s) non normalisé(s)</strong>
                  <ul style={{ margin: "4px 0 0", paddingLeft: "1.2rem", color: "var(--color-error)" }}>
                    {notReady.map(a => (
                      <li key={a.id}>{a.filename}{a.validation_error ? ` — ${a.validation_error}` : " — en attente FFmpeg"}</li>
                    ))}
                  </ul>
                  <p style={{ margin: "6px 0 0", color: "var(--color-text-muted)" }}>
                    Cliquez "Retry" sur ces audios avant d'assigner, ou sélectionnez uniquement les audios avec le point vert.
                  </p>
                </div>
              )}

              <MultiUserSelect
                users={users}
                selectedIds={transcripteurIds}
                onChange={setTranscripteurIds}
              />

              <div style={{ marginTop: "1rem", fontSize: "0.8rem", color: "var(--color-text-muted)" }}>
                {transcripteurIds.length === 0 && (
                  <div style={{ padding: "8px", background: "rgba(255,255,255,0.05)", borderRadius: "4px" }}>
                    ℹ️ Aucun collaborateur sélectionné : l'audio sera disponible en <strong>Libre Service</strong>.
                  </div>
                )}
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "2rem", paddingTop: "1rem", borderTop: "1px solid var(--color-outline)" }}>
                <button className="za-btn za-btn--ghost" onClick={() => { setActiveModal("none"); setTranscripteurIds([]); }}>Annuler</button>
                <button
                  className="za-btn za-btn--primary"
                  onClick={executeAssign}
                  disabled={notReady.length === selectedIds.size}
                  title={notReady.length === selectedIds.size ? "Tous les audios sélectionnés doivent être normalisés d'abord" : undefined}
                >
                  Valider l'équipe
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {activeModal === "report" && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 200 }}>
          <div className="za-glass" style={{ padding: "2rem", borderRadius: "1rem", width: "460px" }}>
            <h3 style={{ marginTop: 0 }}>Résultat de l'assignation</h3>
            {assignBatch.status === "processing" ? (
              <p style={{ color: "var(--color-text-muted)" }}>En cours... ({assignBatch.progress}/{assignBatch.total})</p>
            ) : (
              <>
                {(() => {
                  const successes = assignBatch.results.filter(r => r.success);
                  const failures = assignBatch.results.filter(r => !r.success);
                  return (
                    <>
                      {successes.length > 0 && (
                        <p style={{ color: "var(--color-success)", fontWeight: 700 }}>
                          {successes.length} assignation(s) réussie(s).
                        </p>
                      )}
                      {failures.length > 0 && (
                        <div>
                          <p style={{ color: "var(--color-error)", fontWeight: 700, marginBottom: "0.5rem" }}>
                            {failures.length} échec(s) — ces audios ne peuvent pas être assignés :
                          </p>
                          <ul style={{ margin: 0, paddingLeft: "1.2rem", fontSize: "0.85rem", color: "var(--color-error)" }}>
                            {failures.map(r => (
                              <li key={r.id} style={{ marginBottom: "4px" }}>
                                Audio #{r.id} : {r.error || "Erreur inconnue"}
                              </li>
                            ))}
                          </ul>
                          <p style={{ fontSize: "0.8rem", color: "var(--color-text-muted)", marginTop: "0.75rem" }}>
                            Les audios doivent être normalisés par le worker FFmpeg avant d'être assignés. Vérifiez que le service est en ligne.
                          </p>
                        </div>
                      )}
                    </>
                  );
                })()}
                <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "1.5rem" }}>
                  <button className="za-btn za-btn--primary" onClick={() => setActiveModal("none")}>Fermer</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {activeModal === "delete-project" && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 200 }}>
          <div className="za-glass" style={{ padding: "2rem", borderRadius: "1rem", width: "420px" }}>
            <h3 style={{ marginTop: 0, color: "var(--color-error)" }}>Supprimer le projet</h3>
            <p>
              Vous êtes sur le point de supprimer <strong>{projectDetail?.name || `le projet #${projectId}`}</strong> ainsi que tous ses fichiers audio.
            </p>
            <p style={{ fontSize: "0.85rem", color: "var(--color-text-muted)" }}>
              Cette action est <strong>irréversible</strong>. Les audios transcrit(s) ou validé(s) bloquent la suppression.
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "1.5rem" }}>
              <button
                className="za-btn za-btn--ghost"
                onClick={() => setActiveModal("none")}
                disabled={deleteProjectLoading}
              >
                Annuler
              </button>
              <button
                className="za-btn za-btn--primary"
                style={{ background: "var(--color-error)", border: "none" }}
                onClick={handleDeleteProject}
                disabled={deleteProjectLoading}
              >
                {deleteProjectLoading ? "Suppression..." : "Confirmer la suppression"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
