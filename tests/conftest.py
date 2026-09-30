"""Shared pytest fixtures for the whole test suite."""

from __future__ import annotations

import pytest

from orchestrator import connection_registry
from orchestrator.state import DiscoveryResult


@pytest.fixture(autouse=True)
def stub_discovery(monkeypatch):
    """Graph-level tests exercise routing/pause-resume, not real discovery
    (that's covered by tests/integration/test_assessment_agent.py and
    test_schema_extractor.py, which call the adapter/agent directly and never
    touch the LangGraph Discover node or this registry)."""
    monkeypatch.setattr(
        connection_registry, "get", lambda job_id: ({"host": "src"}, {"host": "tgt"})
    )
    monkeypatch.setattr(
        "orchestrator.graph.run_discovery",
        lambda job_id, source, target, conn: DiscoveryResult(),
    )
