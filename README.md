# llm-agent-from-scratch

A minimal LLM agent built **from scratch — no framework** (no LangChain/LangGraph),
on top of the raw Anthropic SDK. It implements the core production patterns of a
tool-using agent so the mechanics are explicit instead of hidden inside a framework.

## Why

Most "AI agent" code glues together a framework and treats the agent loop as a black
box. This project implements that loop by hand to show the patterns that actually
matter in production:

- **Agent loop** — call the LLM, run the tools it requests, feed results back, repeat
  until it returns a final answer (driven by `stop_reason`).
- **Parallel tool use** — the LLM can request several tools in one response; each gets
  its own `tool_result`, matched by `tool_use_id`.
- **Idempotency on side effects** — the write tool (`apri_reclamo`) is guarded by a key
  over its *stable identity* (the order id, not the free-text reason), persisted in SQLite
  with a TTL, so a retry or duplicate never opens a second complaint — even across restarts.
- **Error handling** — a failing tool becomes an `is_error` result the model can react
  to, instead of crashing the loop.
- **Retry with backoff** — transient API failures (network / 429 / 5xx) are retried with
  exponential backoff; client errors (4xx) fail fast.
- **Eval harness** — a golden dataset + a "contains" matcher scores the agent end-to-end
  and catches regressions.
- **Observability** — every request gets a `trace_id` / `session_id`; each LLM and tool
  call logs latency, tokens, cost and outcome as structured JSON, plus a per-request summary.
- **Human approval gate** — side-effect tools (`apri_reclamo`) require human confirmation
  before they run; the risk policy lives in code, so a prompt injection can't bypass it.
- **HTTP API (FastAPI)** — the same agent served as a web service (`/health`, `/chat`,
  `DELETE /chat/{id}`), typed with Pydantic; a middleware logs every request and an
  exception handler returns clean JSON errors (no stack traces leaked), all under one id.
- **Persistent conversation memory** — chat history lives in SQLite keyed by `session_id`
  (load → run → save), so a conversation survives restarts instead of dying with the process.

## Architecture

```
main.py          CLI: multi-turn chat loop
api.py           HTTP API (FastAPI): /health, /chat, DELETE /chat/{id} + logging & error middleware
agent.py         the agent loop (rispondi) + LLM retry (call_with_retry)
tools.py         tool functions, JSON schemas, idempotency, dispatch (execute_tool)
storage.py       SQLite persistence: conversations + idempotency keys (load/save)
observability.py structured per-request tracing (log_event)
guardrails.py    tool risk policy + human approval gate (requires_approval)
eval.py          golden dataset + runner -> pass_rate
```

The loop, in one picture:

```
user message
    |
    v
call LLM --> stop_reason == "tool_use" ? --> execute tool(s) --> append results --+
   ^                                                                              |
   +------------------------------------------------------------------------------+
    |
    +--> stop_reason == "end_turn" --> return final text
```

## Run it (CLI)

Requires Python 3.10+ and an Anthropic API key.

```bash
pip install -r requirements.txt
cp .env.example .env          # then edit .env and paste your ANTHROPIC_API_KEY
python main.py                # chat with the agent
python eval.py                # run the eval suite
```

Example conversation (the model requests two tools in parallel here):

```
Tu:  com'è il mio ordine ORD-123 e apri un reclamo perché è in ritardo
Bot: L'ordine ORD-123 è in consegna (arriva domani). Ho aperto il reclamo per il ritardo.
```

## Run as an API

Serve the same agent over HTTP:

```bash
pip install fastapi uvicorn
python -m uvicorn api:app --reload      # http://localhost:8000  (interactive docs at /docs)
```

Endpoints:

```
GET    /health             -> {"status": "ok"}
POST   /chat               body {"session_id": "...", "message": "..."}  ->  {"reply": "..."}
DELETE /chat/{session_id}  -> wipe a conversation
```

Conversation history is persisted in SQLite per `session_id`, so it survives restarts.
Side-effect tools are denied by default over HTTP. Every request is logged (method, path,
status, latency) and unhandled errors return a clean JSON 500 with a request id — the same
id ties the HTTP log to the agent's internal trace.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests cover the tool layer with **no API calls**: idempotency-key determinism, the
idempotency guard (a duplicate `apri_reclamo` runs the side effect exactly once, even when
the reason is re-worded), and error handling (unknown tool / missing argument become
results, not crashes). Each test runs against an isolated temp database.

## What I'd add for production

- **Shared store for multi-instance** — the SQLite session/idempotency store is durable on
  one node; move it to Redis/Postgres to share it across multiple server processes.
- **A tool registry** instead of the `if/elif` dispatch, with Pydantic-generated schemas.
- **An input injection screen** — an ML/LLM classifier (e.g. Llama Guard / Prompt Guard)
  for jailbreak detection, layered on top of the deterministic approval gate.

## Stack

Python · Anthropic SDK · FastAPI · SQLite · no agent framework (by design).
