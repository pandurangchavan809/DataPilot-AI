# DataPilot AI Interview Preparation

A practical interview guide for **DataPilot AI** as it exists in this repository: an agentic,
read-only natural-language analytics app with a Flask backend and a React + TypeScript frontend.

Use it to prepare answers for:

- project explanation and end-to-end flow
- AI system design (agents, model routing, fallback, grounding)
- database safety (read-only enforcement)
- backend, frontend and deployment choices
- "Why this tech stack?"
- limitations, trade-offs and the roadmap

## 1. One-minute project introduction

If the interviewer says, **"Tell me about your project"**:

> DataPilot AI lets people ask questions about a SQL database in plain English and get back a
> written answer, the result table, the SQL that produced it, and a chart when they ask for one.
> Behind the chat is a small team of agents: a router works out what the user wants, a schema agent
> picks the relevant tables, a SQL agent writes the query, a deterministic guard checks that it is
> read-only, and then the query runs. If it fails, the SQL agent sees the error and repairs its own
> query. Finally a visualization agent picks a chart and an insight agent streams the answer. Users
> can connect their own PostgreSQL or MySQL database, or try a bundled SQLite demo. Everything is
> read-only, enforced in three independent layers. The backend is Flask with Server-Sent Events, the
> frontend is React, TypeScript and Tailwind, and the LLM layer supports Nebius (Nemotron), Gemini
> and OpenAI with role-based routing and automatic fallback, all configured from `.env`.

Shorter version:

> It's a ChatGPT-style analytics assistant: you ask a question in English, agents write and verify
> read-only SQL against your database, and you get an answer, a table and a chart, streamed live.

## 2. Problem statement

**"What problem does this solve?"**

> Many people know the business question but not SQL or the database structure. Analysts become a
> bottleneck for simple questions. DataPilot closes that gap, but the hard part is trust: an LLM
> writing SQL against a real database is risky. So the project is as much about safety and
> transparency as about generation. Every answer shows the SQL, the data and the steps the agents
> took, and the system cannot modify data.

## 3. Main features

- Natural language → SQL → answer, streamed step by step in a chat UI
- Agentic pipeline with self-repair (up to `MAX_SQL_RETRIES` attempts)
- Charts on request (bar, line, area, pie, scatter) rendered inline, switchable by the user
- Follow-up questions ("now only Europe") resolved using recent chat history
- Connect PostgreSQL or MySQL, or use the bundled SQLite demo database
- Read-only by design, enforced at SQL, session and transaction level
- Multiple LLM providers and models, picked by role or chosen by the user in the UI
- Session-only chats: nothing is stored server-side; credentials are encrypted and expire
- Schema explorer, SQL viewer with copy, paginated result table with CSV export, dark mode, mobile layout
- Production deployment: Docker, gunicorn, nginx, Redis, rate limiting, structured JSON logs

## 4. Architecture

**"Explain the architecture."**

> There are three tiers. The React frontend is a single-page chat app. It sends the question plus
> the last few turns to `POST /api/chat` and reads back a Server-Sent Events stream: step updates,
> the SQL, the result rows, a chart spec and the answer tokens. The Flask backend has an
> orchestrator, a state machine that runs the agents in order and yields events. Agents never talk
> to an LLM SDK directly. They go through an LLM gateway that knows which model plays which role,
> falls back to another provider on failure, and strips reasoning `<think>` blocks. Databases are
> reached through a connection manager that only ever creates read-only engines. Session state
> lives in memory or Redis, so the backend is stateless and can scale horizontally.

```
React (chat, trace, table, chart)  ──SSE──▶  Flask API
                                              └─ Orchestrator
                                                  Router → Schema → SQL ⇄ Guard ⇄ Executor → Viz → Insight
                                              └─ LLM gateway (roles, fallback)  → Nebius / Gemini / OpenAI
                                              └─ Connection manager (read-only engines, LRU cache)
                                              └─ Session store (memory / Redis, Fernet-encrypted creds)
```

## 5. End-to-end flow

**"What happens when a user asks a question?"**

1. The frontend sends `{message, history, model}` with an `X-Session-Id` header.
2. The backend resolves the session's connection (rebuilding the engine from the encrypted store
   if this worker hasn't seen it yet) and validates the model choice. Errors here return normal
   HTTP codes before any streaming starts.
