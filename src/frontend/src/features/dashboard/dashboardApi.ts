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

export function fetchManagerProjects(token: string): Promise<ProjectSummary[]> {
  return apiJson<ProjectSummary[]>("/v1/projects?include=audio_summary", token);
}

export function fetchMyAudioTasks(token: string): Promise<AudioTask[]> {
  return apiJson<AudioTask[]>("/v1/me/audio-tasks", token);
}

export function fetchProjectStatus(id: number, token: string): Promise<ProjectStatusResponse> {
  return apiJson<ProjectStatusResponse>(`/v1/projects/${id}/status`, token);
}

export function fetchExpertTasks(token: string): Promise<ExpertTask[]> {
  return apiJson<ExpertTask[]>("/v1/expert/tasks", token);
}

export function fetchGoldenSetStatus(token: string): Promise<GoldenSetStatus> {
  return apiJson<GoldenSetStatus>("/v1/golden-set/status", token);
}
