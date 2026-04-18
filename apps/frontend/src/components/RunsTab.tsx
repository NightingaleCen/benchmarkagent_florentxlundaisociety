"use client";

import { useEffect, useState } from "react";
import { api, RunRecord } from "@/lib/api";

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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  async function trigger() {
    setBusy(true);
    setError(null);
    try {
      const n = limit.trim() === "" ? undefined : Number(limit);
      const prov = provider === "auto" ? undefined : provider;
      await api.triggerRun(
        sessionId,
        model,
        Number.isFinite(n!) ? n : undefined,
        prov,
      );
      await reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
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
        <button
          onClick={trigger}
          disabled={busy}
          className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-700 disabled:bg-slate-300"
        >
          {busy ? "running..." : "run benchmark"}
        </button>
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
      <div className="flex-1 overflow-y-auto p-3">
        {runs.length === 0 ? (
          <div className="text-sm text-slate-400">
            No runs yet. Trigger one above, or ask the agent to call dry_run.
          </div>
        ) : (
          <table className="mono w-full text-xs">
            <thead>
              <tr className="text-left text-slate-500">
                <th className="py-1 pr-3">run_id</th>
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
                <tr key={r.run_id} className="border-t">
                  <td className="py-1 pr-3">{r.run_id}</td>
                  <td className="py-1 pr-3">{r.summary.model}</td>
                  <td className="py-1 pr-3">{r.summary.count}</td>
                  <td className="py-1 pr-3">{r.summary.passed}</td>
                  <td className="py-1 pr-3">{r.summary.pass_rate.toFixed(2)}</td>
                  <td className="py-1 pr-3">{r.summary.total_input_tokens}</td>
                  <td className="py-1 pr-3">{r.summary.total_output_tokens}</td>
                  <td className="py-1 pr-3">
                    {r.summary.mean_latency_ms.toFixed(0)}
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
