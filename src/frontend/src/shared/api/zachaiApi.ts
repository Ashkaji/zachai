import { apiFetch } from "../../auth/api-client";

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function parseErrorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") {
    return fallback;
  }
  const asRecord = payload as Record<string, unknown>;
  const detail = asRecord.detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (detail && typeof detail === "object") {
    const err = (detail as Record<string, unknown>).error;
    if (typeof err === "string") {
      return err;
    }
  }
  const err = asRecord.error;
  if (typeof err === "string") {
    return err;
  }
  return fallback;
}

export async function apiJson<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(path, token, init);
  const text = await response.text();
  const payload = text ? (JSON.parse(text) as unknown) : null;
  if (!response.ok) {
    throw new ApiError(parseErrorMessage(payload, `HTTP ${response.status}`), response.status);
  }
  return payload as T;
}
