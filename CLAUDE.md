# BenchmarkAgent

> Agent-assisted construction and execution of task-specific LLM benchmarks for non-technical users.

This document is the canonical reference for the project. It defines what we are building, how it is structured, the conventions we follow, and the decisions we have already made (so they don't have to be re-litigated). Future Claude Code sessions should read this first.

---

## 1. Mission

LLMs are powerful but hard to evaluate on real, domain-specific tasks. Existing eval tools (HELM, OpenAI Evals, lm-evaluation-harness) assume ML expertise and offer no help with the hardest part: **figuring out what to measure**.

BenchmarkAgent closes that gap. A non-technical domain expert (a lawyer, a biotech PM, a support lead) describes their use case in plain language, and the system guides them — through interview, examples, and tradeoff explanations — to a complete benchmark they can run repeatedly against any LLM.

The output is not a chat transcript or a report. **The output is a self-contained, versioned, executable benchmark artifact** that can be exported, shared, and re-run independently of our agent infrastructure. This is the product's core value proposition: rigor that survives outside the conversation.

---

## 2. Product Shape: Three Decoupled Phases

The system has three phases, deliberately separated so each can be reasoned about, tested, and replaced independently.

```
┌────────────────────┐    ┌──────────────────────┐    ┌──────────────────┐
│   1. Construction  │───▶│   2. Artifact        │───▶│   3. Execution   │
│   (agent-driven)   │    │   (standalone)       │    │   (deterministic)│
│                    │    │                      │    │                  │
│ User chats with    │    │ Directory of files:  │    │ `benchmarkrun`   │
│ orchestrator agent │    │  manifest.yaml       │    │ CLI loads the    │
│ in a web UI to     │    │  dataset.jsonl       │    │ artifact and runs│
│ produce an artifact│    │  adapter.py          │    │ it against any   │
│                    │    │  evaluator.py        │    │ supported model  │
└────────────────────┘    └──────────────────────┘    └──────────────────┘
       interactive              file system               batch / CLI
```

The boundary between (1) and (2) is the **artifact directory** — the agent writes files, the user edits files, export is just zipping a directory. The boundary between (2) and (3) is the **artifact schema** — `benchmarkrun` knows nothing about how the artifact was made.

This separation is non-negotiable. An artifact is worthless if it can only be run by the same system that built it.

---

## 3. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                       Frontend (Next.js + shadcn/ui)                 │
│  ┌─────────────────────┐  ┌──────────────────────────────────────┐   │
│  │ Chat panel          │  │ Structured artifact panels (tabs):   │   │
│  │ — orchestrator      │  │  Intent · Schema · Dataset           │   │
│  │   conversation,     │  │  Adapter · Evaluator · Run results   │   │
│  │   streaming via SSE │  │ Each tab edits a file in the session │   │
│  └─────────────────────┘  └──────────────────────────────────────┘   │
└─────────────────┬─────────────────────────────────┬──────────────────┘
                  │ SSE (chat stream)               │ REST (file CRUD,
                  │                                 │ run trigger)
┌─────────────────▼─────────────────────────────────▼──────────────────┐
│                   Backend (FastAPI + Claude Agent SDK)               │
│                                                                      │
│  Orchestrator Agent (main)                                           │
│   ├─ tool: read_artifact_file / write_artifact_file                  │
│   ├─ tool: generate_schema_draft(intent_summary)                     │
│   ├─ tool: generate_adapter_draft(schema, model_io_format)           │
│   ├─ tool: generate_evaluator_draft(output_schema, criteria)         │
│   ├─ tool: dry_run(sample_size=3) — invokes runner internally        │
│   ├─ sub-agent: adapter_fixer / evaluator_fixer                      │
│   │      (spawned on dry_run failure; iterates in isolation          │
│   │       until the file passes, returns only the fixed file)        │
│   └─ sub-agent: data_processor (only on user opt-in for data access) │
│                                                                      │
│  Session store (local FS for MVP)                                    │
│   sessions/{id}/artifact/  ← live, editable workspace                │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    │  Export → zip
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│              Standalone Artifact (the deliverable)                   │
│   my_benchmark/                                                      │
│     manifest.yaml      task metadata, schemas, judge config          │
│     dataset.jsonl      test cases (input + expected)                 │
│     adapter.py         model invocation logic                        │
│     evaluator.py       evaluation logic (returns 0/1 + reason)       │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    │  pip install benchmarkrun
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│                Execution Engine (`benchmarkrun` CLI)                 │
│                                                                      │
│   $ benchmarkrun ./my_benchmark --model claude-sonnet-4-6            │
│                                                                      │
│   Loads manifest → dynamically imports adapter & evaluator           │
│   → iterates dataset → calls model via adapter                       │
│   → scores via evaluator → writes results.jsonl + summary.json       │
│                                                                      │
│   Zero dependency on backend or frontend. Runs anywhere Python runs. │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 4. Repository Layout

Monorepo with strict dependency direction: **runner depends on nothing the user can't install standalone**. Backend and frontend may depend on `artifact_schema`, but nothing in `packages/` may depend on anything in `apps/`.

```
benchmarkagent/
├── apps/
│   ├── backend/                          # FastAPI + Claude Agent SDK
│   │   ├── pyproject.toml
│   │   ├── src/backend/
│   │   │   ├── main.py                   # FastAPI entrypoint
│   │   │   ├── config.py
│   │   │   ├── sessions.py               # session/workspace lifecycle
│   │   │   ├── agent/
│   │   │   │   ├── orchestrator.py       # main agent definition + system prompt
│   │   │   │   ├── tools.py              # tool implementations
│   │   │   │   ├── data_processor.py     # opt-in sub-agent
│   │   │   │   └── prompts/              # prompt templates as files
│   │   │   └── api/
│   │   │       ├── chat.py               # POST /sessions/{id}/messages (SSE)
│   │   │       ├── artifact.py           # GET/PUT /sessions/{id}/artifact/*
│   │   │       ├── runs.py               # POST /sessions/{id}/runs
│   │   │       └── export.py             # GET /sessions/{id}/export.zip
│   │   ├── tests/
│   │   └── sessions/                     # gitignored — runtime workspaces
│   └── frontend/                         # Next.js 14 (App Router) + shadcn/ui
│       ├── package.json
│       ├── app/
│       │   ├── page.tsx                  # main two-pane layout
│       │   ├── layout.tsx
│       │   └── api/                      # only thin proxies to backend
│       ├── components/
│       │   ├── ChatPanel.tsx
│       │   ├── ArtifactTabs.tsx
│       │   ├── tabs/
│       │   │   ├── IntentTab.tsx
│       │   │   ├── SchemaTab.tsx
│       │   │   ├── DatasetTab.tsx
│       │   │   ├── AdapterTab.tsx
│       │   │   ├── EvaluatorTab.tsx
│       │   │   └── ResultsTab.tsx
│       │   └── ExportButton.tsx
│       └── lib/
│           ├── api.ts                    # backend client
│           └── sse.ts                    # SSE helpers
├── packages/
│   ├── runner/                           # `benchmarkrun` — the standalone CLI
│   │   ├── pyproject.toml                # deps: pyyaml, anthropic, openai, pydantic
│   │   ├── src/benchmarkrun/
│   │   │   ├── __init__.py
│   │   │   ├── cli.py                    # entrypoint registered as `benchmarkrun`
│   │   │   ├── loader.py                 # load manifest, import adapter/evaluator
│   │   │   ├── runtime.py                # main execution loop
│   │   │   ├── model_clients.py          # thin wrappers: anthropic, openai
│   │   │   ├── judges.py                 # rule judge + llm-as-judge helpers
│   │   │   └── reporting.py              # results.jsonl + summary.json writers
│   │   └── tests/
│   └── artifact_schema/                  # the contract between phases
│       ├── pyproject.toml                # deps: pydantic, pyyaml only
│       ├── src/artifact_schema/
│       │   ├── __init__.py
│       │   ├── manifest.py               # Pydantic models for manifest.yaml
│       │   ├── dataset.py                # Pydantic models for dataset records
│       │   └── jsonschema/
│       │       └── manifest.schema.json  # generated, for editor tooling
│       └── tests/
├── examples/
│   └── classification_demo/              # canonical example & first runner test
│       ├── manifest.yaml
│       ├── dataset.jsonl
│       ├── adapter.py
│       └── evaluator.py
├── docs/
│   ├── artifact-spec.md                  # human-readable artifact format spec
│   └── adr/                              # architecture decision records
├── CLAUDE.md                             # this file
└── README.md
```

**Dependency rules (enforced in code review):**

- `packages/runner` may import `packages/artifact_schema`. Nothing else.
- `packages/artifact_schema` imports nothing from this repo.
- `apps/backend` may import both `packages/`. Never the reverse.
- `apps/frontend` talks to `apps/backend` only via HTTP. No shared TypeScript types generated from Python (yet) — keep the boundary thin and explicit.

---

## 5. The Artifact Specification

The artifact is the most important contract in the system. It must be:

- **Human-readable**: a domain expert should be able to open a file and understand it.
- **Human-editable**: a power user should be able to edit any file by hand without breaking things.
- **Self-describing**: the manifest declares what's in the artifact and how to run it.
- **Versioned**: every manifest has `schema_version`; the runner refuses incompatible versions.
- **Reproducible**: every source of nondeterminism (e.g., LLM-as-judge model + temperature) is pinned in the manifest.

### `manifest.yaml`

```yaml
schema_version: "0.1"

name: "contract-clause-classifier"
description: "Identify whether a contract clause is an indemnification clause."
created_by: "agent-session-{uuid}"
created_at: "2026-04-18T10:30:00Z"

task:
  type: "binary_classification"          # MVP: only this type
  input_schema:
    clause_text: { type: string }
  output_schema:
    label: { type: string, enum: ["indemnification", "other"] }

adapter:
  module: "adapter.py"
  entrypoint: "run_model"

evaluator:
  module: "evaluator.py"
  entrypoint: "evaluate"
  judge:
    type: "rule"                          # "rule" | "llm"
    # When type == "llm", the following fields are REQUIRED:
    # model: "claude-sonnet-4-6"
    # temperature: 0
    # prompt_template: "..."

dataset:
  path: "dataset.jsonl"
  count: 50

runtime:
  python: ">=3.11"
  requirements:                          # extra pip deps the adapter/evaluator need
    - "tiktoken>=0.5"
    - "requests>=2.31"
```

The `runtime` section is the artifact's dependency manifest. The runner validates that declared packages are importable at startup and refuses to run if anything is missing, with a message telling the user exactly what to `pip install`. This is how we make good on the "runs anywhere Python runs" promise without forcing every artifact to bundle its environment.

### `adapter.py` — Interface Contract

A single Python function. The runner dynamically imports the module and calls the entrypoint once per dataset record. **Nothing in `adapter.py` may import from the agent backend, Claude Agent SDK, or any service that is not reachable from the user's machine.**

**Signature:**

```python
def run_model(model_client: ModelClient, input_record: dict) -> dict:
    ...
```

**Input:**

- `model_client`: an instance the runner constructs from the `--model` flag. See Model Client Interface below.
- `input_record`: the `input` field of one dataset record (not the whole record). A dict matching `task.input_schema`.

**Required return shape:**

```python
{
    "output": dict,              # must match task.output_schema — the model's answer
    "usage": {                   # token accounting; aggregated into summary.json
        "input_tokens": int,
        "output_tokens": int,
    },
    "latency_ms": int,           # wall-clock time of the full adapter call
    "raw_response": Any,         # optional. raw provider payload, preserved for debugging
}
```

**Rules:**

- The adapter MAY call the model multiple times internally (chain-of-thought, multi-step tool use, retries with different prompts). The interface stays "one input record → one structured output."
- The adapter MUST NOT reach into the evaluator, the judge, or any scoring logic. Its sole job is to produce the model's answer.
- On failure (API error, parse failure, timeout), **raise an exception**. The runner catches it, records the sample as an error with the traceback in `results.jsonl`, and continues to the next sample. A single bad sample never aborts the run.

**Example:**

```python
import time

def run_model(model_client, input_record: dict) -> dict:
    start = time.perf_counter()
    response = model_client.complete(
        prompt=f"Classify this clause: {input_record['clause_text']}",
    )
    return {
        "output": {"label": response.text.strip().lower()},
        "usage": {"input_tokens": response.input_tokens, "output_tokens": response.output_tokens},
        "latency_ms": int((time.perf_counter() - start) * 1000),
        "raw_response": response.raw,
    }
```

### Model Client Interface

The runner provides a `ModelClient` to every adapter. The client is a minimum portable abstraction — not a complete wrapper around every provider feature. It exposes:

```python
class ModelClient(Protocol):
    def complete(self, prompt: str, **kwargs) -> CompletionResponse: ...
    def messages(self, messages: list[dict], **kwargs) -> CompletionResponse: ...

    # escape hatch for provider-specific features
    raw_client: Any  # the underlying anthropic.Anthropic() or openai.OpenAI()

class CompletionResponse:
    text: str
    input_tokens: int
    output_tokens: int
    raw: Any          # raw provider response
```

If an adapter needs a provider-specific feature (Anthropic extended thinking, OpenAI structured outputs, etc.), it uses `model_client.raw_client` and must declare the provider SDK in `runtime.requirements`. The common case — "prompt in, text out" — is covered by `.complete()` and stays portable across providers.

### `evaluator.py` — Interface Contract

A single Python function. The runner imports it and calls the entrypoint once per adapter result.

**Signature:**

```python
def evaluate(model_output: dict, expected: dict, judge: Judge | None = None) -> dict:
    ...
```

**Input:**

- `model_output`: the `output` field from the adapter's return value (not the whole adapter result).
- `expected`: the `expected` field from the dataset record.
- `judge`: provided by the runner based on `evaluator.judge` in the manifest. `None` for pure rule evaluators; a `Judge` instance (see below) when `judge.type == "llm"`.

**Required return shape:**

```python
{
    "score": int,                # 0 or 1 in MVP. reserved for finer-grained scales later.
    "reason": str,               # human-readable justification — shown in results UI
    "judge_trace": dict,         # optional. when LLM-as-judge is used:
                                 #   {"prompt": str, "raw_response": Any, "model": str}
}
```

**Rules:**

- Rule-based evaluators ignore the `judge` argument and return scores from deterministic logic.
- LLM-as-judge evaluators call `judge.score(...)`, which wraps the pinned `model`, `temperature=0`, and `prompt_template` from the manifest. Evaluators never instantiate their own LLM client for judging — always go through `judge` so the manifest remains the single source of truth for judge configuration.
- On failure, raise an exception. Same semantics as adapter failures.

**Example (rule-based):**

```python
def evaluate(model_output: dict, expected: dict, judge=None) -> dict:
    score = 1 if model_output.get("label") == expected.get("label") else 0
    return {
        "score": score,
        "reason": f"expected={expected['label']}, got={model_output.get('label')}",
    }
```

**Example (LLM-as-judge):**

```python
def evaluate(model_output: dict, expected: dict, judge=None) -> dict:
    verdict = judge.score(
        model_answer=model_output["answer"],
        reference=expected["reference_answer"],
    )
    return {
        "score": 1 if verdict.pass_ else 0,
        "reason": verdict.explanation,
        "judge_trace": {"prompt": verdict.prompt, "raw_response": verdict.raw, "model": verdict.model},
    }
```

### Judge Interface

The runner constructs a `Judge` from `manifest.evaluator.judge` when `type == "llm"`:

```python
class Judge(Protocol):
    def score(self, **fields) -> JudgeVerdict: ...

class JudgeVerdict:
    pass_: bool
    explanation: str
    prompt: str        # the rendered prompt, for audit
    raw: Any           # raw judge model response
    model: str         # judge model ID, for audit
```

The `**fields` passed to `score()` are substituted into the pinned `prompt_template`. This keeps the judge prompt fully declared in the manifest — the evaluator code only decides *what fields to compare*, never *how the judge is configured*.

### `dataset.jsonl`

One JSON object per line. Each line has `input` (matches `input_schema`) and `expected` (matches `output_schema`).

```jsonl
{"input": {"clause_text": "Party A shall indemnify..."}, "expected": {"label": "indemnification"}}
{"input": {"clause_text": "This agreement is governed by..."}, "expected": {"label": "other"}}
```

### Output (produced by `benchmarkrun`)

`results.jsonl` — one line per test case with `input`, `model_output`, `expected`, `score`, `reason`, and `judge_raw_response` (when LLM-as-judge is used).

`summary.json` — aggregate stats: `pass_rate`, `count`, `model`, `judge_config`, `runner_version`, `started_at`, `finished_at`.

---

## 6. Component Specifications

### 6.1 `packages/artifact_schema`

The single source of truth for what an artifact looks like. Pydantic models for all four files, plus a JSON Schema export for editor tooling.

Critical responsibilities:
- Validate a manifest on load. Reject anything ambiguous.
- Enforce that `judge.type == "llm"` implies `model`, `temperature`, and `prompt_template` are present.
- Own the `schema_version` constant and any future migration logic.

### 6.2 `packages/runner` (`benchmarkrun`)

A standalone, pip-installable CLI. **Build this as if it will live in a different repo** — never reach for backend code.

Responsibilities:
- Parse CLI args: `benchmarkrun <artifact_dir> --model <model_id> [--limit N] [--out <dir>]`.
- Load and validate the manifest via `artifact_schema`.
- Dynamically import `adapter.py` and `evaluator.py` from the artifact directory.
- Construct a model client based on `--model` (Anthropic or OpenAI in MVP).
- Iterate `dataset.jsonl`, call adapter, call evaluator, accumulate results.
- Write `results.jsonl` and `summary.json` to the output directory.
- Exit nonzero if validation or execution fails; log clearly.

The runner must not require a network call to start (validation is offline). It must be safe to run with `--limit 1` for smoke-testing.

### 6.3 `apps/backend`

FastAPI service that wraps Claude Agent SDK. Owns session workspaces.

Endpoints:
- `POST /sessions` → create a new session, returns `{id}`.
- `GET /sessions/{id}/artifact/*` → serve files in the workspace.
- `PUT /sessions/{id}/artifact/*` → write a file (used by the frontend's edit-in-place tabs).
- `POST /sessions/{id}/messages` → SSE stream of orchestrator output.
- `POST /sessions/{id}/runs` → trigger a `benchmarkrun` execution against the workspace, stream results.
- `GET /sessions/{id}/export.zip` → download the artifact.

Sessions are filesystem directories under `apps/backend/sessions/`. No database in MVP. This trades durability for simplicity; we accept the loss of all sessions on disk wipe and revisit when there's a real user base.

### 6.4 `apps/frontend`

Next.js 14 with App Router and shadcn/ui. Two-pane layout: chat on the left, artifact tabs on the right.

Each tab is a thin editor over a single file:
- **Intent**: a notes scratchpad — what the user is trying to evaluate. Free text.
- **Schema**: pretty-printed view of `manifest.yaml`'s `task.input_schema` / `task.output_schema`, with a raw YAML toggle.
- **Dataset**: table view of `dataset.jsonl`, with row add/edit/delete.
- **Adapter / Evaluator**: Monaco editor over the Python files.
- **Results**: rendered view of the most recent run's `summary.json` and `results.jsonl`.

The frontend is dumb on purpose. All logic lives in the backend or in the artifact files themselves. The frontend renders state and forwards intent.

### 6.5 Orchestrator Agent

Built with the Claude Agent SDK. The system prompt establishes:

- **Role**: a benchmark construction guide. Conversational, not lecture-y. Ask questions before generating.
- **Workflow** (rough; agent is allowed to deviate when the user steers):
  1. Interview to understand the task and what "good" means for it.
  2. Propose a draft `task.input_schema` / `output_schema`. Get confirmation.
  3. Decide dataset source: user uploads, or (with explicit consent) `data_processor` sub-agent extracts from raw user data.
  4. Draft `adapter.py` together with the user.
  5. Draft `evaluator.py`, including judge type. If LLM-as-judge, walk through judge prompt and pin temperature.
  6. Run `dry_run(sample_size=3)` to verify everything wires up.
  7. Hand off — user reviews, edits, exports.
- **Constraint**: every artifact change goes through `write_artifact_file`. The agent never "remembers" state in the conversation; the workspace is the source of truth.
- **Constraint**: the agent must not invent task details. When information is missing, ask.

#### Sub-agents vs Tools — when to use which

The orchestrator has both tools and sub-agents. The distinction is not "important vs unimportant" — it's about whether the work needs its own multi-turn loop or isolated context.

**Use a tool** for single-shot operations whose decisions should remain visible in the main conversation:

- `generate_schema_draft`, `generate_adapter_draft`, `generate_evaluator_draft` — the user sees what was generated and why; the orchestrator carries the result forward (e.g., designs the evaluator with knowledge of the adapter shape).
- `read_artifact_file`, `write_artifact_file` — direct file ops.
- `dry_run` — runs the runner on a small sample and returns the result structured.

If the decision is "describe intent → get one artifact back," it's a tool. Full stop.

**Use a sub-agent** when the work genuinely needs independent multi-turn reasoning or context isolation:

- `adapter_fixer` / `evaluator_fixer` — spawned when `dry_run` reports a failure. Given the current file, the offending sample, and the error, the sub-agent iterates on the code in its own loop until `dry_run` passes (or it gives up with a reasoned explanation). Only the final file and a one-line verdict return to the main orchestrator. This keeps debugging noise out of the user-facing chat.
- `data_processor` — spawned with explicit user consent to process raw user data into `dataset.jsonl`. Separation here is a **privacy boundary**, not just a complexity boundary: the main orchestrator never receives raw user data, only the schema-conforming output. This makes the privacy promise inspectable in the codebase.

The rule: if a task can be completed in one generation, it's a tool; if it needs a loop or must not contaminate the main context, it's a sub-agent.

---

## 7. Design Principles

These are load-bearing decisions. Don't quietly violate them.

1. **Artifact independence is sacred.** The runner must not import backend code. The artifact must run on a fresh machine with only `pip install benchmarkrun`. If a feature would require coupling, find another way.

2. **The agent produces files, not summaries.** Every meaningful output is a write to the workspace. The frontend reads files, not chat history.

3. **Determinism is enforced at the manifest level.** Any source of nondeterminism (LLM judges, sampling, random seeds) must be declared and pinned in `manifest.yaml`. The runner refuses to run if pinning is missing.

4. **Boundaries are typed contracts.** Use Pydantic at every internal boundary (manifest, dataset records, adapter return, evaluator return). Validation errors should be loud and early.

5. **Build for the editor, not just the agent.** A power user should be able to delete the agent entirely and still produce a valid artifact by hand-editing files. If the format is hard to edit by hand, it is wrong.

6. **No premature abstractions.** MVP supports one task type, two model providers, two judge types. Don't generalize until the second use case is real.

7. **No agent at runtime.** The runner imports pure Python — nothing in `adapter.py` or `evaluator.py` may depend on the orchestrator, Claude Agent SDK, or any backend service. LLM-as-judge is a plain provider API call, not an agent call. Every piece of information the generated code needs at run-time must be written into the file or the manifest, never left implicit in "what the agent remembered during construction." The agent compiles the artifact; once compiled, the agent is gone.

8. **Declared dependencies, not assumed ones.** Any extra pip package the artifact uses must appear in `manifest.runtime.requirements`. The runner validates presence at startup. An artifact that silently assumes `tiktoken` is installed is a broken artifact.

---

## 8. MVP Scope

**In scope:**

- One task type: `binary_classification` (text input → label).
- Two judge types: rule-based (string equality / regex) and LLM-as-judge (with pinned config).
- Two model providers in the runner: Anthropic and OpenAI.
- Single-user, no auth, local filesystem session store.
- Full loop: chat-driven construction → in-browser artifact editing → export → standalone CLI execution.

**Explicitly out of scope for MVP** (extension points reserved, not implemented):

- Other task types (generation, extraction, multi-turn). Will require new `task.type` values and richer schema support.
- Rubric or multi-dimensional scoring. The evaluator return is already a dict; just add fields later.
- Multi-user, auth, persistent database.
- Artifact versioning and diff (git-style history within a session).
- Custom HTTP-endpoint model adapters (the existing adapter.py format already supports this, we just don't ship a template).
- Sandboxing for adapter/evaluator code. **MVP runs user-authored Python with full privileges.** Document this prominently. When we add artifact sharing, this gets sandboxed (likely subprocess isolation with resource limits, possibly WASM later).

---

## 9. Development Roadmap

Build in this order. Each step is independently verifiable, which means each step adds a checkpoint where the work so far has standalone value.

### Phase A — The Contract (`packages/artifact_schema`)

Define Pydantic models for `manifest.yaml`, `dataset.jsonl` records, adapter return, evaluator return. Generate `manifest.schema.json`. Write tests for valid and invalid manifests.

**Done when:** loading a valid manifest succeeds, loading a malformed one raises a clear error.

### Phase B — The Example (`examples/classification_demo`)

Hand-write a complete artifact (manifest, dataset of ~10 cases, adapter, evaluator) for a trivial task. This is the runner's first test target and the spec's first reality check.

**Done when:** the example validates against `artifact_schema`.

### Phase C — The Runner (`packages/runner`)

Implement `benchmarkrun` CLI. Wire model clients for Anthropic and OpenAI. Implement rule-based and LLM-as-judge paths.

**Done when:** `benchmarkrun ./examples/classification_demo --model claude-sonnet-4-6` produces `results.jsonl` and `summary.json` with a sensible pass rate. The standalone-execution promise is now real.

### Phase D — The Backend (`apps/backend`)

FastAPI app. Session workspace management. Claude Agent SDK integration. Implement the core tools (`read_artifact_file`, `write_artifact_file`, `generate_*_draft`, `dry_run`). Wire the SSE chat endpoint.

**Done when:** an HTTP client can create a session, exchange messages with the orchestrator, and observe artifact files appearing in the workspace.

### Phase E — The Frontend (`apps/frontend`)

Next.js app with two-pane layout. Read-only artifact tabs first (proves the data flow), then editable tabs, then run-trigger and results view, then export.

**Done when:** a user can complete the full flow in the browser without touching a terminal.

### Phase F — Integration & Polish

End-to-end run: chat to construct → edit → export → CLI run on the exported zip. Fix the rough edges that only show up when the seams are stretched.

**Done when:** the verification scenarios in §10 all pass.

---

## 10. Verification Strategy

These are the scenarios that, when they all pass, mean the MVP is real.

### 10.1 Standalone runner test

```bash
cd packages/runner && pip install -e .
cd ../../examples/classification_demo
benchmarkrun . --model claude-sonnet-4-6 --limit 3
```

Without the backend or frontend ever starting, this must produce valid `results.jsonl` and `summary.json`. If this fails, the artifact independence promise is broken and nothing else matters.

### 10.2 Agent end-to-end construction

Start backend (`uvicorn backend.main:app`) and frontend (`pnpm dev`). In the browser:

1. Send: "I want to evaluate whether a model can detect spam emails."
2. Follow the orchestrator's questions; let it draft each piece.
3. Edit at least one file by hand in the artifact panels.
4. Trigger a dry run; see results render.
5. Click Export.
6. Unzip in a fresh directory; run `benchmarkrun . --model ...`.

The exported artifact must run identically to how it ran inside the session.

### 10.3 Determinism check

Run the same artifact twice with the same model:

- Rule-based judge: results.jsonl must be byte-identical (modulo timestamps in summary.json).
- LLM-as-judge with `temperature=0`: ≥95% of scores match (perfect match is unrealistic due to model nondeterminism, but close).

### 10.4 Refusal-to-hallucinate check

In the chat: "Just give me a benchmark for legal stuff."

Expected: the orchestrator asks clarifying questions about the specific task, expected behavior, and data availability. It must not produce a plausible-but-fabricated artifact.

### 10.5 Validation contract check

Manually corrupt the example's `manifest.yaml` (e.g., remove `schema_version`, set `judge.type: "llm"` without `model`). Run the runner.

Expected: nonzero exit, clear error message naming the missing field.

---

## 11. Conventions

- **Python**: 3.11+, type hints required on public functions, Pydantic for data classes, `ruff` for lint, `pytest` for tests. Use `uv` for dependency management.
- **TypeScript**: strict mode on. shadcn/ui components, no ad-hoc CSS frameworks. Server components by default; client components only when needed.
- **Commit messages**: imperative mood, lowercase subject, focus on why over what.
- **No comments explaining what code does** — name things well instead. Comments are reserved for non-obvious why (a workaround, a constraint, a surprising invariant).
- **Tests live next to the package they test** (`packages/runner/tests/`, `apps/backend/tests/`).
- **Secrets**: never in code or repo. `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` from environment. Document required env vars in each `pyproject.toml`'s README section.

---

## 12. Anti-Scope

Decisions already made that we will not revisit without strong new evidence:

- ❌ Streamlit/Gradio rapid prototype — go straight to Next.js.
- ❌ LangGraph orchestration — use Claude Agent SDK.
- ❌ Single-file Python artifact — use a directory with YAML.
- ❌ DSL for evaluation logic — use Python; flexibility wins.
- ❌ Multi-user / auth / database — single-user local FS until we have real users.
- ❌ Artifact marketplace and sandboxing — wait until sharing is a real need.
- ❌ Backend and frontend in the same language — Python is non-negotiable for backend (Claude SDK + ML ecosystem); TypeScript is non-negotiable for frontend (best chat UI tooling).

---

## 13. Glossary

- **Artifact**: the directory containing `manifest.yaml`, `dataset.jsonl`, `adapter.py`, `evaluator.py`. The unit of distribution.
- **Adapter**: the Python module that knows how to call a model with one input record and return its structured output.
- **Evaluator**: the Python module that knows how to score one (model_output, expected) pair as 0 or 1.
- **Judge**: the mechanism inside the evaluator that produces the score. `rule` (deterministic) or `llm` (LLM-as-judge with pinned config). The runner provides a `Judge` instance to the evaluator when `judge.type == "llm"`; it encapsulates the pinned model, temperature, and prompt template from the manifest.
- **Model Client**: the minimum portable abstraction the runner hands to the adapter. Exposes `.complete()` / `.messages()` for the common case and `.raw_client` as an escape hatch for provider-specific features.
- **Manifest**: `manifest.yaml`. Declares everything the runner needs to know about an artifact.
- **Orchestrator**: the main agent that drives the conversation and edits the workspace.
- **Runner**: `benchmarkrun`, the standalone CLI that executes an artifact.
- **Session**: a workspace directory under `apps/backend/sessions/{id}/` containing one in-progress artifact and the conversation that built it.
- **Workspace**: synonymous with session, viewed as a filesystem.
