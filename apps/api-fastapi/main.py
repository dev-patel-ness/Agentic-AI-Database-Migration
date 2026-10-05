"""FastAPI gateway: REST/WebSocket API, auth middleware, job queue.

Phase 1 scope (architecture.md §6/§9): drives the stub LangGraph workflow via
a Postgres-backed checkpointer, exposes job creation/status/review endpoints,
and streams progress over a WebSocket. Real per-agent business logic lands in
later phases; this wires the plumbing end-to-end.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from langgraph.types import Command
from pydantic import BaseModel, SecretStr

# Must run before any orchestrator/agent/tool_adapter imports below, since
# those can construct boto3 clients (Bedrock, S3) at import time that read
# AWS_* env vars from the process environment.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from orchestrator import connection_registry
from orchestrator.checkpointer import build_checkpointer, build_checkpointer_pool
from orchestrator.graph import compile_graph
from orchestrator.state import DialectPair, MigrationState
from tool_adapters.schema_extractor_adapter import SchemaExtractorAdapter

logger = logging.getLogger(__name__)

AUTH_HEADER_NAME = "X-API-Key"
DialectName = Literal["oracle", "mysql", "postgresql"]


# --- Lifespan: own the checkpointer connection pool for the app's lifetime ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = build_checkpointer_pool()
    checkpointer = build_checkpointer(pool)
    app.state.pool = pool
    app.state.graph = compile_graph(checkpointer=checkpointer)
    if not os.getenv("AUTH_API_KEY"):
        logger.warning(
            "AUTH_API_KEY is not set — API auth is DISABLED (dev mode only, "
            "see architecture.md §14 before deploying)."
        )
    try:
        yield
    finally:
        pool.close()


app = FastAPI(title="Agentic Migration Platform API", lifespan=lifespan)


# --- Auth (stub, hardened in Phase 9 per architecture.md §14) ---------------


@app.middleware("http")
async def api_key_auth_middleware(request: Request, call_next):
    expected = os.getenv("AUTH_API_KEY")
    if expected and request.headers.get(AUTH_HEADER_NAME) != expected:
        return JSONResponse(status_code=401, content={"detail": "invalid or missing API key"})
    return await call_next(request)


def _check_ws_auth(websocket: WebSocket) -> bool:
    expected = os.getenv("AUTH_API_KEY")
    if not expected:
        return True
    return websocket.headers.get(AUTH_HEADER_NAME) == expected


# --- Request/response schemas -------------------------------------------------


class ConnectionConfig(BaseModel):
    """Raw DB connection details, collected from the UI at job-creation time.

    Deliberately never stored on MigrationState/the LangGraph checkpoint (see
    architecture.md §14) -- held only in orchestrator.connection_registry for
    the short window until the Discover node consumes it.
    """

    host: str
    port: int
    username: str
    password: SecretStr
    database: str  # DB/service to connect to (Postgres db, MySQL db, Oracle service_name)
    schema_name: Optional[
        str
    ] = None  # namespace to discover within it (Postgres only; default "public")


class JobCreateRequest(BaseModel):
    source_dialect: DialectName
    target_dialect: DialectName
    source_connection: ConnectionConfig
    target_connection: ConnectionConfig


class JobCreateResponse(BaseModel):
    job_id: str


class ReviewDecisionRequest(BaseModel):
    decision: Literal["approve", "modify", "reject", "retry", "abort"]
    reviewer: str
    comment: Optional[str] = None


class JobStatusResponse(BaseModel):
    job_id: str
    current_phase: str
    status: str
    retry_count: int
    approvals: list[dict[str, Any]]
    retry_history: list[dict[str, Any]]
    execution_trace: list[dict[str, Any]]  # Detailed execution steps for UI observability
    discovery: Optional[dict[str, Any]] = None
    plan: Optional[dict[str, Any]] = None
    schema_translation: Optional[dict[str, Any]] = None
    code_refactor: Optional[dict[str, Any]] = None
    data_migration: Optional[dict[str, Any]] = None
    validation: Optional[dict[str, Any]] = None
    test_report: Optional[dict[str, Any]] = None
    deployment: Optional[dict[str, Any]] = None
    interrupt: Optional[dict[str, Any]] = None


class SchemaSqlResponse(BaseModel):
    source_dialect: str
    target_dialect: str
    source_schema_sql: str
    target_schema_sql: str


# --- Helpers ------------------------------------------------------------------


# schema.sql convention: tables first, then dependent objects, FK constraints last.
_SCHEMA_SQL_OBJECT_ORDER = ("table", "view", "procedure", "function", "trigger", "foreign_key")


def _dump_schema_sql(
    adapter: SchemaExtractorAdapter, dialect_name: str, connection_config: dict[str, Any]
) -> str:
    """Live-introspect one side's full object catalog and concatenate every
    object's DDL text into a single schema.sql-style script."""
    config = adapter.prepare({"dialect": dialect_name, "connection": connection_config})
    result = adapter.run(config)
    if not result.success:
        raise RuntimeError(result.error or "schema introspection failed")

    by_type: dict[str, list[dict[str, Any]]] = {}
    for entry in result.output["object_catalog"]:
        by_type.setdefault(entry["object_type"], []).append(entry)

    chunks: list[str] = [
        f"-- {object_type.upper()}: {entry['schema']}.{entry['name']}\n{entry['definition'].rstrip().rstrip(';')};"
        for object_type in _SCHEMA_SQL_OBJECT_ORDER
        for entry in by_type.get(object_type, [])
        if entry.get("definition")
    ]
    return "\n\n".join(chunks) if chunks else "-- no objects found"


