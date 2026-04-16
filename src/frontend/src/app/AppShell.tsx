import { lazy, Suspense, useMemo, useState, useEffect } from "react";
import type { ReactNode } from "react";
import { useTheme } from "../theme/ThemeContext";
import type { AppRole } from "../types/rbac";
import { ROLE_NAVIGATION, type AppRouteId } from "./navigation";
import { useNotifications } from "../shared/notifications/NotificationContext";
import { ChevronLeft, ChevronRight, LogOut, Moon, Sun } from "lucide-react";

const AdminDashboard = lazy(() =>
  import("../features/dashboard/RoleDashboards").then((m) => ({ default: m.AdminDashboard })),
);
const ExpertDashboard = lazy(() =>
  import("../features/dashboard/RoleDashboards").then((m) => ({ default: m.ExpertDashboard })),
);
const ManagerDashboard = lazy(() =>
  import("../features/dashboard/RoleDashboards").then((m) => ({ default: m.ManagerDashboard })),
);
const TranscriberDashboard = lazy(() =>
  import("../features/dashboard/RoleDashboards").then((m) => ({ default: m.TranscriberDashboard })),
);
const NewProjectWizard = lazy(() =>
  import("../features/project-wizard/NewProjectWizard").then((m) => ({ default: m.NewProjectWizard })),
);
const ProjectDetailManager = lazy(() =>
  import("../features/projects/ProjectDetailManager").then((m) => ({ default: m.ProjectDetailManager })),
);
const Playground = lazy(() => import("../dev/Playground").then((m) => ({ default: m.Playground })));
const ReconciliationWorkspace = lazy(() =>
  import("../features/reconciliation/ReconciliationWorkspace").then((m) => ({
    default: m.ReconciliationWorkspace,
  })),
);
const ProfileCenter = lazy(() =>
  import("../features/profile/ProfileCenter").then((m) => ({ default: m.ProfileCenter })),
);

