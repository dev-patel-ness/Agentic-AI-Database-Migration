#!/usr/bin/env python3
"""Check CrackSQL local database."""

import sqlite3
import os

db_path = r"c:\Users\user\Downloads\Capstone\Agentic-AI-Database-Migration\tool_adapters\cracksql_adapter\instance\info.db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check if llm_models table exists
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='llm_models';")
if not cursor.fetchone():
    print("❌ llm_models table does not exist")
else:
    print("✅ llm_models table exists")
    cursor.execute("SELECT name, deployment_type, api_base FROM llm_models;")
    for row in cursor.fetchall():
        print(f"   - {row[0]}: deployment_type={row[1]}, api_base={row[2]}")

conn.close()