def _thread_config(job_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": job_id}}


def _run_graph(request: Request, config: dict[str, Any], payload: Any) -> None:
    job_id = config["configurable"]["thread_id"]
    try:
        request.app.state.graph.invoke(payload, config=config)
    except Exception:
        logger.exception("job %s: graph run failed", job_id)


def _snapshot_to_status(job_id: str, snapshot) -> JobStatusResponse:
    if not snapshot.values:
        raise HTTPException(status_code=404, detail="job not found")
    state = MigrationState.model_validate(snapshot.values)
    interrupt_payload = None
    if snapshot.interrupts:
        first = snapshot.interrupts[0]
        interrupt_payload = {
            "id": first.id,
            **(first.value if isinstance(first.value, dict) else {"value": first.value}),
        }
    return JobStatusResponse(
        job_id=job_id,
        current_phase=state.current_phase,
        status=state.status,
        retry_count=state.retry_count,
        approvals=[a.model_dump(mode="json") for a in state.approvals],
        retry_history=[r.model_dump(mode="json") for r in state.retry_history],
        execution_trace=[step.model_dump(mode="json") for step in state.execution_trace],
        discovery=state.discovery.model_dump(mode="json") if state.discovery else None,
        plan=state.plan.model_dump(mode="json") if state.plan else None,
        schema_translation=(
            state.schema_translation.model_dump(mode="json") if state.schema_translation else None
        ),
        code_refactor=state.code_refactor.model_dump(mode="json") if state.code_refactor else None,
        data_migration=(
            state.data_migration.model_dump(mode="json") if state.data_migration else None
        ),
        validation=state.validation.model_dump(mode="json") if state.validation else None,
        test_report=state.test_report.model_dump(mode="json") if state.test_report else None,
        deployment=state.deployment.model_dump(mode="json") if state.deployment else None,
        interrupt=interrupt_payload,
    )


# --- Endpoints ------------------------------------------------------------------


@app.post("/jobs", response_model=JobCreateResponse, status_code=202)
def create_job(payload: JobCreateRequest, request: Request) -> JobCreateResponse:
    job_id = str(uuid.uuid4())
    initial_state = MigrationState(
        job_id=job_id,
        dialects=DialectPair(source=payload.source_dialect, target=payload.target_dialect),
    )
    connection_registry.register(
        job_id,
        {
            **payload.source_connection.model_dump(),
            "password": payload.source_connection.password.get_secret_value(),
        },
        {
            **payload.target_connection.model_dump(),
            "password": payload.target_connection.password.get_secret_value(),
        },
    )
    config = _thread_config(job_id)
    # Fire-and-forget: the graph advances until it hits the first interrupt (or
    # finishes) and checkpoints, while the request returns immediately.
    threading.Thread(
        target=_run_graph, args=(request, config, initial_state.model_dump()), daemon=True
    ).start()
    return JobCreateResponse(job_id=job_id)


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str, request: Request) -> JobStatusResponse:
    snapshot = request.app.state.graph.get_state(_thread_config(job_id))
    return _snapshot_to_status(job_id, snapshot)


