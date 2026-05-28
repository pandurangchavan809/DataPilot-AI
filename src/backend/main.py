from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .agent import generate_sql_from_prompt
from .config import settings
from .db import build_connection_url, execute_sql, get_engine, inspect_schema
from .schema_utils import format_schema, build_schema_prompt

app = FastAPI(
    title="DataPilot AI",
    description="AI-powered NL2SQL assistant for SQLite demo and external MySQL databases.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectionPayload(BaseModel):
    connection_type: str
    database: str | None = None
    user: str | None = None
    password: str | None = None
    host: str | None = "localhost"
    port: int | None = 3306
    path: str | None = None


class SQLRequest(BaseModel):
    connection_type: str
    query: str
    database: str | None = None
    user: str | None = None
    password: str | None = None
    host: str | None = "localhost"
    port: int | None = 3306
    path: str | None = None


class GenerateRequest(SQLRequest):
    natural_language: str


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/api/schema")
async def schema(connection: ConnectionPayload):
    try:
        connection_url = build_connection_url(connection.connection_type, connection.dict())
        engine = get_engine(connection_url)
        raw_schema = inspect_schema(engine)
        return {"schema": format_schema(raw_schema), "schema_text": build_schema_prompt(raw_schema)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/generate")
async def generate(request: GenerateRequest):
    try:
        connection_url = build_connection_url(request.connection_type, request.dict())
        engine = get_engine(connection_url)
        return generate_sql_from_prompt(engine, request.natural_language)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/execute")
async def execute(request: SQLRequest):
    try:
        connection_url = build_connection_url(request.connection_type, request.dict())
        engine = get_engine(connection_url)
        return execute_sql(engine, request.query)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/correct")
async def correct(request: SQLRequest):
    try:
        connection_url = build_connection_url(request.connection_type, request.dict())
        engine = get_engine(connection_url)
        corrected = generate_sql_from_prompt(engine, f"The previous SQL failed. Correct this query: {request.query}")
        result = execute_sql(engine, corrected["sql"])
        return {"corrected_sql": corrected["sql"], "result": result}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