3. **Router** (fast model) classifies intent: `data`, `schema`, `general` or `write`. It detects
   chart requests and rewrites follow-ups into standalone questions.
   - `write` → a polite refusal, no SQL is generated.
   - `schema` / `general` → answered directly from the schema or conversation.
4. **Schema agent** sends the full schema if there are ≤ 15 tables. For larger schemas it asks the
   LLM to choose tables (keyword fallback), adds foreign-key neighbours, and includes a few sample
   rows per table.
5. **SQL agent** (reasoning model) writes dialect-specific SQL plus a short explanation, or says it
   cannot answer.
6. **Guard** parses the SQL with `sqlglot` and rejects anything that isn't a single read query. It
   adds a `LIMIT` if missing.
7. **Executor** runs it on a read-only connection with a timeout, inside a transaction that is
   always rolled back.
8. If the guard or the database rejects it, the error goes back to the SQL agent, which repairs the
   query. This repeats up to `MAX_SQL_RETRIES` times.
9. **Viz agent** (only if a chart was requested) returns a declarative spec `{type, x, y}`, which is
   validated against the real result columns. A heuristic covers the case where the LLM fails.
10. **Insight agent** streams a Markdown answer grounded in the actual rows.
11. The frontend renders each event as it arrives: the agent trace, SQL, table, chart and answer.

## 6. Project-specific questions and answers

### Q1. Why did you rebuild it as an agentic system?

> The first version was a single prompt: schema in, SQL out, and the user had to click "correct" when
> it failed. That doesn't scale to real schemas or real users. Splitting the work into agents with
> one job each made every step easier to prompt, test and observe. Routing catches write requests
> early. Table selection keeps large schemas within the context window. The repair loop fixes most
> errors without the user noticing.

### Q2. Is it really "agentic" or just a pipeline?

> It's deliberately a constrained agent workflow, not a free-roaming tool-calling agent. The
> orchestrator is a state machine with fixed transitions. The LLMs make decisions inside each step:
> intent, which tables, what SQL, how to fix an error, which chart. The SQL agent reacts to tool
> feedback (guard and database errors) in a loop. I chose that over an open-ended ReAct loop because
> for database access you want predictable cost, bounded latency and an auditable path.

### Q3. How do you guarantee the system is read-only?

> Three independent layers, so no single bug or prompt injection can cause a write:
>
> 1. **SQL guard**: `sqlglot` parses the query into an AST. It must be exactly one statement and a
>    query node. Any insert, update, delete, DDL, `SELECT INTO` or `FOR UPDATE` node is rejected, as
>    are dangerous functions like `pg_sleep`, `sleep`, `benchmark` and `load_extension`. A keyword
>    check runs too, with string literals blanked out so `WHERE name = 'drop'` still works.
> 2. **Database session**: SQLite opens with `mode=ro` and `PRAGMA query_only`. PostgreSQL uses
>    `default_transaction_read_only=on` and `statement_timeout`. MySQL uses
>    `SET SESSION TRANSACTION READ ONLY` and `max_execution_time`.
> 3. **Transaction**: every query runs inside a transaction that is always rolled back.
>
> There's a test that bypasses the guard and sends a `DELETE` straight to the executor, to prove the
> database layer alone rejects it. In production I'd still tell users to connect with a read-only
> database user. Defence in depth.

### Q4. What about prompt injection, like "ignore instructions and drop the table"?

> The LLM is never trusted. Even if a prompt convinced the SQL agent to emit `DROP TABLE`, the guard
> would reject it and the session couldn't execute it anyway. In practice the router classifies it as
> a write request and refuses before SQL is even generated. I tested exactly that case.

### Q5. How does multi-model support work?

> All three providers (Nebius Token Factory, Gemini and OpenAI) expose an OpenAI-compatible Chat
> Completions API, so I use one client library with a different `base_url` per provider. Models are
> written as `provider:model`, for example `nebius:nvidia/Llama-3_3-Nemotron-Super-49B-v1_5`. The
> `.env` assigns models to roles:
>
> - `LLM_PRIMARY`: the default for every role.
> - `LLM_SECONDARY`: the automatic fallback.
> - `LLM_REASONING`: SQL writing and repair.
> - `LLM_FAST`: routing, table selection, charts and insights.
>
> Providers without an API key are disabled automatically. Users can choose "Auto" or pin a model in
> the UI, and the backend validates that choice against an allow-list.