@app.get("/jobs/{job_id}/schema-sql", response_model=SchemaSqlResponse)
def get_schema_sql(job_id: str, request: Request) -> SchemaSqlResponse:
    """Live side-by-side schema.sql for the full source DB and full target DB
    (not just the job's persisted discovery snapshot), for UI comparison."""
    snapshot = request.app.state.graph.get_state(_thread_config(job_id))
    if not snapshot.values:
        raise HTTPException(status_code=404, detail="job not found")
    state = MigrationState.model_validate(snapshot.values)

    conns = connection_registry.get(job_id)
    if conns is None:
        raise HTTPException(
            status_code=410,
            detail=(
                "source/target connection details are no longer available for this "
                "job -- either it reached a terminal state (Done/Aborted/RolledBack), "
                "or the API process restarted since the job was created (the registry "
                "is in-memory only); create a new job to use this feature"
            ),
        )
    source_connection, target_connection = conns

    adapter = SchemaExtractorAdapter()
    try:
        source_sql = _dump_schema_sql(adapter, state.dialects.source, source_connection)
        target_sql = _dump_schema_sql(adapter, state.dialects.target, target_connection)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"failed to introspect schema: {exc}") from exc

    return SchemaSqlResponse(
        source_dialect=state.dialects.source,
        target_dialect=state.dialects.target,
        source_schema_sql=source_sql,
        target_schema_sql=target_sql,
    )


@app.post("/jobs/{job_id}/review", status_code=202)
def review_job(job_id: str, payload: ReviewDecisionRequest, request: Request) -> dict[str, str]:
    config = _thread_config(job_id)
    snapshot = request.app.state.graph.get_state(config)
    if not snapshot.values:
        raise HTTPException(status_code=404, detail="job not found")
    if not snapshot.interrupts:
        raise HTTPException(status_code=409, detail="job is not awaiting review")
    threading.Thread(
        target=_run_graph,
        args=(request, config, Command(resume=payload.model_dump())),
        daemon=True,
    ).start()
    return {"job_id": job_id, "accepted": "true"}


@app.websocket("/jobs/{job_id}/ws")
async def job_progress_ws(websocket: WebSocket, job_id: str) -> None:
    if not _check_ws_auth(websocket):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    graph = websocket.app.state.graph
    terminal_statuses = {"DONE", "ABORTED", "ROLLED_BACK"}
    last_payload: dict[str, Any] | None = None
    try:
        while True:
            snapshot = graph.get_state(_thread_config(job_id))
            if not snapshot.values:
                await websocket.send_json({"job_id": job_id, "error": "job not found"})
                await websocket.close(code=4404)
                return
            status = _snapshot_to_status(job_id, snapshot).model_dump(mode="json")
            if status != last_payload:
                await websocket.send_json(status)
                last_payload = status
            if status["status"] in terminal_statuses:
                break
            await asyncio.sleep(1.0)
        await websocket.close()
    except WebSocketDisconnect:
        logger.info("job %s: progress websocket disconnected", job_id)
