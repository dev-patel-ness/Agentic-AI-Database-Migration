"""One-time setup: initialize CrackSQL's LLM/embedding model rows + ingest its
bundled per-dialect knowledge bases (mysql/postgresql/oracle) into the
Postgres+pgvector-backed store (see CrackSQL's vector_store/chroma_store.py).

Run once after (re)building the editable cracksql package
(tool_adapters/cracksql_adapter/vendor/CrackSQL/build_editable.py) or after
changing tool_adapters/cracksql_adapter/vendor/CrackSQL/backend/config/
init_config.yaml. Safe to re-run (idempotent:
skips models/KBs that already exist; re-imports append/upsert vector rows).

NOTE: cracksql.init_knowledge_base.initialize_kb() calls sys.exit(1) on
failure -- deliberately run this as a standalone script, never imported into
request-serving code (tool_adapters/cracksql_adapter).
"""
import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

_CRACKSQL_HOME = os.path.join(os.path.dirname(__file__), "..", "tool_adapters", "cracksql_adapter")
os.makedirs(os.path.join(_CRACKSQL_HOME, "instance"), exist_ok=True)
os.makedirs(os.path.join(_CRACKSQL_HOME, "logs"), exist_ok=True)
os.chdir(_CRACKSQL_HOME)

from cracksql.cracksql import initkb  # noqa: E402

CONFIG_FILE = r"C:\Workspace\CAPSTONE\CrackSQL\backend\config\init_config.yaml"

if __name__ == "__main__":
    ok = initkb(CONFIG_FILE)
    print("initkb() ->", ok)
