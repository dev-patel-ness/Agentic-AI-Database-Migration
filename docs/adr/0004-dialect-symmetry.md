# 0004. Dialect Symmetry

- Status: Proposed
- Date: 2026-09-29

## Context

The platform must support any-to-any migration between Oracle, MySQL, and PostgreSQL (e.g. Oracle→PostgreSQL, MySQL→Oracle, PostgreSQL→MySQL). Without a deliberate design constraint, it would be easy to end up with source-specific and target-specific code paths that double the number of dialect implementations and hard-code direction into agent logic.

## Decision

Model each database engine as a single symmetric `Dialect` plugin, usable as either source or target, per the abstract contract in [`dialects/base.py`](../../dialects/base.py):

```python
class Dialect(ABC):
    name: str
    def type_map(self) -> dict[str, str]: ...
    def export_ddl_command(self, connection_config: dict) -> list[str]: ...
    def quote_identifier(self, identifier: str) -> str: ...
```

- A single `DialectPair` (`source`, `target`) in `MigrationState` determines direction at job-creation time.
- Agents and adapters are direction-agnostic: they read `dialects.source` / `dialects.target` off `MigrationState` and dispatch to the matching plugin — no agent branches on "is this the source-side code path" vs. "target-side."
- Infrastructure provisioning mirrors this: the same Terraform `rds-instance` module is parameterized by engine type for both `RDS_A`/`RDS_B`, rather than having fixed "source module" and "target module" (see [§11](../../architecture.md#11-deployment-architecture)).
- A new dialect (e.g. DB2) = one new folder under `dialects/<name>/` implementing `base.py`; it is immediately usable as both source and target since the contract is symmetric, with no changes to `orchestrator/graph.py` (see [§15](../../architecture.md#15-extensibility-adding-new-features)).

## Consequences

- Every dialect implementation must support both export (as source) and target-side operations (type mapping, identifier quoting, DDL generation) even if a given migration only exercises one direction — there is no "read-only source dialect" shortcut.
- Adding SQL Server or DB2 support later is additive (one new plugin folder) rather than requiring changes across agents or the orchestrator.
- Any future asymmetry (e.g. a dialect that can only ever be a source) would break this contract and needs its own ADR rather than a quiet special case in agent code.
