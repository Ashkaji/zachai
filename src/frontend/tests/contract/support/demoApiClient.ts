let apiUrl = process.env.API_URL ?? "http://localhost:8000";

export function setApiUrl(url: string): void {
  apiUrl = url;
}

export type EchoResponse = {
  message: string;
};

export async function fetchEcho(): Promise<EchoResponse> {
  const response = await fetch(`${apiUrl}/api/echo`);
  if (!response.ok) {
    throw new Error(`Unexpected status ${response.status}`);
  }
  return (await response.json()) as EchoResponse;
}
