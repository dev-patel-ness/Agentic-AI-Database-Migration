import sqlite3

conn = sqlite3.connect("tool_adapters/cracksql_adapter/instance/info.db")
cur = conn.cursor()
cur.execute(
    "UPDATE knowledge_bases SET embedding_model_name = ? WHERE embedding_model_name = ?",
    ("amazon.titan-embed-text-v2:0", "text-embedding-ada-002"),
)
conn.commit()
cur.execute("SELECT kb_name, embedding_model_name FROM knowledge_bases")
for row in cur.fetchall():
    print(row)
conn.close()
