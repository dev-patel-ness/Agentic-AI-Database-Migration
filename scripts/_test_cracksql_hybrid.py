"""Manual smoke test: exercise CrackSQL's hybrid local-to-global pipeline
(AST rewrite + RAG + LLM + live validation against a real target DB)."""
import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from tool_adapters.cracksql_adapter import CrackSQLAdapter

source_sql = (
    "CREATE TABLE employees (\n"
    "  id NUMBER(10) PRIMARY KEY,\n"
    "  name VARCHAR2(100) NOT NULL,\n"
    "  hired_at DATE DEFAULT SYSDATE,\n"
    "  notes CLOB\n"
    ")"
)

target_connection = {
    "host": os.environ["POSTGRES_SAMPLE_HOST"],
    "port": int(os.environ["POSTGRES_SAMPLE_PORT"]),
    "username": os.environ["POSTGRES_SAMPLE_USER"],
    "password": os.environ["POSTGRES_SAMPLE_PASSWORD"],
    "database": os.environ["POSTGRES_SAMPLE_DATABASE"],
}

adapter = CrackSQLAdapter()
config = adapter.prepare(
    {
        "source_dialect": "oracle",
        "target_dialect": "postgresql",
        "source_sql": source_sql,
        "target_connection": target_connection,
    }
)
result = adapter.run(config)
print("success:", result.success)
print("error:", result.error)
print("output:", result.output)
print("confidence:", result.confidence_score)
print("time:", result.execution_time_seconds)
