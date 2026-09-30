# 0001. Retry and Escalation Policy

- Status: Proposed
- Date: 2026-09-29

## Context

Every migration phase invokes either an LLM (AWS Bedrock) or an external tool adapter (SeaTunnel, CrackSQL, OpenRewrite, kubectl, Terraform, ...). Both call types can fail transiently (timeouts, malformed LLM output, tool exit errors) or fail persistently (bad config, unrecoverable source data). The orchestrator needs a single, predictable failure-handling rule so that no phase can loop forever, while still giving transient failures a chance to self-heal without paging a human every time.

## Decision

Wrap every LLM call and tool-adapter invocation in the same bounded-retry policy inside its LangGraph node:

- **Retry limit: 3 automatic attempts** per phase, with exponential backoff between attempts.
- `MigrationState.retry_count` is persisted at every checkpoint (per phase), so a crash/restart does not reset the attempt count.
- After the 3rd failed attempt, the graph stops looping and raises a `HumanReviewFailure` interrupt, surfacing the captured error/exception and last-attempt context to the reviewer.
- The reviewer can **Retry** (resets `retry_count` to 0, re-invokes the same phase) or **Abort** (job marked `ABORTED`, audit logged).
- This infra/LLM-call retry is distinct from the **business-logic** retry on `Test --> Validate: test report FAIL` (§6 of [architecture.md](../../architecture.md#61-failure-handling--retry-policy)) — that edge represents a legitimate validation failure, not an execution fault, and is not subject to the 3-attempt cap.

## Consequences

- Every agent/adapter node must implement identical retry/backoff logic (or share a common LangGraph decorator/wrapper) — no phase gets a bespoke retry count.
- `MigrationState` must always carry `retry_count` and `max_retries` fields, and every checkpoint write must include them for correct resume behavior.
- Human reviewers become the only path past 3 consecutive failures, which bounds automation risk but means the UI/API must reliably surface `HumanReviewFailure` interrupts with enough error context to act on.
- Distinguishing "infra failure" from "business-logic failure" must be enforced consistently by each agent, or the two retry semantics will bleed into each other.
