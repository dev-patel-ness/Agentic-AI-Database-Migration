# 0002. Tool Adapter Contract

- Status: Proposed
- Date: 2026-09-29

## Context

The platform wraps several heterogeneous third-party migration tools (CrackSQL, Apache SeaTunnel, OpenRewrite, Aider, kubectl, Terraform, plus custom checksum/schema-extractor logic). Agents must invoke these tools without knowing their tool-specific APIs, so that a new tool (e.g. replacing SeaTunnel) or a new agent can be added without editing `orchestrator/graph.py`.

## Decision

Define a single abstract interface, `BaseToolAdapter` (see [`tool_adapters/base.py`](../../tool_adapters/base.py)), that every adapter must implement:

```python
class BaseToolAdapter(ABC):
    def prepare(self, config: dict) -> AdapterConfig: ...
    def run(self, config: AdapterConfig) -> ToolResult: ...
    def status(self, job_id: str) -> JobStatus: ...
    def rollback(self, job_id: str) -> RollbackResult: ...
```

- `prepare()` validates/normalizes raw job config into an `AdapterConfig` — the only place adapter-specific config parsing happens.
- `run()` executes the underlying tool and returns a uniform `ToolResult` (`success`, `output`, `error`).
- `status()` reports point-in-time state for long-running jobs (`JobStatus`).
- `rollback()` undoes a previously run job where supported (`RollbackResult`).
- Agents (Assessment, Schema, Data, Code, Validation, Deployment) call adapters only through this contract — never through tool-specific SDK calls directly in agent code.
- A new migration tool = a new folder under `tool_adapters/<tool>_adapter/` implementing `BaseToolAdapter`; this never requires touching `orchestrator/graph.py` (see [§15](../../architecture.md#15-extensibility-adding-new-features)).

## Consequences

- Every adapter must model its tool's success/failure/rollback semantics into these four methods, even for tools with no native rollback (e.g. return `success=False` with an explanatory `detail`).
- Agents gain uniform error handling and retry integration (ADR 0001) for free, since all adapters return the same result shapes.
- Adding a genuinely new capability that doesn't fit `prepare/run/status/rollback` requires either extending the shared contract (impacts all adapters) or introducing a second interface — this should be rare and reviewed carefully.
