const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";

export interface ArtifactListResponse {
  files: string[];
}

export interface FileContent {
  path: string;
  content: string;
}

export interface ChatEntry {
  ts: string;
  role: string;
  content: unknown;
}

export interface RunSummary {
  artifact_name: string;
  model: string;
  count: number;
  passed: number;
  failed: number;
  errored: number;
  pass_rate: number;
  total_input_tokens: number;
  total_output_tokens: number;
  mean_latency_ms: number;
  started_at: string;
  finished_at: string;
  judge_config: Record<string, unknown>;
}

export interface RunRecord {
  run_id: string;
  summary: RunSummary;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BACKEND_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`${r.status} ${path}: ${text}`);
  }
  return (await r.json()) as T;
}

export const api = {
  backendUrl: BACKEND_URL,
  createSession: () => req<{ id: string }>("/sessions", { method: "POST" }),
  getSession: (sid: string) =>
    req<{ id: string; files: string[]; chat_entries: number }>(`/sessions/${sid}`),
  listFiles: (sid: string) =>
    req<ArtifactListResponse>(`/sessions/${sid}/artifact`),
  readFile: (sid: string, path: string) =>
    req<FileContent>(`/sessions/${sid}/artifact/${path}`),
  writeFile: (sid: string, path: string, content: string) =>
    req<{ ok: boolean }>(`/sessions/${sid}/artifact/${path}`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    }),
  getMessages: (sid: string) =>
    req<{ entries: ChatEntry[] }>(`/sessions/${sid}/messages`),
  triggerRun: (sid: string, model: string, limit?: number) =>
    req<{ run_id: string; summary: RunSummary }>(`/sessions/${sid}/runs`, {
      method: "POST",
      body: JSON.stringify({ model, limit: limit ?? null }),
    }),
  listRuns: (sid: string) =>
    req<{ runs: RunRecord[] }>(`/sessions/${sid}/runs`),
  getRun: (sid: string, runId: string) =>
    req<{ run_id: string; summary: RunSummary; results: Array<Record<string, unknown>> }>(
      `/sessions/${sid}/runs/${runId}`,
    ),
  exportUrl: (sid: string) => `${BACKEND_URL}/sessions/${sid}/export`,
};
