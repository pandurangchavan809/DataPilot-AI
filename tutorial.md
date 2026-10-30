# DataPilot AI Configuration Tutorial

How to configure DataPilot: add API keys, offer 4–5 models in the model picker, assign models to
agents, and tune limits. All configuration is plain environment variables, so no code changes
are needed.

---

## 1. Which `.env` file does what?

| File | Used? | Purpose |
|---|---|---|
| `backend/.env` | **Yes, the main one** | API keys, models, limits, sessions. Everything below lives here. Never committed (gitignored). |
| `backend/.env.example` | Template | Documented copy of every setting with safe defaults. Committed. Copy it to create `backend/.env`. |
| `frontend/.env` | Optional | Only needed when the frontend and backend are hosted on **different domains**. Holds no secrets. |
| `frontend/.env.example` | Template | Shows the one frontend setting, `VITE_API_BASE_URL`. |
| Root `.env` | **No** | Removed. It belonged to the old Streamlit version. Nothing reads it now. |

Why secrets live only in the backend: the frontend is shipped to the browser, so anything in
`frontend/.env` is visible to every user. **Never put API keys in the frontend.**

### When do you need `frontend/.env`?

| Setup | `VITE_API_BASE_URL` |
|---|---|
| Local dev (`npm run dev`) | empty: Vite forwards `/api` to `localhost:5000` |
| Docker Compose | empty: nginx forwards `/api` to the backend |
| Frontend on Vercel/Netlify, backend on Render (separate domains) | `https://your-backend.onrender.com` |

For the separate-domains case, also add the frontend's address to `CORS_ORIGINS` in
`backend/.env`, for example `CORS_ORIGINS=https://your-app.vercel.app`. `VITE_` variables are
read **at build time**, so rebuild the frontend after changing them.

---

## 2. Add your Nebius (and OpenAI) API keys

Open `backend/.env` and fill in the keys:

```env
NEBIUS_API_KEY=your-nebius-token-factory-key
GEMINI_API_KEY=your-gemini-key          # already filled in
OPENAI_API_KEY=your-openai-key          # optional
```

Rules:

- A provider is **enabled only when its key is set**. Leave a key empty to switch that provider off.
  Its models disappear from the picker, and agents skip it automatically.
- No quotes or spaces are needed around values.
- **Restart the backend** after any change. Settings are read once at startup.

Where to get the keys:

- **Nebius Token Factory:** tokenfactory.nebius.com → API keys
- **Gemini:** aistudio.google.com → Get API key
- **OpenAI:** platform.openai.com → API keys

---

## 3. Model names: the `provider:model` format

Every model is written as **`provider:model-id`**. The part before the first `:` is the provider,
and the rest is the exact model ID that the provider's API expects:

```
nebius:nvidia/Llama-3_3-Nemotron-Super-49B-v1_5
gemini:gemini-2.5-flash
openai:gpt-4.1
```

The UI shows the last part as the label (`Llama-3_3-Nemotron-Super-49B-v1_5`) and groups models
by provider.

> **Copy model IDs exactly from the provider's catalog.** IDs are case-sensitive. A typo only
> shows up as an error when that model is called. For Nebius, open the Token Factory model
> catalog, click a model and copy its ID. The Nebius IDs in this tutorial are examples, so check
> them against your catalog.

---

## 4. Offer 4–5 models in the model picker

`LLM_AVAILABLE_MODELS` is the list users can choose from in the header's model picker. It's
comma-separated, all on **one line** with no spaces:

```env
LLM_AVAILABLE_MODELS=nebius:nvidia/Llama-3_3-Nemotron-Super-49B-v1_5,nebius:meta-llama/Llama-3.3-70B-Instruct,nebius:Qwen/Qwen3-235B-A22B,gemini:gemini-2.5-flash,openai:gpt-4.1
```

That gives five models: three on Nebius, one on Gemini and one on OpenAI. Notes:

- The models in the role settings (section 5) are **always added** to the list, even if you don't
  repeat them here.
- Models whose provider has no key are hidden automatically.
- The picker always has **Auto** at the top. Auto uses the role setup from section 5. Picking a
  specific model makes *every* agent use that model for that chat.
- Users can only pick models from this list. The backend rejects anything else.

**Nemotron-only setup** (for example, small / medium / large):

```env
LLM_AVAILABLE_MODELS=nebius:nvidia/NVIDIA-Nemotron-Nano-9B-v2,nebius:nvidia/Llama-3_3-Nemotron-Super-49B-v1_5,nebius:nvidia/Llama-3_1-Nemotron-Ultra-253B-v1
```

---

## 5. Decide which model each agent uses (roles)

DataPilot has four roles. Each points to one model:

```env
LLM_PRIMARY=nebius:nvidia/Llama-3_3-Nemotron-Super-49B-v1_5   # default for everything
LLM_SECONDARY=gemini:gemini-2.5-flash                         # fallback if a call fails
LLM_REASONING=nebius:nvidia/Llama-3_3-Nemotron-Super-49B-v1_5 # SQL agent (write + repair SQL)
LLM_FAST=gemini:gemini-2.5-flash                              # router, table picker, charts, insight
```

| Role | Used by | Pick a model that is… |
|---|---|---|
| `LLM_REASONING` | SQL agent | best at SQL / reasoning. This matters most for accuracy. |
| `LLM_FAST` | Router, schema agent, viz agent, insight writer | fast and cheap. These calls are frequent and simple. |
| `LLM_PRIMARY` | Default when a role is empty, and second in the fallback chain | your best all-rounder |
| `LLM_SECONDARY` | Fallback | a **different provider** from primary, so one provider outage doesn't stop the app |

