# DataPilot AI Backend Guide

A file-by-file tour of the Flask backend: what each file does, its important functions, and why it
exists. Read it top to bottom once, then use it as a reference.

> Big picture: the browser sends a question, `app/api/chat.py` receives it, the **orchestrator** runs
> the **agents**, the agents use the **LLM gateway** to call models and the **db** layer to run
> read-only SQL, and every step streams back to the browser as Server-Sent Events.

```
wsgi.py ─▶ app/__init__.py (create_app) ─▶ app/api/*        (HTTP routes)
                                             │
                                             ▼
                                   app/agents/orchestrator.py ─▶ router · schema · sql · viz · insight
                                             │                         │
                                             ▼                         ▼
                                   app/db/* (guard, executor,     app/llm/* (registry, gateway)
                                   connectors, introspect,              │
                                   manager, session_store)              ▼
                                                                 Nebius · Gemini · OpenAI
```

**Dependency rule:** `api → agents → (llm, db) → core`. Lower layers never import higher ones.
For example, `db/` knows nothing about Flask or LLMs, so each layer can be tested and changed on
its own.

---

## 1. Root files

### `wsgi.py`: the entry point

```python
from app import create_app
app = create_app()          # the Flask application object

if __name__ == "__main__":  # only when you run: python wsgi.py
    app.run(host="0.0.0.0", port=5000, debug=..., threaded=True)
```

- **What "WSGI" means:** *Web Server Gateway Interface*. It's the standard contract between a
  Python web app and a web server: the server calls an `app` object for every request.
  `wsgi.py` exists to expose that object.
- **Local dev:** `python wsgi.py` starts Flask's built-in development server, with auto-reload and
  debug mode.
- **Production:** `gunicorn -c gunicorn.conf.py wsgi:app` means *"import the module `wsgi` and use
  the variable `app` inside it"*. Flask's dev server is single-purpose and not built for real
  traffic; gunicorn is.

**Why not rename it to `app.py`?** Because the folder `app/` is a Python package with the same
name. When both exist, Python's import system picks the **package** (`app/__init__.py`) and
silently ignores `app.py`. I tested this: `import app` loaded `app/__init__.py`, and
`hasattr(app, "app")` was `False`. So `gunicorn app:app` would fail with *"Failed to find attribute
'app' in 'app'"*. Other safe names are `main.py`, `run.py` and `server.py`, but `wsgi.py` is the
standard convention (Django generates the same file), so anyone reading the repo knows what it is.

### `gunicorn.conf.py`: production server settings

| Setting | Value | Why |
|---|---|---|
| `bind` | `0.0.0.0:$PORT` | Listens on the port Render, Docker or a host gives it (default 5000) |
| `worker_class` | `gthread` | Threaded workers. A streamed answer can stay open for 10–60 s, and a thread waiting on the LLM is cheap. |
| `workers` | `WEB_CONCURRENCY` or min(4, CPUs) | Processes. Use **1** with in-memory sessions, more with Redis. |
| `threads` | `GUNICORN_THREADS` or 8 | Concurrent requests per process |
| `timeout` | 180 s | Long LLM answers must not be killed mid-stream |
| `accesslog` / `errorlog` | `-` | Log to stdout, which Docker and Render collect |

The name `gunicorn.conf.py` is gunicorn's **default config filename**. Gunicorn even loads it
automatically from the working directory, and `-c` just makes that explicit. It's a Python file, so
settings can read environment variables.

### Other root files

| File | Purpose |
|---|---|
| `requirements.txt` | Runtime dependencies (installed on Render and in Docker) |
| `requirements-dev.txt` | `-r requirements.txt` plus `pytest` (local development only) |
| `.env` / `.env.example` | Settings and secrets (see `tutorial.md`). `.env` is gitignored. |
| `Dockerfile`, `.dockerignore` | Backend container image (see `docker.md`) |
| `data/demo.db` | Demo SQLite database, **created automatically** on first start, gitignored |

---

