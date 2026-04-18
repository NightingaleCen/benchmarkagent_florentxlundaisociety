"use client";

import { useEffect, useState } from "react";
import { api, ChatEntry, RunRecord, SessionInfo } from "@/lib/api";

interface MonitorTabProps {
  sessionId: string;
  refreshToken: number;
}

interface SessionSnapshot extends SessionInfo {
  runCount: number;
}

const POLL_MS = 2000;

export function MonitorTab({
  sessionId,
  refreshToken,
}: MonitorTabProps) {
  const [sessions, setSessions] = useState<SessionSnapshot[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState(sessionId);
  const [messages, setMessages] = useState<ChatEntry[]>([]);
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [manualRefreshTick, setManualRefreshTick] = useState(0);

  useEffect(() => {
    setSelectedSessionId((current) => current || sessionId);
  }, [sessionId]);

  useEffect(() => {
    let cancelled = false;

    async function loadOverview() {
      try {
        if (!cancelled) {
          setLoading(true);
          setError(null);
        }
        const listed = await api.listSessions();
        const snapshots = await Promise.all(
          listed.ids.map(async (id) => {
            const [session, runResp] = await Promise.all([
              api.getSession(id),
              api.listRuns(id),
            ]);
            return {
              ...session,
              runCount: runResp.runs.length,
            };
          }),
        );
        snapshots.sort((a, b) => {
          const scoreA = a.chat_entries + a.runCount + a.files.length;
          const scoreB = b.chat_entries + b.runCount + b.files.length;
          return scoreB - scoreA || b.id.localeCompare(a.id);
        });
        if (!cancelled) {
          setSessions(snapshots);
          setSelectedSessionId((current) => {
            if (current && snapshots.some((s) => s.id === current)) return current;
            if (snapshots.some((s) => s.id === sessionId)) return sessionId;
            return snapshots[0]?.id ?? "";
          });
          setLastUpdated(new Date().toLocaleTimeString());
        }
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadOverview();
    if (!autoRefresh) return () => {
      cancelled = true;
    };

    const timer = window.setInterval(loadOverview, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [autoRefresh, sessionId, refreshToken, manualRefreshTick]);

  useEffect(() => {
    if (!selectedSessionId) {
      setMessages([]);
      setRuns([]);
      return;
    }

    let cancelled = false;

    async function loadDetails() {
      try {
        if (!cancelled) {
          setDetailLoading(true);
          setError(null);
        }
        const [messageResp, runResp] = await Promise.all([
          api.getMessages(selectedSessionId),
          api.listRuns(selectedSessionId),
        ]);
        if (!cancelled) {
          setMessages(messageResp.entries);
          setRuns(runResp.runs.slice().reverse());
          setLastUpdated(new Date().toLocaleTimeString());
        }
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      } finally {
        if (!cancelled) setDetailLoading(false);
      }
    }

    loadDetails();
    if (!autoRefresh) return () => {
      cancelled = true;
    };

    const timer = window.setInterval(loadDetails, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [autoRefresh, selectedSessionId, refreshToken, manualRefreshTick]);

  const selected =
    sessions.find((session) => session.id === selectedSessionId) ?? null;
  const totalChatEntries = sessions.reduce(
    (sum, session) => sum + session.chat_entries,
    0,
  );
  const totalRuns = sessions.reduce((sum, session) => sum + session.runCount, 0);
  const activeSessions = sessions.filter(
    (session) => session.chat_entries > 0 || session.runCount > 0 || session.files.length > 0,
  ).length;

  return (
    <div className="flex h-full flex-col bg-white">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-800">Backend Monitor</h2>
          <div className="mt-1 text-xs text-slate-500">
            polling every {POLL_MS / 1000}s from <span className="mono">{api.backendUrl}</span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-slate-600">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            auto refresh
          </label>
          <button
            onClick={() => {
              setLastUpdated(null);
              setLoading(true);
              setDetailLoading(true);
              setSelectedSessionId((current) => current || sessionId);
              setManualRefreshTick((tick) => tick + 1);
            }}
            className="rounded border px-3 py-1 text-xs text-slate-600 hover:bg-slate-100"
          >
            refresh now
          </button>
        </div>
      </div>

      <div className="grid grid-cols-[320px_minmax(0,1fr)] gap-0 overflow-hidden">
        <aside className="border-r">
          <div className="grid grid-cols-2 gap-2 border-b bg-slate-50 p-3 text-xs">
            <StatCard label="sessions" value={String(sessions.length)} />
            <StatCard label="active" value={String(activeSessions)} />
            <StatCard label="chat rows" value={String(totalChatEntries)} />
            <StatCard label="runs" value={String(totalRuns)} />
          </div>

          <div className="border-b px-3 py-2 text-xs text-slate-500">
            {loading ? "refreshing session list..." : `last updated ${lastUpdated ?? "-"}`}
          </div>

          <div className="max-h-[calc(100vh-250px)] overflow-y-auto">
            {sessions.length === 0 ? (
              <div className="p-4 text-sm text-slate-400">No sessions yet.</div>
            ) : (
              sessions.map((session) => {
                const selectedClass =
                  session.id === selectedSessionId
                    ? "border-l-2 border-slate-900 bg-slate-50"
                    : "border-l-2 border-transparent";
                return (
                  <button
                    key={session.id}
                    onClick={() => setSelectedSessionId(session.id)}
                    className={`block w-full px-3 py-3 text-left hover:bg-slate-50 ${selectedClass}`}
                  >
                    <div className="mono text-xs text-slate-700">{session.id}</div>
                    <div className="mt-2 flex gap-3 text-xs text-slate-500">
                      <span>{session.chat_entries} chat</span>
                      <span>{session.files.length} files</span>
                      <span>{session.runCount} runs</span>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </aside>

        <section className="flex min-w-0 flex-col">
          {error && (
            <div className="border-b border-red-200 bg-red-50 px-4 py-2 text-xs text-red-700">
              {error}
            </div>
          )}

          {!selected ? (
            <div className="flex h-full items-center justify-center text-sm text-slate-400">
              Pick a session to inspect.
            </div>
          ) : (
            <>
              <div className="border-b px-4 py-3">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <div className="mono text-sm text-slate-900">{selected.id}</div>
                    <div className="mt-1 text-xs text-slate-500">
                      {selected.chat_entries} chat entries, {selected.files.length} files,{" "}
                      {selected.runCount} runs
                    </div>
                  </div>
                  <div className="text-xs text-slate-500">
                    {detailLoading ? "refreshing details..." : `last updated ${lastUpdated ?? "-"}`}
                  </div>
                </div>
              </div>

              <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
                <div className="min-h-0 border-r">
                  <div className="border-b px-4 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                    Recent Messages
                  </div>
                  <div className="max-h-full overflow-y-auto px-4 py-3">
                    {messages.length === 0 ? (
                      <div className="text-sm text-slate-400">No messages yet.</div>
                    ) : (
                      messages
                        .slice(-24)
                        .reverse()
                        .map((entry, index) => (
                          <div key={`${entry.ts}-${index}`} className="mb-3 rounded border p-3">
                            <div className="flex items-center justify-between gap-3 text-xs text-slate-500">
                              <span className="mono">{entry.role}</span>
                              <span className="mono">{formatTimestamp(entry.ts)}</span>
                            </div>
                            <pre className="mono mt-2 overflow-x-auto whitespace-pre-wrap text-xs text-slate-800">
                              {stringifyContent(entry.content)}
                            </pre>
                          </div>
                        ))
                    )}
                  </div>
                </div>

                <div className="min-h-0">
                  <div className="border-b px-4 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                    Runs
                  </div>
                  <div className="max-h-full overflow-y-auto px-4 py-3">
                    {runs.length === 0 ? (
                      <div className="text-sm text-slate-400">No benchmark runs yet.</div>
                    ) : (
                      runs.map((run) => (
                        <div key={run.run_id} className="mb-3 rounded border p-3">
                          <div className="flex items-center justify-between gap-3">
                            <div className="mono text-xs text-slate-800">{run.run_id}</div>
                            <div className="text-xs text-slate-500">
                              {run.summary.pass_rate.toFixed(2)} pass rate
                            </div>
                          </div>
                          <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-600">
                            <span>model: {run.summary.model}</span>
                            <span>count: {run.summary.count}</span>
                            <span>passed: {run.summary.passed}</span>
                            <span>failed: {run.summary.failed}</span>
                            <span>errored: {run.summary.errored}</span>
                            <span>avg ms: {run.summary.mean_latency_ms.toFixed(0)}</span>
                            <span>in tok: {run.summary.total_input_tokens}</span>
                            <span>out tok: {run.summary.total_output_tokens}</span>
                          </div>
                        </div>
                      ))
                    )}

                    <div className="mt-6 border-t pt-3">
                      <div className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                        Files
                      </div>
                      {selected.files.length === 0 ? (
                        <div className="text-sm text-slate-400">No artifact files yet.</div>
                      ) : (
                        <div className="space-y-2">
                          {selected.files.map((file) => (
                            <div
                              key={file}
                              className="mono rounded bg-slate-50 px-2 py-1 text-xs text-slate-700"
                            >
                              {file}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border bg-white px-3 py-2">
      <div className="text-[11px] uppercase tracking-[0.14em] text-slate-500">{label}</div>
      <div className="mono mt-1 text-sm text-slate-900">{value}</div>
    </div>
  );
}

function stringifyContent(content: unknown) {
  if (typeof content === "string") return content;
  try {
    return JSON.stringify(content, null, 2);
  } catch {
    return String(content);
  }
}

function formatTimestamp(ts: string) {
  const date = new Date(ts);
  if (Number.isNaN(date.getTime())) return ts;
  return date.toLocaleString();
}
