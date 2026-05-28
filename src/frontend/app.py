import requests
import streamlit as st

API_BASE = st.secrets.get("api_base", "http://localhost:8000")


def build_connection_payload():
    # Default SQLite demo database
    return {
        "connection_type": "sqlite",
        "path": "./data/top50_countries.db"
    }


def fetch_schema(payload):
    response = requests.post(
        f"{API_BASE}/api/schema",
        json=payload,
        timeout=30
    )

    response.raise_for_status()
    return response.json()


def generate_sql(payload, natural_language):
    request_payload = {
        **payload,
        "natural_language": natural_language,
        "query": ""
    }

    response = requests.post(
        f"{API_BASE}/api/generate",
        json=request_payload,
        timeout=60
    )

    response.raise_for_status()
    return response.json()


def execute_sql(payload, sql):
    request_payload = {
        **payload,
        "query": sql
    }

    response = requests.post(
        f"{API_BASE}/api/execute",
        json=request_payload,
        timeout=60
    )

    response.raise_for_status()
    return response.json()


def main():
    st.set_page_config(
        page_title="DataPilot AI",
        layout="wide"
    )

    st.title("🌍 DataPilot AI — Autonomous NL2SQL Assistant")

    st.markdown("""
    Query a rich database of the world's top 50 countries using natural language.

    ### Example Questions
    - Which countries have the highest GDP growth?
    - Show top Asian countries by literacy rate
    - Compare inflation rates between India and USA
    - Which countries have highest tourism revenue?
    - List countries with internet usage above 90%
    """)

    payload = build_connection_payload()

    # Sidebar
    st.sidebar.title("📊 Database Browser")

    if st.sidebar.button("Load Database Schema"):
        try:
            schema_response = fetch_schema(payload)

            st.sidebar.success("Schema Loaded Successfully")

            st.sidebar.markdown("### Tables")

            for table in schema_response["schema"]:
                st.sidebar.markdown(
                    f"**{table['table']}**"
                )

                st.sidebar.caption(
                    f"Columns: {', '.join(table['columns'])}"
                )

            st.session_state.schema_text = schema_response.get(
                "schema_text",
                ""
            )

        except Exception as exc:
            st.sidebar.error(f"Schema fetch failed: {exc}")

    # NL to SQL
    st.header("🧠 Natural Language to SQL")

    prompt = st.text_area(
        "Enter your query in plain English:",
        height=120,
        placeholder="Example: Show top 5 countries by GDP growth"
    )

    if st.button("Generate SQL") and prompt:
        try:
            generation = generate_sql(payload, prompt)

            st.session_state.generated_sql = generation["sql"]

            st.success("SQL Generated Successfully")

        except Exception as exc:
            st.error(f"SQL generation failed: {exc}")

    # Display Generated SQL
    if st.session_state.get("generated_sql"):
        st.subheader("Generated SQL")

        st.code(
            st.session_state.generated_sql,
            language="sql"
        )

    # Execute SQL
    st.header("⚡ Execute SQL Query")

    sql_query = st.text_area(
        "SQL Query",
        value=st.session_state.get("generated_sql", ""),
        height=160
    )

    if st.button("Run Query") and sql_query:
        try:
            result = execute_sql(payload, sql_query)

            if result.get("columns"):
                st.success("Query Executed Successfully")

                st.dataframe(result["rows"])

            else:
                st.success(
                    f"Rows affected: {result.get('rows_affected')}"
                )

        except requests.HTTPError as exc:
            st.error(
                f"Query execution failed: {exc.response.text}"
            )

        except Exception as exc:
            st.error(f"Query execution failed: {exc}")

    # Footer
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "Built with ❤️ using FastAPI, LangChain, Gemini API, and SQLite"
    )


if __name__ == "__main__":
    main()