import { useAuth } from "react-oidc-context";
import { TranscriptionEditor } from "./editor/TranscriptionEditor";

export function App() {
  const auth = useAuth();

  if (auth.isLoading) {
    return <p style={{ padding: "2rem" }}>Chargement de l'authentification…</p>;
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
        <h1>ZachAI — Transcription Editor</h1>
        <button
          onClick={() => auth.signinRedirect()}
          style={{
            marginTop: "1rem",
            padding: "0.75rem 2rem",
            fontSize: "1rem",
            cursor: "pointer",
          }}
        >
          Se connecter avec Keycloak
        </button>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: "960px", margin: "0 auto", padding: "1rem" }}>
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          borderBottom: "1px solid #ddd",
          paddingBottom: "0.5rem",
          marginBottom: "1rem",
        }}
      >
        <h1 style={{ margin: 0, fontSize: "1.25rem" }}>ZachAI Editor</h1>
        <div>
          <span style={{ marginRight: "1rem", fontSize: "0.875rem" }}>
            {auth.user?.profile.preferred_username ?? auth.user?.profile.sub}
          </span>
          <button onClick={() => auth.signoutRedirect()}>Déconnexion</button>
        </div>
      </header>
      <TranscriptionEditor />
    </div>
  );
}
