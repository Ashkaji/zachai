import { apiJson } from "../../shared/api/zachaiApi";

export type ProjectSummary = {
  id: number;
  name: string;
  nature_name: string;
  status: string;
  created_at: string;
  audio_counts_by_status?: {
    uploaded: number;
    assigned: number;
    in_progress: number;
    transcribed: number;
    validated: number;
  };
  unassigned_normalized_count?: number;
};

export type Label = {
  id: number;
  name: string;
  color: string;
  is_speech: boolean;
  is_required: boolean;
};

export type ProjectDetail = {
  id: number;
  name: string;
  description: string | null;
  nature_id: number;
  nature_name: string;
  production_goal: string | null;
  status: string;
  manager_id: string;
  label_studio_project_id: number | null;
  created_at: string;
  labels: Label[];
};

export type AudioTask = {
  audio_id: number;
  project_id: number;
  project_name: string;
  filename: string;
  status: string;
  assigned_at: string;
  help_requested?: boolean;
  help_message?: string | null;
};

export type AudioRow = {
  id: number;
  project_id: number;
  filename: string;
  minio_path: string;
  normalized_path: string | null;
  duration_s: number | null;
  status: string;
  validation_error: string | null;
  validation_attempted_at: string | null;
  uploaded_at: string;
  updated_at: string;
  assigned_to: string | null;
  assigned_at: string | null;
  help_requested?: boolean;
  help_message?: string | null;
};

export type ProjectStatusResponse = {
  project_status: string;
  audios: AudioRow[];
};

export type ExpertTask = {
  audio_id: number;
  project_id: number;
  project_name: string;
  filename: string;
  status: string;
  assigned_at: string | null;
  expert_id: string | null;
  source: string;
  priority: string | null;
  label_studio_project_id: number | null;
  label_studio_url: string | null;
};

export type GoldenSetStatus = {
  count: number;
  threshold: number;
  last_training_at: string | null;
  next_trigger_at: string | null;
};

export type AuditLogEntry = {
  id: number;
  user_id: string;
  action: string;
  details: Record<string, any>;
  created_at: string;
};

export type User = {
  id: string;
  username: string;
  email?: string;
  firstName?: string;
  lastName?: string;
};

export type UserCreate = {
  username: string;
  email: string;
  firstName: string;
  lastName: string;
  role: "Admin" | "Manager" | "Transcripteur" | "Expert";
  enabled?: boolean;
  /** Si absent, l’API génère un mot de passe et le renvoie dans la réponse (`initial_password`). */
  password?: string;
};

export type UserCreateResponse = {
  status: string;
  id: string;
  initial_password?: string;
};

export function fetchManagerProjects(token: string): Promise<ProjectSummary[]> {
  return apiJson<ProjectSummary[]>("/v1/projects?include=audio_summary", token);
}

export function fetchMyAudioTasks(token: string): Promise<AudioTask[]> {
  return apiJson<AudioTask[]>("/v1/me/audio-tasks", token);
}

export function fetchAvailableTasks(token: string): Promise<AudioTask[]> {
  return apiJson<AudioTask[]>("/v1/me/available-tasks", token);
}

export function claimTask(audioId: number, token: string): Promise<void> {
  return apiJson<void>(`/v1/audio-files/${audioId}/claim`, token, {
    method: "POST",
  });
}

export function toggleHelp(audioId: number, requested: boolean, message: string | null, token: string): Promise<void> {
  return apiJson<void>(`/v1/audio-files/${audioId}/help`, token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ requested, message }),
  });
}

export function fetchProjectStatus(id: number, token: string): Promise<ProjectStatusResponse> {
  return apiJson<ProjectStatusResponse>(`/v1/projects/${id}/status`, token);
}

export function fetchProjectDetail(id: number, token: string): Promise<ProjectDetail> {
  return apiJson<ProjectDetail>(`/v1/projects/${id}`, token);
}

export function fetchExpertTasks(token: string): Promise<ExpertTask[]> {
  return apiJson<ExpertTask[]>("/v1/expert/tasks", token);
}

export function fetchGoldenSetStatus(token: string): Promise<GoldenSetStatus> {
  return apiJson<GoldenSetStatus>("/v1/golden-set/status", token);
}

export function fetchProjectAuditTrail(id: number, token: string): Promise<AuditLogEntry[]> {
  return apiJson<AuditLogEntry[]>(`/v1/projects/${id}/audit-trail`, token);
}

export function listUsers(token: string): Promise<User[]> {
  return apiJson<User[]>("/v1/iam/users", token);
}

export function assignAudio(projectId: number, audioId: number, transcripteurIds: string[], token: string): Promise<void> {
  return apiJson<void>(`/v1/projects/${projectId}/assign`, token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ audio_id: audioId, transcripteur_ids: transcripteurIds }),
  });
}

export function validateAudio(audioId: number, approved: boolean, comment: string | null, token: string): Promise<void> {
  return apiJson<void>(`/v1/transcriptions/${audioId}/validate`, token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved, comment }),
  });
}

// Audio/project management actions
export function deleteAudio(projectId: number, audioId: number, token: string): Promise<void> {
  return apiJson<void>(`/v1/projects/${projectId}/audio-files/${audioId}`, token, {
    method: "DELETE",
  });
}

export function retryNormalization(projectId: number, audioId: number, token: string): Promise<void> {
  return apiJson<void>(`/v1/projects/${projectId}/audio-files/${audioId}/normalize`, token, {
    method: "POST",
  });
}

export function deleteProject(projectId: number, token: string): Promise<void> {
  return apiJson<void>(`/v1/projects/${projectId}`, token, {
    method: "DELETE",
  });
}

export function createUser(userData: UserCreate, token: string): Promise<UserCreateResponse> {
  const body: Record<string, unknown> = {
    username: userData.username,
    email: userData.email,
    firstName: userData.firstName,
    lastName: userData.lastName,
    role: userData.role,
    enabled: userData.enabled ?? true,
  };
  if (userData.password != null && String(userData.password).trim() !== "") {
    body.password = userData.password;
  }
  return apiJson<UserCreateResponse>("/v1/iam/users", token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
