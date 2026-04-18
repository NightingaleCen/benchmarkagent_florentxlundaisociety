"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface Props {
  sessionId: string;
  path: string;
  language?: string;
  emptyHint?: string;
  refreshToken?: number;
  allowUpload?: boolean;
  allowDownload?: boolean;
  downloadName?: string;
}

export function FileEditor({
  sessionId,
  path,
  language = "text",
  emptyHint,
  refreshToken,
  allowUpload = false,
  allowDownload = false,
  downloadName,
}: Props) {
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [missing, setMissing] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  async function reload() {
    setLoading(true);
    try {
      const r = await api.readFile(sessionId, path);
      setContent(r.content);
      setMissing(false);
      setDirty(false);
    } catch {
      setContent("");
      setMissing(true);
      setDirty(false);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, path, refreshToken]);

  async function save() {
    setSaving(true);
    try {
      await api.writeFile(sessionId, path, content);
      setMissing(false);
      setDirty(false);
    } finally {
      setSaving(false);
    }
  }

  async function handleUpload(file: File | null) {
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    try {
      const text = await file.text();
      await api.writeFile(sessionId, path, text);
      setContent(text);
      setMissing(false);
      setDirty(false);
    } catch (e) {
      setUploadError((e as Error).message);
    } finally {
      setUploading(false);
    }
  }

  function handleDownload() {
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = downloadName || path.split("/").pop() || "download.txt";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b px-3 py-2 text-xs">
        <span className="mono text-slate-500">{path}</span>
        <div className="flex items-center gap-2">
          <span className="text-slate-400">{language}</span>
          {missing && <span className="text-amber-600">not created yet</span>}
          {dirty && <span className="text-amber-600">unsaved</span>}
          {allowUpload && (
            <label className="rounded border px-2 py-0.5 text-slate-600 hover:bg-slate-100">
              {uploading ? "uploading..." : "upload file"}
              <input
                type="file"
                className="hidden"
                disabled={uploading}
                onChange={(e) => {
                  void handleUpload(e.target.files?.[0] ?? null);
                  e.target.value = "";
                }}
              />
            </label>
          )}
          {allowDownload && (
            <button
              onClick={handleDownload}
              disabled={loading || missing}
              className="rounded border px-2 py-0.5 text-slate-600 hover:bg-slate-100 disabled:text-slate-300"
            >
              download
            </button>
          )}
          <button
            onClick={reload}
            className="rounded border px-2 py-0.5 text-slate-600 hover:bg-slate-100"
          >
            refresh
          </button>
          <button
            onClick={save}
            disabled={!dirty || saving}
            className="rounded bg-slate-900 px-2 py-0.5 text-white hover:bg-slate-700 disabled:bg-slate-300"
          >
            {saving ? "saving..." : "save"}
          </button>
        </div>
      </div>
      {uploadError && (
        <div className="border-b border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {uploadError}
        </div>
      )}
      {loading ? (
        <div className="flex-1 p-4 text-sm text-slate-400">loading...</div>
      ) : missing && !dirty ? (
        <div className="flex-1 p-4 text-sm text-slate-400">
          {emptyHint ||
            "this file does not exist yet. Ask the agent to create it, or start typing to draft it yourself."}
          <button
            onClick={() => {
              setMissing(false);
              setDirty(true);
            }}
            className="ml-3 rounded border px-2 py-0.5 text-xs text-slate-700 hover:bg-slate-100"
          >
            start editing
          </button>
        </div>
      ) : (
        <textarea
          className="mono flex-1 resize-none p-3 text-xs outline-none"
          value={content}
          onChange={(e) => {
            setContent(e.target.value);
            setDirty(true);
          }}
          spellCheck={false}
        />
      )}
    </div>
  );
}
