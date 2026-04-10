import { apiJson } from "../../shared/api/zachaiApi";

type LabelPayload = {
  name: string;
  color: string;
  is_speech: boolean;
  is_required: boolean;
};

export type NatureItem = {
  id: number;
  name: string;
  description: string | null;
  labels?: LabelPayload[];
};

export type ProjectItem = {
  id: number;
  name: string;
  status: string;
};

type UploadRequestResult = {
  object_key: string;
  presigned_url: string;
  expires_in: number;
};

type AudioRegisterResult = {
  id: number;
  filename: string;
  status: string;
};

export function listNatures(token: string): Promise<NatureItem[]> {
  return apiJson<NatureItem[]>("/v1/natures", token);
}

export function createNature(
  token: string,
  body: { name: string; description?: string; labels: LabelPayload[] },
): Promise<NatureItem> {
  return apiJson<NatureItem>("/v1/natures", token, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function createProject(
  token: string,
  body: {
    name: string;
    description?: string;
    nature_id: number;
    production_goal: "livre" | "sous-titres" | "dataset" | "archive";
  },
): Promise<ProjectItem> {
  return apiJson<ProjectItem>("/v1/projects", token, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function requestAudioUpload(
  token: string,
  projectId: number,
  body: { filename: string; content_type: string },
): Promise<UploadRequestResult> {
  return apiJson<UploadRequestResult>(`/v1/projects/${projectId}/audio-files/upload`, token, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function registerAudio(
  token: string,
  projectId: number,
  objectKey: string,
): Promise<AudioRegisterResult> {
  return apiJson<AudioRegisterResult>(`/v1/projects/${projectId}/audio-files/register`, token, {
    method: "POST",
    body: JSON.stringify({ object_key: objectKey }),
  });
}

export function assignAudio(
  token: string,
  projectId: number,
  audioId: number,
  transcripteurId: string,
): Promise<void> {
  return apiJson<void>(`/v1/projects/${projectId}/assign`, token, {
    method: "POST",
    body: JSON.stringify({ audio_id: audioId, transcripteur_id: transcripteurId }),
  });
}
