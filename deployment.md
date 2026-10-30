# DataPilot AI Deployment Guide

This guide covers two things:

1. **Deploying:** the backend (Flask) on **Render** and the frontend (React) on **Vercel**.
2. **How it works:** how the agents learn a database's schema, find the right data, build charts and
   stream Markdown answers, plus the full text of every prompt the agents use.

---

## Part 1: Deployment

### 1.1 What goes where

```
 Browser ──HTTPS──▶  Vercel (frontend/)          static React build
    │
    └──────HTTPS──▶  Render (repo root)          Flask + gunicorn, streams answers (SSE)
                        ├──▶ Nebius / Gemini / OpenAI   (LLM APIs)
                        ├──▶ user's PostgreSQL / MySQL   (read-only)
                        └──▶ Render Key Value (Redis)    optional, for multiple workers
```

The browser calls the Render backend **directly**, so two settings must point at each other:

| Setting | Where | Value |
|---|---|---|
| `VITE_API_BASE_URL` | Vercel env var | `https://<your-backend>.onrender.com` |
| `CORS_ORIGINS` | Render env var | `https://<your-frontend>.vercel.app` |

### 1.2 Before you start

- [ ] Code is pushed to GitHub. `.env`, `frontend/.env`, `data/` and `.venv/` are gitignored, so
      your keys are **not** on GitHub. You'll type them into Render instead.
- [ ] You have accounts on render.com and vercel.com, both signed in with GitHub.
- [ ] Your LLM API keys (Nebius, Gemini, OpenAI) are at hand.
- [ ] You have a strong secret key. Generate one with:

  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(48))"
  ```

### 1.3 Deploy the backend on Render

1. Render dashboard → **New +** → **Web Service** → connect your GitHub repo.
2. Fill in:

   | Field | Value |
   |---|---|
   | Name | `datapilot-api` (your URL becomes `https://datapilot-api.onrender.com`) |
   | Language / Runtime | **Python 3** |
   | Branch | `main` |
   | Root Directory | *(leave empty: the backend is at the repo root)* |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `gunicorn -c gunicorn.conf.py wsgi:app` |
   | Health Check Path | `/api/health` (under **Advanced**) |
   | Instance type | Free works for demos; Starter avoids cold starts |

   `gunicorn.conf.py` already listens on Render's `$PORT` and uses threaded workers, which suit
   streamed answers.

3. **Environment variables** (Environment tab → Add). Copy the values from your local `.env`:

   | Key | Value | Why |
   |---|---|---|
   | `PYTHON_VERSION` | `3.11.9` | Same Python the project is tested on |
   | `APP_ENV` | `production` | JSON logs, production behaviour |
   | `SECRET_KEY` | *(the long random string)* | Encrypts users' DB passwords in sessions |
   | `CORS_ORIGINS` | `https://<your-frontend>.vercel.app` | Only your frontend may call the API. Fill it in after step 1.4, then redeploy. |
   | `PROXY_FIX_HOPS` | `1` | Render sits behind a proxy; needed for correct per-IP rate limits |
   | `WEB_CONCURRENCY` | `1` | **One worker process** while sessions are in memory (see 1.6) |
   | `NEBIUS_API_KEY` | *(your key)* | |
   | `NEBIUS_MODELS` | `nvidia/Nemotron-3_5-Lightning,Qwen/Qwen3-235B-A22B-Instruct-2507` | |
   | `GEMINI_API_KEY` | *(your key)* | |
   | `GEMINI_MODELS` | `gemini-3.5-flash` | |
   | `OPENAI_API_KEY` | *(your key)* | |
   | `OPENAI_MODELS` | `gpt-4.1` | |
   | `LLM_PRIMARY` | `nebius:nvidia/Nemotron-3_5-Lightning` | Auto uses this first |
   | `LLM_SECONDARY` | `gemini:gemini-3.5-flash` | Fallback |

   > Tip: Render's **Add from .env** button lets you paste the contents of your local `.env`. Then
   > change `APP_ENV` and `CORS_ORIGINS`, and add the extra keys above.

