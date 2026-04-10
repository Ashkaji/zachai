import { useAuth } from "react-oidc-context";
import { TranscriptionEditor } from "./editor/TranscriptionEditor";
import { AppShell } from "./app/AppShell";
import { ThemeProvider } from "./theme/ThemeContext";
import { resolveAppRole } from "./types/rbac";

export function App() {
  const auth = useAuth();
  const role = resolveAppRole(auth.user?.profile as Record<string, unknown> | undefined);
  const username = (auth.user?.profile.preferred_username as string | undefined) ?? auth.user?.profile.sub ?? "Utilisateur";

  if (auth.isLoading) {
    return <p style={{ padding: "2rem" }}>Chargement de l'authentification...</p>;
  }

  if (auth.error) {
    return (
      <div style={{ padding: "2rem", color: "#c00" }}>
        <p>Erreur OIDC : {auth.error.message}</p>
        <button onClick={() => auth.signinRedirect()}>Réessayer</button>
      </div>
    );
  }

  if (!auth.isAuthenticated) {
    return (
      <div style={{ padding: "2rem", textAlign: "center" }}>
        <h1 style={{ fontFamily: "var(--font-headline)" }}>ZachAI - Plateforme de Transcription</h1>
        <button onClick={() => auth.signinRedirect()} className="za-btn za-btn--primary" style={{ marginTop: "1rem" }}>
          Se connecter avec Keycloak
        </button>
      </div>
    );
  }

  return (
    <ThemeProvider>
      <AppShell
        role={role}
        username={String(username)}
        onSignout={() => auth.signoutRedirect()}
        legacyEditor={<TranscriptionEditor />}
      />
    </ThemeProvider>
  );
}
