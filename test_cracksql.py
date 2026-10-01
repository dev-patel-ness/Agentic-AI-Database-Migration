#!/usr/bin/env python3
"""Quick test to see if CrackSQL hybrid translation works now."""

import sys
import os
from dotenv import load_dotenv

# Load env
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from tool_adapters.cracksql_adapter import CrackSQLAdapter

test_cases = [
    {
        "name": "Oracle to PostgreSQL: Simple CREATE VIEW",
        "source_dialect": "oracle",
        "target_dialect": "postgresql",
        "source_sql": """
CREATE OR REPLACE VIEW sample_user.v_departments AS
SELECT department_id, department_name, manager_id
FROM sample_user.departments
WHERE status = 'ACTIVE';
""",
    },
    {
        "name": "Oracle to PostgreSQL: Create Function with PL/SQL",
        "source_dialect": "oracle",
        "target_dialect": "postgresql",
        "source_sql": """
CREATE OR REPLACE FUNCTION sample_user.get_emp_salary(emp_id NUMBER) RETURN NUMBER IS
    v_salary NUMBER;
BEGIN
    SELECT salary INTO v_salary FROM sample_user.employees WHERE employee_id = emp_id;
    RETURN v_salary;
END get_emp_salary;
""",
    },
]

adapter = CrackSQLAdapter()

print("=" * 80)
print("CrackSQL Hybrid Translation Test")
print("=" * 80)

for test in test_cases:
    print(f"\n[TEST] {test['name']}")
    print(f"  Source: {test['source_dialect'].upper()}")
    print(f"  Target: {test['target_dialect'].upper()}")
    
    config = adapter.prepare({
        "source_dialect": test["source_dialect"],
        "target_dialect": test["target_dialect"],
        "source_sql": test["source_sql"],
    })
    
    result = adapter.run(config)
    
    print(f"  Success: {result.success}")
    print(f"  Confidence: {result.confidence_score}")
    if result.output:
        print(f"  Method: {result.output.get('method', '?')}")
        print(f"  Translated SQL: {result.output.get('translated_sql', 'N/A')[:100]}...")
    if result.error:
        print(f"  Error: {result.error}")
    
    if result.confidence_score >= 0.75:
        print(f"  ✅ HIGH CONFIDENCE")
    elif result.confidence_score >= 0.5:
        print(f"  ⚠️  MEDIUM CONFIDENCE (fallback)")
    else:
        print(f"  ❌ LOW CONFIDENCE")

print("\n" + "=" * 80)