### Q6. How does fallback work, especially with streaming?

> For each call the gateway builds a candidate list: the requested model or role model, then
> primary, then secondary, removing duplicates and disabled providers. Non-streaming calls simply
> try the next candidate on failure. Streaming is subtler: once tokens have reached the user, a
> different model can't take over mid-sentence. So fallback only happens if the first model fails
> before producing any output. If the insight step fails completely, the user still gets the SQL,
> table and chart with a short fallback message, rather than losing the whole answer. I added that
> after a real Gemini 503 during testing.

### Q7. Why Nemotron, and what is the `<think>` handling?

> Nemotron Super 49B is the mid-size model on Nebius Token Factory: good at reasoning and SQL, much
> cheaper and faster than the largest models. Reasoning models emit `<think>…</think>` blocks before
> the answer. The gateway strips them, and for streaming I wrote a small state-machine filter that
> handles tags split across chunks, so users never see raw reasoning.

### Q8. How do you handle large schemas?

> Up to `SCHEMA_FULL_CONTEXT_MAX_TABLES` (default 15) the whole schema goes in the prompt, because
> that's the most accurate option. Above that, the schema agent gives the LLM a compact table index
> and asks it to choose tables, with keyword matching as a fallback. It then adds tables linked by
> foreign keys so joins still work, and includes a few sample rows. Sample values help the model
> match real values, for example `'Asia'` and not `'asia'`.

### Q9. How do you get structured output from LLMs reliably?

> Each agent has a strict output contract: JSON for the router, schema agent and viz agent, and a
> fenced `sql` block plus `Explanation:` for the SQL agent. Parsers are tolerant: they strip think
> blocks and code fences and extract the first JSON object. Everything is validated after parsing.
> For example, chart columns must exist in the result. Every LLM-dependent step also has a
> deterministic fallback, so a malformed response degrades quality but never crashes the request.

### Q10. Why Server-Sent Events instead of WebSockets or plain JSON?

> The answer flows one way, from server to client, and arrives in stages. SSE fits that exactly. It
> works over normal HTTP, through proxies and with standard auth headers, and needs no extra server
> infrastructure. Plain JSON would make users wait 5–15 seconds staring at a spinner. I send the
> request as a POST, so the browser `EventSource` API doesn't work; the frontend reads the stream
> with `fetch` and a small parser. That also gives cancellation through `AbortController` for the
> Stop button.

### Q11. How are sessions and credentials handled?

> There are no accounts and no stored chats, which was a requirement. The frontend generates a random
> session id and keeps chat history in `sessionStorage`, so closing the tab clears it. On connect,
> the backend stores the connection config Fernet-encrypted, with a key derived from `SECRET_KEY`,
> and a sliding TTL. Storage is in memory for development and Redis in production. Live database
> engines are cached per process in an LRU and disposed when evicted. If a request lands on a worker
> that doesn't have the engine, it rebuilds it from the encrypted store. That keeps workers stateless.

### Q12. How did you make it production-ready rather than a demo?

> - Configuration is centralized in `.env` and validated with `pydantic-settings`.
> - A Flask app factory with blueprints, plus a typed error hierarchy that maps to HTTP codes and
>   stable error codes.
> - Request validation with Pydantic, and request size and history limits.
> - Rate limiting per client IP with flask-limiter (Redis-backed in production), and `ProxyFix` for
>   correct client IPs behind nginx.
> - CORS restricted to configured origins.
> - Structured JSON logging.
> - gunicorn with threaded workers (cheap for long SSE streams) and nginx with proxy buffering off
>   for SSE.
> - Dockerfiles for both services and a compose file with Redis.
> - Tests for the guard, the LLM parsing and the API lifecycle.

### Q13. Why is there a `docker-compose.yml` at the repo root?

> Because it describes the whole system, not a single service. It builds `./backend` and
> `./frontend` from their own Dockerfiles, adds Redis, and connects them on one network, so the full
> production-like stack starts with one command. Compose resolves build paths relative to the
> file's location, so the root is the natural place for a file that spans folders. Each service is
> still independently deployable. On Render, Railway or Kubernetes you'd deploy the two images
> separately with a managed Redis.

