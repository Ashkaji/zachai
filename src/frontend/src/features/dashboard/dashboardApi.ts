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

export type UserCreate = {
  username: string;
  email: string;
  firstName: string;
  lastName: string;
  role: "Admin" | "Manager" | "Transcripteur" | "Expert";
  enabled?: boolean;
};

export function fetchManagerProjects(token: string): Promise<ProjectSummary[]> {
  return apiJson<ProjectSummary[]>("/v1/projects?include=audio_summary", token);
}

export function fetchMyAudioTasks(token: string): Promise<AudioTask[]> {
  return apiJson<AudioTask[]>("/v1/me/audio-tasks", token);
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

export function assignAudio(projectId: number, audioId: number, transcripteurId: string, token: string): Promise<void> {
  return apiJson<void>(`/v1/projects/${projectId}/assign`, token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ audio_id: audioId, transcripteur_id: transcripteurId }),
  });
}

export function validateAudio(audioId: number, approved: boolean, comment: string | null, token: string): Promise<void> {
  return apiJson<void>(`/v1/transcriptions/${audioId}/validate`, token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved, comment }),
  });
}

export function createUser(userData: UserCreate, token: string): Promise<void> {
  return apiJson<void>("/v1/iam/users", token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(userData),
  });
}