4. **Create Web Service.** The first build takes about 2–4 minutes. On start, the app creates the
   demo database (`data/demo.db`) by itself, so there's nothing to upload.
5. Check it: open `https://<your-backend>.onrender.com/api/health`. It should return
   `{"status": "ok", "llm_ready": true, ...}`.

### 1.4 Deploy the frontend on Vercel

1. Vercel dashboard → **Add New… → Project** → import the same GitHub repo.
2. Fill in:

   | Field | Value |
   |---|---|
   | Framework Preset | **Vite** |
   | Root Directory | `frontend` ← **important** |
   | Build Command | `npm run build` (default) |
   | Output Directory | `dist` (default) |
   | Install Command | `npm install` (default) |

3. **Environment variable:**

   | Key | Value | Environments |
   |---|---|---|
   | `VITE_API_BASE_URL` | `https://<your-backend>.onrender.com` (no trailing slash) | Production (and Preview if you use previews) |

   Vite bakes this into the JavaScript **at build time**. If you change it, redeploy the frontend.

4. **Deploy.** You get a URL such as `https://datapilot-ai.vercel.app`.

### 1.5 Connect them and test

1. Copy the Vercel URL into Render's `CORS_ORIGINS`. For more than one URL (a custom domain, a
   preview URL), separate them with commas and no spaces:
   `https://datapilot-ai.vercel.app,https://datapilot.mydomain.com`
2. Render redeploys automatically after an environment change. Wait until it shows **Live**.
3. Open the Vercel URL → **Try the demo database** → ask *"Plot the top 5 countries by GDP"*.
   You should see the agent steps, SQL, a table, a bar chart and a streamed answer.

### 1.6 Sessions: one worker, or add Redis

Each user's database connection is kept in a **session store**:

- **Memory (default):** each gunicorn worker process has its own memory. With 2+ workers, a
  user might connect on worker A and then chat on worker B, and get *"not connected"*. That's why
  `WEB_CONCURRENCY=1`. One process with 8 threads (`GUNICORN_THREADS`) still serves several users at
  once, which is enough for a demo or internship project.
- **Redis (to scale):** create a Render **Key Value** instance (Redis-compatible) in the same
  region, copy its *Internal URL*, then set:

  | Key | Value |
  |---|---|
  | `SESSION_BACKEND` | `redis` |
  | `REDIS_URL` | `redis://red-xxxx:6379/0` |
  | `RATE_LIMIT_STORAGE_URI` | `redis://red-xxxx:6379/1` |
  | `WEB_CONCURRENCY` | `2` or more |

  Now every worker, and every instance if you scale out, shares sessions and rate limits.

### 1.7 Free-tier notes

- **Cold starts:** Render's free web services sleep after about 15 minutes idle. The first request
  then takes about 30–60 seconds. Paid instances don't sleep.
- **Ephemeral disk:** the demo DB is recreated on every deploy or restart. That's fine, because it's
  read-only seed data.
- **Database access:** Render must be able to reach the user's PostgreSQL or MySQL over the
  internet. If the database has an IP allow-list, add Render's outbound IPs (Render dashboard →
  service → **Connect** → Outbound).

### 1.8 Updating

Push to `main`. Render and Vercel both redeploy automatically.

### 1.9 Troubleshooting

| Symptom | Fix |
|---|---|
| Browser console shows a **CORS error** | `CORS_ORIGINS` on Render must exactly match the Vercel URL (`https://`, no trailing slash). Redeploy. |
| Frontend shows "DataPilot is unavailable" | Wrong `VITE_API_BASE_URL`, or the backend is asleep or crashed. Open `/api/health`, fix the variable, redeploy Vercel. |
| `"not connected"` right after connecting | More than one worker with memory sessions. Set `WEB_CONCURRENCY=1` or add Redis (1.6). |
| Model missing from the picker | That provider's `*_API_KEY` is missing on Render |
| Answers arrive all at once instead of streaming | A proxy is buffering. Render streams by default; if you put another proxy or CDN in front, turn buffering off for `/api/chat`. |
| Build fails on Render | Check `PYTHON_VERSION=3.11.9` and that the Root Directory is empty |
| Build fails on Vercel | Root Directory must be `frontend` |
| Can't connect to your own database | The database must be publicly reachable and allow Render's IPs. Use SSL for cloud databases. |

