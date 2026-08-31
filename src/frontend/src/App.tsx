import { lazy } from "react";
import { useAuth } from "react-oidc-context";
import { AppShell } from "./app/AppShell";

const TranscriptionEditor = lazy(() =>
  import("./editor/TranscriptionEditor").then((m) => ({ default: m.TranscriptionEditor })),
);
import { ThemeProvider } from "./theme/ThemeContext";
import { NotificationProvider } from "./shared/notifications/NotificationContext";
import { AuthLanding } from "./features/auth/AuthLanding";
import { resolveAppRole } from "./types/rbac";

export function App() {
  const auth = useAuth();
  const role = resolveAppRole(auth.user?.profile as Record<string, unknown> | undefined);
  const username = (auth.user?.profile.preferred_username as string | undefined) ?? auth.user?.profile.sub ?? "Utilisateur";

  // ThemeProvider wraps every state so design tokens (and light/dark mode)
  // are always applied — including the pre-auth screens.
  return (
    <ThemeProvider>
      {auth.isLoading ? (
        <AuthLanding variant="loading" />
      ) : auth.error ? (
        <AuthLanding
          variant="error"
          errorMessage={auth.error.message}
          onSignin={() => auth.signinRedirect()}
        />
      ) : !auth.isAuthenticated ? (
        <AuthLanding variant="signin" onSignin={() => auth.signinRedirect()} />
      ) : (
        <NotificationProvider>
          <AppShell
            role={role}
            username={String(username)}
            onSignout={() => auth.signoutRedirect()}
            legacyEditor={<TranscriptionEditor />}
          />
        </NotificationProvider>
      )}
    </ThemeProvider>
  );
}