`LLM_REASONING` and `LLM_FAST` are optional; if empty, they use `LLM_PRIMARY`.

**Fallback order** for each call: the role's model (or the user's pick) → primary → secondary.
Duplicate models and providers without keys are skipped.

### Ready-made recipes

**All Nebius, with Gemini as a safety net:**

```env
LLM_PRIMARY=nebius:nvidia/Llama-3_3-Nemotron-Super-49B-v1_5
LLM_REASONING=nebius:nvidia/Llama-3_3-Nemotron-Super-49B-v1_5
LLM_FAST=nebius:meta-llama/Llama-3.3-70B-Instruct
LLM_SECONDARY=gemini:gemini-2.5-flash
```

**Cheapest setup:**

```env
LLM_PRIMARY=gemini:gemini-2.5-flash
LLM_FAST=gemini:gemini-2.5-flash
LLM_REASONING=nebius:nvidia/Llama-3_3-Nemotron-Super-49B-v1_5
LLM_SECONDARY=openai:gpt-4o-mini
```

**Highest accuracy:**

```env
LLM_PRIMARY=openai:gpt-4.1
LLM_REASONING=gemini:gemini-2.5-pro
LLM_FAST=gemini:gemini-2.5-flash
LLM_SECONDARY=nebius:nvidia/Llama-3_3-Nemotron-Super-49B-v1_5
```

---

## 6. Add a new provider (Groq, Together, OpenRouter, a local Ollama…)

Any service with an **OpenAI-compatible** API works. You need three lines plus a model:

```env
LLM_PROVIDERS=nebius,gemini,openai,openrouter        # 1. add the name

OPENROUTER_API_KEY=your-key                           # 2. <NAME>_API_KEY
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1      # 3. <NAME>_BASE_URL

LLM_AVAILABLE_MODELS=...,openrouter:anthropic/claude-sonnet-4.5   # 4. use it
```

The name in `LLM_PROVIDERS` must match the variable prefix: `openrouter` → `OPENROUTER_`.

For a local Ollama, use `OLLAMA_BASE_URL=http://localhost:11434/v1` and any non-empty key, such as
`OLLAMA_API_KEY=ollama`.

---

## 7. Other settings you may want to change

All of these are in `backend/.env`:

| Setting | Default | What it does |
|---|---|---|
| `LLM_TEMPERATURE` | `0.1` | Higher values give more creative output. Keep it low for SQL. |
| `LLM_MAX_TOKENS` | `4096` | Maximum length of each model reply. Reasoning models need room to think. |
| `LLM_TIMEOUT_SECONDS` | `60` | Time before a model call gives up and falls back. |
| `MAX_SQL_RETRIES` | `2` | How many times the SQL agent may fix its own failed query. |
| `SCHEMA_FULL_CONTEXT_MAX_TABLES` | `15` | Above this many tables, the schema agent picks the relevant ones. |
| `SCHEMA_SAMPLE_ROWS` | `3` | Example rows shown to the SQL agent per table. |
| `CHAT_HISTORY_TURNS` | `6` | Previous messages used for follow-up questions. |
| `QUERY_ROW_LIMIT` | `1000` | Maximum rows returned per query. |
| `QUERY_TIMEOUT_SECONDS` | `15` | Database query time limit. |
| `ALLOWED_DB_TYPES` | `sqlite_demo,postgresql,mysql` | Remove one to hide it from the Connect dialog. |
| `RATE_LIMIT` | `30/minute` | Requests allowed per IP address. |
| `SESSION_TTL_MINUTES` | `60` | Idle time before a database connection is forgotten. |
| `CORS_ORIGINS` | `http://localhost:5173` | Frontend addresses allowed to call the API. |
| `SECRET_KEY` | (random) | Encrypts session credentials. Use a long random value and keep it private. |

Production-only settings, which Docker Compose already sets for you:
`APP_ENV=production`, `SESSION_BACKEND=redis`, `REDIS_URL`, `RATE_LIMIT_STORAGE_URI`,
`PROXY_FIX_HOPS=1`.

---

## 8. Apply and verify

1. Save `backend/.env`.
2. Restart the backend: stop `python wsgi.py` and start it again, or run `docker compose up -d --build`.
3. Check which models are active:

   ```bash
   curl http://localhost:5000/api/config
   ```

   `models` lists what the picker will show. Each model's `roles` field shows which roles it fills
   (primary, reasoning…). If a model is missing, its provider's API key is probably empty.
4. Reload the browser, open the model picker, choose a model and ask a demo question. The model
   badge under the answer shows which model actually answered.

### Troubleshooting

| Symptom | Likely cause |
|---|---|
| Model missing from the picker | The provider's `*_API_KEY` is empty, or the provider isn't in `LLM_PROVIDERS` |
| Answer badge shows the fallback model | The chosen model failed: wrong model ID, no credits, or a rate limit. Check the backend logs. |
| `Model '…' is not available` | The UI asked for a model not in `LLM_AVAILABLE_MODELS` or a role. Reload the page after a config change. |
| Settings change has no effect | The backend wasn't restarted, or a real environment variable is overriding `.env` |
| CORS error in the browser console | Add the frontend's URL to `CORS_ORIGINS` |
