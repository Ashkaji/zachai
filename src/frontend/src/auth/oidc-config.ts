import type { AuthProviderProps } from "react-oidc-context";
import { WebStorageStateStore } from "oidc-client-ts";

const KEYCLOAK_URL =
  import.meta.env.VITE_KEYCLOAK_URL ?? "http://localhost:8180";
const REALM = import.meta.env.VITE_KEYCLOAK_REALM ?? "zachai";
const CLIENT_ID =
  import.meta.env.VITE_KEYCLOAK_CLIENT_ID ?? "zachai-frontend";

// Stable, param-free redirect target so the state created at signin always
// matches the one read back at the callback (prevents "No matching state
// found in storage" when the current URL carries leftover query params).
const REDIRECT_URI = `${window.location.origin}/`;

export const oidcConfig: AuthProviderProps = {
  authority: `${KEYCLOAK_URL}/realms/${REALM}`,
  client_id: CLIENT_ID,
  redirect_uri: REDIRECT_URI,
  post_logout_redirect_uri: window.location.origin,
  // Include `roles` so the access token carries `realm_access.roles` (Keycloak default client scope).
  scope: "openid profile email roles",
  automaticSilentRenew: true,
  // Persist auth + signin state in localStorage (survives reloads and is shared
  // across tabs) instead of the default per-tab sessionStorage.
  userStore: new WebStorageStateStore({ store: window.localStorage }),
  stateStore: new WebStorageStateStore({ store: window.localStorage }),
  onSigninCallback: () => {
    const url = new URL(window.location.href);
    url.searchParams.delete("code");
    url.searchParams.delete("state");
    url.searchParams.delete("session_state");
    url.searchParams.delete("iss");
    window.history.replaceState({}, document.title, url.pathname + url.search);
  },
};
