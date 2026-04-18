"use client";

import { useEffect, useState } from "react";
import { api, RunDetail as RunDetailData, SampleResult } from "@/lib/api";

type FilterState = "all" | "passed" | "failed" | "errored";

function sampleStatus(s: SampleResult): "pass" | "fail" | "error" {
  if (s.error) return "error";
  return s.score === 1 ? "pass" : "fail";
}

function StatusBadge({ status }: { status: "pass" | "fail" | "error" }) {
  const cls =
    status === "pass"
      ? "bg-green-100 text-green-800"
      : status === "fail"
        ? "bg-red-100 text-red-800"
        : "bg-yellow-100 text-yellow-800";
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${cls}`}>
      {status}
    </span>
  );
}

function JsonBlock({ label, value }: { label: string; value: unknown }) {
  const [open, setOpen] = useState(false);
  if (value === null || value === undefined) return null;
  const text =
    typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 text-xs font-semibold text-slate-600 hover:text-slate-900"
      >
        <span>{open ? "▾" : "▸"}</span>
        {label}
      </button>
      {open && (
        <pre className="mt-1 max-h-64 overflow-auto rounded bg-slate-50 p-2 text-xs text-slate-800">
          {text}
        </pre>
      )}
    </div>
  );
}

function SampleCard({ sample }: { sample: SampleResult }) {
  const [expanded, setExpanded] = useState(false);
  const status = sampleStatus(sample);
  const reasonPreview = sample.reason
    ? sample.reason.length > 80
      ? sample.reason.slice(0, 80) + "…"
      : sample.reason
    : sample.error
      ? sample.error.split("\n")[0].slice(0, 80)
      : "—";

  return (
    <div className="rounded border bg-white">
      <button
        onClick={() => setExpanded((o) => !o)}
        className="flex w-full items-center gap-3 px-3 py-2 text-left text-xs hover:bg-slate-50"
      >
        <span className="mono w-8 shrink-0 text-slate-400">
          #{sample.index}
        </span>
        <StatusBadge status={status} />
        <span className="flex-1 truncate text-slate-700">{reasonPreview}</span>
        {sample.latency_ms !== null && (
          <span className="mono shrink-0 text-slate-400">
            {sample.latency_ms}ms
          </span>
        )}
        {sample.usage && (
          <span className="mono shrink-0 text-slate-400">
            {sample.usage.input_tokens}↑ {sample.usage.output_tokens}↓
          </span>
        )}
        <span className="text-slate-400">{expanded ? "▾" : "▸"}</span>
      </button>

      {expanded && (
        <div className="border-t px-3 py-2">
          <JsonBlock label="input" value={sample.input} />
          <JsonBlock label="expected" value={sample.expected} />
          <JsonBlock label="model_output" value={sample.model_output} />
          {sample.judge_trace && (
            <JsonBlock label="judge_trace" value={sample.judge_trace} />
          )}
          {sample.raw_response !== undefined &&
            sample.raw_response !== null && (
              <JsonBlock label="raw_response (provider)" value={sample.raw_response} />
            )}
          {sample.error && (
            <div className="mt-2">
              <span className="text-xs font-semibold text-red-700">error</span>
              <pre className="mt-1 max-h-48 overflow-auto rounded bg-red-50 p-2 text-xs text-red-800">
                {sample.error}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function RunDetail({
  sessionId,
  runId,
  onBack,
}: {
  sessionId: string;
  runId: string;
  onBack: () => void;
}) {
  const [data, setData] = useState<RunDetailData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterState>("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    api
      .getRun(sessionId, runId)
      .then(setData)
      .catch((e) => setError((e as Error).message));
  }, [sessionId, runId]);

  const filtered = data?.results.filter((s) => {
    if (filter === "passed" && sampleStatus(s) !== "pass") return false;
    if (filter === "failed" && sampleStatus(s) !== "fail") return false;
    if (filter === "errored" && sampleStatus(s) !== "error") return false;
    if (search) {
      const hay =
        (s.reason ?? "") +
        JSON.stringify(s.input) +
        JSON.stringify(s.model_output);
      if (!hay.toLowerCase().includes(search.toLowerCase())) return false;
    }
    return true;
  });

  const jsonlUrl = api.runFileUrl(sessionId, runId, "results.jsonl");
  const summaryUrl = api.runFileUrl(sessionId, runId, "summary.json");
  const zipUrl = api.runZipUrl(sessionId, runId);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* top bar */}
      <div className="flex shrink-0 items-center gap-2 border-b p-3">
        <button
          onClick={onBack}
          className="rounded border px-2 py-1 text-xs text-slate-600 hover:bg-slate-100"
        >
          ← back to runs
        </button>
        <span className="mono flex-1 truncate text-xs text-slate-500">
          {runId}
        </span>
        <a
          href={jsonlUrl}
          download="results.jsonl"
          className="rounded border px-2 py-1 text-xs text-slate-600 hover:bg-slate-100"
        >
          results.jsonl
        </a>
        <a
          href={summaryUrl}
          download="summary.json"
          className="rounded border px-2 py-1 text-xs text-slate-600 hover:bg-slate-100"
        >
          summary.json
        </a>
        <a
          href={zipUrl}
          download={`${runId}.zip`}
          className="rounded bg-slate-900 px-2 py-1 text-xs text-white hover:bg-slate-700"
        >
          run.zip
        </a>
      </div>

      {error && (
        <div className="shrink-0 border-b border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {error}
        </div>
      )}

      {!data && !error && (
        <div className="flex flex-1 items-center justify-center text-sm text-slate-400">
          loading…
        </div>
      )}

      {data && (
        <>
          {/* summary card */}
          <div className="mono shrink-0 grid grid-cols-4 gap-x-4 gap-y-1 border-b bg-slate-50 px-4 py-3 text-xs">
            <span className="text-slate-500">model</span>
            <span className="col-span-3 truncate">{data.summary.model}</span>
            <span className="text-slate-500">pass rate</span>
            <span className="col-span-3">
              {(data.summary.pass_rate * 100).toFixed(1)}% (
              {data.summary.passed} / {data.summary.count})
            </span>
            <span className="text-slate-500">failed / errored</span>
            <span className="col-span-3">
              {data.summary.failed} / {data.summary.errored}
            </span>
            <span className="text-slate-500">tokens</span>
            <span className="col-span-3">
              {data.summary.total_input_tokens}↑{" "}
              {data.summary.total_output_tokens}↓
            </span>
            <span className="text-slate-500">avg latency</span>
            <span className="col-span-3">
              {data.summary.mean_latency_ms.toFixed(0)} ms
            </span>
            <span className="text-slate-500">judge</span>
            <span className="col-span-3">
              {String(data.summary.judge_config?.type ?? "—")}
              {data.summary.judge_config?.model
                ? ` · ${data.summary.judge_config.model}`
                : ""}
            </span>
            <span className="text-slate-500">started</span>
            <span className="col-span-3">{data.summary.started_at}</span>
          </div>

          {/* filter bar */}
          <div className="flex shrink-0 items-center gap-2 border-b px-3 py-2">
            {(["all", "passed", "failed", "errored"] as FilterState[]).map(
              (f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={`rounded px-2 py-1 text-xs ${
                    filter === f
                      ? "bg-slate-900 text-white"
                      : "border text-slate-600 hover:bg-slate-100"
                  }`}
                >
                  {f}
                </button>
              ),
            )}
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="search reason / input…"
              className="mono ml-2 flex-1 rounded border px-2 py-1 text-xs"
            />
            <span className="text-xs text-slate-400">
              {filtered?.length ?? 0} / {data.results.length}
            </span>
          </div>

          {/* sample list */}
          <div className="flex-1 space-y-1 overflow-y-auto p-3">
            {filtered?.length === 0 && (
              <div className="text-sm text-slate-400">no matching samples</div>
            )}
            {filtered?.map((s) => <SampleCard key={s.index} sample={s} />)}
          </div>
        </>
      )}
    </div>
  );
}
