# DataPilot AI Interview Preparation

This file is a practical interview guide for the **DataPilot AI** project in this repository.

Use it to prepare answers for:

- project explanation
- architecture discussion
- AI and database questions
- frontend and backend choices
- "Why this tech stack?"
- limitations, tradeoffs, and future improvements

## 1. One minute project introduction

If the interviewer says, **"Tell me about your project"**, you can answer:

> DataPilot AI is an AI-powered Natural Language to SQL assistant. It allows a user to ask database questions in plain English, converts that request into SQL using Gemini, executes the SQL on either a built-in SQLite demo database or an external MySQL database, and then shows the results in a Streamlit UI. I built it with a Streamlit frontend, a FastAPI backend, SQLAlchemy for database abstraction and schema inspection, and a prompt-based Gemini integration for SQL generation and correction.

Shorter version:

> It is an NL2SQL application that turns English questions into SQL queries and runs them on relational databases through a simple web interface.

## 2. Problem statement

If the interviewer asks, **"What problem does this solve?"**

Answer:

> Many non-technical users know what business question they want to ask, but they do not know SQL syntax or database structure. DataPilot AI reduces that gap by letting users ask in natural language while the system handles schema discovery, SQL generation, execution, and basic correction.

## 3. Main features in this project

You should be ready to mention these:

- Natural language to SQL generation
- Dynamic database connection
- Support for a built-in SQLite demo database
- Support for external MySQL databases
- Automatic schema inspection
- SQL execution and result display
- SQL correction when execution fails
- CSV download from the frontend

## 4. Architecture explanation

If the interviewer asks, **"Explain the architecture"**

Answer:

> The project is split into two layers. The frontend is built in Streamlit and is responsible for user input, connection selection, showing the generated SQL, running the query, and displaying result tables. The backend is built in FastAPI and exposes APIs for schema extraction, SQL generation, query execution, and query correction. The backend uses SQLAlchemy to create database engines and inspect schemas. Once the schema is extracted, it is converted into prompt context and passed to Gemini, which returns SQL. That SQL is then executed and the result is returned to the frontend.

## 5. End to end flow

If the interviewer asks, **"What happens when a user enters a question?"**

Answer:

1. The user selects either the demo SQLite database or an external MySQL database.
2. The frontend sends the connection payload to the backend.
3. The backend inspects the schema using SQLAlchemy.
4. The schema is formatted into prompt context.
5. The natural language question plus schema context is sent to Gemini.
6. Gemini returns raw SQL.
7. The backend sends the SQL back to the frontend.
8. The user can run the SQL.
9. The backend executes it and returns rows or affected row count.
10. If execution fails, the correction endpoint asks Gemini to rewrite the failed SQL and tries again.

## 6. Project specific interview questions and answers

### Q1. Why did you build this project?

> I wanted to build something that combines AI, backend development, databases, and practical usability. NL2SQL is a good real-world problem because it needs prompt engineering, schema understanding, API design, error handling, and clean UI interaction.

### Q2. What was your role in this project?

> I designed the overall flow, implemented the backend APIs, integrated Gemini for SQL generation, built the Streamlit frontend, added schema inspection and SQL execution logic, and created a demo SQLite dataset so the application can be tested without external infrastructure.

### Q3. Why is schema inspection important in NL2SQL?

> Without schema context, the model can hallucinate table names or columns. By inspecting the live schema first and sending that structure in the prompt, I reduce hallucination and help the model generate more valid SQL.

### Q4. How does the app support multiple databases?

> I abstract database connection creation through a helper that builds different connection URLs based on the selected database type. Right now the app supports SQLite for the local demo and MySQL through SQLAlchemy with the PyMySQL driver.

### Q5. Why did you include a demo SQLite database?

> It removes setup friction. Interviewers, recruiters, or users can test the application immediately without creating a cloud database. It also gives me a controlled dataset for demos and debugging.

### Q6. What tables are in the demo dataset?

