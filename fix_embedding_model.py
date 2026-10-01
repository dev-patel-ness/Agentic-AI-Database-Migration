#!/usr/bin/env python3
"""Fix embedding model configuration in CrackSQL."""

import sqlite3

db_path = r"c:\Users\user\Downloads\Capstone\Agentic-AI-Database-Migration\tool_adapters\cracksql_adapter\instance\info.db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Update amazon.titan-embed-text-v2:0 to use bedrock deployment
cursor.execute("""
    UPDATE llm_models 
    SET deployment_type = 'bedrock', api_base = 'us-east-1', api_key = ''
    WHERE name = 'amazon.titan-embed-text-v2:0';
""")

# Disable the broken OpenAI embedding model (text-embedding-ada-002)
cursor.execute("""
    UPDATE llm_models
    SET is_active = 0
    WHERE name = 'text-embedding-ada-002';
""")

conn.commit()

# Verify
print("Updated models:")
cursor.execute("SELECT name, deployment_type, api_base, is_active FROM llm_models ORDER BY name;")
for row in cursor.fetchall():
    status = "ACTIVE" if row[3] else "DISABLED"
    print(f"  {row[0]}: {row[1]}, {row[2]} [{status}]")

conn.close()
print("\nEmbedding model now configured for Bedrock!")
