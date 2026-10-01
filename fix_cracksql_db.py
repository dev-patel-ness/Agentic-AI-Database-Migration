#!/usr/bin/env python3
"""Update CrackSQL model configuration."""

import sqlite3
import os

db_path = r"c:\Users\user\Downloads\Capstone\Agentic-AI-Database-Migration\tool_adapters\cracksql_adapter\instance\info.db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Update amazon.nova-pro-v1:0 to use bedrock deployment
cursor.execute("""
    UPDATE llm_models 
    SET deployment_type = 'bedrock', api_base = 'us-east-1'
    WHERE name = 'amazon.nova-pro-v1:0';
""")

conn.commit()

# Verify
cursor.execute("SELECT name, deployment_type, api_base FROM llm_models WHERE name LIKE 'amazon%';")
print("✅ Updated LLM models:")
for row in cursor.fetchall():
    print(f"   - {row[0]}: deployment_type={row[1]}, api_base={row[2]}")

conn.close()
