import {
  LayoutDashboard,
  Layers, 
  ListTodo, 
  CheckSquare, 
  FolderPlus,
  Palette,
  UserCircle
} from "lucide-react";
import type { AppRole } from "../types/rbac";

export type AppRouteId =
  | "dashboard-admin"
  | "dashboard-manager"
  | "dashboard-transcriber"
  | "dashboard-expert"
  | "project-wizard"
  | "project-detail"
  | "reconciliation-workspace"
  | "legacy-editor"
  | "playground"
  | "profile";

export type NavItem = {
  id: AppRouteId;
  label: string;
  description: string;
  icon: React.ElementType;
};

const PROFILE_ITEM: NavItem = { id: "profile", label: "Profil & Sécurité", description: "RGPD, préférences, export", icon: UserCircle };
// The transcription editor is opened contextually from a task ("Reprendre"),
// never as a standalone destination — so it has no top-level nav entry.

export const ROLE_NAVIGATION: Record<AppRole, NavItem[]> = {
  admin: [
    { id: "dashboard-admin", label: "Dashboard Admin", description: "Supervision globale", icon: LayoutDashboard },
    { id: "playground", label: "Playground UI", description: "Validation Design Tokens", icon: Palette },
    PROFILE_ITEM,
  ],
  manager: [
    { id: "dashboard-manager", label: "Mes Projets", description: "Portefeuille projets", icon: Layers },
    { id: "project-wizard", label: "Nouveau Projet", description: "Créer nature, labels, audios", icon: FolderPlus },
    PROFILE_ITEM,
  ],
  transcriber: [
    { id: "dashboard-transcriber", label: "Mes Tâches", description: "File de tâches assignées", icon: ListTodo },
    PROFILE_ITEM,
  ],
  expert: [
    { id: "dashboard-expert", label: "Réconciliation", description: "Réconciliation & Golden Set", icon: CheckSquare },
    PROFILE_ITEM,
  ],
};
