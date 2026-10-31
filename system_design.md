# DataPilot AI System Design

This document describes how DataPilot AI works today: the request workflow, every component, and
each technology in the stack. For each technology it covers **what it does here** and **why it
was chosen**.

Related docs: [README.md](README.md) (quick start), [tutorial.md](tutorial.md) (configuration),
[interview.md](interview.md) (Q&A).

---

## 1. What the system does

DataPilot AI is a chat app for asking questions about a SQL database in plain English. A user
connects a database (PostgreSQL, MySQL, or the bundled SQLite demo) and asks a question. A
pipeline of AI agents writes SQL, verifies that it is read-only, runs it, and streams back:

- the agents' progress, step by step
- the SQL and an explanation of it
- the result table
- a chart, if the user asked for one
- a written answer based on the returned rows

**Design goals**

| Goal | How it is met |
|---|---|
| Never modify user data | Read-only enforced in three independent layers (section 6) |
| Accurate SQL | Real schema plus sample rows in the prompt, and a self-repair loop |
| Feels fast | Server-Sent Events stream every step and every token |
| Swappable models | One OpenAI-compatible gateway; providers and models chosen in `.env` |
| Resilient | Fallback across providers; every LLM step has a non-LLM fallback |
| Private | No accounts and no stored chats; credentials encrypted and short-lived |
| Scalable | Stateless backend workers, with shared state in Redis |

---

## 2. High-level architecture

```
┌───────────────────────── Browser ─────────────────────────┐
│ React 19 + TypeScript + Tailwind v4 (Vite build)          │
│  Chat · Agent trace · SQL viewer · Table · Charts          │
│  Zustand store → sessionStorage (chat lives in the tab)   │
└───────────────┬───────────────────────────────────────────┘
                │ HTTPS: JSON requests, SSE stream for /api/chat
                ▼
┌──────────────── nginx (production) ───────────────────────┐
│ Serves built SPA files · proxies /api (buffering OFF)     │
└───────────────┬───────────────────────────────────────────┘
                ▼
┌────────────────── uvicorn → FastAPI app ──────────────────┐
│ API layer: auth · meta · connections · chat (routers)     │
│ Cross-cutting: CORS · rate limiter · client IP · errors · │
│                JSON logging                               │
│                                                           │
│ Orchestrator (LangGraph state graph)                      │
│   Router → Schema → SQL ⇄ Guard ⇄ Executor → Viz → Insight│
│                                                           │
│ LLM Gateway ──────────────► Nebius · Gemini · OpenAI      │
│ Connection Manager ───────► PostgreSQL · MySQL · SQLite   │
│ Session Store ────────────► Redis (or in-memory in dev)   │
└───────────────────────────────────────────────────────────┘
```

### Backend layers

| Layer | Folder | Responsibility |
|---|---|---|
| API | `app/api/` | HTTP routes, request validation, SSE response |
| Agents | `app/agents/` | Orchestrator plus one module per agent, and all prompts |
| LLM | `app/llm/` | Provider registry (clients, models, roles) and gateway (calls, fallback, streaming) |
| DB | `app/db/` | Connectors, SQL guard, executor, schema introspection, session store, connection manager |
| Core | `app/core/` | Errors, logging, JSON serialization |
| Config | `app/config.py` | All settings, loaded from the root `.env` |
| Wiring | `app/services.py`, `__init__.py` | Builds the shared services once and creates the FastAPI app |

Dependencies point one way: **API → Agents → (LLM, DB) → Core**. Agents never import FastAPI, and
the DB layer knows nothing about LLMs. Each part can be tested and replaced on its own.

---

## 3. Request workflows

### 3.1 App start-up

1. The browser loads the SPA. The store creates a random **session id** and saves it in
   `sessionStorage`.
2. `GET /api/config` returns the available models, their roles, the enabled database types and
   the limits. The UI builds the model picker and the Connect dialog from this.
3. `GET /api/connections/current` returns the session's connection, if there is one, so a page
   refresh keeps you connected.

Every session-scoped request carries the `X-Session-Id` header.

### 3.2 Connecting a database

