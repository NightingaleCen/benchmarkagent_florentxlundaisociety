"use client";

import { useEffect, useRef, useState } from "react";
import { api, ChatEntry } from "@/lib/api";
import { postSSE } from "@/lib/sse";

interface Props {
  sessionId: string;
  onArtifactChanged: () => void;
  agentModel: string;
  allowAgentDataAccess: boolean;
}

interface RenderedMessage {
  id: string;
  role: "user" | "assistant" | "tool" | "error" | "continuation";
  text: string;
  tool?: { name: string; detail: string };
}

function renderToolEntry(name: string, resultRaw: string): string {
  try {
    const r = JSON.parse(resultRaw);
    if (r.ok === false) return `${name} → error: ${r.error}`;
    const keys = r.result ? Object.keys(r.result).slice(0, 3).join(", ") : "";
    return `${name} → ok${keys ? ` (${keys})` : ""}`;
  } catch {
    return `${name} → (unparseable)`;
  }
}

function hydrateFromLog(entries: ChatEntry[]): RenderedMessage[] {
  const out: RenderedMessage[] = [];
  for (let i = 0; i < entries.length; i++) {
    const e = entries[i];
    const id = `${e.ts}-${i}`;
    if (e.role === "user") {
      out.push({ id, role: "user", text: String(e.content) });
    } else if (e.role === "assistant") {
      out.push({ id, role: "assistant", text: String(e.content) });
    } else if (e.role === "tool_use") {
      const c = e.content as { name: string; input: unknown };
      out.push({
        id,
        role: "tool",
        text: "",
        tool: { name: c.name, detail: `calling ${c.name}...` },
      });
    } else if (e.role === "tool_result") {
      const c = e.content as { name: string; result: string };
      out.push({
        id,
        role: "tool",
        text: "",
        tool: { name: c.name, detail: renderToolEntry(c.name, c.result) },
      });
    } else if (e.role === "error") {
      const c = e.content as { message: string };
      out.push({ id, role: "error", text: c.message });
    } else if (e.role === "continuation_required") {
      const c = e.content as { used_iterations: number; model: string };
      out.push({
        id,
        role: "continuation",
        text: `Reached the iteration limit (${c.used_iterations} steps). Click Continue to proceed.`,
      });
    }
  }
  return out;
}

