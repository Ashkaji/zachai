import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { useAuth } from "react-oidc-context";
import { bearerForApi } from "../../auth/api-client";
import { ApiError } from "../../shared/api/zachaiApi";
import { Card } from "../../shared/ui/Primitives";
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
] as const;

export type UploadedAudioRow = {
  id: string;
  name: string;
  file: File;
  transcripteurId: string;
};

const STEPS = ["Nature et metadonnees", "Labels", "Audios", "Assignation"] as const;

type Props = {
  onCancel: () => void;
  onComplete: () => void;
};

function colorFromLabel(label: string): string {
  let hash = 0;
  for (let i = 0; i < label.length; i++) hash = (hash * 31 + label.charCodeAt(i)) >>> 0;
  const hue = hash % 360;
  return `hsl(${hue} 70% 55%)`;
}

export function NewProjectWizard({ onCancel, onComplete }: Props) {
  const auth = useAuth();
  const token = useMemo(() => bearerForApi(auth.user), [auth.user]);
  const fileInputId = useId();

  const [step, setStep] = useState(0);
  const [projectName, setProjectName] = useState("");
  const [description, setDescription] = useState("");
  const [objective, setObjective] = useState("");
  const [productionGoal, setProductionGoal] = useState<(typeof PRODUCTION_GOALS)[number]["id"]>("livre");
  const [nature, setNature] = useState<string>(NATURE_PRESETS[0]);
  const [customNature, setCustomNature] = useState("");
  const [labels, setLabels] = useState<string[]>(["Orateur", "Priere", "Citation biblique"]);
  const [labelDraft, setLabelDraft] = useState("");
  const [audios, setAudios] = useState<UploadedAudioRow[]>([]);

  const [natures, setNatures] = useState<NatureItem[]>([]);
  const [loadingNatures, setLoadingNatures] = useState(false);
  const [isSubmitting, setSubmitting] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [errorMessage, setErrorMessage] = useState<string>("");

  const effectiveNature = nature === "Autre (personnalise)" ? customNature.trim() || "-" : nature;

  useEffect(() => {
    if (!token) return;
    let active = true;
    setLoadingNatures(true);
    listNatures(token)
      .then((items) => {
        if (!active) return;
        setNatures(items);
      })
      .catch((error: unknown) => {
        if (!active) return;
        if (error instanceof ApiError && error.status === 403) {
          setErrorMessage("Le backend refuse l'acces aux natures pour cet utilisateur.");
          return;
        }
        setErrorMessage("Impossible de charger les natures backend.");
      })
      .finally(() => {
        if (active) setLoadingNatures(false);
      });
    return () => {
      active = false;
    };
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
          id: `${file.name}-${typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : String(Date.now())}`,
          name: file.name,
          file,
          transcripteurId: "",
        });
      }
      return [...prev, ...added];
    });
  }, []);

  const setTranscripteurId = useCallback((id: string, value: string) => {
    setAudios((prev) => prev.map((row) => (row.id === id ? { ...row, transcripteurId: value } : row)));
  }, []);

  const canAdvance = useMemo(() => {
    if (step === 0) return projectName.trim().length > 0 && effectiveNature !== "-";
    if (step === 1) return labels.length > 0;
    if (step === 2) return audios.length > 0;
    return true;
  }, [step, projectName, effectiveNature, labels.length, audios.length]);

  const handleFinish = useCallback(async () => {
    if (!token) {
      setErrorMessage("Utilisateur non authentifie.");
      return;
    }
    if (audios.length === 0) {
      setErrorMessage("Ajoute au moins un audio.");
      return;
    }

    setSubmitting(true);
    setErrorMessage("");
    setStatusMessage("Creation de la nature/projet...");

    try {
      let natureId: number;
      const existing = natures.find((n) => n.name.toLowerCase() === effectiveNature.toLowerCase());
      if (existing) {
        natureId = existing.id;
      } else {
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
      }

      const project = await createProject(token, {
        name: projectName.trim(),
        description: description || undefined,
        nature_id: natureId,
        production_goal: productionGoal,
      });

      setStatusMessage("Upload et enregistrement des audios...");
      const uploadResult: Array<{ audioId: number; transcripteurId: string }> = [];
      for (const row of audios) {
        const req = await requestAudioUpload(token, project.id, {
          filename: row.file.name,
          content_type: row.file.type || "audio/mpeg",
        });

        const put = await fetch(req.presigned_url, {
          method: "PUT",
          body: row.file,
          headers: { "Content-Type": row.file.type || "audio/mpeg" },
        });
        if (!put.ok) {
          throw new Error(`Upload MinIO echoue pour ${row.file.name} (${put.status})`);
        }

        const registered = await registerAudio(token, project.id, req.object_key);
        uploadResult.push({ audioId: registered.id, transcripteurId: row.transcripteurId.trim() });
      }

      setStatusMessage("Assignation des transcripteurs...");
      for (const row of uploadResult) {
        if (!row.transcripteurId) continue;
        await assignAudio(token, project.id, row.audioId, row.transcripteurId);
      }

      setStatusMessage("Projet cree et synchronise avec le backend.");
      onComplete();
    } catch (error: unknown) {
      if (error instanceof ApiError) {
        setErrorMessage(`API: ${error.message}`);
      } else if (error instanceof Error) {
        setErrorMessage(error.message);
      } else {
        setErrorMessage("Erreur inattendue pendant la creation du projet.");
      }
    } finally {
      setSubmitting(false);
    }
  }, [token, audios, natures, effectiveNature, description, labels, projectName, productionGoal, onComplete]);

  return (
    <div>
      <div style={{ marginBottom: "var(--spacing-5)", display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "var(--spacing-3)" }}>
        <div>
          <h2 style={{ margin: 0, fontFamily: "var(--font-headline)", fontSize: "1.35rem" }}>Nouveau projet</h2>
          <p style={{ margin: "var(--spacing-2) 0 0", color: "var(--color-text-muted)", maxWidth: "700px" }}>
            Wizard connecte au backend: creation de nature/projet, upload MinIO, enregistrement audio et assignation.
          </p>
        </div>
        <button type="button" className="za-btn za-btn--ghost" onClick={onCancel}>Fermer</button>
      </div>

      <div className="za-stepper" role="list">
        {STEPS.map((label, index) => (
          <div key={label} role="listitem" className={`za-step ${index === step ? "za-step--active" : ""} ${index < step ? "za-step--done" : ""}`}>
            <span style={{ fontFamily: "var(--font-headline)", fontWeight: 700 }}>{index + 1}</span>
            <span>{label}</span>
          </div>
        ))}
      </div>

      {errorMessage ? <p style={{ color: "var(--color-error)", marginTop: 0 }}>{errorMessage}</p> : null}
      {statusMessage ? <p style={{ color: "var(--color-text-muted)", marginTop: 0 }}>{statusMessage}</p> : null}

      {step === 0 ? (
        <Card title="Nature et informations" subtitle="Natures backend + production_goal conforme API">
          <div style={{ display: "grid", gap: "var(--spacing-4)" }}>
            <div>
              <label className="za-label" htmlFor="proj-name">Nom du projet</label>
              <input id="proj-name" className="za-input" value={projectName} onChange={(e) => setProjectName(e.target.value)} />
            </div>
            <div>
              <label className="za-label" htmlFor="proj-obj">Objectif metier (libre)</label>
              <input id="proj-obj" className="za-input" value={objective} onChange={(e) => setObjective(e.target.value)} />
            </div>
            <div>
              <label className="za-label" htmlFor="proj-goal">production_goal (backend)</label>
              <select id="proj-goal" className="za-select" value={productionGoal} onChange={(e) => setProductionGoal(e.target.value as (typeof PRODUCTION_GOALS)[number]["id"])}>
                {PRODUCTION_GOALS.map((g) => <option key={g.id} value={g.id}>{g.label}</option>)}
              </select>
            </div>
            <div>
              <label className="za-label" htmlFor="proj-nature">Nature du projet</label>
              <select id="proj-nature" className="za-select" value={nature} onChange={(e) => setNature(e.target.value)}>
                {NATURE_PRESETS.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
              {loadingNatures ? <p style={{ color: "var(--color-text-muted)", fontSize: "0.82rem" }}>Chargement des natures backend...</p> : null}
            </div>
            {nature === "Autre (personnalise)" ? (
              <div>
                <label className="za-label" htmlFor="proj-custom-nature">Libelle de la nature</label>
                <input id="proj-custom-nature" className="za-input" value={customNature} onChange={(e) => setCustomNature(e.target.value)} />
              </div>
            ) : null}
            <div>
              <label className="za-label" htmlFor="proj-desc">Description</label>
              <textarea id="proj-desc" className="za-textarea" value={description} onChange={(e) => setDescription(e.target.value)} />
            </div>
          </div>
        </Card>
      ) : null}

      {step === 1 ? (
        <Card title="Labels d'annotation" subtitle="Persistes dans la nature si creation necessaire">
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-2)", marginBottom: "var(--spacing-4)" }}>
            {labels.map((l) => (
              <span key={l} className="za-chip">
                {l}
                <button type="button" className="za-btn za-btn--ghost" style={{ padding: "2px 6px", fontSize: "0.75rem" }} onClick={() => removeLabel(l)}>Retirer</button>
              </span>
            ))}
          </div>
          <div style={{ display: "flex", gap: "var(--spacing-2)", flexWrap: "wrap", alignItems: "flex-end" }}>
            <div style={{ flex: "1 1 220px" }}>
              <label className="za-label" htmlFor="label-add">Nouveau label</label>
              <input id="label-add" className="za-input" value={labelDraft} onChange={(e) => setLabelDraft(e.target.value)} onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addLabel())} />
            </div>
            <button type="button" className="za-btn za-btn--primary" onClick={addLabel}>Ajouter</button>
          </div>
        </Card>
      ) : null}

      {step === 2 ? (
        <Card title="Import audio" subtitle="Upload presigned URL puis register cote backend">
          <div className="za-dropzone" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); onFilesPicked(e.dataTransfer.files); }}>
            <p style={{ margin: "0 0 var(--spacing-3)" }}>Glissez-deposez des fichiers ou selectionnez-les.</p>
            <input id={fileInputId} type="file" accept="audio/*,.mp3,.wav,.m4a,.flac,.ogg" multiple style={{ display: "none" }} onChange={(e) => onFilesPicked(e.target.files)} />
            <label htmlFor={fileInputId} className="za-btn za-btn--primary" style={{ cursor: "pointer", display: "inline-block" }}>Choisir des fichiers</label>
          </div>
          {audios.length > 0 ? (
            <ul style={{ margin: "var(--spacing-4) 0 0", paddingLeft: "1.25rem", color: "var(--color-text-muted)" }}>
              {audios.map((a) => <li key={a.id} style={{ marginBottom: "var(--spacing-1)" }}>{a.name}</li>)}
            </ul>
          ) : <p style={{ color: "var(--color-text-muted)", marginTop: "var(--spacing-3)" }}>Aucun fichier selectionne.</p>}
        </Card>
      ) : null}

      {step === 3 ? (
        <Card title="Assignation des taches" subtitle="Saisissez les IDs Keycloak (sub) des transcripteurs">
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "var(--spacing-3)" }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", padding: "10px 8px", borderBottom: "1px solid var(--color-outline)", color: "var(--color-text-muted)" }}>Audio</th>
                  <th style={{ textAlign: "left", padding: "10px 8px", borderBottom: "1px solid var(--color-outline)", color: "var(--color-text-muted)" }}>transcripteur_id</th>
                </tr>
              </thead>
              <tbody>
                {audios.map((row) => (
                  <tr key={row.id}>
                    <td style={{ padding: "12px 8px", borderBottom: "1px solid var(--color-outline)" }}>{row.name}</td>
                    <td style={{ padding: "12px 8px", borderBottom: "1px solid var(--color-outline)" }}>
                      <input className="za-input" style={{ maxWidth: "320px" }} placeholder="uuid-sub-keycloak" value={row.transcripteurId} onChange={(e) => setTranscripteurId(row.id, e.target.value)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : null}

      <div style={{ marginTop: "var(--spacing-6)", display: "flex", gap: "var(--spacing-3)", flexWrap: "wrap", justifyContent: "flex-end" }}>
        <button type="button" className="za-btn za-btn--ghost" disabled={step === 0 || isSubmitting} onClick={() => setStep((s) => Math.max(0, s - 1))}>Precedent</button>
        {step < STEPS.length - 1 ? (
          <button type="button" className="za-btn za-btn--primary" disabled={!canAdvance || isSubmitting} onClick={() => setStep((s) => s + 1)}>Suivant</button>
        ) : (
          <button type="button" className="za-btn za-btn--primary" disabled={audios.length === 0 || isSubmitting} onClick={() => void handleFinish()}>
            {isSubmitting ? "Synchronisation..." : "Creer le projet"}
          </button>
        )}
      </div>
    </div>
  );
}
