# DataPilot AI Configuration Tutorial

How to add API keys, choose which models users can pick, and set the model order for **Auto**.
All of it is done in `.env` files, with no code changes.

---

## 1. The two `.env` files

| File | Belongs to | What goes in it | Committed? |
|---|---|---|---|
| `.env` (repo root) | Backend (Flask) | API keys, models, `SECRET_KEY`, allowed frontend URL | **No** (gitignored) |
| `.env.example` (repo root) | Template | Same keys with empty values. Copy it to make `.env`. | Yes |
| `frontend/.env` | Frontend (React) | Only the backend URL, `VITE_API_BASE_URL` | **No** (gitignored) |
| `frontend/.env.example` | Template | The same single line | Yes |

**Never put API keys in `frontend/.env`.** Everything in it is built into the JavaScript that every
user downloads.

The two files must point at each other:

```env
# frontend/.env : where the backend is
VITE_API_BASE_URL=http://localhost:5000

# .env (root) : which frontend may call the backend (CORS)
CORS_ORIGINS=http://localhost:5173
```

In production, replace both with the real URLs, for example
`VITE_API_BASE_URL=https://api.myapp.com` and `CORS_ORIGINS=https://myapp.com`.
`VITE_API_BASE_URL` is read at **build time**, so rebuild the frontend after changing it.

---

## 2. The backend `.env`, line by line

```env
APP_ENV=development                 # use "production" when deployed
SECRET_KEY=a-long-random-string     # encrypts DB passwords and signs login tokens; keep it secret
CORS_ORIGINS=http://localhost:5173  # frontend URL(s), comma-separated

NEBIUS_API_KEY=                     # empty = provider switched off
NEBIUS_MODELS=nvidia/Nemotron-3_5-Lightning

GEMINI_API_KEY=
GEMINI_MODELS=gemini-3.5-flash

OPENAI_API_KEY=
OPENAI_MODELS=gpt-4.1

LLM_PRIMARY=nebius:nvidia/Nemotron-3_5-Lightning
LLM_SECONDARY=gemini:gemini-3.5-flash
```

That's all you normally touch. **Restart the backend after every change**, because settings are
read once at startup.

---

## 3. Add your Nebius key

```env
NEBIUS_API_KEY=your-nebius-token-factory-key
```

A provider is **on only when its key is set**. If you leave `OPENAI_API_KEY` empty, OpenAI's models
are hidden from the picker and never called.

Where to get keys:

- **Nebius Token Factory:** tokenfactory.nebius.com → API keys
- **Gemini:** aistudio.google.com → Get API key
- **OpenAI:** platform.openai.com → API keys

---

## 4. Choose the models users can pick (4–5 models)

Each provider has a `_MODELS` line: a comma-separated list of model IDs, with no spaces and no
provider prefix. The picker in the app header shows all of them, grouped by provider.

**Example: the current setup, four models**

```env
NEBIUS_MODELS=nvidia/Nemotron-3_5-Lightning,Qwen/Qwen3-235B-A22B-Instruct-2507
GEMINI_MODELS=gemini-3.5-flash
OPENAI_MODELS=gpt-4.1
```

> Copy model IDs **exactly** from the provider's catalog (on Nebius, it's the "Routing key"); they
> are case-sensitive. A wrong ID only shows up as an
> error when that model is used.

---

## 5. How "Auto" picks a model

The picker's default option is **Auto**. It uses:

1. `LLM_PRIMARY` for every agent.
2. `LLM_SECONDARY` if the primary fails (error, rate limit, outage).

Both are written as `provider:model`:

```env
LLM_PRIMARY=nebius:nvidia/Nemotron-3_5-Lightning
LLM_SECONDARY=gemini:gemini-3.5-flash
```

Tips:

- Put the secondary on a **different provider** from the primary, so one outage doesn't stop the app.
- Primary and secondary always appear in the picker, even if they aren't in a `_MODELS` list.
- If a user picks a specific model instead of Auto, that model is used first, then primary, then
  secondary as fallbacks.

---

## 6. Optional settings (not in `.env` by default)

Every setting has a default in `app/config.py`. Add a line to `.env` only to change one.

| Setting | Default | What it does |
|---|---|---|
| `LLM_REASONING` | primary | Separate model for the SQL agent, e.g. a stronger model |
| `LLM_FAST` | primary | Separate model for the other agents, e.g. a cheaper model |
| `LLM_TEMPERATURE` | `0.1` | Creativity. Keep it low for SQL. |
| `LLM_MAX_TOKENS` | `4096` | Maximum length of each model reply |
| `LLM_TIMEOUT_SECONDS` | `60` | How long to wait before falling back |
| `MAX_SQL_RETRIES` | `2` | How many times the SQL agent may fix its own failed query |
| `QUERY_ROW_LIMIT` | `1000` | Maximum rows returned per query |
| `QUERY_TIMEOUT_SECONDS` | `15` | Database query time limit |
| `RATE_LIMIT` | `30/minute` | Requests allowed per IP address |
| `SESSION_TTL_MINUTES` | `60` | Idle time before a DB connection is forgotten |
| `DEMO_USER_EMAIL` / `DEMO_USER_PASSWORD` | `user` / `User@1234` | Demo login created on start. Set `DEMO_USER_EMAIL=` (empty) to turn it off. |
| `ACCESS_TOKEN_MINUTES` / `REFRESH_TOKEN_DAYS` | `15` / `7` | How long login tokens last |
| `JWT_SECRET_KEY` | `SECRET_KEY` | Separate key for signing tokens. Changing it logs everyone out. |
| `AUTH_DB_PATH` | `auth/auth.db` | Where user accounts are stored |
| `<NAME>_BASE_URL` | built in | Override a provider's API URL |
| `SESSION_BACKEND`, `REDIS_URL`, `RATE_LIMIT_STORAGE_URI`, `PROXY_FIX_HOPS` | memory | Production with several workers: switch to Redis (see the commented lines in `.env.example`) |

### Adding another provider (OpenRouter, Groq, local Ollama…)

Any OpenAI-compatible API works:

```env
LLM_PROVIDERS=nebius,gemini,openai,openrouter
OPENROUTER_API_KEY=your-key
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODELS=anthropic/claude-sonnet-4.5
```

---

## 7. Apply and check

1. Save `.env` and restart the backend (`python wsgi.py`).
2. Open http://localhost:5000/api/config. `models` is exactly what the picker will show, and each
   model's `roles` shows whether it's primary or secondary.
3. Reload the app, pick a model, and ask a demo question. The badge under the answer shows which
   model actually replied.

| Problem | Likely cause |
|---|---|
| A model is missing from the picker | That provider's `_API_KEY` is empty |
| The answer badge shows the secondary model | The primary failed: wrong model ID, no credits, or a rate limit. Check the backend terminal. |
| `Model '…' is not available` | The page was opened before a config change. Reload it. |
| The browser shows a CORS error | `CORS_ORIGINS` in `.env` doesn't match the frontend's URL |
| The frontend can't reach the backend | `VITE_API_BASE_URL` in `frontend/.env` is wrong. Restart `npm run dev` after changing it. |
| A change has no effect | The backend wasn't restarted |
