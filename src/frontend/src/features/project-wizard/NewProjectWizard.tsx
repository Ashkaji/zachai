import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { useAuth } from "react-oidc-context";
import { bearerForApi } from "../../auth/api-client";
import { ApiError } from "../../shared/api/zachaiApi";
import { Card } from "../../shared/ui/Primitives";
import { listUsers, type User } from "../dashboard/dashboardApi";
import {
  assignAudio,
  createNature,
  createProject,
  listNatures,
  registerAudio,
  requestAudioUpload,
  type NatureItem,
} from "./projectApi";

const NATURE_PRESETS = [
  "Camp Biblique",
  "Temoignage de conversion",
  "Campagne d'evangelisation",
  "Enseignements thematiques",
  "Autre (personnalise)",
] as const;

const PRODUCTION_GOALS = [
  { id: "livre", label: "Livre" },
  { id: "sous-titres", label: "Sous-titres" },
  { id: "dataset", label: "Dataset" },
  { id: "archive", label: "Archive" },
  { id: "autre", label: "Autre" },
] as const;

export type UploadedAudioRow = {
  id: string;
  name: string;
  file: File;
  transcripteurIds: string[];
  status: "pending" | "uploading" | "registering" | "assigning" | "complete" | "error";
  progress: number;
  errorDetail?: string;
};

const STEPS = ["Nature et metadonnees", "Labels", "Audios", "Assignation"] as const;

type Props = {
  onCancel: () => void;
  onComplete: () => void;
};

function colorFromLabel(label: string): string {
  let hash = 0;
  for (let i = 0; i < label.length; i++) hash = (hash * 31 + label.charCodeAt(i)) >>> 0;
  const color = (hash & 0x00FFFFFF).toString(16).toUpperCase();
  return "#" + "000000".substring(0, 6 - color.length) + color;
}

