"use client";

import { useState } from "react";
import { FileEditor } from "./FileEditor";
import { RunsTab } from "./RunsTab";
import { api } from "@/lib/api";

type TabKey =
  | "manifest"
  | "dataset"
  | "adapter"
  | "evaluator"
  | "runs";

const TABS: { key: TabKey; label: string }[] = [
  { key: "manifest", label: "Manifest" },
  { key: "dataset", label: "Dataset" },
  { key: "adapter", label: "Adapter" },
  { key: "evaluator", label: "Evaluator" },
  { key: "runs", label: "Runs" },
];

export function ArtifactTabs({
  sessionId,
  refreshToken,
}: {
  sessionId: string;
  refreshToken: number;
}) {
  const [active, setActive] = useState("manifest" as TabKey);

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
        <a
          href={api.exportUrl(sessionId)}
          className="mr-3 rounded border border-slate-300 px-3 py-1 text-sm text-slate-700 hover:bg-slate-100"
          download
        >
          Export .zip
        </a>
      </div>
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
      </div>
    </div>
  );
}