### Q14. How does charting work?

> The LLM never generates chart code. It returns a small declarative spec (`type`, `x`, `y`, `title`)
> that's validated against the real columns, with a heuristic fallback: a time-like x gives a line
> chart, few categories give a bar chart. The frontend renders it with Recharts using a fixed,
> colorblind-validated palette, separate light and dark mode colours, and a custom tooltip. Users can
> switch between bar, line, area and pie. Recharts is lazy-loaded, so it only downloads when the
> first chart appears.

### Q15. What were the biggest technical challenges?

> - **Safety:** making read-only a guarantee rather than a prompt instruction.
> - **Streaming fallback:** you can't switch models mid-answer.
> - **Messy model output:** reasoning tags, code fences and occasionally invalid JSON.
> - **SSE through proxies:** buffering, timeouts and hop-by-hop headers.
> - **Scaling with sessions:** stateless workers while keeping a user's connection, solved with an
>   encrypted session store plus a rebuildable engine cache.

### Q16. How do you test an LLM application?

> I separate the deterministic parts from the model. The guard has an allow/deny matrix across
> dialects. The parsers are tested against messy model output: think tags, fences and missing JSON.
> API tests cover the connection lifecycle, validation errors, session headers, and a database-level
> write rejection that bypasses the guard. The next step is an evaluation set: questions with
> expected results on the demo database, scored on execution accuracy, so prompt or model changes
> can be compared objectively.

### Q17. What are the current limitations?

> - No user accounts or authentication. Sessions are anonymous, which suits a demo but not a
>   multi-tenant SaaS.
> - No automated SQL-accuracy benchmark yet.
> - Only SQLite, PostgreSQL and MySQL.
> - No query result caching.
> - No clarifying questions for ambiguous requests yet: the agents make a best guess and show the SQL.
> - Large-schema table selection could use embeddings instead of an LLM index pass.
> - Credentials are entered per session. In an enterprise setting I'd integrate a secrets manager.

### Q18. What did you learn?

> Most of the reliability in an LLM system comes from what surrounds the model: grounding it in real
> schema and sample data, strict output contracts, deterministic validation, and fallbacks at every
> step. Model choice matters less than I expected; system design matters more.

## 7. Why this tech stack?

### Why Python and Flask?

> Python has the best ecosystem for LLMs and databases (SQLAlchemy, sqlglot, provider SDKs). I chose
> Flask over FastAPI because the request flow is synchronous: blocking database drivers and
> streaming generators. Flask with gunicorn's threaded workers handles that simply and predictably.
> Validation still uses Pydantic, so I didn't lose typed request models. Flask's app factory and
> blueprints keep it modular.

**"Why not FastAPI?"**

> FastAPI is great for async I/O. But my database drivers are synchronous, so I'd either block the
> event loop or wrap everything in thread pools. With Flask, gthread workers and SSE generators, the
> concurrency model is explicit and easy to reason about. The trade-off is that I wrote small helpers
> for body parsing and errors myself.

### Why React, TypeScript and Tailwind (instead of Streamlit)?

> The first version used Streamlit, which is great for prototypes. But a ChatGPT-style streaming
> interface with a live agent trace, cancellation, inline charts, a model picker, a schema explorer,
> dark mode and a mobile layout needs full UI control. TypeScript keeps the SSE event contract
> type-safe between backend and UI. Tailwind gives a consistent design system without a component
> library dependency. Vite gives fast builds and code splitting.

### Why Zustand?

> The app state is small: config, connection, messages and the selected model. Zustand gives a tiny
> global store with no boilerplate and built-in persistence to `sessionStorage`, which is exactly the
> "session-only chat" requirement.

### Why SQLAlchemy and sqlglot?

> SQLAlchemy gives one engine and inspection API across SQLite, PostgreSQL and MySQL, plus pooling and
> connection events where I set read-only mode. sqlglot is a real SQL parser that understands
> multiple dialects. That's essential for the guard: regex alone can't safely tell a `SELECT` from a
> CTE that hides a write.

### Why the OpenAI SDK for every provider instead of LangChain?

> Nebius, Gemini and OpenAI all speak the same API, so one small gateway (routing, fallback,
> streaming, think-tag filtering) is about 200 lines I fully understand and can debug. A framework
> would add abstraction layers and dependency churn without solving my actual problems, which are
> role-based routing and stream-safe fallback.

