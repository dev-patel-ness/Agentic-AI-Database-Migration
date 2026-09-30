# 0003. Checkpointing Strategy

- Status: Proposed
- Date: 2026-09-29

## Context

Migration jobs run through a long, multi-phase LangGraph workflow (Discover → Analyse → Plan → Transform → Generate → Validate → Test → Approve → Migrate → Verify) spanning human-in-the-loop approval interrupts that can pause for arbitrary lengths of time. The orchestrator must be able to pause at any interrupt, survive process restarts/crashes, and resume a job exactly where it left off — including its `retry_count` (ADR 0001) — without replaying already-completed side effects.

## Decision

Use LangGraph's built-in checkpointer, backed by the platform's Postgres metadata database (`orchestrator/checkpointer.py`), as the single source of truth for in-flight job state:

- The full `MigrationState` (job id, dialect pair, discovery/plan/translation/validation results, approvals, retry counts, current phase/status) is serialized and persisted at every node transition, not just at approval interrupts.
- On resume (after an approval decision or a process restart), the graph re-enters at the exact node it paused on, using the persisted state — no phase is silently re-run from scratch.
- Checkpoint history doubles as the audit trail: every `ApprovalRecord` and rollback event is persisted from the checkpoint that recorded it (see [§10](../../architecture.md#10-data--knowledge-stores)), not retrofitted after the fact.
- The Postgres checkpoint store is part of the platform's own operational metadata DB, separate from the source/target databases being migrated.

## Consequences

- The platform depends on a Postgres instance being available for the orchestrator itself, independent of whatever source/target dialect a given job is migrating.
- `MigrationState` must remain a serializable Pydantic model; any new field added to it must be checkpoint-compatible (no non-serializable objects, no in-memory-only state).
- Disaster recovery for the checkpoint DB is a distinct concern from migration-job data recovery, and is called out as open work in [§16](../../architecture.md#16-open-questions--future-work).
- Because every node transition is checkpointed, replay/audit is possible for any job at any phase, at the cost of a Postgres write on every phase transition.