## 2. `app/`: application core

### `app/__init__.py`: the application factory

**`create_app(settings=None) -> Flask`** builds and wires the whole app:

1. `configure_logging`: JSON logs in production, readable text in development.
2. Flask config: `MAX_CONTENT_LENGTH` = 1 MB (rejects huge requests).
3. **ProxyFix** (only if `PROXY_FIX_HOPS` > 0): trusts the `X-Forwarded-For` header from Render or
   nginx, so the real client IP is known.
4. **CORS**: only `CORS_ORIGINS` may call `/api/*`, with headers `Content-Type` and `X-Session-Id`.
5. **Limiter**: rate limits keyed by client IP.
6. `_ensure_demo_db`: creates `data/demo.db` if it's missing.
7. `Services.build`: creates the shared services once.
8. `register_api`: mounts all routes under `/api`.
9. **Error handlers**: `AppError` returns its own status and code, `HTTPException` returns JSON, and
   any other exception is logged and returns a generic 500 that hides internals.

*Why a factory?* Tests can call `create_app(test_settings)` to get a fresh app with a temporary
database. The factory pattern is Flask's recommended structure.

### `app/config.py`: all settings in one place

- **`Settings`** (pydantic-settings): every setting is a typed field with a default. Values come
  from real environment variables first, then `.env`. Wrong types fail **at startup**, not mid-request.
- `ROOT_DIR` and `ENV_FILE`: paths are resolved from the file's location, so the app works from any
  working directory.
- `CsvList`: lets `CORS_ORIGINS=a,b` become a Python list.
- **`provider_credentials(provider)`** returns `(<NAME>_API_KEY, <NAME>_BASE_URL)`.
- **`provider_models(provider)`** parses `<NAME>_MODELS` into a list.
- `reasoning_model` and `fast_model`: optional per-agent models, falling back to `LLM_PRIMARY`.
- **`get_settings()`**: cached with `@lru_cache`, so `.env` is read **once**. That's why a change
  needs a restart.

### `app/services.py`: the service container

**`Services`** holds the long-lived objects: `settings`, `registry` (LLM providers), `llm`
(gateway) and `connections` (DB manager). `Services.build()` creates them once per process, and
**`services()`** fetches them inside a request.

*Why?* Building OpenAI clients and connection pools per request would be slow. This also keeps
wiring in one place instead of global variables scattered across modules.

---

## 3. `app/api/`: HTTP layer

The thin layer: validate the input, call a service, return JSON or a stream. No business logic.

| File | Endpoints / functions | What it does |
|---|---|---|
| `__init__.py` | `register_api(app, limiter, rate_limit, auth_rate_limit)` | Registers the blueprints under `/api` (auth under `/api/auth`). Applies the rate limit to `chat` and `connections`, and a stricter one (`10/minute`) to `auth` against password guessing. |
| `auth.py` | `POST /api/auth/signup`, `/login` | Create an account / check the password, then return an access + refresh token pair |
| | `POST /api/auth/refresh`, `/logout` | Rotate the refresh token / revoke it |
| | `GET /api/auth/me` | The logged-in user |
| `meta.py` | `GET /api/health` | Public. Liveness check, plus `llm_ready` (is any provider configured?). Used by Render and Docker health checks. |
| | `GET /api/config` | Bootstraps the UI: model list (with roles), enabled DB types, limits |
| `connections.py` | `POST /api/connections` | Validate config → connect read-only → introspect schema → return connection and schema |
| | `GET /api/connections/current` | Current session's connection (so a page refresh keeps it) |
| | `DELETE /api/connections/current` | Disconnect, dispose the engine, delete the session data |
| | `POST /api/schema/refresh` | Re-read the schema after the database changed |
| `chat.py` | `POST /api/chat` | **The main endpoint.** See below. |
| `deps.py` | `require_auth()` | Runs before every request on the `meta_private`, `connections` and `chat` blueprints. Reads `Authorization: Bearer …`, verifies the JWT, and puts the user id in `flask.g`. Missing or invalid → 401. |
| | `session_id()` | Reads the `X-Session-Id` header, validates the format (16–64 chars of letters, digits and dashes) and prefixes it with the user id (`u7-<id>`), so one user can never reach another user's DB connection |
| | `parse_body(Model)` | Parses JSON into a Pydantic model; bad input gives a clean 400 |
| `schemas.py` | `ChatRequest`, `HistoryTurn`, `ConnectRequest`, `AuthRequest`, `RefreshRequest` | Request shapes. History is limited to 50 turns. |

