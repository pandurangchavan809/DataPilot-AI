# DataPilot AI

An AI-powered Natural Language to SQL assistant for relational databases.

## Overview

DataPilot AI lets users query external MySQL databases or a built-in SQLite demo dataset using plain English. The platform includes:

- Streamlit frontend for conversational query input
- FastAPI backend for schema extraction, SQL generation, execution, and error correction
- LangChain SQL agent with Gemini/Vertex AI integration
- Demo SQLite database for easy testing and evaluation

## Features

- Natural Language to SQL conversion
- Dynamic database connection via credentials
- Automatic schema discovery
- Context-aware SQL generation
- Query execution and results display
- Automated SQL correction for failed execution
- Built-in SQLite demo dataset

## Folder structure

- `src/backend/` – FastAPI application, database utilities, AI agent orchestration
- `src/frontend/` – Streamlit UI
- `src/data/` – demo database initialization and schema files
- `src/data/init_top50_countries_db.py` – generates a Top 50 Countries SQLite dataset
- `src/data/top50_countries_schema.sql` – schema definition for the dataset

## Getting Started

Recommended workflow:

1. Create a virtual environment.
2. Activate the environment.
3. Install dependencies.
4. Create a `.env` file with `GEMINI_API_KEY` and `GEMINI_MODEL_NAME`.
5. Initialize the demo SQLite database.
6. Start the FastAPI backend.
7. Start the Streamlit frontend.

### Commands

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
rem edit .env and add your GEMINI_API_KEY
python src/data/init_demo_db.py
uvicorn src.backend.main:app --host 0.0.0.0 --port 8000 --reload
streamlit run src/frontend/app.py
```

### Deploy to Streamlit Cloud

1. Push the repo to GitHub.
2. Connect the repo in Streamlit Cloud.
3. Add `GEMINI_API_KEY` and `GEMINI_MODEL_NAME` as Streamlit secrets.
4. Set the main file to `src/frontend/app.py`.
5. If using a backend, deploy the FastAPI service separately and point the frontend to it.

## Environment

Create a `.env` file with your Gemini API key and the model name you want to use.

```env
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL_NAME=gemini-2.5-flash
```

> Use `GEMINI_API_KEY` for Gemini key-based auth instead of service account credentials.

## Notes

- `src/data/init_demo_db.py` creates `data/demo.db`.
- Use built-in demo mode or connect to a MySQL database with credentials.
