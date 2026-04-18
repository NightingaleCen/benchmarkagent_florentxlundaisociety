"use client";

import { useState } from "react";
import { FileEditor } from "./FileEditor";
import { RunsTab } from "./RunsTab";
import { MonitorTab } from "./MonitorTab";
import { api } from "@/lib/api";

type TabKey =
  | "manifest"
  | "dataset"
  | "adapter"
  | "evaluator"
  | "runs"
  | "monitor";

const TABS: { key: TabKey; label: string }[] = [
  { key: "manifest", label: "Manifest" },
  { key: "dataset", label: "Dataset" },
  { key: "adapter", label: "Adapter" },
  { key: "evaluator", label: "Evaluator" },
  { key: "runs", label: "Runs" },
  { key: "monitor", label: "Monitor" },
];

export function ArtifactTabs({
  sessionId,
  refreshToken,
  onArtifactChanged,
}: {
  sessionId: string;
  refreshToken: number;
  onArtifactChanged: () => void;
}) {
  const [active, setActive] = useState("manifest" as TabKey);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);

  async function handleImport(file: File | null) {
    if (!file) return;
    setImporting(true);
    setImportError(null);
    try {
      await api.importBenchmark(sessionId, file);
      onArtifactChanged();
    } catch (e) {
      setImportError((e as Error).message);
    } finally {
      setImporting(false);
    }
  }

  return (
    <div className="flex h-full flex-col bg-white">
      <div className="flex items-center justify-between border-b">
        <div className="flex">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setActive(t.key)}
              className={`px-4 py-2 text-sm ${
                active === t.key
                  ? "border-b-2 border-slate-900 font-semibold text-slate-900"
                  : "text-slate-500 hover:text-slate-900"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="mr-3 flex items-center gap-2">
          <label className="rounded border border-slate-300 px-3 py-1 text-sm text-slate-700 hover:bg-slate-100">
            {importing ? "Importing..." : "Import .zip"}
            <input
              type="file"
              accept=".zip,application/zip"
              className="hidden"
              disabled={importing}
              onChange={(e) => {
                void handleImport(e.target.files?.[0] ?? null);
                e.target.value = "";
              }}
            />
          </label>
          <a
            href={api.exportUrl(sessionId)}
            className="rounded border border-slate-300 px-3 py-1 text-sm text-slate-700 hover:bg-slate-100"
            download
          >
            Export .zip
          </a>
        </div>
      </div>
      {importError && (
        <div className="border-b border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {importError}
        </div>
      )}
      <div className="flex-1 overflow-hidden">
        {active === "manifest" && (
          <FileEditor
            sessionId={sessionId}
            path="manifest.yaml"
            language="yaml"
            refreshToken={refreshToken}
          />
        )}
        {active === "dataset" && (
          <FileEditor
            sessionId={sessionId}
            path="dataset.jsonl"
            language="jsonl"
            emptyHint='one JSON record per line: {"input": {...}, "expected": {...}}'
            refreshToken={refreshToken}
            allowUpload
            allowDownload
            downloadName="dataset.jsonl"
          />
        )}
        {active === "adapter" && (
          <FileEditor
            sessionId={sessionId}
            path="adapter.py"
            language="python"
            refreshToken={refreshToken}
          />
        )}
        {active === "evaluator" && (
          <FileEditor
            sessionId={sessionId}
            path="evaluator.py"
            language="python"
            refreshToken={refreshToken}
          />
        )}
        {active === "runs" && (
          <RunsTab sessionId={sessionId} refreshToken={refreshToken} />
        )}
        {active === "monitor" && (
          <MonitorTab sessionId={sessionId} refreshToken={refreshToken} />
        )}
      </div>
    </div>
  );
}