**`chat()` in detail:**

1. Validates the message (not empty, at most `MAX_MESSAGE_CHARS`).
2. **Before streaming**, resolves everything that can fail: the session's connection (409 if not
   connected) and the chosen model (400 if not allowed). Once a stream starts, the HTTP status is
   already 200, so errors found before that point get proper status codes.
3. Builds an `AgentContext` and returns
   `Response(stream_with_context(stream()), mimetype="text/event-stream")`.
   `stream()` iterates `orchestrator.run(ctx)` and converts each `(event, data)` into SSE text.
4. Headers `Cache-Control: no-cache, no-transform` and `X-Accel-Buffering: no` stop proxies from
   buffering the stream.

---

## 3b. `app/auth/`: accounts and JWT

Users are stored in **`auth/auth.db`**, a SQLite file of its own at the repo root. It is separate
from `data/demo.db`, the data users ask questions about, and gitignored. Full explanation in [auth.md](auth.md).

| File | Important functions | What it does and why |
|---|---|---|
| `store.py` | `UserStore` | Creates three tables on start: `users`, `refresh_tokens`, `login_events`. Opens one short-lived `sqlite3` connection per operation, which is safe across gunicorn threads. |
| | `create`, `get_by_email`, `get_by_id` | Account rows. A unique email is enforced by the database (`UNIQUE` → `IntegrityError` → 409). |
| | `record_login` | Writes every attempt (success or failure, IP, browser) to `login_events` and updates `last_login_at` / `login_count`. This is the login tracking. |
| | `add_refresh_token`, `use_refresh_token` | Each refresh token is stored by its id (`jti`). `use_refresh_token` revokes it in one atomic `UPDATE … WHERE revoked = 0`, so it works exactly once. |
| | `revoke_all_refresh_tokens` | Logs a user out everywhere (used on token theft). |
| `service.py` | `AuthService.signup` | Validates the email and password strength, then hashes the password (`werkzeug` scrypt + salt) |
| | `login` | Checks the hash. A wrong email also runs a hash check, so a wrong email and a wrong password take the same time and can't be told apart. Records the attempt. |
| | `issue_tokens` | Signs an **access token** (HS256, 15 min) and a **refresh token** (7 days, `jti` saved in the DB) |
| | `refresh` | Verifies the refresh token, uses it up and issues a new pair (**rotation**). A token that was already used means it was copied, so all the user's tokens are revoked. |
| | `user_from_access_token` | Verifies the signature, expiry and `type == "access"`. No database lookup, so it's fast. |
| | `seed_demo_user` | Creates `user` / `User@1234` on start (`DEMO_USER_EMAIL`, `DEMO_USER_PASSWORD`; empty disables it) |

---

## 4. `app/agents/`: the AI brain

### `orchestrator.py`: the conductor

**`run(ctx)`** is a generator that yields `(event, data)` pairs. It's the state machine:

```
route ─┬─ write    → fixed refusal text
       ├─ general/schema → _conversational (streamed answer)
       └─ data     → _data_flow
```

**`_data_flow(...)`**, the main pipeline:

1. `select_tables`: schema step.
2. A loop of `1 + MAX_SQL_RETRIES` attempts: `SqlAgent.draft()` or `.repair(error)`, then
   `validate_readonly_sql` (guard), then `execute_readonly`. On a guard or DB error, the error
   message feeds the next repair attempt.
