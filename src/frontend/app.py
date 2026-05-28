import requests
import streamlit as st
import pandas as pd

API_BASE = "http://localhost:8000"


def build_connection_payload():
    """
    Build dynamic database connection payload.
    """

    db_type = st.session_state.get(
        "db_type",
        "SQLite Demo"
    )

    if db_type == "SQLite Demo":

        return {
            "connection_type": "sqlite",
            "path": "src/data/top50_countries.db"
        }

    return {
        "connection_type": "mysql",
        "host": st.session_state.get("host"),
        "port": int(st.session_state.get("port")),
        "user": st.session_state.get("user"),
        "password": st.session_state.get("password"),
        "database": st.session_state.get("database"),
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


def correct_sql(payload, sql):

    request_payload = {
        **payload,
        "query": sql
    }

    response = requests.post(
        f"{API_BASE}/api/correct",
        json=request_payload,
        timeout=60
    )

    response.raise_for_status()

    return response.json()


def initialize_session_state():

    if "schema_text" not in st.session_state:
        st.session_state.schema_text = ""

    if "generated_sql" not in st.session_state:
        st.session_state.generated_sql = ""

    if "query_results" not in st.session_state:
        st.session_state.query_results = None


def main():

    st.set_page_config(
        page_title="DataPilot AI",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    initialize_session_state()

    st.title(
        "DataPilot AI — Autonomous NL2SQL Assistant"
    )

    st.markdown("""
    Query databases using natural language.

    Example Questions:
    - Which countries have the highest GDP growth?
    - Show top Asian countries by literacy rate
    - Compare inflation rates between India and USA
    - Which countries have highest tourism revenue?
    - List countries with internet usage above 90%
    """)

    st.sidebar.title("Database Connection")

    db_type = st.sidebar.radio(
        "Select Database",
        [
            "SQLite Demo",
            "MySQL Cloud Database"
        ],
        key="db_type"
    )

    if db_type == "SQLite Demo":

        st.sidebar.success(
            "Using built-in Top 50 Countries dataset"
        )

    else:

        st.sidebar.text_input(
            "Host",
            placeholder="mysql.example.com",
            key="host"
        )

        st.sidebar.text_input(
            "Port",
            value="3306",
            key="port"
        )

        st.sidebar.text_input(
            "Username",
            key="user"
        )

        st.sidebar.text_input(
            "Password",
            type="password",
            key="password"
        )

        st.sidebar.text_input(
            "Database Name",
            key="database"
        )

    payload = build_connection_payload()

    if st.sidebar.button("Load Database Schema"):

        try:

            with st.spinner("Loading schema..."):

                schema_response = fetch_schema(
                    payload
                )

            st.sidebar.success(
                "Database Connected Successfully"
            )

            st.sidebar.markdown(
                "### Tables"
            )

            for table in schema_response["schema"]:

                st.sidebar.markdown(
                    f"Table: {table['table']}"
                )

                st.sidebar.caption(
                    f"Columns: {', '.join(table['columns'])}"
                )

            st.session_state.schema_text = (
                schema_response.get(
                    "schema_text",
                    ""
                )
            )

        except Exception as exc:

            st.sidebar.error(
                f"Database connection failed: {str(exc)}"
            )

    st.sidebar.markdown("---")

    st.sidebar.markdown(
        "### Technology Stack"
    )

    st.sidebar.markdown("""
    Frontend: Streamlit

    Backend: FastAPI

    LLM: Gemini API

    Database: SQLite / MySQL

    AI Layer: Prompt-based NL2SQL
    """)

    st.sidebar.markdown("---")

    st.sidebar.markdown(
        "Built with love using FastAPI, Gemini API, and Streamlit"
    )

    st.header(
        "Natural Language to SQL"
    )

    col1, col2 = st.columns([3, 1])

    with col1:

        prompt = st.text_area(
            "Enter your query in plain English:",
            height=120,
            placeholder="Example: Show top 5 countries by GDP growth"
        )

    with col2:

        st.write("")
        st.write("")

        generate_btn = st.button(
            "Generate SQL"
        )

    if generate_btn and prompt:

        try:

            with st.spinner(
                "Generating SQL..."
            ):

                generation = generate_sql(
                    payload,
                    prompt
                )

            st.session_state.generated_sql = (
                generation.get(
                    "sql",
                    ""
                )
            )

            st.success(
                "SQL Generated Successfully"
            )

        except Exception as exc:

            st.error(
                f"SQL generation failed: {str(exc)}"
            )

    if st.session_state.get(
        "generated_sql"
    ):

        st.subheader(
            "Generated SQL Query"
        )

        st.code(
            st.session_state.generated_sql,
            language="sql"
        )

    st.header(
        "Execute SQL Query"
    )

    sql_query = st.text_area(
        "SQL Query to Execute:",
        value=st.session_state.get(
            "generated_sql",
            ""
        ),
        height=160
    )

    col1, col2 = st.columns(2)

    with col1:

        execute_btn = st.button(
            "Run Query"
        )

    with col2:

        correct_btn = st.button(
            "Correct Query"
        )

    if execute_btn and sql_query:

        try:

            with st.spinner(
                "Executing query..."
            ):

                result = execute_sql(
                    payload,
                    sql_query
                )

            st.session_state.query_results = result

            if result.get("columns"):

                st.success(
                    "Query Executed Successfully"
                )

                df = pd.DataFrame(
                    result["rows"]
                )

                st.dataframe(
                    df,
                    use_container_width=True
                )

                csv = df.to_csv(
                    index=False
                )

                st.download_button(
                    label="Download Results as CSV",
                    data=csv,
                    file_name="query_results.csv",
                    mime="text/csv"
                )

            else:

                rows_affected = result.get(
                    "rows_affected",
                    0
                )

                st.success(
                    f"Rows affected: {rows_affected}"
                )

        except Exception as exc:

            st.error(
                f"Query execution failed: {str(exc)}"
            )

    if correct_btn and sql_query:

        try:

            with st.spinner(
                "Correcting query..."
            ):

                result = correct_sql(
                    payload,
                    sql_query
                )

            st.session_state.generated_sql = (
                result.get(
                    "corrected_sql",
                    ""
                )
            )

            st.success(
                "Query Corrected Successfully"
            )

            st.code(
                st.session_state.generated_sql,
                language="sql"
            )

            if result.get("result", {}).get("columns"):

                df = pd.DataFrame(
                    result["result"]["rows"]
                )

                st.dataframe(
                    df,
                    use_container_width=True
                )

        except Exception as exc:

            st.error(
                f"Query correction failed: {str(exc)}"
            )


if __name__ == "__main__":
    main()