```
UI ── POST /api/connections {type, host, port, database, username, password, ssl}
   │
   ▼ ConnectionManager.connect
     1. Validate the config (Pydantic) and check the type is in ALLOWED_DB_TYPES
     2. Build a READ-ONLY SQLAlchemy engine for that dialect
     3. Run a test query (verify_connection)        → 422 connection_failed on error
     4. Introspect the schema: tables, views, columns, keys, foreign keys
     5. Encrypt the config with Fernet and save it in the session store (with TTL)
     6. Cache the live engine in this process's LRU cache
   ▼
UI ◀── public connection info (no password) + schema → Schema Explorer
```

### 3.3 Asking a question (`POST /api/chat`, the core flow)

Before streaming starts, the backend resolves the session's connection and validates the chosen
model. Errors such as "not connected" or "unknown model" therefore return normal HTTP status
codes. After that, the response is an SSE stream.

```
                          ┌────────────┐
 question + history ─────▶│  Router    │ fast model → {intent, needs_chart, chart_type, question}
                          └─────┬──────┘
          ┌──────────────┬──────┴───────┬──────────────────────────┐
     intent=write   intent=schema   intent=general            intent=data
          │              │              │                         │
     refusal text   answer from     general answer          ┌─────▼──────┐
     (no SQL)       schema                                  │ Schema     │ picks tables + samples
                                                            └─────┬──────┘
                                                            ┌─────▼──────┐
                                              ┌────────────▶│ SQL agent  │ reasoning model
                                              │  error      └─────┬──────┘
                                              │             ┌─────▼──────┐
                                              ├─────────────│ Guard      │ sqlglot AST, no LLM
                                              │  rejected   └─────┬──────┘
                                              │             ┌─────▼──────┐
                                              └─────────────│ Executor   │ read-only, timeout,
                                       up to MAX_SQL_RETRIES└─────┬──────┘ always rollback
                                                                  │ rows
                                                            ┌─────▼──────┐
                                                 if chart → │ Viz agent  │ → {type, x, y, title}
                                                            └─────┬──────┘
                                                            ┌─────▼──────┐
                                                            │ Insight    │ streams Markdown answer
                                                            └────────────┘
```

**SSE events** sent to the browser:

| Event | When | Payload |
|---|---|---|
| `step` | Each agent starts or ends | `{id, label, kind, status, detail}`, drawn as the live agent trace |
| `sql` | SQL passed the guard | `{sql, explanation}` |
| `result` | Query finished | `{columns, rows, row_count, truncated, elapsed_ms, column_types}` |
| `chart` | Viz agent finished | `{type, x, y, title, max_points}` |
| `model` | A model starts producing output | model id, shown as a badge under the answer |
| `token` | Answer text chunk | text |
| `error` | Unrecoverable failure | `{code, message}` |
| `done` | End of stream | none |

The frontend reads the stream with `fetch` and a `ReadableStream` parser. The browser's built-in
`EventSource` only supports GET, and this request needs a POST body. The **Stop** button cancels
the request with an `AbortController`.

### 3.4 Follow-up questions

The frontend sends the last turns (`CHAT_HISTORY_TURNS`) with each request. The router rewrites
"now only Europe" into a standalone question, for example "total GDP by continent for Europe
only", before the other agents run. The server keeps no chat history.

---

## 4. The agents

| Agent | Model role | Input → Output | Fallback if the LLM fails |
|---|---|---|---|
| **Router** | `fast` | question + history → intent, chart need, rewritten question | Keyword heuristics |
| **Schema** | `fast` | question + schema → relevant tables (+ FK neighbours, sample rows) | Full schema if ≤ 15 tables, otherwise keyword match |
| **SQL** | `reasoning` | question + selected schema → SQL + explanation, or `CANNOT_ANSWER` | Retry with the error, then the next model in the fallback chain |
| **Guard** | none | SQL → approved SQL (with `LIMIT`) or rejection | Deterministic, so it has no LLM to fail |
| **Executor** | none | SQL → rows | n/a |
| **Viz** | `fast` | columns + sample rows + request → chart spec | Heuristic: dates give a line chart, categories give a bar chart |
| **Insight** | `fast` | question + SQL + rows (capped at 8,000 chars) → streamed Markdown | Short fallback text; the table and chart still show |

**Why a fixed pipeline rather than a free tool-calling agent?** The orchestrator is a LangGraph
state graph with fixed edges, and the LLMs make decisions *inside* each step. This keeps cost and
latency bounded, makes every run auditable (the user sees each step), and leaves prompt injection
little room to change what the system does. The SQL ⇄ Guard ⇄ Executor loop is where the system
acts like an agent: it reads tool feedback and corrects itself.