3. Yields `result` (the rows).
4. If a chart was requested, `build_chart_spec` yields `chart`.
5. `stream_insight` yields `token` events. If the insight model fails, the answer **degrades**
   (a fallback note) instead of failing, because the rows and chart were already delivered.

**`StepTracker`** produces the `step` events (start and end, with status, detail and duration) that
the UI shows as the live agent trace.
**`_conversational`** streams a Markdown answer for general and schema questions.
Errors become an `error` event; a `done` event always ends the stream.

### `base.py`: shared types

- **`Turn`**: one past chat message (role, content, optional SQL).
- **`AgentContext`**: everything an agent needs: the question, history, connection, LLM gateway,
  settings, the user's model override, and `models_used`.
- **`history_messages(max_chars)`**: turns recent history into chat messages, trimming long ones
  so the prompt stays small.

### `router.py`: understand the question

**`route(ctx) -> Route(intent, needs_chart, chart_type, question)`** calls the fast model with
`ROUTER_SYSTEM` and recent history, then parses the JSON. The rewritten `question` resolves
follow-ups, so "only Asia" becomes a full question. **Fallback:** keyword heuristics if the model
fails, so the app never crashes here.

### `schema_agent.py`: choose the tables

**`select_tables(ctx, question) -> (tables, how)`**:

- 15 tables or fewer: the full schema.
- More than 15: the LLM picks from a compact index; `_keyword_match` is the fallback.
- **`_with_related`** adds foreign-key neighbours, so joins are possible.
- `load_samples` adds 3 real rows each for up to 8 tables.

### `sql_agent.py`: write and fix SQL

- **`SqlAgent(ctx, question, schema_text)`** keeps a **conversation**: system prompt (with the
  schema), history, then the question.
- **`draft()`**: first attempt.
- **`repair(error)`**: appends the model's previous answer plus "The previous query failed:
  {error}", so the model sees its own mistake and fixes it. That's the self-correction loop.
- **`parse_sql_response(text)` → `SqlDraft(sql, explanation, cannot_answer)`**: pulls the SQL out of
  a fenced code block, reads `Explanation:`, and detects `CANNOT_ANSWER:`.

### `viz_agent.py`: design the chart

**`build_chart_spec(ctx, question, result, preferred)`** gives the model the column names and
types plus 8 sample rows, and gets back `{type, x, y, title}`.

- **`_validate`**: the type must be allowed, the columns must exist, and `y` must be numeric.
- **`_heuristic`**: the fallback. A time-like x column gives a line chart, otherwise a bar chart.

The model **never** writes chart code; the frontend plots the real rows.

### `insight_agent.py`: write the answer

**`stream_insight(...)`** sends the question, SQL and results (trimmed to about 8,000 characters by
`_result_payload`) and **streams** Markdown text back token by token.

### `prompts.py`

All prompt templates as constants: `ROUTER_SYSTEM`, `SCHEMA_SELECT_SYSTEM`, `SQL_SYSTEM`,
`SQL_RETRY_USER`, `VIZ_SYSTEM`, `INSIGHT_SYSTEM`, `GENERAL_SYSTEM` and `WRITE_REFUSAL`. Keeping them
in one file makes prompts easy to review and tune. The full text is in `deployment.md`, Part 3.

---

## 5. `app/llm/`: talking to models

### `registry.py`: which providers and models exist

- **`ModelRef(provider, name)`**: a model reference such as `nebius:nvidia/Nemotron-3_5-Lightning`.
  **`parse()`** splits on the first `:`, so slashes in model names are safe. `label` is the short
  name shown in the UI.
- **`ProviderRegistry`**:
  - creates one `OpenAI(api_key, base_url)` client **per provider that has a key**; providers
    without a key are skipped
  - `DEFAULT_BASE_URLS` supplies Nebius, Gemini and OpenAI URLs, so `.env` doesn't need them
  - **`roles()`**: primary, secondary, reasoning and fast
  - **`available_models()`**: role models plus each provider's `<NAME>_MODELS`, enabled providers
    only. This is what the picker shows.
  - **`resolve_override(model_id)`**: validates the user's choice against that list. `"auto"`
    means no override.