### 1.10 Security checklist

- [ ] API keys only in Render env vars. Never in `frontend/.env` or Vercel: anything with the
      `VITE_` prefix is visible to every user.
- [ ] `SECRET_KEY` is long and random, and differs from your local one.
- [ ] `CORS_ORIGINS` lists only your frontend URLs.
- [ ] Recommend users connect with a **read-only database user**. The app also enforces read-only
      access itself in three layers (see 2.4).

---

## Part 2: How the system works

### 2.1 One question, end to end

```
User types: "Plot the top 5 countries by GDP"
   │
   ▼ frontend: POST /api/chat  {message, last few turns, model}   header X-Session-Id
   │
   ▼ backend loads this session's DB connection + schema
   │
 ① Router agent      → {"intent":"data", "needs_chart":true, "chart_type":"bar", "question":"..."}
 ② Schema agent      → picks the relevant tables, adds FK-linked tables, loads 3 sample rows each
 ③ SQL agent         → ```sql SELECT ... ``` + "Explanation: ..."
 ④ Guard (no LLM)    → parse with sqlglot: single SELECT only, add LIMIT        ─┐ on failure, the
 ⑤ Executor (no LLM) → run read-only, with a timeout, then roll back            ─┘ error goes back to ③
 ⑥ Viz agent         → {"type":"bar", "x":"country_name", "y":["gdp"], "title":"..."}
 ⑦ Insight agent     → streams a Markdown answer, token by token
   │
   ▼ every step is sent to the browser as a Server-Sent Event the moment it happens
```

### 2.2 How the agent learns the schema when a user connects a database

This happens **once, at connect time**, not on every question. No AI is involved; it reads the
database's own metadata.

1. **Connect** (`POST /api/connections`): the backend builds a **read-only** SQLAlchemy engine
   (`app/db/connectors.py`) and runs a test query.
2. **Introspect** (`app/db/introspect.py → introspect_schema`): SQLAlchemy's `inspect()` reads the
   database catalog and collects, for up to 300 tables and views:
   - table and view names
   - every column's name, type, nullability and primary-key flag
   - **foreign keys**: which column points to which table. This is how the agents know how to
     join tables.
3. The schema is kept with the session's connection and shown in the sidebar's **Schema Explorer**.
4. **Sample rows** (`load_samples`) are loaded lazily, only for tables a question actually needs:
   `SELECT * FROM table LIMIT 3`. Real values teach the model the data's format, for example that
   continents are stored as `'Asia'` and not `'asia'`, or that `gdp` is in dollars rather than
   billions.

When the database changes, the user clicks **Refresh schema** (`POST /api/schema/refresh`) to
re-read it.

### 2.3 How the agents find the right data

**Step ①, Router (fast model).** Decides whether the message needs data at all (`data`, `schema`,
`general` or `write`), detects chart requests, and rewrites follow-ups into a standalone question,
using the last few chat turns. For example, "now only Asia" becomes "top 5 countries by GDP in
Asia".

**Step ②, Schema agent (`app/agents/schema_agent.py`).** Decides which tables the SQL agent sees:

- **15 tables or fewer:** sends the **whole schema**. This is the most accurate option, because
  nothing can be missed.
- **More than 15 tables:** the LLM gets a compact index (`table: col1, col2, …`) and picks the
  needed tables. If that fails, a keyword match between question words and table and column names
  is used instead.
- Tables linked by **foreign keys** to the chosen ones are added, so joins still work.
- Up to 8 tables get **3 sample rows** each.

