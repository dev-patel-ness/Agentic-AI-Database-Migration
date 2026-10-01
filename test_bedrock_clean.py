#!/usr/bin/env python3
"""Clean test for CrackSQL with Bedrock."""

import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from tool_adapters.cracksql_adapter import CrackSQLAdapter

test_sql = """
CREATE OR REPLACE VIEW sample_user.v_departments AS
SELECT department_id, department_name, manager_id
FROM sample_user.departments
WHERE status = 'ACTIVE';
"""

print("=" * 80)
print("CrackSQL Bedrock Test - Oracle to PostgreSQL")
print("=" * 80)

adapter = CrackSQLAdapter()
config = adapter.prepare({
    "source_dialect": "oracle",
    "target_dialect": "postgresql",
    "source_sql": test_sql,
})

result = adapter.run(config)

print(f"\nSuccess: {result.success}")
print(f"Confidence: {result.confidence_score}")
if result.output:
    print(f"Method: {result.output.get('method', '?')}")
    translated = result.output.get('translated_sql', 'N/A')
    if translated:
        print(f"Translated SQL:\n{translated}")
    else:
        print("Translated SQL: N/A")
if result.error:
    print(f"Error: {result.error}")

print("\n" + "=" * 80)
if result.confidence_score >= 0.75:
    print("RESULT: HIGH CONFIDENCE - LLM translation successful!")
elif result.confidence_score >= 0.5:
    print("RESULT: MEDIUM CONFIDENCE - using fallback")
else:
    print("RESULT: FAILED")
print("=" * 80)
