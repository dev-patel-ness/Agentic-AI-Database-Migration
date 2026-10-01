import sqlite3

conn = sqlite3.connect("tool_adapters/cracksql_adapter/instance/info.db")
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("TABLES:", [r[0] for r in cur.fetchall()])
cur.execute("SELECT name, dimension FROM llm_models WHERE category='embedding'")
for row in cur.fetchall():
    print(row)
conn.close()
