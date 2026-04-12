import { apiJson } from "../../shared/api/zachaiApi";

export type UserConsentStatus = {
  ml_usage: boolean;
  biometric_data: boolean;
  deletion_pending: boolean;
  updated_at: string;
};

export type UserProfile = {
  sub: string;
  name: string | null;
  email: string | null;
  roles: string[];
  consents: UserConsentStatus;
};

export function fetchMyProfile(token: string): Promise<UserProfile> {
  return apiJson<UserProfile>("/v1/me/profile", token);
}

export function updateMyConsents(
  ml_usage: boolean,
  biometric_data: boolean,
  token: string
): Promise<UserConsentStatus> {
  return apiJson<UserConsentStatus>("/v1/me/consents", token, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ml_usage, biometric_data }),
  });
}

export function requestAccountDeletion(token: string): Promise<UserConsentStatus> {
  return apiJson<UserConsentStatus>("/v1/me/account", token, {
    method: "DELETE",
  });
}

export function cancelAccountDeletion(token: string): Promise<UserConsentStatus> {
  return apiJson<UserConsentStatus>("/v1/me/delete-cancel", token, {
    method: "POST",
  });
}

export async function exportMyData(token: string): Promise<void> {
  const response = await fetch("/v1/me/export-data", {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  if (!response.ok) {
    throw new Error("Erreur lors de l'export des données");
  }
  
  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `zachai_export_${new Date().toISOString().split("T")[0]}.zip`;
  document.body.appendChild(a);
  a.click();
  window.URL.revokeObjectURL(url);
  document.body.removeChild(a);
}
