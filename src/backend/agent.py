from __future__ import annotations

from typing import Any

from .config import settings


def _import_langchain_components() -> dict[str, Any]:
    try:
        import inspect

        from langchain.agents import create_sql_agent
        from langchain.llms import VertexAI
        from langchain.sql_database import SQLDatabase
        from langchain.agents.agent_toolkits import SQLDatabaseToolkit

        return {
            "create_sql_agent": create_sql_agent,
            "VertexAI": VertexAI,
            "SQLDatabase": SQLDatabase,
            "SQLDatabaseToolkit": SQLDatabaseToolkit,
            "inspect": inspect,
        }
    except Exception as exc:
        raise RuntimeError(
            "LangChain or required LLM integrations are not installed or failed to import.\n"
            "Install `langchain` and configure Gemini/Vertex compatibly. Original error: "
            f"{exc}"
        )


def build_llm():
    components = _import_langchain_components()
    VertexAI = components["VertexAI"]
    inspect = components["inspect"]

    kwargs: dict[str, Any] = {"model_name": settings.gemini_model_name}
    if settings.gemini_api_key:
        signature = inspect.signature(VertexAI)
        if "api_key" in signature.parameters:
            kwargs["api_key"] = settings.gemini_api_key
    return VertexAI(**kwargs)


def create_sql_agent_for_engine(engine):
    components = _import_langchain_components()
    SQLDatabase = components["SQLDatabase"]
    SQLDatabaseToolkit = components["SQLDatabaseToolkit"]
    create_sql_agent = components["create_sql_agent"]

    db = SQLDatabase(engine)
    toolkit = SQLDatabaseToolkit(db=db)
    llm = build_llm()
    return create_sql_agent(llm=llm, toolkit=toolkit, verbose=False)


def generate_sql_from_prompt(engine, natural_language: str) -> dict:
    agent = create_sql_agent_for_engine(engine)
    prompt = (
        "Generate a SQL query for the user request, using the database schema. "
        "Only return the raw SQL query without explanation.\n" + natural_language
    )
    # Some agents return a string; keep behavior consistent
    response = agent.run(prompt)
    return {"sql": str(response)}