### Why Redis?

> Production has several gunicorn workers and possibly several containers. Sessions and rate-limit
> counters must be shared across them. Redis does both and supports TTL-based expiry natively.

### Why SQLite for the demo?

> Zero setup. Anyone can try the app instantly. The demo database has five related tables
> (`countries`, `economy_stats`, `education_stats`, `tourism_stats`, `tech_stats`) covering the top
> 50 countries, so joins and real analytical questions work. It's opened read-only like any other
> database.

### Short "why this stack" answer

> I optimized for safety, clarity and real-world deployability: Python for the AI and database
> ecosystem, Flask for a simple synchronous streaming model, sqlglot and SQLAlchemy for safe
> multi-dialect SQL, an OpenAI-compatible gateway so models are swappable from `.env`, and React with
> TypeScript for a production-grade chat UI.

## 8. Tough questions

### Q1. What if the LLM writes a correct-looking but wrong query?

> That's the main risk in NL2SQL, and you can't fully eliminate it. I mitigate it with grounding
> (schema plus sample rows) and transparency: the SQL, its explanation and the raw rows are always
> visible, so a user can verify the answer. The insight agent is instructed to use only the returned
> data. Next steps are an evaluation set and clarifying questions for ambiguous requests.

### Q2. What stops someone from running a very expensive query?

> Statement timeouts at the database (PostgreSQL `statement_timeout`, MySQL `max_execution_time`,
> and a progress-handler timeout on SQLite), an automatic `LIMIT`, row limits on fetch, blocked
> sleep and benchmark functions, and per-IP rate limits.

### Q3. Is sending credentials to the backend safe?

> They travel over HTTPS in production, are encrypted at rest in the session store, expire with the
> session, and are never logged or returned to the client. The API returns only a public view of the
> connection. The safest setup is still a dedicated read-only database user, which I recommend in
> the README.

### Q4. Why not let the LLM call tools freely (a ReAct agent)?

> Unbounded loops mean unpredictable cost and latency, and more room for prompt injection to steer
> behaviour. A fixed graph with LLM decisions inside each step gives most of the benefit with
> bounded retries and a clear audit trail. It's the same idea as LangGraph-style workflows.

### Q5. Why not fine-tune a model?

> Grounding with the live schema solves most of the problem at a fraction of the cost. Fine-tuning
> would tie me to one model, and the project is designed so models are swappable from `.env`.

### Q6. How would you scale to many users?

> The backend is already stateless: shared state is in Redis, engines are rebuilt on demand, and
> workers scale horizontally behind nginx or a load balancer. Next would be schema caching in Redis,
> result caching for repeated questions, connection pool tuning per tenant, and moving long jobs to
> a queue if needed.

## 9. Repo questions someone might ask after reading the code

### Q1. Why is the old Streamlit and FastAPI code gone?

> It was the v1 prototype. The new architecture replaced it completely, so I removed it to keep the
> repo clear. It's still in the git history.

### Q2. Why is there a `requirements.txt` at the root and in `backend/`?

> The backend owns its dependencies in `backend/requirements.txt`. The root file just includes it
> (`-r backend/requirements.txt`) for hosting platforms and tools that look for a root
> `requirements.txt`. There's one source of truth.

### Q3. Why is `.env` inside `backend/` and not at the root?

> The backend is the only service with secrets. Keeping its `.env` next to its code means the
> backend Docker image and `docker compose` (`env_file: backend/.env`) use the same file. The
> frontend only needs a public build-time variable, `VITE_API_BASE_URL`.

## 10. Roadmap ("What would you do next?")

> - **v2, data ingestion:** users upload CSV or Excel files. The pipeline infers types, cleans
>   headers and values, and loads the data into a per-session workspace database. That workspace
>   becomes another connection type next to the demo, so the agents need no changes.
> - An evaluation harness for SQL accuracy across models.
> - Clarifying questions for ambiguous requests.
> - Authentication and saved workspaces.
> - Result caching, plus SQL Server and Snowflake connectors.

## 11. Closing line

> This project taught me that building with LLMs is mostly system design: grounding, contracts,
> validation, fallbacks and transparency. The model writes the SQL, but the system around it is what
> makes the answer safe and trustworthy.