> The demo dataset includes `countries`, `economy_stats`, `education_stats`, `tourism_stats`, and `tech_stats`. This structure is useful because it naturally supports joins and analytical questions across multiple domains.

### Q7. How do you generate SQL from natural language?

> I inspect the schema, turn it into a compact text description like table names and columns, then combine that with prompt instructions such as "return only raw SQL" and the user's natural language request. Gemini generates the SQL based on that structured prompt.

### Q8. How do you handle failed SQL queries?

> I added a correction endpoint. If a query fails, the failed SQL is sent back through the same schema-aware generation pipeline with instructions to correct it and return only valid SQL. Then the corrected SQL is executed again.

### Q9. How do you return results to the user?

> The backend executes the SQL using SQLAlchemy, converts each row into a dictionary, and sends the columns and rows as JSON. The Streamlit frontend then converts that to a DataFrame and displays it in a table.

### Q10. How does the frontend keep track of state?

> Streamlit session state stores values like the loaded schema text, generated SQL, and query results. That allows the user to generate a query first, inspect it, and then run or correct it without losing context.

### Q11. What were the biggest technical challenges?

> The main challenges were reducing hallucinated SQL, handling dynamic schemas, supporting more than one database type, and making the flow smooth enough that a user can connect, inspect, generate, run, and correct queries from one interface.

### Q12. How do you reduce hallucination?

> I reduce it mainly through schema-aware prompting. Instead of asking the model to guess the database structure, I provide the actual table and column information from the target database. I also instruct the model to return only SQL and avoid explanation text.

### Q13. Why not let the model query the database directly?

> I wanted stronger control and separation of concerns. The model only generates SQL. The backend controls schema inspection, execution, error handling, and response formatting. That makes the system more auditable and easier to secure.

### Q14. How do you ensure the generated SQL is correct?

> I do not assume the first output is always correct. I validate it by actually executing it. If it fails, the correction flow tries to repair it. In a production version, I would also add SQL parsing, read-only enforcement, and query safety validation before execution.

### Q15. How would you scale this project?

> I would add connection pooling, schema caching, async job handling for long-running queries, request-level authentication, observability, prompt/version tracking, and database-specific adapters for MySQL, PostgreSQL, and SQL Server.

### Q16. How would you make it production ready?

> I would add authentication, role-based access, TLS, secret management, query allowlists or read-only guards, audit logs, rate limiting, structured monitoring, test coverage, and stronger prompt safety around destructive SQL.

### Q17. What are the limitations of the current version?

> The current version is best described as a working prototype. It does not yet include authentication, strict SQL safety controls, advanced query validation, schema caching, full test coverage, or production-grade deployment controls. It also supports only SQLite and MySQL right now.

### Q18. How would you improve SQL safety?

> I would classify queries before execution, allow only `SELECT` in shared environments, block dangerous statements like `DROP`, `DELETE`, or `ALTER` unless explicitly authorized, and parse the SQL with a validator before sending it to the database.

### Q19. Why is this a good AI project and not just a normal CRUD app?

> The difficult part is not storing data, it is translating ambiguous human language into executable database logic while grounding the model on a live schema. That makes it a useful applied AI system rather than a standard form-based application.

### Q20. What did you learn from this project?

> I learned that good AI output depends heavily on context quality, not just model choice. I also learned the importance of separating model generation from execution, building a clear backend contract, and creating a zero-friction demo environment.

## 7. Why this tech stack?

This section is especially useful if the interviewer asks, **"Why did you choose these technologies only?"**

### Why Python?

> Python was the best fit because the project combines backend APIs, AI integration, data handling, and database work. Python has a very strong ecosystem for LLMs, web backends, and data tools, so it let me build the whole system quickly without switching languages.

### Why FastAPI?

> I chose FastAPI because it is lightweight, fast to develop with, and gives automatic request validation through Pydantic. It also provides OpenAPI docs out of the box, which is useful for debugging and backend testing.

If they ask, **"Why FastAPI instead of Flask?"**

> Flask is great, but FastAPI gives stronger type validation, cleaner API modeling, and built-in documentation with less manual setup.

