import type { AppRole } from "../types/rbac";

export type AppRouteId =
  | "dashboard-admin"
  | "dashboard-manager"
  | "dashboard-transcriber"
  | "dashboard-expert"
  | "project-wizard"
  | "project-detail"
  | "legacy-editor";

export type NavItem = {
  id: AppRouteId;
  label: string;
  description: string;
};

const BASE_ITEMS: NavItem[] = [{ id: "legacy-editor", label: "Éditeur hérité", description: "Migration progressive" }];

export const ROLE_NAVIGATION: Record<AppRole, NavItem[]> = {
  admin: [
    { id: "dashboard-admin", label: "Dashboard Admin", description: "Supervision globale" },
    ...BASE_ITEMS,
  ],
  manager: [
    { id: "dashboard-manager", label: "Dashboard Manager", description: "Portefeuille projets" },
    {
      id: "project-wizard",
      label: "Nouveau projet",
      description: "Nature, labels, audios, assignation",
    },
    ...BASE_ITEMS,
  ],
  transcriber: [
    { id: "dashboard-transcriber", label: "Dashboard Transcripteur", description: "File de tâches assignées" },
    ...BASE_ITEMS,
  ],
  expert: [
    { id: "dashboard-expert", label: "Dashboard Expert", description: "Réconciliation & Golden Set" },
    ...BASE_ITEMS,
  ],
};