export function ChatPanel({
  sessionId,
  onArtifactChanged,
  agentModel,
  allowAgentDataAccess,
}: Props) {
  const [messages, setMessages] = useState<RenderedMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [needsContinue, setNeedsContinue] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.getMessages(sessionId).then((r) => setMessages(hydrateFromLog(r.entries)));
  }, [sessionId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  async function send() {
    const content = input.trim();
    if (!content || busy) return;
    setInput("");
    setBusy(true);
    setNeedsContinue(false);
    const userMsg: RenderedMessage = {
      id: `local-${Date.now()}`,
      role: "user",
      text: content,
    };
    setMessages((m) => [...m, userMsg]);

    let assistantBuf = "";
    let assistantId: string | null = null;

    try {
      await postSSE(
        `${api.backendUrl}/sessions/${sessionId}/messages`,
        {
          content,
          model: agentModel || undefined,
          allow_agent_data_access: allowAgentDataAccess,
        },
        (ev) => {
          const data = JSON.parse(ev.data);
          if (ev.event === "assistant_text") {
            assistantBuf += data.text;
            if (assistantId === null) {
              assistantId = `asst-${Date.now()}`;
              setMessages((m) => [
                ...m,
                { id: assistantId!, role: "assistant", text: assistantBuf },
              ]);
            } else {
              setMessages((m) =>
                m.map((msg) =>
                  msg.id === assistantId ? { ...msg, text: assistantBuf } : msg,
                ),
              );
            }
          } else if (ev.event === "tool_use") {
            assistantId = null;
            assistantBuf = "";
            setMessages((m) => [
              ...m,
              {
                id: `tu-${data.id}`,
                role: "tool",
                text: "",
                tool: { name: data.name, detail: `calling ${data.name}...` },
              },
            ]);
          } else if (ev.event === "tool_result") {
            assistantId = null;
            assistantBuf = "";
            setMessages((m) => [
              ...m,
              {
                id: `tr-${Date.now()}-${Math.random()}`,
                role: "tool",
                text: "",
                tool: {
                  name: data.name,
                  detail: renderToolEntry(data.name, data.result),
                },
              },
            ]);
            if (data.name === "write_artifact_file" || data.name === "dry_run") {
              onArtifactChanged();
            }
          } else if (ev.event === "error") {
            setMessages((m) => [
              ...m,
              {
                id: `err-${Date.now()}`,
                role: "error",
                text: data.message || "unknown error",
              },
            ]);
          } else if (ev.event === "continuation_required") {
            setNeedsContinue(true);
            setMessages((m) => [
              ...m,
              {
                id: `cont-${Date.now()}`,
                role: "continuation",
                text: `Reached the iteration limit (${data.used_iterations} steps). Click Continue to proceed.`,
              },
            ]);
          }
        },
      );
    } catch (e) {
      setMessages((m) => [
        ...m,
        {
          id: `err-${Date.now()}`,
          role: "error",
          text: (e as Error).message,
        },
      ]);
    } finally {
      setBusy(false);
      onArtifactChanged();
    }
  }

  async function continueTurn() {
    if (busy) return;
    setBusy(true);
    setNeedsContinue(false);

    let assistantBuf = "";
    let assistantId: string | null = null;

    try {
      await postSSE(
        api.continueTurnUrl(sessionId),
        {
          model: agentModel || undefined,
          allow_agent_data_access: allowAgentDataAccess,
        },
        (ev) => {
          const data = JSON.parse(ev.data);
          if (ev.event === "assistant_text") {
            assistantBuf += data.text;
            if (assistantId === null) {
              assistantId = `asst-${Date.now()}`;
              setMessages((m) => [
                ...m,
                { id: assistantId!, role: "assistant", text: assistantBuf },
              ]);
            } else {
              setMessages((m) =>
                m.map((msg) =>
                  msg.id === assistantId ? { ...msg, text: assistantBuf } : msg,
                ),
              );
            }
          } else if (ev.event === "tool_use") {
            assistantId = null;
            assistantBuf = "";
            setMessages((m) => [
              ...m,
              {
                id: `tu-${data.id}`,
                role: "tool",
                text: "",
                tool: { name: data.name, detail: `calling ${data.name}...` },
              },
            ]);
          } else if (ev.event === "tool_result") {
            assistantId = null;
            assistantBuf = "";
            setMessages((m) => [
              ...m,
              {
                id: `tr-${Date.now()}-${Math.random()}`,
                role: "tool",
                text: "",
                tool: {
                  name: data.name,
                  detail: renderToolEntry(data.name, data.result),
                },
              },
            ]);
            if (data.name === "write_artifact_file" || data.name === "dry_run") {
              onArtifactChanged();
            }
          } else if (ev.event === "error") {
            setMessages((m) => [
              ...m,
              {
                id: `err-${Date.now()}`,
                role: "error",
                text: data.message || "unknown error",
              },
            ]);
          } else if (ev.event === "continuation_required") {
            setNeedsContinue(true);
            setMessages((m) => [
              ...m,
              {
                id: `cont-${Date.now()}`,
                role: "continuation",
                text: `Reached the iteration limit (${data.used_iterations} steps). Click Continue to proceed.`,
              },
            ]);
          }
        },
      );
    } catch (e) {
      setMessages((m) => [
        ...m,
        {
          id: `err-${Date.now()}`,
          role: "error",
          text: (e as Error).message,
        },
      ]);
    } finally {
      setBusy(false);
      onArtifactChanged();
    }
  }

  return (
    <div className="flex h-full flex-col bg-white">
      <div className="flex items-center justify-between border-b px-4 py-2">
        <div className="flex items-baseline gap-2">
          <h2 className="text-sm font-semibold text-slate-700">Orchestrator</h2>
          <span className="mono text-xs text-slate-400">{agentModel}</span>
          <span className="rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-500">
            {allowAgentDataAccess ? "dataset visible" : "dataset hidden"}
          </span>
        </div>
        <span className="mono text-xs text-slate-400">session {sessionId}</span>
      </div>
      <div
        ref={scrollRef}
        className="flex-1 space-y-3 overflow-y-auto px-4 py-4"
      >
        {messages.length === 0 && (
          <div className="text-sm text-slate-400">
            Start by describing the task you want to evaluate. E.g. &quot;I want to
            test whether a model correctly classifies support emails as urgent
            or not.&quot;
          </div>
        )}
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
      </div>
      <div className="border-t p-3">
        {needsContinue && (
          <div className="mb-2 flex items-center gap-2 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            <span className="flex-1">The agent paused — iteration limit reached.</span>
            <button
              onClick={continueTurn}
              disabled={busy}
              className="rounded bg-amber-600 px-3 py-1 text-sm text-white hover:bg-amber-700 disabled:bg-amber-300"
            >
              Continue
            </button>
          </div>
        )}
        <textarea
          className="w-full resize-none rounded border border-slate-300 p-2 text-sm outline-none focus:border-slate-500"
          rows={3}
          placeholder={
            busy ? "agent is working..." : "describe your task, or ask a question"
          }
          value={input}
          disabled={busy}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              send();
            }
          }}
        />
        <div className="mt-2 flex items-center justify-between">
          <span className="text-xs text-slate-400">⌘/Ctrl + Enter to send</span>
          <button
            onClick={send}
            disabled={busy || !input.trim()}
            className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-700 disabled:bg-slate-300"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: RenderedMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-lg bg-slate-900 px-3 py-2 text-sm text-white">
          {message.text}
        </div>
      </div>
    );
  }
  if (message.role === "assistant") {
    return (
      <div className="flex justify-start">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-900">
          {message.text}
        </div>
      </div>
    );
  }
  if (message.role === "tool") {
    return (
      <div className="mono text-xs text-slate-500">
        <span className="inline-block rounded bg-slate-50 px-2 py-1">
          {message.tool?.detail ?? message.tool?.name}
        </span>
      </div>
    );
  }
  if (message.role === "continuation") {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
        {message.text}
      </div>
    );
  }
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
      error: {message.text}
    </div>
  );
}
