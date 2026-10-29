# DataPilot AI

**Agentic natural-language analytics over your SQL database: read-only by design.**

Ask questions in plain English. A team of agents plans, writes, verifies and runs SQL against your
PostgreSQL, MySQL or the bundled demo database. It then explains the results, and draws a chart
when you ask for one. Everything streams live into a ChatGPT-style interface.

---

## Architecture

```
┌──────────────────────────┐        ┌──────────────────────────────────────────────────────────┐
│ React + TS + Tailwind    │  SSE   │ Flask API (gunicorn gthread)                              │
│  chat · agent trace      │◀──────▶│                                                          │
│  tables · charts · SQL   │  JSON  │  Orchestrator ── Router ─┬─ write    → refusal           │
└──────────────────────────┘        │   (state machine)        ├─ general  → answer            │
                                    │                          └─ data → Schema agent          │
                                    │                                   → SQL agent ◀─┐ repair │
                                    │                                   → Guard  ─────┤ loop   │
                                    │                                   → Executor ───┘        │
                                    │                                   → Viz agent (spec)     │
                                    │                                   → Insight agent (stream)│
                                    │  LLM Gateway: roles · fallback · <think> stripping       │
                                    │  Session store (memory/Redis, Fernet-encrypted creds)    │
                                    └───────────────┬──────────────────────────────────────────┘
                                                    │ read-only connections
                                       SQLite demo · PostgreSQL · MySQL
```

### Agents

| Agent | Model role | Responsibility |
|---|---|---|
| Router | `fast` | Intent (data / schema / general / write), chart detection, rewrites follow-ups into standalone questions |
| Schema | `fast` | Picks relevant tables for large schemas (full schema if ≤ `SCHEMA_FULL_CONTEXT_MAX_TABLES`), adds FK-linked tables, samples rows |
| SQL | `reasoning` | Writes dialect-specific SQL; on guard/DB errors repairs its own query (`MAX_SQL_RETRIES`) |
| Guard | none (deterministic) | Gets the final say on safety; never trusts LLM output |
| Viz | `fast` | Returns a declarative chart spec (`type, x, y`), validated against result columns, with a heuristic fallback |
| Insight | `fast` | Streams a grounded Markdown answer from the actual rows |

### Read-only, enforced three ways

1. **SQL guard** (`sqlglot` AST): exactly one statement, must be a query, no DML/DDL/admin nodes, no
   dangerous functions (`pg_sleep`, `load_extension`, `sleep`…), no `SELECT INTO`/`FOR UPDATE`, auto `LIMIT`.
2. **Database session**: SQLite `mode=ro` + `query_only`, PostgreSQL `default_transaction_read_only`,
   MySQL `SET SESSION TRANSACTION READ ONLY`, plus per-dialect statement timeouts.
3. **Transaction**: every execution runs in a transaction that is always rolled back.

### Multi-model, configured in `.env`

Every provider speaks the OpenAI Chat Completions protocol (Nebius Token Factory, Gemini, OpenAI…).
Models are referenced as `provider:model` and assigned to roles:

```env
LLM_PRIMARY=nebius:nvidia/Llama-3_3-Nemotron-Super-49B-v1_5
LLM_SECONDARY=gemini:gemini-2.5-flash      # automatic fallback
LLM_REASONING=nebius:nvidia/Llama-3_3-Nemotron-Super-49B-v1_5
LLM_FAST=gemini:gemini-2.5-flash
LLM_AVAILABLE_MODELS=...                   # what users can pick in the UI
```

Providers without an API key are disabled automatically. Users can choose **Auto** (role-based
routing) or pin a single model from the header. To add a new provider, append it to `LLM_PROVIDERS`
and set `<NAME>_API_KEY` / `<NAME>_BASE_URL`.

### Sessions

There are no accounts and no stored chats. Chat history lives in the browser tab (`sessionStorage`) and
the last turns are sent with each request for follow-up context. Connection credentials are
Fernet-encrypted in the session store (memory, or Redis for multi-worker deployments) and expire after
`SESSION_TTL_MINUTES`.

---

## Quick start (local)

**Backend** (Python 3.11+)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env               # add at least one provider API key + SECRET_KEY
python wsgi.py                     # http://localhost:5000  (demo DB is created on first start)
```

**Frontend** (Node 20+)

```bash
cd frontend
npm install
npm run dev                        # http://localhost:5173  (proxies /api to :5000)
```

Open the app and click **Try the demo database**.

## Production (Docker)

```bash
cp backend/.env.example backend/.env   # fill in keys + a strong SECRET_KEY
docker compose up --build              # http://localhost:8080
```

nginx serves the built SPA and proxies `/api` (SSE-safe, unbuffered) to gunicorn. Redis backs
sessions and rate limits, so you can scale the backend horizontally.

## API

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Liveness + whether any LLM is configured |
| GET | `/api/config` | Models, roles, enabled DB types, limits (client bootstrap) |
| POST | `/api/connections` | Connect (`sqlite_demo`, `postgresql`, `mysql`) |
| GET / DELETE | `/api/connections/current` | Current connection + schema / disconnect |
| POST | `/api/schema/refresh` | Re-introspect the schema |
| POST | `/api/chat` | Run the agents. Streams SSE events: `step`, `sql`, `result`, `chart`, `token`, `model`, `error`, `done` |

All session-scoped endpoints require an `X-Session-Id` header (generated by the frontend).

## Tests

```bash
cd backend && pytest -q
```

Covers the SQL guard (allow/deny matrix across dialects), DB-level read-only enforcement, the
connection lifecycle API, and LLM output parsing (`<think>` stripping, JSON/SQL extraction).

## Project layout

```
backend/
  app/
    agents/     orchestrator, router, schema, sql, viz, insight, prompts
    llm/        provider registry + gateway (fallback, streaming)
    db/         connectors, guard, executor, introspection, session store, manager
    api/        Flask blueprints (meta, connections, chat)
    core/       errors, logging, serialization
  scripts/seed_demo.py   demo dataset
  tests/
frontend/
  src/
    components/  chat/, sidebar/, connection/, ui/
    hooks/       useChat (SSE streaming), useConnection
    store/       zustand (session-scoped)
    lib/         api client, formatting
```

## Roadmap

- **v2: Data ingestion.** Upload CSV/Excel, infer types, clean and load into a per-user
  workspace database. This becomes another connection type next to `sqlite_demo`, so the agents
  need no changes.
- Query result caching, saved charts, and SQL Server / Snowflake connectors.
