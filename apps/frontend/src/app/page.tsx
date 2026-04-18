"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ChatPanel } from "@/components/ChatPanel";
import { ArtifactTabs } from "@/components/ArtifactTabs";

const STORAGE_KEY = "bmk-session-id";
const MODEL_STORAGE_KEY = "bmk-agent-model";
const DATA_ACCESS_STORAGE_KEY = "bmk-agent-data-access";

export default function Home() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [agentModel, setAgentModel] = useState<string>("");
  const [backendDefault, setBackendDefault] = useState<string>("");
  const [allowAgentDataAccess, setAllowAgentDataAccess] = useState(true);

  useEffect(() => {
    api
      .getConfig()
      .then((c) => {
        setBackendDefault(c.orchestrator_model_default);
        const saved = localStorage.getItem(MODEL_STORAGE_KEY);
        setAgentModel(saved || c.orchestrator_model_default);
        const savedDataAccess = localStorage.getItem(DATA_ACCESS_STORAGE_KEY);
        setAllowAgentDataAccess(savedDataAccess !== "false");
      })
      .catch((e) => setError(e.message));

    const existing = localStorage.getItem(STORAGE_KEY);
    if (existing) {
      api
        .getSession(existing)
        .then(() => setSessionId(existing))
        .catch(() => {
          localStorage.removeItem(STORAGE_KEY);
          bootstrap();
        });
    } else {
      bootstrap();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function updateAgentModel(v: string) {
    setAgentModel(v);
    if (v && v !== backendDefault) {
      localStorage.setItem(MODEL_STORAGE_KEY, v);
    } else {
      localStorage.removeItem(MODEL_STORAGE_KEY);
    }
  }

  function updateAgentDataAccess(v: boolean) {
    setAllowAgentDataAccess(v);
    localStorage.setItem(DATA_ACCESS_STORAGE_KEY, String(v));
  }

  function bootstrap() {
    api
      .createSession()
      .then((r) => {
        localStorage.setItem(STORAGE_KEY, r.id);
        setSessionId(r.id);
      })
      .catch((e) => setError(e.message));
  }

  function resetSession() {
    localStorage.removeItem(STORAGE_KEY);
    setSessionId(null);
    bootstrap();
  }

  if (error) {
    return (
      <main className="flex h-screen items-center justify-center">
        <div className="max-w-md rounded border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <div className="font-semibold">cannot reach backend</div>
          <div className="mono mt-2 text-xs">{error}</div>
          <div className="mt-3 text-xs">
            make sure the backend is running at{" "}
            <span className="mono">{api.backendUrl}</span>
          </div>
        </div>
      </main>
    );
  }

  if (!sessionId) {
    return (
      <main className="flex h-screen items-center justify-center text-sm text-slate-500">
        starting session...
      </main>
    );
  }

  return (
    <main className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b bg-white px-4 py-2">
        <div className="flex items-baseline gap-3">
          <h1 className="text-base font-semibold">BenchmarkAgent</h1>
          <span className="text-xs text-slate-400">
            build a reusable LLM benchmark
          </span>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-slate-600">
            agent model
            <input
              className="mono w-64 rounded border px-2 py-1 text-xs"
              value={agentModel}
              onChange={(e) => updateAgentModel(e.target.value)}
              placeholder={backendDefault}
              title={`backend default: ${backendDefault}`}
            />
            {agentModel && agentModel !== backendDefault && (
              <button
                onClick={() => updateAgentModel(backendDefault)}
                className="text-xs text-slate-400 hover:text-slate-700"
                title="reset to backend default"
              >
                reset
              </button>
            )}
          </label>
          <label className="flex items-center gap-2 text-xs text-slate-600">
            <input
              type="checkbox"
              checked={allowAgentDataAccess}
              onChange={(e) => updateAgentDataAccess(e.target.checked)}
            />
            allow agent to read dataset
          </label>
          <button
            onClick={resetSession}
            className="rounded border px-2 py-1 text-xs text-slate-600 hover:bg-slate-100"
          >
            new session
          </button>
        </div>
      </header>
      <div className="grid flex-1 grid-cols-[minmax(380px,1fr)_minmax(600px,1.4fr)] overflow-hidden">
        <div className="border-r overflow-hidden">
          <ChatPanel
            sessionId={sessionId}
            onArtifactChanged={() => setRefreshToken((t) => t + 1)}
            agentModel={agentModel}
            allowAgentDataAccess={allowAgentDataAccess}
          />
        </div>
        <div className="overflow-hidden">
          <ArtifactTabs
            sessionId={sessionId}
            refreshToken={refreshToken}
            onArtifactChanged={() => setRefreshToken((t) => t + 1)}
          />
        </div>
      </div>
    </main>
  );
}