These tables are rendered as compact DDL with sample rows. This is the real output for two demo
tables, exactly what the SQL agent reads:

```text
TABLE countries (
  country_id INTEGER PRIMARY KEY,
  country_name TEXT,
  capital TEXT,
  continent TEXT,
  population INTEGER,
  gdp REAL,
  currency TEXT,
  official_language TEXT
)
-- sample rows:
-- country_id | country_name | capital | continent | population | gdp | currency | official_language
-- 1 | United States | Washington, D.C. | North America | 334000000 | 26700000000000.0 | USD | English

TABLE economy_stats (
  country_id INTEGER,
  year INTEGER,
  gdp_growth REAL,
  inflation_rate REAL,
  unemployment_rate REAL,
  exports REAL,
  imports REAL,
  FOREIGN KEY (country_id) REFERENCES countries(country_id)
)
-- sample rows:
-- country_id | year | gdp_growth | inflation_rate | unemployment_rate | exports | imports
-- 1 | 2024 | 2.1 | 3.5 | 4.1 | 1200000000000.0 | 1100000000000.0
```

**Step ③, SQL agent (reasoning model).** Writes one dialect-correct `SELECT` using only that
schema, plus a one-line explanation. It answers `CANNOT_ANSWER: …` if the schema can't answer the
question.

**Steps ④–⑤, Guard and Executor, the self-repair loop.** The guard rejects anything that isn't a
single read query. The executor runs the query read-only. If either fails (unsafe SQL, a wrong
column name, a syntax error), the **exact error message** goes back into the SQL agent's
conversation using the "retry" prompt. The agent fixes its own query, up to `MAX_SQL_RETRIES`
(default 2) extra attempts. This loop is the most *agentic* part of the system: the model reacts
to real feedback from the database.

### 2.4 Read-only safety (three layers)

| Layer | What it does |
|---|---|
| SQL guard (`sqlglot`) | Parses the SQL. Exactly one statement, must be a query, no DML or DDL, no dangerous functions such as `pg_sleep` or `load_extension`. Adds a `LIMIT`. |
| Read-only DB session | SQLite `mode=ro`, PostgreSQL `default_transaction_read_only`, MySQL `TRANSACTION READ ONLY`, plus statement timeouts |
| Transaction | Every query is rolled back, always |

The LLM is never trusted. Even a prompt-injected `DROP TABLE` can't run.

### 2.5 How graphs are generated

The **LLM never writes chart code.** It only picks *what* to plot.

1. The router sets `needs_chart: true` when the user asks for a chart, graph or plot, and may name
   a preferred type.
2. The **Viz agent** (`app/agents/viz_agent.py`, fast model) receives the result's column names and
   types (`number`, `string` or `boolean`) and 8 sample rows. It returns a small JSON spec:

   ```json
   {"type": "bar", "x": "country_name", "y": ["gdp"], "title": "Top 5 countries by GDP"}
   ```

3. The backend **validates** the spec. The type must be one of bar, line, area, pie or scatter;
   `x` must be a real column; and each `y` must be a numeric column, at most 3. If the spec is
   invalid or the LLM fails, a **heuristic** takes over: a date-like x column gives a line chart,
   otherwise a bar chart. A pie chart with more than 8 slices becomes a bar chart.
4. The spec is streamed as a `chart` event. The rows themselves come separately in the `result`
   event, so the chart always plots the **real query result** and never numbers invented by the
   model.

### 2.6 How the UI renders charts, tables and Markdown

