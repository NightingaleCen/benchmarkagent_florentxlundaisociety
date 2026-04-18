"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ChatPanel } from "@/components/ChatPanel";
import { ArtifactTabs } from "@/components/ArtifactTabs";

const STORAGE_KEY = "bmk-session-id";

export default function Home() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
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
        <button
          onClick={resetSession}
          className="rounded border px-2 py-1 text-xs text-slate-600 hover:bg-slate-100"
        >
          new session
        </button>
      </header>
      <div className="grid flex-1 grid-cols-[minmax(380px,1fr)_minmax(600px,1.4fr)] overflow-hidden">
        <div className="border-r overflow-hidden">
          <ChatPanel
            sessionId={sessionId}
            onArtifactChanged={() => setRefreshToken((t) => t + 1)}
          />
        </div>
        <div className="overflow-hidden">
          <ArtifactTabs sessionId={sessionId} refreshToken={refreshToken} />
        </div>
      </div>
    </main>
  );
}