export function NewProjectWizard({ onCancel, onComplete }: Props) {
  const auth = useAuth();
  const token = useMemo(() => bearerForApi(auth.user), [auth.user]);
  const fileInputId = useId();

  const [step, setStep] = useState(0);
  const [projectName, setProjectName] = useState("");
  const [description, setDescription] = useState("");
  const [productionGoal, setProductionGoal] = useState<(typeof PRODUCTION_GOALS)[number]["id"]>("livre");
  const [nature, setNature] = useState<string>(NATURE_PRESETS[0]);
  const [customNature, setCustomNature] = useState("");
  const [labels, setLabels] = useState<string[]>(["Orateur", "Priere", "Citation biblique"]);
  const [labelDraft, setLabelDraft] = useState("");
  const [audios, setAudios] = useState<UploadedAudioRow[]>([]);

  const [natures, setNatures] = useState<NatureItem[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [isSubmitting, setSubmitting] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  // Once created, holds the project ID so back+forward doesn't recreate it
  const [createdProjectId, setCreatedProjectId] = useState<number | null>(null);
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [overallProgress, setOverallProgress] = useState(0);

  const effectiveNature = nature === "Autre (personnalise)" ? customNature.trim() || "-" : nature;

  useEffect(() => {
    if (!token) return;
    let active = true;

    Promise.all([
      listNatures(token),
      listUsers(token)
    ])
      .then(([natureItems, userItems]) => {
        if (!active) return;
        setNatures(natureItems);
        setUsers(userItems);
      })
      .catch(() => {
        if (!active) return;
        setErrorMessage("Impossible de charger les données initiales du backend.");
      });

    return () => { active = false; };
  }, [token]);

  const addLabel = useCallback(() => {
    const next = labelDraft.trim();
    if (!next || labels.includes(next)) return;
    setLabels((prev) => [...prev, next]);
    setLabelDraft("");
  }, [labelDraft, labels]);

  const removeLabel = useCallback((value: string) => {
    setLabels((prev) => prev.filter((l) => l !== value));
  }, []);

  const onFilesPicked = useCallback((list: FileList | null) => {
    if (!list?.length) return;
    setAudios((prev) => {
      const existing = new Set(prev.map((p) => p.name));
      const added: UploadedAudioRow[] = [];
      for (const file of Array.from(list)) {
        if (existing.has(file.name)) continue;
        existing.add(file.name);
        added.push({
          id: `${file.name}-${String(Date.now())}`,
          name: file.name,
          file,
          transcripteurIds: [],
          status: "pending",
          progress: 0,
        });
      }
      return [...prev, ...added];
    });
  }, []);

  // Remove a file from the import list (only before submission)
  const removeAudio = useCallback((id: string) => {
    setAudios((prev) => prev.filter((a) => a.id !== id));
  }, []);

  const addTranscripteur = useCallback((audioId: string, userId: string) => {
    if (!userId) return;
    setAudios((prev) => prev.map((row) => {
      if (row.id === audioId) {
        if (row.transcripteurIds.includes(userId)) return row;
        return { ...row, transcripteurIds: [...row.transcripteurIds, userId] };
      }
      return row;
    }));
  }, []);

  const removeTranscripteur = useCallback((audioId: string, userId: string) => {
    setAudios((prev) => prev.map((row) => (
      row.id === audioId
        ? { ...row, transcripteurIds: row.transcripteurIds.filter(id => id !== userId) }
        : row
    )));
  }, []);

  const canAdvance = useMemo(() => {
    if (step === 0) return projectName.trim().length > 0 && effectiveNature !== "-";
    if (step === 1) return labels.length > 0;
    if (step === 2) return audios.filter(a => a.status !== "error").length > 0;
    return true;
  }, [step, projectName, effectiveNature, labels.length, audios]);

  const updateAudioStatus = useCallback((id: string, status: UploadedAudioRow["status"], progress?: number, errorDetail?: string) => {
    setAudios((prev) => prev.map((a) => a.id === id ? { ...a, status, progress: progress ?? a.progress, errorDetail: errorDetail ?? a.errorDetail } : a));
  }, []);

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

  const handleFinish = useCallback(async () => {
    if (!token) return;
    setSubmitting(true);
    setErrorMessage("");
    setStatusMessage("Initialisation du projet...");
    setOverallProgress(0);

    try {
      let projectId = createdProjectId;

      // Skip nature/project creation if already done (back+forward guard)
      if (!projectId) {
        let natureId: number;
        const existing = natures.find((n) => n.name.toLowerCase() === effectiveNature.toLowerCase());
        if (existing) {
          natureId = existing.id;
        } else {
          try {
            const createdNature = await createNature(token, {
              name: effectiveNature,
              description: description || undefined,
              labels: labels.map((name) => ({
                name,
                color: colorFromLabel(name),
                is_speech: true,
                is_required: false,
              })),
            });
            natureId = createdNature.id;
          } catch {
            // Nature may already exist from a previous failed attempt — re-fetch and use it
            const freshNatures = await listNatures(token);
            setNatures(freshNatures);
            const found = freshNatures.find((n) => n.name.toLowerCase() === effectiveNature.toLowerCase());
            if (found) {
              natureId = found.id;
            } else {
              throw new Error(`Impossible de créer ou trouver la nature "${effectiveNature}"`);
            }
          }
        }

        const project = await createProject(token, {
          name: projectName.trim(),
          description: description || undefined,
          nature_id: natureId,
          production_goal: productionGoal,
        });
        projectId = project.id;
        setCreatedProjectId(projectId);
      }

      setStatusMessage("Traitement des audios...");
      // Only process files still pending (skip already completed or errored)
      const pendingAudios = audios.filter(a => a.status === "pending");
      const alreadyDone = audios.filter(a => a.status === "complete").length;
      let completedCount = alreadyDone;

      for (const row of pendingAudios) {
        try {
          updateAudioStatus(row.id, "uploading", 0);
          const req = await requestAudioUpload(token, projectId, {
            filename: row.file.name,
            content_type: row.file.type || "audio/mpeg",
          });

          await uploadToMinio(req.presigned_url, row.file, (p) => {
            updateAudioStatus(row.id, "uploading", p);
          });

          updateAudioStatus(row.id, "registering", 100);
          const registered = await registerAudio(token, projectId, req.object_key);

          if (row.transcripteurIds.length > 0) {
            if (registered.normalized_path && !registered.validation_error) {
              // Audio normalized — assign immediately
              updateAudioStatus(row.id, "assigning", 100);
              await assignAudio(token, projectId, registered.id, row.transcripteurIds);
            } else {
              // Audio not yet normalized — skip assignment, manager can assign from project view
              updateAudioStatus(row.id, "complete", 100, "Normalisé ultérieurement — assignez depuis la vue projet");
              completedCount++;
              setOverallProgress(Math.floor((completedCount / audios.length) * 100));
              continue;
            }
          }

          updateAudioStatus(row.id, "complete", 100);
          completedCount++;
          setOverallProgress(Math.floor((completedCount / audios.length) * 100));
        } catch (err) {
          const detail = err instanceof ApiError
            ? `${err.message} (HTTP ${err.status})`
            : err instanceof Error ? err.message : "Erreur inconnue";
          updateAudioStatus(row.id, "error", undefined, detail);
          // Continue with remaining audios instead of aborting
        }
      }

      const hasErrors = audios.some(a => a.status === "error") || pendingAudios.some(a => a.status === "error");
      if (hasErrors) {
        setErrorMessage("Certains fichiers ont rencontré des erreurs (indiqués en rouge). Le projet a été créé — vous pouvez réessayer les fichiers en attente.");
      } else {
        setStatusMessage("Projet créé avec succès !");
        setIsSuccess(true);
      }
    } catch (error: unknown) {
      if (error instanceof ApiError) {
        setErrorMessage(`API: ${error.message} (HTTP ${error.status})`);
      } else {
        setErrorMessage(error instanceof Error ? error.message : "Erreur inconnue");
      }
    } finally {
      setSubmitting(false);
    }
  }, [token, audios, natures, effectiveNature, description, labels, projectName, productionGoal, createdProjectId, updateAudioStatus]);

  if (isSuccess) {
    return (
      <div style={{ textAlign: "center", padding: "var(--spacing-8) 0" }}>
        <div style={{ fontSize: "4rem", marginBottom: "var(--spacing-4)" }}>✅</div>
        <h2 style={{ fontFamily: "var(--font-headline)" }}>Projet créé avec succès !</h2>
        <p style={{ color: "var(--color-text-muted)", marginBottom: "var(--spacing-6)" }}>
          Le projet "{projectName}" a été configuré et les audios ont été uploadés.
        </p>
        <button className="za-btn za-btn--primary" onClick={onComplete}>Accéder au tableau de bord</button>
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: "var(--spacing-5)", display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "var(--spacing-3)" }}>
        <div>
          <h2 style={{ margin: 0, fontFamily: "var(--font-headline)", fontSize: "1.35rem" }}>Nouveau projet</h2>
          <p style={{ margin: "var(--spacing-2) 0 0", color: "var(--color-text-muted)", maxWidth: "700px" }}>
            Wizard avec suivi d'upload granulaire et assignation multiple.
          </p>
        </div>
        <button type="button" className="za-btn za-btn--ghost" onClick={onCancel} disabled={isSubmitting}>Fermer</button>
      </div>

      <div className="za-stepper" role="list">
        {STEPS.map((label, index) => (
          <div key={label} role="listitem" className={`za-step ${index === step ? "za-step--active" : ""} ${index < step ? "za-step--done" : ""}`}>
            <span style={{ fontFamily: "var(--font-headline)", fontWeight: 700 }}>{index + 1}</span>
            <span>{label}</span>
          </div>
        ))}
      </div>

      {errorMessage ? <div style={{ color: "var(--color-error)", background: "rgba(255,0,0,0.1)", padding: "12px", borderRadius: "8px", marginBottom: "var(--spacing-4)" }}>{errorMessage}</div> : null}

      {isSubmitting && (
        <div style={{ marginBottom: "var(--spacing-6)", background: "var(--color-surface-low)", padding: "var(--spacing-4)", borderRadius: "var(--radius-md)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "var(--spacing-2)", fontWeight: 600 }}>
            <span>{statusMessage}</span>
            <span>{overallProgress}%</span>
          </div>
          <div style={{ height: "10px", background: "var(--color-outline)", borderRadius: "5px", overflow: "hidden" }}>
            <div style={{ width: `${overallProgress}%`, height: "100%", background: "var(--color-primary)", transition: "width 0.3s" }} />
          </div>
        </div>
      )}

      {step === 0 ? (
        <Card title="Nature et informations">
          <div style={{ display: "grid", gap: "var(--spacing-4)" }}>
            <div>
              <label className="za-label">Nom du projet</label>
              <input className="za-input" value={projectName} onChange={(e) => setProjectName(e.target.value)} disabled={isSubmitting} />
            </div>
            <div>
              <label className="za-label">Nature du projet</label>
              <select className="za-select" value={nature} onChange={(e) => setNature(e.target.value)} disabled={isSubmitting}>
                {NATURE_PRESETS.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
            {nature === "Autre (personnalise)" && (
              <div>
                <label className="za-label">Libelle de la nature</label>
                <input className="za-input" value={customNature} onChange={(e) => setCustomNature(e.target.value)} disabled={isSubmitting} />
              </div>
            )}
            <div>
              <label className="za-label">Objectif de production</label>
              <select className="za-select" value={productionGoal} onChange={(e) => setProductionGoal(e.target.value as typeof productionGoal)} disabled={isSubmitting}>
                {PRODUCTION_GOALS.map((g) => <option key={g.id} value={g.id}>{g.label}</option>)}
              </select>
            </div>
            <div>
              <label className="za-label">Description</label>
              <textarea className="za-textarea" value={description} onChange={(e) => setDescription(e.target.value)} disabled={isSubmitting} />
            </div>
          </div>
        </Card>
      ) : null}

      {step === 1 ? (
        <Card title="Labels d'annotation">
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-2)", marginBottom: "var(--spacing-4)" }}>
            {labels.map((l) => (
              <span key={l} className="za-chip">
                {l}
                {!isSubmitting && <button type="button" className="za-btn za-btn--ghost" style={{ padding: "0 4px" }} onClick={() => removeLabel(l)}>&times;</button>}
              </span>
            ))}
          </div>
          <div style={{ display: "flex", gap: "var(--spacing-2)" }}>
            <input className="za-input" value={labelDraft} onChange={(e) => setLabelDraft(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addLabel()} placeholder="Ajouter un label..." disabled={isSubmitting} />
            <button type="button" className="za-btn za-btn--primary" onClick={addLabel} disabled={isSubmitting}>Ajouter</button>
          </div>
        </Card>
      ) : null}

      {step === 2 ? (
        <Card title="Import audio">
          {!isSubmitting && (
            <div className="za-dropzone" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); onFilesPicked(e.dataTransfer.files); }}>
              <p>Glissez-deposez des fichiers audio ici</p>
              <input id={fileInputId} type="file" multiple accept="audio/*" style={{ display: "none" }} onChange={(e) => onFilesPicked(e.target.files)} />
              <label htmlFor={fileInputId} className="za-btn za-btn--primary" style={{ cursor: "pointer" }}>Choisir des fichiers</label>
            </div>
          )}
          <div style={{ marginTop: "var(--spacing-4)" }}>
            {audios.map((a) => (
              <div key={a.id} style={{ marginBottom: "var(--spacing-3)", padding: "12px", border: `1px solid ${a.status === "error" ? "var(--color-error)" : "var(--color-outline)"}`, borderRadius: "8px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px", fontSize: "0.9rem" }}>
                  <span style={{ fontWeight: 500, flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.name}</span>
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-2)", flexShrink: 0, marginLeft: "var(--spacing-2)" }}>
                    <span style={{ color: a.status === "error" ? "var(--color-error)" : "var(--color-text-muted)", fontSize: "0.8rem" }}>
                      {a.status === "pending" ? "Prêt" : a.status === "uploading" ? `Upload ${a.progress}%` : a.status}
                    </span>
                    {!isSubmitting && (a.status === "pending" || a.status === "error") && (
                      <button
                        type="button"
                        title="Retirer ce fichier"
                        onClick={() => removeAudio(a.id)}
                        style={{ background: "none", border: "none", cursor: "pointer", color: "var(--color-text-muted)", fontSize: "1rem", lineHeight: 1, padding: "2px 4px" }}
                      >
                        ✕
                      </button>
                    )}
                  </div>
                </div>
                {a.status !== "pending" && a.status !== "complete" && a.status !== "error" && (
                  <div style={{ height: "4px", background: "var(--color-outline)", borderRadius: "2px", overflow: "hidden" }}>
                    <div style={{ width: `${a.progress}%`, height: "100%", background: "var(--color-primary)", transition: "width 0.2s" }} />
                  </div>
                )}
                {a.status === "complete" && <div style={{ fontSize: "0.75rem", color: "var(--color-success)", marginTop: "4px" }}>{a.errorDetail ?? "Fichier enregistré"}</div>}
                {a.status === "error" && a.errorDetail && <div style={{ fontSize: "0.75rem", color: "var(--color-error)", marginTop: "4px" }}>{a.errorDetail}</div>}
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      {step === 3 ? (
        <Card title="Assignation de l'équipe">
          {createdProjectId && (
            <div style={{ marginBottom: "var(--spacing-3)", padding: "10px 14px", background: "rgba(0,160,255,0.08)", border: "1px solid rgba(0,160,255,0.25)", borderRadius: "6px", fontSize: "0.82rem", display: "flex", justifyContent: "space-between", alignItems: "center", gap: "var(--spacing-3)" }}>
              <span style={{ color: "var(--color-text-muted)" }}>
                ℹ️ Ce projet a déjà été créé lors d'une tentative précédente (ID {createdProjectId}). Seuls les fichiers restants seront soumis. Si vous souhaitez recommencer depuis zéro, fermez et rouvrez le wizard.
              </span>
            </div>
          )}
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", padding: "12px 8px", borderBottom: "2px solid var(--color-outline)" }}>Audio</th>
                  <th style={{ textAlign: "left", padding: "12px 8px", borderBottom: "2px solid var(--color-outline)" }}>Équipe</th>
                </tr>
              </thead>
              <tbody>
                {audios.map((row) => (
                  <tr key={row.id}>
                    <td style={{ padding: "12px 8px", borderBottom: "1px solid var(--color-outline)" }}>{row.name}</td>
                    <td style={{ padding: "12px 8px", borderBottom: "1px solid var(--color-outline)" }}>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-2)", alignItems: "center" }}>
                        {row.transcripteurIds.map(userId => {
                          const u = users.find(user => user.id === userId);
                          return (
                            <span key={userId} className="za-chip" style={{ background: "var(--color-primary-soft)", color: "var(--color-primary-text)" }}>
                              {u?.username || userId}
                              {!isSubmitting && <button type="button" style={{ background: "none", border: "none", marginLeft: "6px", cursor: "pointer", fontWeight: "bold" }} onClick={() => removeTranscripteur(row.id, userId)}>&times;</button>}
                            </span>
                          );
                        })}
                        {!isSubmitting && (
                          <select className="za-select za-select--sm" style={{ width: "auto" }} value="" onChange={(e) => addTranscripteur(row.id, e.target.value)}>
                            <option value="">+ Ajouter transcripteur...</option>
                            {users.filter(u => !row.transcripteurIds.includes(u.id)).map(u => (
                              <option key={u.id} value={u.id}>{u.username}</option>
                            ))}
                          </select>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p style={{ marginTop: "var(--spacing-3)", fontSize: "0.8rem", color: "var(--color-text-muted)" }}>
            L'assignation requiert que la normalisation FFmpeg soit terminée. Si un audio n'est pas encore prêt, assignez-le depuis la vue projet après création.
          </p>
        </Card>
      ) : null}

      <div style={{ marginTop: "var(--spacing-6)", display: "flex", gap: "var(--spacing-3)", justifyContent: "flex-end" }}>
        <button
          type="button"
          className="za-btn za-btn--ghost"
          disabled={step === 0 || isSubmitting}
          onClick={() => { setErrorMessage(""); setStep((s) => s - 1); }}
        >
          Precedent
        </button>
        {step < STEPS.length - 1 ? (
          <button type="button" className="za-btn za-btn--primary" disabled={!canAdvance || isSubmitting} onClick={() => setStep((s) => s + 1)}>Suivant</button>
        ) : createdProjectId && audios.filter(a => a.status === "pending").length === 0 ? (
          // Project created, no more pending files — offer direct completion
          <button type="button" className="za-btn za-btn--primary" onClick={() => setIsSuccess(true)}>
            Terminer
          </button>
        ) : (
          <button
            type="button"
            className="za-btn za-btn--primary"
            disabled={audios.filter(a => a.status === "pending").length === 0 || isSubmitting}
            onClick={() => void handleFinish()}
          >
            {isSubmitting ? "En cours..." : createdProjectId ? "Réessayer les fichiers en attente" : "Creer le projet"}
          </button>
        )}
      </div>
    </div>
  );
}
