/**
 * Editor copy — lightweight locale split (Story 14.1).
 * Prefer adding new strings here over scattering literals in components.
 */

export type EditorLocale = "en" | "fr";

const MESSAGES = {
  en: {
    restoreFailureTitle: "Restoration failed",
    restoreFailureDismiss: "Dismiss",
    restoreFailureByCode: {
      SNAPSHOT_NOT_FOUND: "Snapshot not found.",
      AUDIO_NOT_FOUND: "Audio document not found.",
      SNAPSHOT_FETCH_FAILED: "Could not load snapshot from storage.",
      SNAPSHOT_PAYLOAD_INVALID: "Snapshot data is invalid.",
      INTEGRITY_MISMATCH: "Snapshot did not match stored integrity.",
      STORAGE_ERROR: "Restoration failed due to a storage error.",
      UNKNOWN: "Document restoration failed.",
    } as Record<string, string>,
  },
  fr: {
    restoreFailureTitle: "Échec de la restauration",
    restoreFailureDismiss: "Fermer",
    restoreFailureByCode: {
      SNAPSHOT_NOT_FOUND: "Instantané introuvable.",
      AUDIO_NOT_FOUND: "Document audio introuvable.",
      SNAPSHOT_FETCH_FAILED: "Impossible de charger l’instantané depuis le stockage.",
      SNAPSHOT_PAYLOAD_INVALID: "Les données de l’instantané sont invalides.",
      INTEGRITY_MISMATCH: "L’instantané ne correspond pas à l’empreinte enregistrée.",
      STORAGE_ERROR: "Échec de la restauration pour cause d’erreur de stockage.",
      UNKNOWN: "La restauration du document a échoué.",
    } as Record<string, string>,
  },
} as const;

export function resolveEditorLocale(): EditorLocale {
  if (typeof navigator === "undefined") return "fr";
  const lang = (navigator.language || "fr").toLowerCase();
  return lang.startsWith("en") ? "en" : "fr";
}

export function editorStrings(locale: EditorLocale = resolveEditorLocale()) {
  return MESSAGES[locale];
}

export function remoteRestoreFailureFallback(code: string, locale: EditorLocale = resolveEditorLocale()): string {
  const table = MESSAGES[locale].restoreFailureByCode;
  const fallback = table.UNKNOWN ?? MESSAGES.en.restoreFailureByCode.UNKNOWN ?? "Document restoration failed.";
  return table[code] ?? fallback;
}
