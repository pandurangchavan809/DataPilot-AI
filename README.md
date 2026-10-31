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
└──────────────────────────┘        │   (LangGraph graph)      ├─ general  → answer            │
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

### Agent workflow (LangGraph)

The agents run as a [LangGraph](https://github.com/langchain-ai/langgraph) `StateGraph` in
`app/agents/orchestrator.py`. Each stage is a node, and each branch is a conditional edge:

```
route ─┬─ write          → refuse
       ├─ general/schema → converse
       └─ data → select_schema → write_sql → guard → execute ─┬─ chart → insight
                                      ▲         │        │    └─ insight
                                      └─ retry ─┴────────┘    (give_up when retries run out)
```

Nodes send progress through LangGraph's stream writer, so each step and word reaches the browser
over SSE as it happens. Model calls use the OpenAI SDK through the project's own gateway, not
LangChain. The graph has no checkpointer, because chats aren't stored on the server.

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
Each provider lists the models users can pick, and **Auto** uses primary, then secondary:

```env
NEBIUS_API_KEY=...
NEBIUS_MODELS=nvidia/Nemotron-3_5-Lightning
GEMINI_API_KEY=...
GEMINI_MODELS=gemini-3.5-flash

LLM_PRIMARY=nebius:nvidia/Nemotron-3_5-Lightning
LLM_SECONDARY=gemini:gemini-3.5-flash      # automatic fallback
```

See **[tutorial.md](tutorial.md)** for a step-by-step guide covering keys, the model picker, role
recipes, adding providers, and which `.env` file does what.

Providers without an API key are disabled automatically. Users can choose **Auto** or pin a single
model from the header.

### Login (JWT)

Users sign up and log in with email and password. Accounts live in their own SQLite file,
`auth/auth.db`, which is separate from the demo data and never committed. Passwords are stored only as salted hashes.
Login returns a short-lived **access token** (15 min), sent on every API call, and a **refresh token**
(7 days) that is rotated on every use. Every login attempt is recorded. A demo account
(`user` / `User@1234`) is created on start and shown on the login page. See [auth.md](auth.md).

### Sessions

Chats are not stored on the server. Chat history lives in the browser tab (`sessionStorage`) and
the last turns are sent with each request for follow-up context. Connection credentials are
Fernet-encrypted in the session store (memory, or Redis for multi-worker deployments) and expire after
`SESSION_TTL_MINUTES`.

---

## Quick start (local)

**Backend** (Python 3.11+, from the repo root)

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env               # add at least one provider API key + SECRET_KEY
python wsgi.py                     # http://localhost:5000  (demo DB is created on first start)
```

**Frontend** (Node 20+)

```bash
cd frontend
cp .env.example .env               # VITE_API_BASE_URL=http://localhost:5000
npm install
npm run dev                        # http://localhost:5173
```

Open the app, log in with the demo account (`user` / `User@1234`) or sign up, then click **Try the demo database**.

## Production (Docker)

```bash
cp .env.example .env         # fill in keys + a strong SECRET_KEY
docker compose up --build    # http://localhost:8080
```

nginx serves the built SPA and proxies `/api` (SSE-safe, unbuffered) to gunicorn. Redis backs
sessions and rate limits, so you can scale the backend horizontally.

`docker-compose.yml` lives at the repo root because it ties the services together: it builds the
backend (root `Dockerfile`) and `./frontend` from their own Dockerfiles, adds Redis, and wires them on one network.
Each service stays independently deployable. On a platform like Render, Railway or Kubernetes you
deploy the two images separately and use a managed Redis instead.

## API

| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/signup`, `/api/auth/login` | Create an account / log in. Returns access + refresh tokens |
| POST | `/api/auth/refresh` | Swap a refresh token for a new pair (rotation) |
| POST | `/api/auth/logout` | Revoke a refresh token |
| GET | `/api/auth/me` | The logged-in user |
| GET | `/api/health` | Liveness + whether any LLM is configured |
| GET | `/api/config` | Models, roles, enabled DB types, limits (client bootstrap) |
| POST | `/api/connections` | Connect (`sqlite_demo`, `postgresql`, `mysql`) |
| GET / DELETE | `/api/connections/current` | Current connection + schema / disconnect |
| POST | `/api/schema/refresh` | Re-introspect the schema |
| POST | `/api/chat` | Run the agents. Streams SSE events: `step`, `sql`, `result`, `chart`, `token`, `model`, `error`, `done` |

Everything except `/api/health` and `/api/auth/*` requires `Authorization: Bearer <access token>`.
Session-scoped endpoints also need an `X-Session-Id` header (generated by the frontend).

## Tests

```bash
pytest -q
```

Covers the SQL guard (allow/deny matrix across dialects), DB-level read-only enforcement, the
connection lifecycle API, authentication (signup, login, token expiry, refresh rotation and reuse
detection, per-user sessions), the agent graph's routing, retries and live streaming, the LLM gateway's
fallback rules, and LLM output parsing (`<think>` stripping, JSON/SQL extraction).

## Project layout

```
app/                  Flask backend
  agents/             orchestrator (LangGraph graph), router, schema, sql, viz, insight, prompts
  llm/                provider registry + gateway (fallback, streaming)
  db/                 connectors, guard, executor, introspection, session store, manager
  api/                Flask blueprints (auth, meta, connections, chat)
  auth/               user store (SQLite) + JWT access/refresh tokens
  core/               errors, logging, serialization
  config.py           all settings (read from .env)
scripts/seed_demo.py  demo dataset (data/demo.db is created on first start)
auth/auth.db          user accounts (created on first start, gitignored)
tests/                pytest suite
wsgi.py, gunicorn.conf.py, Dockerfile, requirements.txt, .env.example
docker-compose.yml    runs the full stack (frontend + backend + Redis) with one command
system_design.md      architecture, workflow and tech-stack rationale
deployment.md         Render + Vercel deployment, how the agents work, all prompts
backend.md            file-by-file guide to the backend
docker.md             Docker files, commands and interview Q&A
auth.md               login, JWT access/refresh tokens and interview Q&A
agent.md              LangGraph workflow, memory, guardrails, LLMOps and interview Q&A
tutorial.md           configuration guide (.env files, models, providers)
interview.md          design notes and Q&A on the architecture and trade-offs

frontend/             React app (deployed separately)
  .env.example        VITE_API_BASE_URL (backend URL)
  Dockerfile, nginx.conf
  src/
    components/       auth/, chat/, sidebar/, connection/, ui/
    hooks/            useApp (zustand store), useAuth (login + tokens), useChat (SSE streaming), useConnection
    api.ts            API client + SSE parser
    types.ts          shared types
    utils.ts          formatting helpers
```

## Roadmap

- **v2: Data ingestion.** Upload CSV/Excel, infer types, clean and load into a per-user
  workspace database. This becomes another connection type next to `sqlite_demo`, so the agents
  need no changes.
- Query result caching, saved charts, and SQL Server / Snowflake connectors.
