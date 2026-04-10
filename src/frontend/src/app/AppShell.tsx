import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useTheme } from "../theme/ThemeContext";
import type { AppRole } from "../types/rbac";
import { ROLE_NAVIGATION, type AppRouteId } from "./navigation";
import {
  AdminDashboard,
  ExpertDashboard,
  ManagerDashboard,
  TranscriberDashboard,
} from "../features/dashboard/RoleDashboards";
import { NewProjectWizard } from "../features/project-wizard/NewProjectWizard";
import { ProjectDetailManager } from "../features/projects/ProjectDetailManager";

type Notification = {
  id: string;
  title: string;
  body: string;
};

const NOTIFICATIONS: Notification[] = [
  { id: "n1", title: "Validation en attente", body: "21 transcriptions attendent une décision manager." },
  { id: "n2", title: "Cycle ML prêt", body: "Seuil Golden Set atteint, cycle LoRA prêt au lancement." },
  { id: "n3", title: "Nouveau commentaire", body: "Un retour de rework a été ajouté sur Interview_042.wav." },
];

function roleTitle(role: AppRole): string {
  if (role === "admin") return "Admin";
  if (role === "manager") return "Manager";
  if (role === "expert") return "Expert";
  return "Transcripteur";
}

export function AppShell({
  role,
  username,
  onSignout,
  legacyEditor,
}: {
  role: AppRole;
  username: string;
  onSignout: () => void;
  legacyEditor: ReactNode;
}) {
  const { mode, toggleMode } = useTheme();
  const nav = useMemo(() => ROLE_NAVIGATION[role], [role]);
  
  // Adjusted mapping for active route IDs based on navigation.ts
  const initialRoute = (nav[0]?.id as AppRouteId) || "legacy-editor";
  const [activeRoute, setActiveRoute] = useState<AppRouteId>(initialRoute);
  
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [isNotificationsOpen, setNotificationsOpen] = useState(false);
  const [managerRefreshKey, setManagerRefreshKey] = useState(0);

  const handleViewProject = (id: number) => {
    setSelectedProjectId(id);
    setActiveRoute("project-detail");
  };

  const handleBackToDashboard = () => {
    setSelectedProjectId(null);
    setActiveRoute(initialRoute);
    setManagerRefreshKey((prev) => prev + 1);
  };

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "var(--color-bg)" }}>
      {/* 1. Sidebar (Floating Glass) */}
      <aside
        className="za-glass"
        style={{
          width: "280px",
          position: "fixed",
          top: "var(--spacing-4)",
          left: "var(--spacing-4)",
          bottom: "var(--spacing-4)",
          borderRadius: "var(--radius-lg)",
          zIndex: 100,
          display: "flex",
          flexDirection: "column",
          padding: "var(--spacing-6)",
          border: "1px solid var(--color-outline-ghost)",
        }}
      >
        <div style={{ marginBottom: "var(--spacing-8)" }}>
          <h1
            style={{
              fontFamily: "var(--font-headline)",
              fontSize: "1.5rem",
              fontWeight: 900,
              margin: 0,
              color: "var(--color-primary)",
              letterSpacing: "-0.02em",
            }}
          >
            ZachAI
          </h1>
          <div style={{ fontSize: "0.75rem", fontWeight: 700, opacity: 0.6, textTransform: "uppercase", marginTop: "4px" }}>
            {roleTitle(role)}
          </div>
        </div>

        <nav style={{ flex: 1 }}>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: "8px" }}>
            {nav.map((item) => {
              const isActive = activeRoute === item.id;
              return (
                <li key={item.id}>
                  <button
                    onClick={() => {
                      setActiveRoute(item.id as AppRouteId);
                      setSelectedProjectId(null);
                    }}
                    className="za-btn za-btn--ghost"
                    style={{
                      width: "100%",
                      textAlign: "left",
                      border: "none",
                      background: isActive ? "var(--color-primary-soft)" : "transparent",
                      color: isActive ? "var(--color-primary)" : "var(--color-text)",
                      padding: "12px 16px",
                      borderRadius: "var(--radius-md)",
                      fontWeight: isActive ? 700 : 500,
                      boxShadow: isActive ? "var(--glow-primary)" : "none",
                    }}
                  >
                    {item.label}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <div style={{ marginTop: "auto", paddingTop: "var(--spacing-6)" }}>
          <div
            style={{
              padding: "var(--spacing-4)",
              background: "var(--color-surface-hi)",
              borderRadius: "var(--radius-md)",
              marginBottom: "var(--spacing-4)",
            }}
          >
            <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "4px", overflow: "hidden", textOverflow: "ellipsis" }}>{username}</div>
            <div style={{ fontSize: "0.75rem", color: "var(--color-text-muted)" }}>{role === "admin" ? "Super Admin" : role}</div>
          </div>
          <div style={{ display: "grid", gap: "8px" }}>
            <button
              onClick={toggleMode}
              className="za-btn za-btn--ghost"
              style={{ border: "none", width: "100%", textAlign: "left", padding: "8px 12px" }}
            >
              Mode {mode === "dark" ? "Clair" : "Sombre"}
            </button>
            <button
              onClick={onSignout}
              className="za-btn za-btn--ghost"
              style={{ border: "none", width: "100%", textAlign: "left", color: "var(--color-error)", padding: "8px 12px" }}
            >
              Déconnexion
            </button>
          </div>
        </div>
      </aside>

      {/* 2. Main Content */}
      <main
        style={{
          flex: 1,
          marginLeft: "312px", 
          padding: "var(--spacing-8)",
          minWidth: 0,
        }}
      >
        <header
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "var(--spacing-8)",
          }}
        >
          <h2 style={{ margin: 0, fontFamily: "var(--font-headline)", fontSize: "1.75rem", fontWeight: 800 }}>
            {nav.find((n) => n.id === activeRoute)?.label || "ZachAI"}
          </h2>
          <div style={{ display: "flex", gap: "var(--spacing-4)" }}>
            <button
              className="za-btn za-btn--ghost"
              onClick={() => setNotificationsOpen(!isNotificationsOpen)}
              style={{ position: "relative", border: "none" }}
            >
              Notifications ({NOTIFICATIONS.length})
              <span
                style={{
                  position: "absolute",
                  top: 0,
                  right: 0,
                  background: "var(--color-error)",
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                }}
              />
            </button>
          </div>
        </header>

        <section>
          {/* Unified route mapping */}
          {(activeRoute === "dashboard" || activeRoute === "dashboard-admin") && role === "admin" ? <AdminDashboard /> : null}
          
          {(activeRoute === "dashboard" || activeRoute === "dashboard-manager") && role === "manager" ? (
            <ManagerDashboard
              onCreateProject={() => setActiveRoute("project-wizard" as AppRouteId)}
              onViewProject={handleViewProject}
              refreshKey={managerRefreshKey}
            />
          ) : null}

          {activeRoute === "project-wizard" && role === "manager" ? (
            <NewProjectWizard
              onCancel={handleBackToDashboard}
              onComplete={handleBackToDashboard}
            />
          ) : null}

          {activeRoute === "project-detail" && selectedProjectId ? (
            <ProjectDetailManager
              projectId={selectedProjectId}
              onBack={handleBackToDashboard}
            />
          ) : null}

          {activeRoute === "dashboard" && role === "expert" ? <ExpertDashboard /> : null}
          {activeRoute === "dashboard" && role === "transcriber" ? <TranscriberDashboard /> : null}

          {activeRoute === "legacy-editor" ? legacyEditor : null}
        </section>
      </main>

      {/* 3. Notifications Panel (Glass overlay) */}
      {isNotificationsOpen ? (
        <div
          onClick={() => setNotificationsOpen(false)}
          style={{ position: "fixed", inset: 0, zIndex: 200, background: "rgba(0,0,0,0.2)" }}
        >
          <aside
            onClick={(e) => e.stopPropagation()}
            className="za-glass"
            style={{
              position: "absolute",
              top: "var(--spacing-4)",
              right: "var(--spacing-4)",
              width: "360px",
              maxHeight: "calc(100vh - 32px)",
              borderRadius: "var(--radius-lg)",
              padding: "var(--spacing-6)",
              display: "flex",
              flexDirection: "column",
              boxShadow: "0 20px 40px rgba(0,0,0,0.3)",
              border: "1px solid var(--color-outline-ghost)",
            }}
          >
            <h3 style={{ margin: "0 0 var(--spacing-4)", fontSize: "1.1rem", fontWeight: 800 }}>Notifications</h3>
            <div style={{ display: "grid", gap: "12px", overflowY: "auto" }}>
              {NOTIFICATIONS.map((notice) => (
                <article
                  key={notice.id}
                  style={{
                    padding: "var(--spacing-4)",
                    background: "var(--color-surface-hi)",
                    borderRadius: "var(--radius-md)",
                  }}
                >
                  <h4 style={{ margin: 0, fontSize: "0.95rem", fontWeight: 700 }}>{notice.title}</h4>
                  <p style={{ margin: "var(--spacing-2) 0 0", color: "var(--color-text-muted)", fontSize: "0.85rem" }}>
                    {notice.body}
                  </p>
                </article>
              ))}
            </div>
          </aside>
        </div>
      ) : null}
    </div>
  );
}