**Prompts** all live in `app/agents/prompts.py`. Each agent has a strict output contract:
JSON, or a fenced `sql` block plus `Explanation:`. Parsers are tolerant (they strip `<think>`
blocks and code fences) and validate everything they extract.

---

## 5. LLM layer

### 5.1 Provider registry (`llm/registry.py`)

- Builds one OpenAI client per provider (`nebius`, `gemini`, `openai` by default) **that has an API
  key** (`<NAME>_API_KEY`). Base URLs have built-in defaults and can be overridden with
  `<NAME>_BASE_URL`.
- The model picker shows each enabled provider's `<NAME>_MODELS` list plus the role models.
- **Auto** uses `LLM_PRIMARY`, then `LLM_SECONDARY` as fallback. Two optional, advanced settings,
  `LLM_REASONING` (SQL agent) and `LLM_FAST` (other agents), can give agents their own model; when
  unset they use the primary.
- Validates the model a user picks against that allow-list.

### 5.2 Gateway (`llm/gateway.py`)

- **Candidate chain** per call: user's pick or role model → primary → secondary. Duplicates and
  disabled providers are removed.
- **Non-streaming calls** (router, schema, SQL, viz): try each candidate in turn until one
  succeeds.
- **Streaming calls** (insight): fall back only if a model fails *before sending any text*.
  Switching models mid-answer would produce a mixed, inconsistent reply.
- **`<think>` filtering**: reasoning models such as Nemotron emit `<think>…</think>`. A streaming
  state machine removes these blocks even when a tag is split across chunks.
- The OpenAI SDK retries transient errors twice per model before the gateway falls back.

---

## 6. Read-only safety (defence in depth)

The system relies on three independent layers. The LLM is not trusted at any of them.

| Layer | Where | What it blocks |
|---|---|---|
| **1. SQL guard** | `db/guard.py` | Parses with `sqlglot`. Requires exactly one statement that is a query. Rejects INSERT, UPDATE, DELETE, MERGE, DDL, `SELECT INTO`, `FOR UPDATE`, and dangerous functions (`pg_sleep`, `sleep`, `benchmark`, `load_extension`…). Also runs a keyword check with string literals blanked out. Adds a `LIMIT` if missing. |
| **2. Read-only session** | `db/connectors.py` | SQLite: `mode=ro` plus `PRAGMA query_only`. PostgreSQL: `default_transaction_read_only=on` plus `statement_timeout`. MySQL: `SET SESSION TRANSACTION READ ONLY` plus `max_execution_time`. |
| **3. Transaction** | `db/executor.py` | Every query runs in a transaction that is **always rolled back**. Fetches `row_limit + 1` rows to detect truncation. SQLite gets a progress-handler timeout. |

A test sends a `DELETE` straight to the executor, bypassing the guard, to prove layer 2 alone
rejects it. The router also refuses write requests before any SQL is written.

Other protections:

- Request size limits (`MAX_MESSAGE_CHARS`, history ≤ 50 turns)
- A session id format check
- Per-IP rate limiting
- CORS restricted to configured origins
- Passwords never returned to the client and never logged

---

## 7. Sessions and state

| State | Where it lives | Lifetime |
|---|---|---|
| User accounts, refresh tokens, login history | `auth/auth.db` (SQLite, separate from demo data) | Permanent (on a persistent disk) |
| Access + refresh tokens (client copy) | Browser `localStorage` | Until logout or refresh-token expiry (7 days) |
| Chat messages | Browser `sessionStorage` (Zustand persist) | Until the tab closes |
| Session id | Browser `sessionStorage` | Until the tab closes |
| Connection config (incl. password) | Session store, **Fernet-encrypted** | `SESSION_TTL_MINUTES`, renewed on each use |
| Live DB engine (connection pool) | Per-process LRU cache (`ENGINE_CACHE_SIZE`) | Until evicted; the pool is disposed on eviction |
| Schema | Cached in each process next to the engine; re-read when the engine is rebuilt or the user clicks refresh | Same as the engine |
| Rate-limit counters | Redis (prod) or memory (dev) | Rate-limit window |

