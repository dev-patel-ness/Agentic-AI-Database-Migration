# Architecture Decision Records (ADR)

This directory records significant architectural decisions for the Agentic AI Data Migration platform, one file per decision.

## Process

- One ADR per decision, numbered sequentially: `NNNN-short-slug.md` (e.g. `0001-retry-and-escalation-policy.md`).
- Never renumber or delete a merged ADR; if a decision is reversed, add a new ADR that supersedes it and update the old one's `Status` to `Superseded by ADR-NNNN`.
- Status values: `Proposed` → `Accepted` → (optionally) `Superseded` / `Deprecated`.
- Keep each ADR short: Context, Decision, Consequences. Avoid restating the full architecture — link to [`architecture.md`](../../architecture.md) instead.

## Template

Copy this structure for a new ADR:

```markdown
# NNNN. Title

- Status: Proposed
- Date: YYYY-MM-DD

## Context

What problem/forces led to this decision?

## Decision

What was decided?

## Consequences

What becomes easier or harder as a result?
```

## Index

| # | Title | Status |
|---|-------|--------|
| [0001](./0001-retry-and-escalation-policy.md) | Retry and Escalation Policy | Proposed |
| [0002](./0002-tool-adapter-contract.md) | Tool Adapter Contract | Proposed |
| [0003](./0003-checkpointing-strategy.md) | Checkpointing Strategy | Proposed |
| [0004](./0004-dialect-symmetry.md) | Dialect Symmetry | Proposed |
