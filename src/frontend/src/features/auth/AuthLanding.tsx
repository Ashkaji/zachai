import type { ReactNode } from "react";

type AuthLandingProps = {
  variant: "loading" | "error" | "signin";
  errorMessage?: string;
  onSignin?: () => void;
};

/**
 * Full-screen entry surface shown before the app shell mounts.
 * Rendered inside ThemeProvider so design tokens are always available
 * (previously these states rendered token-less on a bare white background).
 */
export function AuthLanding({ variant, errorMessage, onSignin }: AuthLandingProps): ReactNode {
  return (
    <div style={styles.page}>
      <div style={styles.ambient} aria-hidden />
      <main style={styles.card}>
        <div style={styles.brandRow}>
          <span style={styles.logo}>Z</span>
          <span style={styles.brandName}>ZachAI</span>
        </div>

        {variant === "loading" && (
          <>
            <p style={styles.tagline}>Préparation de votre session sécurisée…</p>
            <div style={styles.spinner} role="status" aria-label="Chargement" />
          </>
        )}

        {variant === "error" && (
          <>
            <p style={styles.tagline}>
              La connexion n'a pas pu aboutir. Vous pouvez réessayer en toute sécurité.
            </p>
            {errorMessage ? <p style={styles.errorDetail}>{errorMessage}</p> : null}
            <button type="button" onClick={onSignin} className="za-btn za-btn--primary" style={styles.cta}>
              Réessayer la connexion
            </button>
          </>
        )}

        {variant === "signin" && (
          <>
            <p style={styles.tagline}>
              Plateforme de transcription assistée. Connectez-vous pour accéder à vos tâches.
            </p>
            <button type="button" onClick={onSignin} className="za-btn za-btn--primary" style={styles.cta}>
              Se connecter avec Keycloak
              <span aria-hidden style={{ marginLeft: 8 }}>→</span>
            </button>
            <div style={styles.meta}>OIDC · PKCE S256 · session chiffrée</div>
          </>
        )}
      </main>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: "100vh",
    display: "grid",
    placeItems: "center",
    padding: "24px",
    background: "var(--color-bg)",
    color: "var(--color-text)",
    position: "relative",
    overflow: "hidden",
  },
  ambient: {
    position: "absolute",
    top: "-30%",
    right: "-10%",
    width: "60vw",
    height: "60vw",
    maxWidth: "720px",
    maxHeight: "720px",
    borderRadius: "50%",
    background:
      "radial-gradient(circle, var(--color-primary-soft), transparent 62%)",
    filter: "blur(10px)",
    pointerEvents: "none",
  },
  card: {
    position: "relative",
    width: "100%",
    maxWidth: "420px",
    background: "var(--color-surface-hi)",
    border: "1px solid var(--color-outline)",
    borderRadius: "var(--radius-lg)",
    padding: "44px 34px",
    textAlign: "center",
    display: "grid",
    justifyItems: "center",
    gap: "6px",
    boxShadow: "0 24px 60px -30px rgba(0,0,0,0.55)",
  },
  brandRow: { display: "flex", alignItems: "center", gap: "11px", marginBottom: "6px" },
  logo: {
    width: "36px",
    height: "36px",
    borderRadius: "10px",
    display: "grid",
    placeItems: "center",
    color: "#fff",
    fontFamily: "var(--font-headline)",
    fontWeight: 800,
    fontSize: "1.1rem",
    background: "linear-gradient(135deg, var(--color-primary), var(--color-secondary))",
    boxShadow: "var(--glow-primary)",
  },
  brandName: {
    fontFamily: "var(--font-headline)",
    fontWeight: 800,
    fontSize: "1.55rem",
    letterSpacing: "-0.02em",
  },
  tagline: {
    margin: "8px 0 0",
    color: "var(--color-text-muted)",
    fontSize: "0.95rem",
    maxWidth: "34ch",
    lineHeight: 1.5,
  },
  errorDetail: {
    margin: "4px 0 0",
    color: "var(--color-error)",
    fontSize: "0.8rem",
    fontFamily: "ui-monospace, monospace",
    wordBreak: "break-word",
  },
  cta: { marginTop: "22px", width: "100%", maxWidth: "270px", justifyContent: "center", padding: "12px 16px" },
  meta: { marginTop: "14px", fontSize: "0.72rem", color: "var(--color-text-muted)" },
  spinner: {
    marginTop: "22px",
    width: "30px",
    height: "30px",
    borderRadius: "50%",
    border: "3px solid var(--color-outline)",
    borderTopColor: "var(--color-primary)",
    animation: "za-spin 0.8s linear infinite",
  },
};