**Authentication.** Every API call except `/api/health` and `/api/auth/*` needs a JWT access token.
Access tokens are stateless (signature check only), so any worker can verify them without shared
state. Refresh tokens are stored in `auth/auth.db` so they can be rotated and revoked. DB sessions
are keyed by user id plus session id, so users are isolated from each other. Details: [auth.md](auth.md).

**How a worker serves a session it hasn't seen.** Suppose worker A handled `connect` and worker B
receives the next `chat`. B finds no engine in its cache, so it loads the encrypted config from
Redis, decrypts it, rebuilds a read-only engine, and caches it. A `connected_at` stamp detects a
stale cached engine after a reconnect. This keeps workers **stateless**: any worker or container
can serve any request.

---

## 8. Tech stack: what each piece does and why

### Backend

| Technology | What it does here | Why it was chosen |
|---|---|---|
| **Python 3.11** | Backend language | Strongest ecosystem for LLM SDKs, SQL tooling and data handling. 3.11 is fast and widely supported. |
| **FastAPI** | HTTP API: routers, dependency injection, request validation, streaming responses, automatic docs at `/api/docs` | Validates requests from type hints, and `Depends` keeps login and rate limits in one place. Routes are plain `def` because the DB and LLM calls block, so FastAPI runs them on its thread pool and the event loop stays free. |
| **CORSMiddleware** | Allows only the configured frontend origins to call the API | Needed when the frontend and API are on different origins (local dev, or separate hosting). The allow-list comes from `CORS_ORIGINS`. |
| **limits** | Per-IP rate limits, applied by a FastAPI dependency in `api/deps.py` | Protects LLM spend and user databases from abuse. It's keyed by IP rather than session id, because session ids are client-generated and could be rotated to dodge the limit. The counters can live in Redis. |
| **`client_ip()` + `PROXY_FIX_HOPS`** | Recovers the real client IP behind nginx or a load balancer | Without it, every request looks like it comes from the proxy, and rate limiting breaks. It counts from the right of `X-Forwarded-For`, because a client can fake the left side. |
| **Werkzeug** | `generate_password_hash` and `check_password_hash` only | Salted scrypt hashing. Kept so that existing accounts still work. |
| **Pydantic v2** | Validates request bodies and the connection config | Typed, declarative validation with clear error messages, the same benefit FastAPI gets from it. |
| **pydantic-settings + python-dotenv** | Loads and validates all configuration from `.env` and environment variables | One typed, validated place for configuration. The app fails fast on bad config, and real environment variables override `.env` in Docker or on hosting platforms. |
| **LangGraph** | Runs the agents as a state graph: nodes for each stage, conditional edges for routing and the SQL retry loop | Makes the flow and retries explicit and easy to draw. Its custom stream mode sends each event as it happens, which SSE needs. |
| **OpenAI Python SDK** | One client for every LLM provider | Nebius Token Factory, Gemini and OpenAI all expose OpenAI-compatible endpoints, so one SDK plus a `base_url` covers all of them, including streaming, timeouts and retries. Adding a provider needs only `.env` lines. |
| **SQLAlchemy 2.0** | Engines, connection pools, schema inspection, connection events | One API across SQLite, PostgreSQL and MySQL. Its pooling and connect-time events are where read-only mode and timeouts are applied. |
| **sqlglot** | Parses SQL into an AST for the guard, across dialects | A real parser, unlike regex, so it catches writes hidden in CTEs, multiple statements and dialect-specific forms. Pure Python with no native dependencies. |
| **psycopg 3** (binary) | PostgreSQL driver | The modern, maintained PostgreSQL driver. Supports the session options used for read-only mode. |
| **PyMySQL** | MySQL driver | Pure Python, so there's nothing to compile in Docker or on Windows. Reliable with SQLAlchemy. |
| **SQLite** (stdlib) | Bundled demo database (`data/demo.db`, 5 tables, top 50 countries) | Needs no server, so anyone can try the app instantly. Opened read-only like any other database. |
| **cryptography (Fernet)** | Encrypts database credentials in the session store | Authenticated symmetric encryption that's hard to misuse. The key is derived from `SECRET_KEY`, so a leaked Redis dump doesn't reveal passwords. |
| **Redis** | Shared session store (with TTL) and rate-limit counters in production | See section 9. |
| **uvicorn** | Production ASGI server | Runs the FastAPI app and supports streaming responses. `WEB_CONCURRENCY` sets the number of processes. It has no request timeout like gunicorn had, but each LLM call has its own 60 s timeout, and each SQL query 15 s. |
| **pytest** | Tests for the guard matrix, LLM output parsing, the API lifecycle and DB-level write rejection | Covers the parts that must never break, without needing an LLM key. |

