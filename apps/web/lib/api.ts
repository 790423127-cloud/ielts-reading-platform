export type HealthResponse = {
  ok: boolean;
  service: string;
  version: string;
  migrationPhase: string;
  databaseConnected: boolean;
  features: Record<string, boolean>;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/health`, { signal, cache: "no-store" });
  if (!response.ok) throw new Error(`API health failed: ${response.status}`);
  return response.json() as Promise<HealthResponse>;
}
