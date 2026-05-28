from __future__ import annotations

import google.generativeai as genai

from .config import settings
from .db import inspect_schema


genai.configure(
    api_key=settings.gemini_api_key
)


def build_prompt(
    schema_text: str,
    user_query: str
) -> str:
    """
    Build schema-aware SQL generation prompt.
    """

    return f"""
You are an expert SQL query generator.

DATABASE SCHEMA:
{schema_text}

TASK:
Convert the user request into valid SQL.

RULES:
- Return ONLY raw SQL
- No markdown
- No explanation
- No comments
- Use correct table names
- Use correct column names
- Generate optimized SQL

USER QUERY:
{user_query}
"""


def generate_sql_from_prompt(
    engine,
    natural_language: str
) -> dict:
    """
    Generate SQL query from natural language.
    """

    try:

        schema = inspect_schema(engine)

        schema_text = ""

        for table, columns in schema.items():

            column_names = [
                col["name"]
                for col in columns
            ]

            schema_text += (
                f"Table {table}: "
                f"{', '.join(column_names)}\n"
            )

        prompt = build_prompt(
            schema_text,
            natural_language
        )

        model = genai.GenerativeModel(
            settings.gemini_model_name
        )

        response = model.generate_content(
            prompt
        )

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