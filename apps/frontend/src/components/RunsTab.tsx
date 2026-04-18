"use client";

import { useEffect, useRef, useState } from "react";
import { api, RunProgress, RunRecord } from "@/lib/api";
import { RunDetail } from "@/components/RunDetail";
import { postSSE } from "@/lib/sse";

interface LiveRun {
  runId: string;
  model: string;
  total: number | null;
  progress: RunProgress;
  log: string[]; // last N sample lines
  error: string | null;
}

function ProgressBar({
  done,
  total,
}: {
  done: number;
  total: number | null;
}) {
  const pct = total ? Math.round((done / total) * 100) : null;
  return (
    <div className="mt-1 flex items-center gap-2">
      <div className="flex-1 overflow-hidden rounded-full bg-slate-200 h-1.5">
        <div
          className="h-1.5 rounded-full bg-slate-700 transition-all duration-200"
          style={{ width: pct != null ? `${pct}%` : "100%" }}
        />
      </div>
      <span className="mono shrink-0 text-xs text-slate-500">
        {pct != null ? `${done}/${total} (${pct}%)` : `${done} done`}
      </span>
    </div>
  );
}

function RunStatusBadge({ status }: { status: string }) {
  const cls =
    status === "completed"
      ? "bg-green-100 text-green-800"
      : status === "running"
        ? "bg-blue-100 text-blue-800"
        : status === "failed"
          ? "bg-red-100 text-red-800"
          : "bg-slate-100 text-slate-600";
  return (
    <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${cls}`}>
      {status}
    </span>
  );
}

export function RunsTab({
  sessionId,
  refreshToken,
}: {
  sessionId: string;
  refreshToken: number;
}) {
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [model, setModel] = useState("claude-haiku-4-5-20251001");
  const [provider, setProvider] = useState<string>("auto");
  const [limit, setLimit] = useState<string>("5");
  const [liveRun, setLiveRun] = useState<LiveRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  async function reload() {
    try {
      const r = await api.listRuns(sessionId);
      setRuns(r.runs.slice().reverse());
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, refreshToken]);

  // Poll while a live run is active so the table reflects server state after
  // the stream ends (or if the user refreshes and we detect a server-side run).
  useEffect(() => {
    if (liveRun) return;
    // check for any server-side in-progress run on mount
    const serverRunning = runs.some((r) => r.status === "running");
    if (!serverRunning) return;
    const id = window.setInterval(reload, 2000);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [liveRun, runs]);

  async function trigger() {
    if (liveRun) return;
    setError(null);

    const n = limit.trim() === "" ? undefined : Number(limit);
    const prov = provider === "auto" ? undefined : provider;

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLiveRun({
      runId: "",
      model,
      total: null,
      progress: { done: 0, total: null, passed: 0, failed: 0, errored: 0 },
      log: [],
      error: null,
    });

    try {
      await postSSE(
        api.triggerRunStreamUrl(sessionId),
        {
          model,
          limit: Number.isFinite(n!) ? n : null,
          provider: prov ?? null,
        },
        (ev) => {
          const data = JSON.parse(ev.data);

          if (ev.event === "started") {
            setLiveRun((prev) =>
              prev
                ? {
                    ...prev,
                    model: data.model ?? prev.model,
                    total: data.total ?? null,
                  }
                : prev,
            );
          } else if (ev.event === "sample") {
            const scoreMark =
              data.score === 1 ? "✓" : data.error ? "!" : "✗";
            const preview = data.error
              ? data.error.slice(0, 80)
              : (data.reason ?? "").slice(0, 80);
            const line = `#${data.index} ${scoreMark}  ${preview}`;
            setLiveRun((prev) => {
              if (!prev) return prev;
              const log = [...prev.log, line].slice(-30);
              return {
                ...prev,
                progress: {
                  done: data.done,
                  total: data.total ?? prev.total,
                  passed: data.passed,
                  failed: data.failed,
                  errored: data.errored,
                },
                log,
              };
            });
          } else if (ev.event === "done") {
            setLiveRun((prev) =>
              prev ? { ...prev, runId: data.run_id ?? prev.runId } : prev,
            );
          } else if (ev.event === "error") {
            setLiveRun((prev) =>
              prev ? { ...prev, error: data.message ?? "unknown error" } : prev,
            );
          }
        },
        ctrl.signal,
      );
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        setError((e as Error).message);
      }
    } finally {
      abortRef.current = null;
      setLiveRun(null);
      await reload();
    }
  }

  function cancelRun() {
    abortRef.current?.abort();
  }

  if (selectedRunId) {
    return (
      <RunDetail
        sessionId={sessionId}
        runId={selectedRunId}
        onBack={() => setSelectedRunId(null)}
      />
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* controls */}
      <div className="flex items-end gap-2 border-b p-3">
        <label className="flex flex-col text-xs text-slate-600">
          model
          <input
            className="mono mt-0.5 rounded border px-2 py-1 text-xs"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="claude-sonnet-4-6 or anthropic:custom-name"
          />
        </label>
        <label className="flex flex-col text-xs text-slate-600">
          provider
          <select
            className="mono mt-0.5 rounded border px-2 py-1 text-xs"
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
          >
            <option value="auto">auto-detect</option>
            <option value="anthropic">anthropic</option>
            <option value="openai">openai</option>
          </select>
        </label>
        <label className="flex flex-col text-xs text-slate-600">
          limit
          <input
            className="mono mt-0.5 w-20 rounded border px-2 py-1 text-xs"
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
            placeholder="all"
          />
        </label>
        {liveRun ? (
          <button
            onClick={cancelRun}
            className="rounded border border-red-300 px-3 py-1.5 text-sm text-red-700 hover:bg-red-50"
          >
            cancel
          </button>
        ) : (
          <button
            onClick={trigger}
            className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-700"
          >
            run benchmark
          </button>
        )}
        <button
          onClick={reload}
          className="rounded border px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100"
        >
          refresh
        </button>
      </div>

      {error && (
        <div className="border-b border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {error}
        </div>
      )}

      {/* live progress panel */}
      {liveRun && (
        <div className="border-b bg-blue-50 px-4 py-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-blue-800">
              Running · {liveRun.model}
            </span>
            <span className="mono text-xs text-blue-600">
              {liveRun.progress.passed}✓ {liveRun.progress.failed}✗{" "}
              {liveRun.progress.errored}!
            </span>
          </div>
          <ProgressBar
            done={liveRun.progress.done}
            total={liveRun.total}
          />
          {liveRun.error && (
            <div className="mt-1 text-xs text-red-700">{liveRun.error}</div>
          )}
          {liveRun.log.length > 0 && (
            <pre className="mono mt-2 max-h-36 overflow-y-auto rounded bg-blue-100 p-2 text-[11px] text-blue-900">
              {liveRun.log.join("\n")}
            </pre>
          )}
        </div>
      )}

      {/* run history table */}
      <div className="flex-1 overflow-y-auto p-3">
        {runs.length === 0 && !liveRun ? (
          <div className="text-sm text-slate-400">
            No runs yet. Trigger one above, or ask the agent to call dry_run.
          </div>
        ) : (
          <table className="mono w-full text-xs">
            <thead>
              <tr className="text-left text-slate-500">
                <th className="py-1 pr-3">run_id</th>
                <th className="py-1 pr-3">status</th>
                <th className="py-1 pr-3">model</th>
                <th className="py-1 pr-3">count</th>
                <th className="py-1 pr-3">passed</th>
                <th className="py-1 pr-3">rate</th>
                <th className="py-1 pr-3">in tok</th>
                <th className="py-1 pr-3">out tok</th>
                <th className="py-1 pr-3">avg ms</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr
                  key={r.run_id}
                  className={`border-t ${r.status === "completed" ? "cursor-pointer hover:bg-slate-50" : ""}`}
                  onClick={() =>
                    r.status === "completed" && setSelectedRunId(r.run_id)
                  }
                >
                  <td className="py-1 pr-3 text-blue-600 underline decoration-dashed underline-offset-2">
                    {r.run_id}
                  </td>
                  <td className="py-1 pr-3">
                    <RunStatusBadge status={r.status} />
                  </td>
                  <td className="py-1 pr-3">
                    {r.summary?.model ?? r.model ?? "—"}
                  </td>
                  <td className="py-1 pr-3">
                    {r.status === "running" && r.progress
                      ? `${r.progress.done}/${r.progress.total ?? "?"}`
                      : (r.summary?.count ?? "—")}
                  </td>
                  <td className="py-1 pr-3">
                    {r.status === "running" && r.progress
                      ? r.progress.passed
                      : (r.summary?.passed ?? "—")}
                  </td>
                  <td className="py-1 pr-3">
                    {r.summary ? r.summary.pass_rate.toFixed(2) : "—"}
                  </td>
                  <td className="py-1 pr-3">
                    {r.summary?.total_input_tokens ?? "—"}
                  </td>
                  <td className="py-1 pr-3">
                    {r.summary?.total_output_tokens ?? "—"}
                  </td>
                  <td className="py-1 pr-3">
                    {r.summary ? r.summary.mean_latency_ms.toFixed(0) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
