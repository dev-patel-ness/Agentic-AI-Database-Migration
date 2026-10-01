# Implementation Plan — Agentic AI-Powered Database Migration Platform

> Derived from [architecture.md](./docs/architecture.md) and [Capstone_Proposal.md](./Capstone_Proposal.md).
> Scope: full any-to-any Oracle/MySQL/PostgreSQL support, full production stack (Terraform/EKS/Bedrock/LangSmith/Prometheus/Grafana).
> Team: 2-4 engineers. Duration: 10 weeks (fits within an 8-12 week window; compress by dropping stretch items if needed).
> Each phase ends with a demo-able increment and a defined Definition of Done (DoD).
>
> **Status legend** (updated 2026-10-01, see [architecture.md §17](./architecture.md#17-implementation-status) for detail): ✅ Done · 🟨 Partially done · 🔮 Future extension (designed, not yet built).

---

## Team Role Split (used throughout phases)

| Role | Owns |
|---|---|
| **Platform/Orchestration Eng** | LangGraph state machine, FastAPI, Streamlit, checkpointer, HITL gates |
| **Data/DB Eng** | Dialect plugins, schema extractor, SeaTunnel/data migration, checksum validation |
| **AI/Agent Eng** | Bedrock integration, Planner/Schema/Code agents, RAG knowledge base, CrackSQL/OpenRewrite/Aider adapters |
| **DevOps/Platform Eng** | Terraform, Kubernetes, CI/CD, observability stack, security hardening |

On a 2-person team, merge roles: (Platform+AI) and (Data+DevOps).

---

## Phase 0 — Foundations & Environment Setup (Week 1) ✅ Done

**Goal:** Repo skeleton, tooling, and cloud prerequisites in place so every later phase can build without blocking on infra.

- Scaffold monorepo per [architecture.md §4](./architecture.md#4-repository-structure): `apps/`, `orchestrator/`, `agents/`, `tool_adapters/`, `dialects/`, `knowledge_base/`, `infra/`, `observability/`, `tests/`, `docs/`.
- Set up Python project tooling: `pyproject.toml`/poetry or `uv`, linting (ruff), type checking (mypy/pyright), pre-commit hooks.
- Provision baseline AWS access: Bedrock model access (Nova Pro + Titan Embeddings), IAM user/role for local dev, S3 bucket for Terraform state.
- Stand up local dev stack via Docker Compose: Postgres (metadata + PGVector), Oracle XE, MySQL, PostgreSQL (as sample source/target sandboxes).
- Define `BaseToolAdapter` (§5 class diagram) and `dialects/base.py` contracts as empty interfaces (no implementations yet).
- Initialize GitHub Actions skeleton: lint + unit test job only (full pipeline comes in Phase 9).

**DoD:** `docker compose up` brings up all local DBs; empty adapter/dialect interfaces type-check; CI runs lint on push.

---

## Phase 1 — Orchestration Skeleton & Shared State (Week 2) ✅ Done

**Goal:** The LangGraph backbone and API/UI shells exist end-to-end with a no-op workflow, proving the plumbing before any real agent logic is added.

- Implement `MigrationState` Pydantic schema exactly per [architecture.md §7](./architecture.md#7-shared-state-schema) (`DialectPair`, `MigrationPlan`, `ApprovalRecord`, `ValidationReport`, etc.).
- Build `orchestrator/graph.py`: LangGraph `StateGraph` with all nodes from [§6](./architecture.md#6-orchestration-langgraph-state-machine) wired as stubs (each node just logs + advances `current_phase`).
- Implement Postgres-backed checkpointer (`orchestrator/checkpointer.py`) so pause/resume works from turn one.
- Implement the bounded-retry wrapper described in [§6.1](./architecture.md#61-failure-handling--retry-policy) (`retry_count`, `max_retries=3`, `HumanReviewFailure` escalation) as a reusable decorator/utility around node execution.
- FastAPI gateway (`apps/api-fastapi`): job creation endpoint, job status endpoint, WebSocket/SSE progress stream, stub auth middleware.
- Streamlit UI (`apps/ui-streamlit`): job creation form (source/target dialect + connection config), progress view, generic Approve/Reject/Modify screen wired to the interrupt handler.

**DoD:** Creating a job via Streamlit drives a stub job through every phase in [§6](./architecture.md#6-orchestration-langgraph-state-machine) up to a human review gate, pauses, and resumes correctly after an app restart (checkpoint proven).

---

## Phase 2 — Dialect Plugins & Discovery (Weeks 3-4) ✅ Done

**Goal:** Real discovery against real databases — the first agent that does actual work.

- Implement `dialects/oracle`, `dialects/mysql`, `dialects/postgresql` against `dialects/base.py`: type maps, DDL export commands (`DBMS_METADATA.GET_DDL`, `mysqldump --no-data`, `pg_dump --schema-only`), symmetric source/target usage.
- Implement `schema_extractor_adapter`: runs native DDL export, invokes SQL/DDL parser (sqlglot) to build object catalog + dependency graph.
- Implement **Assessment Agent**: calls the adapter, stores discovery embeddings into PGVector, returns `DiscoveryResult` per the [§8.1 sequence](./architecture.md#81-discovery--assessment).
- Wire `Discover → Analyse` edge in the real graph (replacing the Phase 1 stub).
- Seed the Platform Metadata DB schema per [§10 ERD](./architecture.md#10-data--knowledge-stores): `MIGRATION_JOB`, `OBJECT_CATALOG_ENTRY`, `CHECKPOINT`.

**DoD:** Given real connection configs for any two of the three sample DBs, the platform produces an accurate object catalog + dependency graph and persists it.

---

## Phase 3 — Knowledge Base & Planner Agent (Week 4-5) ✅ Done

**Goal:** RAG-backed migration planning with the first real Human-in-the-Loop gate.

- Build `knowledge_base/ingestion`: load type-mapping rules, vendor syntax quirks, known incompatibilities, historical issues, validation rules as source documents; embed with Titan Embeddings into PGVector.
- Build `knowledge_base/retrievers`: similarity search interface used by Planner/Schema agents.
- Implement **Planner Agent**: consumes `DiscoveryResult` + RAG retrieval, produces `MigrationPlan` (tables/views/procedures/functions/triggers counts, `risk_register`, `manual_review_objects`) matching the [Capstone approval example](./Capstone_Proposal.md#8-human-approval).
- Implement `HumanReviewPlan` node/interrupt with Approve/Modify/Reject routing per [§9](./architecture.md#9-human-in-the-loop-approval-flow); persist `ApprovalRecord`.
- Streamlit: build the real plan-summary review screen (counts + risk breakdown + per-object drill-down).

**DoD:** A discovered schema produces a plan with risk-scored objects, reviewable and modifiable in the UI, with approval persisted and audit-visible.

---

## Phase 4 — Schema & Logic Translation (Weeks 5-6) ✅ Done

**Goal:** Automated DDL/procedure/trigger translation between dialects.

- Implement `cracksql_adapter`: AST-based deterministic translation with Bedrock (Nova Pro) fallback for ambiguous constructs, returning confidence scores.
- Implement **Schema Agent** per [§8.2 sequence](./architecture.md#82-schema--logic-translation): retrieves RAG rules from KB, invokes CrackSQL adapter, returns `TranslationResult`.
- Wire `Transform → Generate` edges; persist `TRANSLATION_RESULT` rows (source DDL, target DDL, confidence) per [§10 ERD](./architecture.md#10-data--knowledge-stores).
- Add low-confidence-translation routing: below-threshold objects get flagged into `manual_review_objects` for a later human pass.
- LangSmith tracing wired for every Bedrock call in this phase (prompt, tokens, latency, cost) — first real observability integration ahead of full Phase 9 rollout, since this is the first LLM-heavy phase.

**DoD:** For a representative schema, DDL/procedures/triggers/views translate source→target with confidence scores, and every LLM call is traced.

---

## Phase 5 — Data Migration (Weeks 6-7) 🟨 Partially done — bulk load implemented; CDC streaming is a 🔮 future extension

**Goal:** Bulk + CDC data movement with measurable throughput.

- Implement `seatunnel_adapter`: generates SeaTunnel Zeta job configs for bulk historical extract/load and streaming CDC, per dialect pair.
- Implement **Data Agent** per [§8.3 sequence](./architecture.md#83-data-migration): triggers bulk load, then CDC stream; captures rows-moved and lag metrics into `DataMigrationResult`.
- Wire `CodeRefactor → DataMigrate` edge (data migration can run in parallel with/after code refactor per job policy — confirm ordering matches [§6](./architecture.md#6-orchestration-langgraph-state-machine)).
- Export SeaTunnel job metrics to Prometheus (early observability hook, full dashboards in Phase 9).

**DoD:** A multi-table dataset (including at least one large table) migrates via bulk load, and simulated CDC changes propagate to the target within an acceptable lag.

---

## Phase 6 — Application Code Refactoring (Week 7) 🔮 Future extension — `agents/code_agent`, `openrewrite_adapter`, `aider_adapter` are empty stubs; `CodeRefactor` graph node is a no-op

**Goal:** Automated application-layer adaptation to the new database dialect.

- Implement `openrewrite_adapter`: AST-based recipe execution for Java/Spring ORM dialect + JDBC driver swap.
- Implement `aider_adapter`: LLM-guided edits for raw SQL / SQLAlchemy config in Python/C++ code.
- Implement **Code Agent** per [§8.4 sequence](./architecture.md#84-application-code-refactoring): branches by app stack, returns diffs + files-changed via `CodeRefactorResult`.
- Provide a small sample app (Java/Spring or Python service) in `tests/e2e/` fixtures to validate refactor diffs against.

**DoD:** Running the Code Agent against the sample app produces a correct, buildable diff for the target dialect, with generated diff surfaced for review.

---

## Phase 7 — Validation, Reconciliation & Testing (Week 8) 🟨 Partially done — checksum/reconciliation validation is real; the automated **Test** phase is a stub that always returns PASS

**Goal:** Deterministic proof of migration correctness plus automated test generation.

- Implement `checksum_adapter`: batched row fetch from source/target, Pandas/PySpark hashing, per-table comparison.
- Implement **Validation Agent** per [§8.5 sequence](./architecture.md#85-validation--reconciliation): produces `ValidationReport` (mismatches, per-table status), persists `VALIDATION_RESULT` rows.
- Wire `Validate → HumanReviewValidation` gate and the `PASS → Test` / `FAIL → retry DataMigrate` router.
- Implement the **Test** phase: generate/execute migration test cases (schema/SQL compatibility, referential integrity, missing objects, performance smoke checks) producing a structured test report; wire `Test → HumanReviewCutover` (PASS) / `Test → Validate` (FAIL) edges.

**DoD:** Given a migrated dataset with at least one deliberately-injected mismatch, the Validation Agent detects and reports it correctly, and a clean dataset produces a PASS test report reaching the cutover gate.

---

## Phase 8 — Deployment, Cutover & Rollback (Week 9) 🔮 Future extension — `agents/deployment_agent`, `kubectl_adapter`, `terraform_adapter`, and all of `infra/` are empty stubs/placeholders; `Cutover`/`Verify`/`Rollback` graph nodes exist but don't call real tooling

**Goal:** Safe, automated cutover with proven rollback.

- Build Terraform modules: `network`, `eks`, `rds-instance` (parameterized by engine), `metadata-db`, `iam` per [§11](./architecture.md#11-deployment-architecture).
- Author Helm charts/manifests for `ns-platform` and `ns-app` namespaces; RBAC scoping Deployment Agent's service account to `ns-app` only (least privilege, [§14](./architecture.md#14-security-considerations)).
- Implement `terraform_adapter` and `kubectl_adapter` against `BaseToolAdapter`.
- Implement **Deployment Agent** per [§8.6 sequence](./architecture.md#86-cutover--rollback): rolling update to new pods, health-check gating, legacy pod termination, and automatic `kubectl rollout undo` on connection-error detection.
- Wire `HumanReviewCutover → Cutover → Verify → Done/Rollback` edges.

**DoD:** A staged cutover rolls out new pods pointing at the migrated DB, passes health checks, and terminates legacy pods; forcing a connection error triggers automatic rollback to legacy pods.

---

## Phase 9 — Observability, Security & CI/CD Hardening (Week 9-10) 🟨 Partially done — Prometheus metrics + lint/unit-test CI are real; LangSmith tracing, Grafana dashboards, full build/scan/deploy pipeline, and Secrets Manager/IRSA are 🔮 future extensions

**Goal:** Production-readiness — full tracing, metrics, dashboards, secrets, and a real pipeline.

- Complete LangSmith tracing across **all** agent/tool calls (not just Phase 4's LLM calls) per [§13](./architecture.md#13-observability).
- Stand up Prometheus + Grafana with dashboards: agent latency & cost, tool success rate, migration throughput, validation pass rate, pod health/rollout status.
- Security hardening pass against [§14](./architecture.md#14-security-considerations) checklist: Secrets Manager/IRSA for all DB and Bedrock credentials, FastAPI allow-list validation on job config, parameterized queries everywhere, typed-config command building for `kubectl`/`terraform` adapters (no raw string interpolation), private-subnet network isolation for source/target DBs.
- Build the full GitHub Actions pipeline per [§12](./architecture.md#12-cicd-pipeline): lint → unit → build images → vulnerability scan → push ECR → deploy staging → E2E migration test (small sample DB) → manual approval gate → Terraform apply + Helm upgrade (prod).
- Threat-model review: confirm LLM-suggested DDL/code diffs never auto-apply without passing through a human gate or automated test/validation.

**DoD:** A full staging deploy runs through the CI/CD pipeline end-to-end including the E2E sample migration test; Grafana dashboards show live data from a real job run; a security checklist review is signed off.

---

## Phase 10 — Final Integration, Docs & Demo (Week 10) 🔮 Future extension — depends on Phases 6/8/9 completing first

**Goal:** Everything works together as one coherent product, documented and demoable.

- Full end-to-end dry run: Discover → Analyse → Plan → Transform → Generate → Validate → Test → Approve → Migrate → Verify, across at least two different dialect pairs (e.g. Oracle→PostgreSQL and MySQL→PostgreSQL) to prove the any-to-any claim.
- Document major decisions (retry policy, adapter contract, checkpointing choice, dialect symmetry) in `docs/architecture.md`.
- Produce migration risk/execution reports (sample output) and architecture diagram export for deliverables.
- Record final demonstration video per [Capstone_Proposal.md deliverables](./Capstone_Proposal.md#expected-deliverables).
- Final review against the Capstone evaluation criteria: working assistant, end-to-end workflow, production-ready quality.

**DoD:** Two distinct dialect-pair migrations run successfully end-to-end with human approvals, dashboards, and a recorded demo ready for submission.

---

## Cross-Cutting Concerns (apply throughout, not a single phase)

- **Testing:** unit tests per adapter/agent as they're built (Phase N work isn't "done" without tests); integration tests once two adjacent phases connect; e2e tests from Phase 7 onward.
- **Extensibility discipline:** per [§15](./architecture.md#15-extensibility-adding-new-features), never let a new dialect or tool adapter require touching `orchestrator/graph.py` — enforce this in code review.
- **Audit trail:** every `ApprovalRecord` and rollback event must be persisted from the moment its phase is implemented, not retrofitted later.

---

## Key Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Bedrock cost/rate limits during Phase 4/6 heavy LLM use | Cache CrackSQL LLM fallbacks; batch translation calls; set per-job cost budget alerts in Grafana |
| CrackSQL/OpenRewrite/Aider are third-party tools with integration risk | Timebox a spike at the start of Phase 4/6 to validate CLI/API integration before committing the full week |
| Oracle/MySQL/PostgreSQL any-to-any matrix triples test surface | Prioritize one pair (Oracle→PostgreSQL) fully working before generalizing to the other five directions |
| Terraform/EKS setup (Phase 8) is the most time-heavy infra item | Start a parallel DevOps spike in Phase 2-3 so Terraform/EKS baseline exists before Phase 8 needs it |
| Retry/HITL logic (§6.1) touches every agent — bugs here block everything | Build and unit-test the retry wrapper once in Phase 1; every later agent reuses it unchanged |

---

## Open Questions Carried From Architecture (revisit before/during relevant phase)

- Multi-tenant isolation model — needed before Phase 8 if concurrent jobs are in scope.
- Formal risk-scoring rubric for Planner Agent — needed before Phase 3 if scoring must be defensible/calibrated rather than heuristic.
- Disaster-recovery plan for the platform's own metadata DB — needed before Phase 9's production-readiness sign-off.