If they ask, **"Why FastAPI instead of Django?"**

> Django is excellent for full-stack business applications, but this project is API-first and AI-driven. I did not need a full ORM, admin panel, or monolithic framework, so FastAPI was a better fit.

### Why Streamlit?

> Streamlit is ideal for rapid prototyping of data and AI applications. I chose it because I wanted a simple interface for query input, generated SQL review, result tables, and CSV export without spending extra time building a custom frontend in React.

If they ask, **"Why not React?"**

> React would give more control and a more polished production UI, but for this project speed of development and data-app usability were more important. Streamlit let me ship the concept faster and focus on the AI and backend logic first.

### Why SQLAlchemy?

> SQLAlchemy gave me a clean abstraction for engine creation, SQL execution, and schema inspection. It helped me support multiple databases more easily than writing database-specific code manually.

If they ask, **"Why not raw database drivers only?"**

> Raw drivers would increase duplicated code and make multi-database support harder. SQLAlchemy gives a cleaner abstraction layer and built-in inspection support.

### Why SQLite and MySQL?

> SQLite was chosen for local demo simplicity because it needs no external server. MySQL was chosen because it is common in real applications, easy to explain in interviews, and useful for showing that the project can work beyond a toy local database.

If they ask, **"Why not PostgreSQL?"**

> PostgreSQL would also be a strong choice and I would support it next. I started with MySQL because it is widely used and simple to demo with SQLAlchemy. The design can be extended to PostgreSQL with an additional driver and connection builder logic.

### Why Gemini?

> Gemini was a strong fit for prompt-based SQL generation because it is easy to integrate, fast enough for interactive use, and capable of following structured instructions like "return only SQL". It also worked well for an affordable prototype.

If they ask, **"Why not OpenAI or Claude?"**

> The project design is model-agnostic at a high level. I chose Gemini based on availability, ease of API integration, and good performance for this use case. In a production version, I would benchmark multiple models on SQL accuracy, latency, and cost before finalizing the choice.

### Why Pydantic and pydantic-settings?

> Pydantic makes request models explicit and reduces runtime errors by validating inputs. `pydantic-settings` makes environment-based configuration cleaner, especially for API keys, ports, and frontend/backend settings.

### Why `requests` in the frontend?

> The frontend only needs a simple HTTP client to call backend APIs. `requests` is lightweight, readable, and enough for this Streamlit-based architecture.

### Why direct Gemini SDK usage instead of a full agent framework?

> In the current implementation, direct SDK usage keeps the flow simple and easier to debug. For this project, I wanted control over the exact prompt and output handling. Agent frameworks are useful when orchestration becomes more complex, but they can add abstraction overhead early on.

## 8. Tough questions an interviewer may ask

### Q1. How do you prevent destructive SQL from running?

Best honest answer:

> In the current version, that is a known limitation. The prototype focuses on SQL generation and execution flow, but production safety would require query classification, read-only restrictions by default, and blocking destructive statements before execution.

### Q2. Why is open CORS not ideal?

> Open CORS is acceptable for quick local development, but it is not appropriate for production because it allows requests from any origin. In production I would restrict origins to trusted frontend domains only.

### Q3. How are database credentials handled?

> For the current prototype, credentials are entered through the UI and sent to the backend so the backend can create a database engine dynamically. In production I would protect that with TLS, authentication, secret management, and stricter tenant isolation.

### Q4. What if the schema is very large?

> A very large schema can create token bloat and hurt accuracy. To solve that, I would add table ranking, schema summarization, query intent classification, and only send the most relevant tables and columns to the model.

### Q5. What if the user asks an ambiguous question?

> The best production approach is clarification. For example, if a user says "show growth" and there are multiple growth metrics, the system should ask a follow-up question rather than guessing.

### Q6. How do you evaluate the quality of generated SQL?

> I would evaluate it on execution success rate, semantic correctness, latency, cost per request, and how often correction is needed. I would also keep a benchmark set of natural language prompts and expected SQL behavior.

### Q7. How would you test this project?

