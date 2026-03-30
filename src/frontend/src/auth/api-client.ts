import type { User } from "oidc-client-ts";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

/** Decode JWT payload (no signature verify — client-side routing only). */
function jwtPayload(token: string): Record<string, unknown> | null {
  try {
    const part = token.split(".")[1];
    if (!part) return null;
    const pad = part.length % 4 === 0 ? "" : "=".repeat(4 - (part.length % 4));
    const b64 = part.replace(/-/g, "+").replace(/_/g, "/") + pad;
    return JSON.parse(atob(b64)) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function tokenHasRoles(payload: Record<string, unknown> | null): boolean {
  if (!payload) return false;

  const ra = payload["realm_access"];
  if (ra && typeof ra === "object") {
    const roles = (ra as Record<string, unknown>)["roles"];
    if (Array.isArray(roles) && roles.length > 0) return true;
  }

  const rac = payload["resource_access"];
  if (rac && typeof rac === "object") {
    for (const _clientId of Object.keys(rac as Record<string, unknown>)) {
      const caccess = (rac as Record<string, unknown>)[_clientId];
      if (caccess && typeof caccess === "object") {
        const roles = (caccess as Record<string, unknown>)["roles"];
        if (Array.isArray(roles) && roles.length > 0) return true;
      }
    }
  }

  return false;
}

/**
 * Bearer token for FastAPI: must include `sub` (Keycloak subject). Some realms omit `sub`
 * from the access token but always set it on the id_token (OIDC).
 */
export function bearerForApi(user: User | null | undefined): string {
  if (!user) return "";

  const access = user.access_token ?? "";
  const id = user.id_token ?? "";

  const accessPl = access ? jwtPayload(access) : null;
  const idPl = id ? jwtPayload(id) : null;

  // Prefer the token that actually carries roles (realm_access or resource_access),
  // because FastAPI authorization is role-based.
  if (access && tokenHasRoles(accessPl)) return access;
  if (id && tokenHasRoles(idPl)) return id;

  // Fallbacks: keep the old `sub`-presence heuristic as last resort.
  if (accessPl?.sub != null && String(accessPl.sub).trim() !== "") return access;
  return id || access;
}

export async function apiFetch(
  path: string,
  token: string,
  init?: RequestInit,
): Promise<Response> {
  const url = `${API_BASE}${path}`;
  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(url, { ...init, headers });
}