| What | Library | File | Details |
|---|---|---|---|
| Charts | **Recharts** | `frontend/src/components/chat/ChartView.tsx` | Builds chart data from `result.rows` using the spec's `x` and `y`. Bar, line, area, pie and scatter, plus a type switcher. Fixed colour-blind-checked palette with separate light and dark colours. Custom tooltip. Legend only for 2+ series. Pies fold into "Other" after 8 slices. **Lazy-loaded**, so Recharts (~120 KB gzipped) downloads only when the first chart appears. |
| Table | Custom React + Tailwind | `ResultTable.tsx` | Pagination, number formatting, NULLs shown, CSV export |
| SQL | Custom highlighter | `SqlBlock.tsx` | Formats and colours the SQL, copy button |
| Answer text | **react-markdown + remark-gfm** | `Markdown.tsx` | Renders headings, bold, lists and GitHub-style tables. Raw HTML is not rendered, which is safe. |
| Agent steps | Custom | `AgentTrace.tsx` | Live list of steps with status and timing |
| Icons | lucide-react | | |
| State | Zustand | `hooks/useApp.ts` | Messages kept in `sessionStorage` (cleared when the tab closes) |

### 2.7 How the Markdown answer streams token by token

1. **Backend:** the Insight agent calls the model with `stream=True`
   (`app/llm/gateway.py → stream`). Each text chunk passes through `ThinkFilter`, which removes
   `<think>…</think>` reasoning blocks, even when a tag is split across chunks. Each chunk is then
   sent as an SSE `token` event:

   ```text
   event: token
   data: "The top 5 countries by GDP are"
   ```

2. **Transport:** `POST /api/chat` returns `Content-Type: text/event-stream` with no buffering
   (`X-Accel-Buffering: no`).
