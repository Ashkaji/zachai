import { 
  LayoutDashboard, 
  Layers, 
  ListTodo, 
  CheckSquare, 
  FolderPlus, 
  FileEdit, 
  Palette 
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
  | "playground";

export type NavItem = {
  id: AppRouteId;
  label: string;
  description: string;
  icon: React.ElementType;
};

const BASE_ITEMS: NavItem[] = [
  { id: "legacy-editor", label: "Éditeur hérité", description: "Migration progressive", icon: FileEdit }
];

export const ROLE_NAVIGATION: Record<AppRole, NavItem[]> = {
  admin: [
    { id: "dashboard-admin", label: "Dashboard Admin", description: "Supervision globale", icon: LayoutDashboard },
    { id: "playground", label: "Playground UI", description: "Validation Design Tokens", icon: Palette },
    ...BASE_ITEMS,
  ],
  manager: [
    { id: "dashboard-manager", label: "Dashboard Manager", description: "Portefeuille projets", icon: Layers },
    { id: "project-wizard", label: "Nouveau projet", description: "Nature, labels, audios, assignation", icon: FolderPlus },
    ...BASE_ITEMS,
  ],
  transcriber: [
    { id: "dashboard-transcriber", label: "Dashboard Transcripteur", description: "File de tâches assignées", icon: ListTodo },
    ...BASE_ITEMS,
  ],
  expert: [
    { id: "dashboard-expert", label: "Dashboard Expert", description: "Réconciliation & Golden Set", icon: CheckSquare },
    ...BASE_ITEMS,
  ],
};