### Frontend

| Technology | What it does here | Why it was chosen |
|---|---|---|
| **React 19** | UI components: chat, trace, table, chart, dialogs | Mature component model and ecosystem. Well suited to a UI that updates many times a second while streaming. |
| **TypeScript 5.8** | Type safety across the app, especially the SSE event contract | The stream carries eight event types with different payloads. Types keep the backend contract and the UI rendering in sync, and catch mistakes at build time. |
| **Vite 6** | Dev server (with `/api` proxy) and production build | Near-instant dev start-up and hot reload. Code splitting keeps the first load at about 140 KB gzipped. |
| **Tailwind CSS v4** | All styling, the design tokens and dark mode | A consistent design system without a heavy component library. v4 builds fast via its Vite plugin. Dark mode uses a `.dark` class variant. |
| **Zustand** | Global state (config, connection, messages, model) persisted to `sessionStorage` | A small store with no boilerplate. Its persist middleware delivers the "chat lives only in this tab" requirement directly. |
| **Recharts** | Bar, line, area, pie and scatter charts | Declarative React charts that map cleanly from the backend's chart spec. **Lazy-loaded**, so its large bundle downloads only when the first chart appears. Uses a colour-blind-checked palette with separate light and dark colours. |
| **react-markdown + remark-gfm** | Renders the insight answer (tables, lists, bold) | Safe Markdown rendering (no raw HTML), with GitHub-style tables. |
| **lucide-react** | Icons | Consistent, tree-shakeable icon set (only the icons used are bundled). |
| **clsx** | Combines conditional class names | Tiny helper for readable Tailwind class logic. |

### Infrastructure

| Technology | What it does here | Why it was chosen |
|---|---|---|
| **Docker** | One image each for the backend (`python:3.11-slim`, non-root user, health check) and the frontend (Node build stage → nginx) | The same artifact runs on a laptop, a VM or Kubernetes. Multi-stage builds keep images small. |
| **nginx** | Serves the built SPA, caches hashed assets for a year, proxies `/api` to uvicorn | Fast static serving. Same-origin `/api` means no CORS in production. `proxy_buffering off` is **essential** for SSE; without it nginx holds back the tokens and the answer arrives all at once. |
| **Docker Compose** | Runs frontend, backend and Redis together with one command | It sits at the repo root because it spans both service folders. In production each image can be deployed separately. |

---

## 9. Redis in detail

**What it does**

1. **Session store.** Holds each session's encrypted connection config and a `connected_at`
   timestamp under a key with a TTL. Every access renews the TTL (a sliding expiry), and idle sessions expire
   automatically with nothing to clean up.
2. **Rate-limit storage.** The `limits` library keeps per-IP request counters in Redis (a separate
   database number), so the limit applies across **all** workers and containers.

**Why it's needed.** In production there are several uvicorn processes, and possibly several
containers. In-memory state is private to one process. Without shared storage, a user who
connected through worker A would appear "not connected" on worker B, and each worker would count
rate limits separately, multiplying the effective limit.

**Why Redis specifically**

- Built-in key expiry (TTL), which is exactly what session-only state needs.
- Very fast in-memory reads; the session lookup happens on every request.
- Supported natively by the `limits` library.
- Simple to run (`redis:7-alpine`) and available as a managed service on every cloud.
- In Compose it runs with persistence off (`--save "" --appendonly no`). Sessions are meant to be
  short-lived, so nothing is written to disk.

**Why not something else?** A SQL table would need cleanup jobs for expiry and is slower. Sticky
sessions at the load balancer would break when a worker restarts and would spread load unevenly.
Memcached has no rate-limiter integration as good as Redis's.

**In development** you don't need Redis. `SESSION_BACKEND=memory` and
`RATE_LIMIT_STORAGE_URI=memory://` work for a single process.

---

## 10. Configuration

Everything is driven by environment variables, loaded from the root `.env` and validated by
`pydantic-settings`. Real environment variables take precedence. `.env` only lists the settings you
normally change; every other setting has a default in `app/config.py`.