3. **Frontend:** `api.ts → streamChat` reads the response with `fetch` and a `ReadableStream`,
   splits it into events, and yields them one by one. (The browser's `EventSource` only supports GET,
   so it can't be used here.) `hooks/useChat.ts` appends each `token` to the message's `content`.
4. React re-renders `<Markdown text={content} />` on every token. **react-markdown** re-parses the
   growing text, so bold, bullets and tables appear as they stream in. A blinking cursor shows
   while the answer is still being written.
5. The **Stop** button aborts the request with an `AbortController`.

### 2.8 Which model does what

| Step | Role | Default model (Auto) |
|---|---|---|
| Router, Schema, Viz, Insight | `fast` (defaults to primary) | `nebius:nvidia/Nemotron-3_5-Lightning` |
| SQL write and repair | `reasoning` (defaults to primary) | `nebius:nvidia/Nemotron-3_5-Lightning` |
| Any step whose model fails | secondary | `gemini:gemini-3.5-flash` |

If the user picks a model in the header, every step uses it first, then primary, then secondary.
All providers are called through the same OpenAI-compatible SDK; only the `base_url` and key
differ.

---

## Part 3: All prompts (copy-paste ready)

These are the exact prompts in `app/agents/prompts.py`. Placeholders in `{braces}` are filled in at
runtime.

### 3.1 Router agent (system prompt)

Sent with the last chat turns, then the user's message. Model role: `fast`.

```text
You are the routing agent of DataPilot, a read-only natural-language analytics assistant over a SQL database.
Classify the user's latest message and rewrite it as a standalone question, resolving references to earlier turns.

Intents:
- "data": needs a database query to answer (lookups, rankings, aggregates, comparisons, trends, charts of data).
- "schema": asks about the structure of the database (what tables/columns exist, what data is available, how tables relate).
- "write": asks to modify data or structure (insert, update, delete, create, drop, alter, etc.).
- "general": greetings, thanks, questions about you, or anything unrelated to the data.

Set "needs_chart" to true only if the user asks for a chart, graph, plot, visualisation, or trend picture.

Respond with ONLY a JSON object:
{"intent": "data|schema|write|general", "needs_chart": true|false, "chart_type": "bar|line|area|pie|scatter|null", "question": "<standalone question>"}
```

### 3.2 Schema agent (system prompt)

Used only when the database has more than 15 tables. Model role: `fast`.

```text
You are the schema agent of DataPilot. Given a list of tables and their columns, choose the minimal set of tables needed to answer the question, including any tables required for joins.
Respond with ONLY a JSON object: {"tables": ["table_a", "table_b"]}
```

User message:

```text
Tables:
{table index, one line per table: "- table: col1, col2, ..."}

Question: {standalone question}
```

### 3.3 SQL agent (system prompt)

`{dialect}` is SQLite, PostgreSQL or MySQL. `{schema}` is the DDL-with-sample-rows block from 2.3.
Sent with the chat history, then the question. Model role: `reasoning`.

````text
You are the SQL agent of DataPilot, an expert {dialect} analyst.
Write ONE read-only query (SELECT, optionally with CTEs) that answers the user's question using ONLY the schema below.

Rules:
- Use only tables and columns that exist in the schema; quote identifiers when needed.
- Never write INSERT, UPDATE, DELETE, or any DDL. Read-only access is enforced.
- Join through foreign keys. Aggregate when the question implies it.
- Use ORDER BY for rankings and LIMIT for top-N questions. Use readable column aliases.
- If a chart is requested, return one category/time column followed by the numeric value column(s).
- Use {dialect} syntax and functions.
- If the question cannot be answered from this schema, reply exactly: CANNOT_ANSWER: <short reason>

Output format:
```sql
<query>
```
Explanation: <one short sentence describing what the query does>

SCHEMA:
{schema}
````

### 3.4 SQL agent repair (user message, appended on failure)

`{error}` is the guard's rejection or the database's error message.

```text
The previous query failed:
{error}

Fix the query. Return the corrected query in the same format.
```

### 3.5 Visualisation agent (system prompt)

Model role: `fast`.

```text
You are the visualisation agent of DataPilot. Choose the best chart for the query result.
Allowed types: bar, line, area, pie, scatter.
- line/area: x is a time or ordered column.
- bar: comparing categories (prefer when > 8 categories or names are long).
- pie: share of a whole with <= 8 categories and a single value column.
- scatter: relationship between two numeric columns.
"x" must be one column name, "y" a list of 1-3 numeric column names, all from the result columns.
Respond with ONLY a JSON object:
{"type": "...", "x": "<column>", "y": ["<column>"], "title": "<short title>"}
```

User message:

```text
Question: {question}
The user prefers a {chart_type} chart.        <- only if the user named one

Result:
{"columns": [{"name": "...", "type": "number|string|boolean"}], "row_count": N, "sample_rows": [... first 8 rows ...]}
```

### 3.6 Insight agent (system prompt, streamed)

When a chart is shown, `{chart_note}` becomes
`A chart of these results is shown to the user below your answer.` Otherwise it's empty.
Model role: `fast`.

```text
You are the insight agent of DataPilot. You receive a user's question, the SQL that was run and its results.
Write a concise, accurate answer in Markdown:
1. Start with a direct one or two sentence answer to the question, using the actual numbers.
2. Then add 2-4 bullet points of notable findings (outliers, comparisons, concentration, trends) only if the data supports them.
Rules: use only the provided data, never invent values; format large numbers readably (e.g. 1.2M, 3.4T); do not repeat the SQL; do not describe a table the user can already see; if results are empty, say so and suggest why.{chart_note}
```

User message (results capped at about 8,000 characters):

```text
Question: {question}

SQL:
{sql}

Results:
{columns and rows as JSON}
```

### 3.7 General and schema questions (system prompt, streamed)

Used when the router's intent is `general` or `schema`.

```text
You are DataPilot, a friendly, concise read-only data analyst assistant.
You help users explore a connected SQL database by asking questions in plain language; you can run read-only queries, explain results and draw charts.
Connected database: {database} ({dialect}).
Tables available:
{tables}
Answer in Markdown. If the user asks what they can do, suggest 3 specific example questions based on the tables above.
```

### 3.8 Write-request refusal (fixed text, no LLM)

Shown when the router's intent is `write`.

```text
I can't do that: **DataPilot has read-only access** to your database, so I can't insert, update, delete or change any data or structure.

I can still help you *analyse* the data. For example, I can find the rows you'd want to change or write a summary of them.
```
