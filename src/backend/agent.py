from __future__ import annotations

import google.generativeai as genai

from .config import settings
from .db import inspect_schema


genai.configure(api_key=settings.gemini_api_key)


def build_prompt(schema_text: str, user_query: str) -> str:
    return f"""
You are an expert SQL query generator.

DATABASE SCHEMA:
{schema_text}

TASK:
Convert the user request into valid SQLite SQL.

RULES:
- Return ONLY SQL
- No markdown
- No explanation
- No comments
- Use valid SQLite syntax

USER QUERY:
{user_query}
"""


def generate_sql_from_prompt(engine, natural_language: str) -> dict:
    try:
        schema = inspect_schema(engine)

        schema_text = ""

        for table, columns in schema.items():
            column_names = ", ".join(
                [column["name"] for column in columns]
            )

            schema_text += f"\nTable {table}: {column_names}"

        prompt = build_prompt(
            schema_text,
            natural_language
        )

        model = genai.GenerativeModel(
            settings.gemini_model_name
        )

        response = model.generate_content(prompt)

        sql_query = response.text.strip()

        sql_query = (
            sql_query
            .replace("```sql", "")
            .replace("```", "")
            .strip()
        )

        return {
            "sql": sql_query
        }

    except Exception as exc:
        raise RuntimeError(
            f"Failed to generate SQL: {str(exc)}"
        )