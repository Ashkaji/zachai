import type { AuthProviderProps } from "react-oidc-context";

const KEYCLOAK_URL =
  import.meta.env.VITE_KEYCLOAK_URL ?? "http://localhost:8180";
const REALM = import.meta.env.VITE_KEYCLOAK_REALM ?? "zachai";
const CLIENT_ID =
  import.meta.env.VITE_KEYCLOAK_CLIENT_ID ?? "zachai-frontend";

export const oidcConfig: AuthProviderProps = {
  authority: `${KEYCLOAK_URL}/realms/${REALM}`,
  client_id: CLIENT_ID,
  redirect_uri: window.location.href,
  post_logout_redirect_uri: window.location.origin,
  scope: "openid profile",
  automaticSilentRenew: true,
  onSigninCallback: () => {
    const url = new URL(window.location.href);
    url.searchParams.delete("code");
    url.searchParams.delete("state");
    url.searchParams.delete("session_state");
    url.searchParams.delete("iss");
    window.history.replaceState({}, document.title, url.pathname + url.search);
  },
};
