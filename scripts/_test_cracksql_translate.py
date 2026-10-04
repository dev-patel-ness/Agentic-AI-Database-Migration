"""Manual smoke test: exercise CrackSQL's real AST + LLM translation pipeline
(not mocked) via tool_adapters.cracksql_adapter -- Oracle -> PostgreSQL DDL."""
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

adapter = CrackSQLAdapter()
config = adapter.prepare(
    {
        "source_dialect": "oracle",
        "target_dialect": "postgresql",
        "source_sql": source_sql,
    }
)
result = adapter.run(config)
print("success:", result.success)
print("error:", result.error)
print("output:", result.output)
print("confidence:", result.confidence_score)
print("time:", result.execution_time_seconds)
