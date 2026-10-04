"""Shared pytest fixtures for the whole test suite."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from dotenv import load_dotenv

from orchestrator import connection_registry
from orchestrator.state import DiscoveryResult

# boto3's default credential chain only prefers env vars over a shared
# ~/.aws/credentials [default] profile if those env vars are actually set --
# pytest never auto-loads .env, so without this, a stale local AWS CLI
# profile silently wins over the (correct) keys in .env.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@pytest.fixture(autouse=True)
def stub_discovery(monkeypatch):
    """Graph-level tests exercise routing/pause-resume, not real discovery
    (that's covered by tests/integration/test_assessment_agent.py and
    test_schema_extractor.py, which call the adapter/agent directly and never
    touch the LangGraph Discover node or this registry). The fake
    source/target connection dicts are never passed to a real DB-API driver
    directly -- Verify's optional health check goes through `connect()`,
    which is also stubbed here so it can't try to dial the fake "src"/"tgt"
    hosts."""
    monkeypatch.setattr(
        connection_registry, "get", lambda job_id: ({"host": "src"}, {"host": "tgt"})
    )
    monkeypatch.setattr(
        "orchestrator.graph.run_discovery",
        lambda job_id, source, target, conn: DiscoveryResult(),
    )
    monkeypatch.setattr("orchestrator.graph.connect", lambda dialect, config: MagicMock())