function RouteFallback() {
  return (
    <p style={{ padding: "2rem", margin: 0, color: "var(--color-text-muted)" }}>Chargement de la page…</p>
  );
}

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
  const { activeNotifications, dismissNotification } = useNotifications();
  const nav = useMemo(() => ROLE_NAVIGATION[role], [role]);
  
  // Adjusted mapping for active route IDs based on navigation.ts
  const initialRoute = (nav[0]?.id as AppRouteId) || "legacy-editor";
  const [activeRoute, setActiveRoute] = useState<AppRouteId>(initialRoute);
  
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [isNotificationsOpen, setNotificationsOpen] = useState(false);
  const [managerRefreshKey, setManagerRefreshKey] = useState(0);

  // Responsive Sidebar State
  const [isCollapsed, setIsCollapsed] = useState(false);

  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < 1024) {
        setIsCollapsed(true);
      } else {
        setIsCollapsed(false);
      }
    };
    // Initial check
    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const handleViewProject = (id: number) => {
    setSelectedProjectId(id);
    setActiveRoute("project-detail");
  };

  const handleBackToDashboard = () => {
    setSelectedProjectId(null);
    setActiveRoute(initialRoute);
    setManagerRefreshKey((prev) => prev + 1);
  };

  const hasCritical = activeNotifications.some(n => n.tier === "critical");
  
  const sidebarWidth = isCollapsed ? 88 : 280;
  const currentNavItem = nav.find((n) => n.id === activeRoute);
  const activeLabel = currentNavItem?.label || "ZachAI";

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "var(--color-bg)" }}>
      {/* 1. Sidebar (Floating Glass) */}
      <aside
        className="za-glass"
        style={{
          width: `${sidebarWidth}px`,
          position: "fixed",
          top: "var(--spacing-4)",
          left: "var(--spacing-4)",
          bottom: "var(--spacing-4)",
          borderRadius: "var(--radius-lg)",
          zIndex: 100,
          display: "flex",
          flexDirection: "column",
          padding: isCollapsed ? "var(--spacing-4)" : "var(--spacing-6)",
          border: "none",
          boxShadow: "var(--glow-primary), 0 8px 32px rgba(0,0,0,0.1)",
          transition: "width 0.3s ease, padding 0.3s ease",
          overflow: "hidden"
        }}
      >
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "var(--spacing-8)" }}>
          <div style={{ opacity: isCollapsed ? 0 : 1, transition: "opacity 0.2s ease", whiteSpace: "nowrap" }}>
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
          
          <button 
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="za-btn za-btn--ghost"
            style={{ padding: "4px", minWidth: "32px", height: "32px", display: "flex", alignItems: "center", justifyContent: "center", border: "none" }}
            aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {isCollapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
          </button>
        </div>

        <nav style={{ flex: 1 }}>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: "8px" }}>
            {nav.map((item) => {
              const isActive = activeRoute === item.id;
              const Icon = item.icon;
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
                      border: "none",
                      background: isActive ? "var(--color-primary-soft)" : "transparent",
                      color: isActive ? "var(--color-primary)" : "var(--color-text)",
                      padding: isCollapsed ? "12px" : "12px 16px",
                      borderRadius: "var(--radius-md)",
                      fontWeight: isActive ? 700 : 500,
                      boxShadow: isActive ? "var(--glow-primary)" : "none",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: isCollapsed ? "center" : "flex-start",
                      gap: "12px",
                      transition: "all 0.2s ease"
                    }}
                    title={isCollapsed ? item.label : undefined}
                  >
                    <Icon size={20} strokeWidth={1.5} />
                    {!isCollapsed && <span style={{ whiteSpace: "nowrap" }}>{item.label}</span>}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <div style={{ marginTop: "auto", paddingTop: "var(--spacing-6)" }}>
          {!isCollapsed && (
            <div
              style={{
                padding: "var(--spacing-4)",
                background: "var(--color-surface-hi)",
                borderRadius: "var(--radius-md)",
                marginBottom: "var(--spacing-4)",
                whiteSpace: "nowrap"
              }}
            >
              <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "4px", overflow: "hidden", textOverflow: "ellipsis" }}>{username}</div>
              <div style={{ fontSize: "0.75rem", color: "var(--color-text-muted)" }}>{role === "admin" ? "Super Admin" : role}</div>
            </div>
          )}
          <div style={{ display: "grid", gap: "8px" }}>
            <button
              onClick={toggleMode}
              className="za-btn za-btn--ghost"
              style={{ 
                border: "none", 
                width: "100%", 
                padding: isCollapsed ? "12px" : "8px 12px",
                display: "flex",
                alignItems: "center",
                justifyContent: isCollapsed ? "center" : "flex-start",
                gap: "12px"
              }}
              title={`Mode ${mode === "dark" ? "Clair" : "Sombre"}`}
            >
              {mode === "dark" ? <Sun size={20} strokeWidth={1.5} /> : <Moon size={20} strokeWidth={1.5} />}
              {!isCollapsed && <span style={{ whiteSpace: "nowrap" }}>Mode {mode === "dark" ? "Clair" : "Sombre"}</span>}
            </button>
            <button
              onClick={onSignout}
              className="za-btn za-btn--ghost"
              style={{ 
                border: "none", 
                width: "100%", 
                color: "var(--color-error)", 
                padding: isCollapsed ? "12px" : "8px 12px",
                display: "flex",
                alignItems: "center",
                justifyContent: isCollapsed ? "center" : "flex-start",
                gap: "12px"
              }}
              title="Déconnexion"
            >
              <LogOut size={20} strokeWidth={1.5} />
              {!isCollapsed && <span style={{ whiteSpace: "nowrap" }}>Déconnexion</span>}
            </button>
          </div>
        </div>
      </aside>

      {/* 2. Main Content */}
      <main
        style={{
          flex: 1,
          marginLeft: `${sidebarWidth + 32}px`, 
          padding: "var(--spacing-8)",
          minWidth: 0,
          transition: "margin-left 0.3s ease"
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
          <div>
            <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--color-text-muted)", marginBottom: "4px", display: "flex", alignItems: "center", gap: "6px" }}>
              <span>Azure Flow</span>
              <span style={{ opacity: 0.5 }}>›</span>
              <span>{roleTitle(role)}</span>
            </div>
            <h2 style={{ margin: 0, fontFamily: "var(--font-headline)", fontSize: "1.75rem", fontWeight: 800, color: "var(--color-primary)" }}>
              {activeLabel}
            </h2>
          </div>
          
          <div style={{ display: "flex", gap: "var(--spacing-4)" }}>
            <button
              className="za-btn za-btn--ghost"
              onClick={() => setNotificationsOpen(!isNotificationsOpen)}
              style={{ position: "relative", border: "none", background: "var(--color-surface-low)" }}
            >
              Notifications ({activeNotifications.length})
              {activeNotifications.length > 0 && (
                <span
                  style={{
                    position: "absolute",
                    top: 0,
                    right: 0,
                    background: hasCritical ? "var(--color-error)" : "var(--color-primary)",
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                  }}
                />
              )}
            </button>
          </div>
        </header>

        <section>
          <Suspense fallback={<RouteFallback />}>
            {/* Unified route mapping — lazy chunks load on first visit */}
            {activeRoute === "dashboard-admin" && role === "admin" ? <AdminDashboard /> : null}

            {activeRoute === "dashboard-manager" && role === "manager" ? (
              <ManagerDashboard
                onCreateProject={() => setActiveRoute("project-wizard" as AppRouteId)}
                onViewProject={handleViewProject}
                refreshKey={managerRefreshKey}
              />
            ) : null}

            {activeRoute === "project-wizard" && role === "manager" ? (
              <NewProjectWizard onCancel={handleBackToDashboard} onComplete={handleBackToDashboard} />
            ) : null}

            {activeRoute === "project-detail" && selectedProjectId ? (
              <ProjectDetailManager projectId={selectedProjectId} onBack={handleBackToDashboard} />
            ) : null}

            {activeRoute === "dashboard-expert" && role === "expert" ? (
              <ExpertDashboard
                onReconcile={(audioId) => {
                  setSelectedProjectId(audioId); // Reusing as Audio ID for now
                  setActiveRoute("reconciliation-workspace");
                }}
              />
            ) : null}

            {activeRoute === "reconciliation-workspace" && (role === "expert" || role === "admin") ? (
              <ReconciliationWorkspace audioId={selectedProjectId!} onBack={handleBackToDashboard} />
            ) : null}
            {activeRoute === "dashboard-transcriber" && role === "transcriber" ? (
              <TranscriberDashboard />
            ) : null}

            {activeRoute === "profile" ? <ProfileCenter /> : null}
            {activeRoute === "legacy-editor" ? legacyEditor : null}
            {activeRoute === "playground" ? <Playground /> : null}
          </Suspense>
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
              boxShadow: "0 20px 40px rgba(0,0,0,0.3), var(--glow-primary)",
              border: "none",
            }}
          >
            <h3 style={{ margin: "0 0 var(--spacing-4)", fontSize: "1.1rem", fontWeight: 800 }}>Notifications</h3>
            <div style={{ display: "grid", gap: "12px", overflowY: "auto" }}>
              {activeNotifications.length === 0 ? (
                <p style={{ color: "var(--color-text-muted)", fontSize: "0.85rem", margin: 0 }}>Aucune notification.</p>
              ) : (
                activeNotifications.map((notice) => (
                  <article
                    key={notice.id}
                    style={{
                      padding: "var(--spacing-4)",
                      background: "var(--color-surface-hi)",
                      borderRadius: "var(--radius-md)",
                      borderLeft: notice.tier === "critical" ? "4px solid var(--color-error)" : "4px solid var(--color-primary)",
                      position: "relative"
                    }}
                  >
                    <button 
                      onClick={() => dismissNotification(notice.id)}
                      style={{ position: "absolute", top: "8px", right: "8px", background: "transparent", border: "none", color: "var(--color-text-muted)", cursor: "pointer" }}
                    >
                      ✕
                    </button>
                    <h4 style={{ margin: 0, fontSize: "0.95rem", fontWeight: 700 }}>{notice.title}</h4>
                    <p style={{ margin: "var(--spacing-2) 0 0", color: "var(--color-text-muted)", fontSize: "0.85rem" }}>
                      {notice.body}
                    </p>
                    <div style={{ fontSize: "0.7rem", color: "var(--color-text-muted)", marginTop: "var(--spacing-2)", opacity: 0.6 }}>
                      {new Date(notice.timestamp).toLocaleTimeString()}
                    </div>
                  </article>
                ))
              )}
            </div>
          </aside>
        </div>
      ) : null}
    </div>
  );
}