*Why the OpenAI SDK for everything?* Nebius, Gemini and OpenAI all offer OpenAI-compatible APIs, so
one SDK covers all of them, including streaming, retries and timeouts.

### `gateway.py`: how calls are made

- **`_candidates(role, override)`**: the fallback chain, `[override or role model, primary,
  secondary]`, with duplicates and disabled providers removed.
- **`complete(messages, role, ...)` → `LLMResult(text, model)`**: tries each candidate until one
  succeeds. Each SDK client also retries twice on 429, 5xx and connection errors.
- **`complete_json(...)`**: `complete` plus **`parse_json_object`**, which tolerates code fences and
  extra text around the JSON.
- **`stream(..., on_model)`**: streams text. It falls back to the next model **only if nothing has
  been sent yet**, because switching models mid-answer would mix two replies.
- **`ThinkFilter`**: a small state machine that removes `<think>…</think>` reasoning blocks from a
  stream, even when a tag is split across chunks. **`clean_text`** does the same for full responses.

---

## 6. `app/db/`: database access (read-only)

### `connectors.py`: read-only engines

- **`ConnectionConfig`**: type (`sqlite_demo`, `postgresql` or `mysql`), host, port, database,
  username, password and ssl. `validate_required()` checks the required fields, and
  `public_dict()` returns the config **without the password** for the UI.
- **`_sqlite_readonly_engine`**: opens the file with `?mode=ro` and `PRAGMA query_only`.
- **`_postgres_engine`**: psycopg 3, with `default_transaction_read_only=on`, `statement_timeout`
  and an SSL mode.
- **`_mysql_engine`**: PyMySQL. A connect event runs `SET SESSION TRANSACTION READ ONLY` and
  `max_execution_time`.
- **`create_readonly_engine(cfg, settings)`** picks the right builder.
  **`verify_connection(engine)`** runs a test query and turns failures into a friendly
  `ConnectionFailedError`.

### `guard.py`: the SQL safety check (no AI)

**`validate_readonly_sql(sql, dialect, row_limit) -> safe_sql`**:

1. Strips comments.
2. Runs a regex check for dangerous keywords (`INSERT`, `DROP`, `PRAGMA`, `ATTACH`…), **with string
   literals blanked out**, so `WHERE name = 'drop'` still works.
3. Parses with **sqlglot**. It must be exactly **one** statement, and that statement must be a query.
4. Walks the syntax tree and rejects forbidden nodes (Insert, Update, Delete, Create, Into…) and
   functions (`pg_sleep`, `sleep`, `benchmark`, `load_extension`…).
5. Adds `LIMIT row_limit` if there isn't one.

It raises **`UnsafeQueryError`**, and the message goes back to the SQL agent to repair.

### `executor.py`: run the query

**`execute_readonly(engine, sql, row_limit, timeout_seconds) -> QueryResult`**:

- Runs inside a transaction that is **always rolled back**.
- SQLite gets a progress handler that aborts after the timeout.
- `fetchmany(row_limit + 1)`: the extra row tells us the result was **truncated**.
- Converts values to JSON-safe types (`to_jsonable`), and **`_infer_type`** marks each column
  number, string or boolean. The viz agent and chart need this.
- Errors become **`QueryExecutionError`**, whose message goes to the repair loop.

### `introspect.py`: learn the schema

- Dataclasses: `Column`, `ForeignKey`, `Table` and `SchemaInfo`.
- **`introspect_schema(engine, dialect)`**: SQLAlchemy `inspect()` reads tables, views, columns,
  primary keys and foreign keys from the database catalog, up to 300 tables.
- **`load_samples(engine, table, limit)`**: `SELECT * … LIMIT 3`, run through the same safe executor.
- **`render_tables(tables)`**: the compact DDL text, with sample rows, that goes into the SQL
  prompt.