> I would add unit tests for connection URL generation, schema formatting, and API payload validation, plus integration tests for SQLite-based generation and execution flows. I would also create prompt regression tests using fixed schemas and example prompts.

### Q8. How would you support PostgreSQL or SQL Server?

> I would extend the connection builder, add the correct SQLAlchemy driver, and test schema inspection plus SQL compatibility differences. The architecture already separates database URL creation from query generation, so the extension path is straightforward.

### Q9. Why not fine-tune a model?

> Fine-tuning is expensive and usually not the first step for an NL2SQL prototype. Grounding the model with live schema context solves a large part of the problem more quickly and with lower operational complexity.

### Q10. Why not store schema embeddings and use RAG?

> That can be useful for very large enterprise schemas. For this version, direct schema inspection and prompt grounding were simpler and enough for a prototype. RAG becomes more valuable when there are hundreds of tables, rich metadata, or business glossary requirements.

## 9. Repo-specific questions you should be ready for

These are the kinds of questions someone may ask if they actually inspect the code.

### Q1. The README mentions LangChain, but the main SQL generation uses the Gemini SDK directly. Why?

> That is true in the current repo. I kept the actual generation path simple by using the Gemini SDK directly for better control and easier debugging. LangChain-related dependencies were added for possible future orchestration, but the current implementation is prompt-based rather than agent-heavy.

### Q2. Why is `sqlmodel` in the requirements if the project mainly uses SQLAlchemy?

> The current implementation uses SQLAlchemy directly. `sqlmodel` is not central to the current flow and could be removed if it stays unused. In interviews, I would frame that as a cleanup opportunity rather than overclaiming its usage.

### Q3. The README references `init_demo_db.py`, but the actual file is `init_top50_countries_db.py`. What would you say?

> I would say that is a documentation inconsistency and I would fix it. In real projects, keeping docs aligned with code matters because onboarding friction is also part of engineering quality.

### Q4. Why are some seeded country names showing encoding artifacts like `Brasilia`-style text corruption?

> That points to a character encoding issue in the seed data file. I would standardize the file to UTF-8 and add a simple validation test to catch malformed text in seeded datasets.

### Q5. Why does the correction endpoint reuse the generation pipeline instead of using a dedicated SQL repair pipeline?

> For a prototype, reuse reduces complexity. The correction path still benefits from the same schema grounding. If accuracy became a problem, I would separate generation and repair prompts and evaluate them independently.

## 10. Best answers for "Why this stack only?"

If the interviewer asks this directly, a strong answer is:

> I chose this stack to optimize for speed, clarity, and real-world relevance. Python gave me the strongest AI and backend ecosystem. FastAPI gave me clean APIs and validation. Streamlit let me build a usable demo UI quickly. SQLAlchemy made multi-database support and schema inspection easier. SQLite made the project demo-friendly, MySQL made it more realistic, and Gemini provided a fast way to convert natural language into SQL. Overall, I wanted the simplest stack that could still demonstrate AI integration, backend design, database handling, and end-to-end product thinking.

Short version:

> I did not want to overengineer the project. I picked tools that let me prove the core idea quickly while still showing good architecture and practical engineering decisions.

## 11. Best answers for strengths and weaknesses

### Strengths

> The main strengths are clear separation between frontend and backend, schema-aware prompt grounding, support for both demo and external databases, and a user flow that goes from question to SQL to execution in one place.

### Weaknesses

> The main weaknesses are that it is still a prototype, so it lacks strong auth, strict SQL safety, full production monitoring, broader database support, and deeper automated testing.

## 12. If they ask "What would you do next?"

You can answer:

> My next steps would be adding PostgreSQL support, restricting execution to safe query types, improving prompt quality with table selection and schema summarization, adding test coverage, and deploying the backend and frontend with proper authentication and monitoring.

## 13. Final interview closing line

If you want a strong final line:

> This project helped me combine AI, APIs, databases, and product thinking in one system. It is not just about generating SQL, it is about building a reliable workflow around model output and making that useful for real users.

