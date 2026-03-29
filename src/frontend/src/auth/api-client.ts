const API_BASE = import.meta.env.VITE_API_BASE ?? "";

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