- **`render_table_index(tables)`**: one line per table, for large-schema selection.

### `session_store.py`: where session data lives

- **`MemorySessionStore`**: a dict with a sliding TTL. Fine for one process.
- **`RedisSessionStore`**: the same interface backed by Redis with `SETEX`, shared by all
  workers.
- **`SecretBox`**: **Fernet** encryption with a key derived from `SECRET_KEY`. `seal()` encrypts and
  `open()` decrypts. DB passwords are never stored in plain text.
- **`build_session_store(settings)`** picks memory or Redis from `SESSION_BACKEND`.

### `manager.py`: connection lifecycle

**`ConnectionManager`** combines the store and a per-process engine cache:

- **`connect(sid, config)`**: build the engine, verify it, introspect, save the **encrypted** config
  with a `connected_at` stamp, and cache the engine.
- **`get(sid)`**: return the cached connection. If this process doesn't have it, for example a
  different worker handled the connect, it **rebuilds** the connection from the encrypted store.
  Raises `NotConnectedError` if there's none.
- `peek`, `refresh_schema` and `disconnect`. The engine cache is an **LRU** (`ENGINE_CACHE_SIZE`)
  and disposes the connection pools it evicts.

---

## 7. `app/core/`: shared utilities

| File | Contents | Why |
|---|---|---|
| `errors.py` | `AppError` (base, with `status_code`, `code` and `to_dict()`) plus `ValidationError` 400, `NotConnectedError` 409, `ConnectionFailedError` 422, `UnsafeQueryError` 422, `QueryExecutionError` 422, `LLMError` 502 | One error shape everywhere: `{"error": {"code", "message"}}`. The frontend can react to `code`. |
| `logging.py` | `JsonFormatter`, `configure_logging(level, json_logs)` | JSON lines in production, which log tools can search; readable text locally |
| `serialization.py` | `to_jsonable(value)`, `sse_event(event, data)` | DB values (Decimal, dates, bytes, NaN) become JSON-safe; formats an SSE message as `event: x\ndata: {...}\n\n` |

---

## 8. `scripts/` and `tests/`

- **`scripts/seed_demo.py`**: `initialize_top50_db(path)` creates the demo database with 5 related
  tables (`countries`, `economy_stats`, `education_stats`, `tourism_stats`, `tech_stats`) covering
  the top 50 countries. It's called automatically by `create_app` when `data/demo.db` is missing.
- **`tests/`** (pytest, 38 tests, no LLM key needed):
  - `test_guard.py`: allowed and blocked SQL across dialects, auto-LIMIT.
  - `test_llm_parsing.py`: `<think>` stripping across chunks, JSON and SQL extraction, model-ref
    parsing.
  - `test_api.py`: health, the connect, current and disconnect lifecycle, 409 without a
    connection, 400 without a session header, and a test that sends a write **directly** to the
    executor to prove the database itself refuses it.
  - `conftest.py`: puts the repo root on `sys.path` so `import app` works.

Run them with `pytest -q` from the repo root.

---

## 9. One request through the files

`POST /api/chat {"message": "Plot top 5 countries by GDP"}`

1. `api/chat.py → chat()`: validate; `services().connections.get(sid)`; `registry.resolve_override`.
2. `agents/orchestrator.py → run()`
3. `agents/router.py → route()` → `llm/gateway.py → complete_json()` → Nebius
4. `agents/schema_agent.py → select_tables()` → `db/introspect.py → load_samples()`
5. `agents/sql_agent.py → SqlAgent.draft()` → gateway → model
6. `db/guard.py → validate_readonly_sql()`
7. `db/executor.py → execute_readonly()` (on an error, back to step 5 with `repair()`)
8. `agents/viz_agent.py → build_chart_spec()`
9. `agents/insight_agent.py → stream_insight()` → `gateway.stream()` → `ThinkFilter`
10. Each step is formatted by `core/serialization.py → sse_event()` and streamed to the browser.
