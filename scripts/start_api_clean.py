# Startup script: truncate target DB and start FastAPI
# Usage: poetry run python scripts/start_api_clean.py

import subprocess
import time
import sys
import os

def truncate_target_db():
    """Truncate all target tables before starting API."""
    print("[Startup] Truncating target database tables...")
    truncate_sql = """
TRUNCATE TABLE sample."DEPARTMENTS" CASCADE;
TRUNCATE TABLE sample."EMPLOYEES" CASCADE;
TRUNCATE TABLE sample."PROJECTS" CASCADE;
TRUNCATE TABLE sample."PROJECT_ASSIGNMENTS" CASCADE;
"""
    try:
        # Write SQL to temp file
        with open("/tmp/truncate_startup.sql", "w") as f:
            f.write(truncate_sql)
        
        # Execute via docker
        result = subprocess.run(
            ["docker", "exec", "postgres-sample", "psql", "-U", "postgres", "-d", "sample_source", "-f", "/tmp/truncate_startup.sql"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            print("[Startup] ✅ Target database truncated successfully")
        else:
            print(f"[Startup] ⚠️  Warning: truncate may have failed: {result.stderr}")
    except Exception as e:
        print(f"[Startup] ⚠️  Warning: Could not truncate target DB: {e}")

if __name__ == "__main__":
    truncate_target_db()
    print("[Startup] Starting FastAPI server...\n")
    
    # Start uvicorn in foreground
    os.chdir(os.path.join(os.path.dirname(__file__), "..", "apps", "api-fastapi"))
    os.execvp("poetry", ["poetry", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"])