| Group | Examples |
|---|---|
| App | `APP_ENV`, `SECRET_KEY`, `LOG_LEVEL`, `CORS_ORIGINS`, `PROXY_FIX_HOPS` |
| Auth | `AUTH_DB_PATH`, `JWT_SECRET_KEY` (defaults to `SECRET_KEY`), `ACCESS_TOKEN_MINUTES`, `REFRESH_TOKEN_DAYS`, `DEMO_USER_EMAIL`, `DEMO_USER_PASSWORD`, `AUTH_RATE_LIMIT` |
| LLM | `<NAME>_API_KEY`, `<NAME>_MODELS`, `LLM_PRIMARY`, `LLM_SECONDARY` (optional: `<NAME>_BASE_URL`, `LLM_PROVIDERS`, `LLM_REASONING`, `LLM_FAST`, `LLM_TEMPERATURE`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_TOKENS`) |
| Agents | `MAX_SQL_RETRIES`, `SCHEMA_FULL_CONTEXT_MAX_TABLES`, `SCHEMA_SAMPLE_ROWS`, `CHAT_HISTORY_TURNS` |
| Data | `DEMO_DB_PATH`, `QUERY_ROW_LIMIT`, `QUERY_TIMEOUT_SECONDS`, `ALLOWED_DB_TYPES`, `MAX_MESSAGE_CHARS` |
| Infrastructure | `SESSION_BACKEND`, `SESSION_TTL_MINUTES`, `REDIS_URL`, `ENGINE_CACHE_SIZE`, `RATE_LIMIT`, `RATE_LIMIT_STORAGE_URI` |

The frontend has a single build-time variable in `frontend/.env`: `VITE_API_BASE_URL`, the backend's
URL. The browser calls the backend directly, so the backend's `CORS_ORIGINS` must include the
frontend's URL. See [tutorial.md](tutorial.md) for step-by-step recipes.

---

## 11. Error handling and resilience

| Failure | Behaviour |
|---|---|
| Bad input | `ValidationError`, returns 400 with a stable error `code` |
| Chat sent without a connection | 409 `not_connected` |
| Database unreachable or wrong credentials | 422 `connection_failed` |
| Unsafe SQL | Rejected by the guard, then sent back to the SQL agent to repair |
| SQL error from the database | Sent back to the SQL agent to repair (up to `MAX_SQL_RETRIES`) |
| One LLM provider down or rate-limited | SDK retries, then the gateway falls back to the next model |
| Insight model fails mid-flow | SQL, table and chart are still delivered, with a fallback message |
| Malformed LLM JSON | Tolerant parsing, then a deterministic fallback for that step |
| Unexpected exception | Logged with a stack trace; the client gets a generic 500 without internal details |

All errors share one shape: `{error: {code, message}}`. Logs are structured JSON lines, ready for
any log aggregator.

---

## 12. Deployment and scaling

```
docker compose up --build   →   http://localhost:8080
  frontend (nginx :80 → host :8080) ──/api──▶ backend (uvicorn :5000) ──▶ redis
```

- **Horizontal scaling:** add backend replicas behind nginx or a load balancer. Redis keeps
  sessions and rate limits consistent across them.
- **Vertical tuning:** `WEB_CONCURRENCY` sets the number of uvicorn processes. Each one runs ordinary
  routes on a thread pool, and each streamed answer on a thread of its own.
- **Split hosting:** the frontend can go on a static host (Vercel, Netlify) with
  `VITE_API_BASE_URL` set, the backend on Render, Railway or Kubernetes, with managed Redis and
  `CORS_ORIGINS` set to the frontend URL.
- **Health check:** `GET /api/health`, used by the Docker `HEALTHCHECK`.

---

## 13. Known limitations and roadmap

**Current limitations**

- No user accounts or authentication. Sessions are anonymous.
- No automated SQL-accuracy benchmark yet.
- Ambiguous questions get a best guess rather than a clarifying question.
- No query result caching.
- Supported databases: SQLite (demo), PostgreSQL and MySQL.

**Roadmap**

- **v2, data ingestion:** upload CSV or Excel files. The pipeline infers types, cleans the data
  and loads it into a per-session workspace database. That workspace becomes another connection
  type, so the agents need no changes.
- An evaluation harness for SQL accuracy across models.
- Clarifying questions for ambiguous requests.
- Authentication and saved workspaces.
- Result and schema caching in Redis.
- SQL Server and Snowflake connectors.
