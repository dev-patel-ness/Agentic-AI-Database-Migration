# Known Issues & Limitations — Agentic AI Database Migration Platform

## Current Release Status

**Version:** 1.0.0 (Phase 10 Release)  
**Release Date:** 2026-10-05  
**Status:** Production-ready for demonstrations and limited production use

This document tracks known limitations and planned future enhancements.

---

## Known Issues

### 1. Oracle-to-PostgreSQL Procedure Translation Accuracy

**Severity:** MEDIUM  
**Phase:** 4 (Schema Translation)  
**Description:**  
CrackSQL translation of complex Oracle PL/SQL procedures to PostgreSQL PL/pgSQL has a confidence threshold of 0.75. Procedures below this threshold are flagged for manual review and do not auto-generate in Phase 4.

**Impact:**  
- ~5-10% of procedures may require manual SQL editing
- Low-complexity procedures (< 50 lines) typically translate with 0.90+ confidence
- Complex procedures with Oracle-specific keywords (DBMS_*, UTL_*, package-level state) drop to 0.40-0.60 confidence

**Workaround:**  
1. Review flagged procedures in the Streamlit UI (`/review/object/PROCEDURE_NAME`)
2. Accept auto-generated DDL as a starting point for manual refinement
3. Re-run validation after manual edits to confirm PL/pgSQL syntax

**Planned Fix (Phase 10+):**  
Integrate OpenRewrite (Phase 6) to provide structured refactoring hints; allow copy-paste of vendor-specific syntax from knowledge base.

---

### 2. Bedrock Rate Limits and Cost Overruns

**Severity:** MEDIUM  
**Phase:** 4 (Schema Translation)  
**Description:**  
AWS Bedrock Nova Pro model has rate limits (100 requests/minute in us-east-1). Large migrations translating 50+ procedures simultaneously may hit rate limits, causing Phase 4 to timeout.

**Impact:**  
- Migration jobs > 50 procedures may take 2-3 hours instead of 30 minutes
- Bedrock API costs scale with request volume: ~$0.003 per 1K input tokens (avg 800 tokens per procedure = $0.0024/proc × N procedures)
- Example: 200 procedures = ~$0.48; 1000 procedures = ~$2.40

**Workaround:**  
1. Implement request batching in `SchemaAgent.translate()` (Phase 4)
2. Add exponential backoff with jitter for rate-limit retries
3. Cache translation results for identical object structures (deterministic hashing)

**Monitoring:**  
- Grafana metric: `llm_call_latency_seconds` with 95th percentile (p95) > 10s indicates rate limiting
- LangSmith traces show `error_code: 429` on rate-limit hits

**Planned Fix (Phase 10+):**  
1. Implement translation result caching (Redis-backed) across migration jobs
2. Add per-job cost budget alerts in Grafana
3. Batch Bedrock requests to minimize API calls (max 10 procedures per request with token-pooling)

---

### 3. SeaTunnel Performance Plateaus on Large Data Volumes

**Severity:** LOW  
**Phase:** 5 (Data Migration)  
**Description:**  
Apache SeaTunnel achieves 5,000-10,000 rows/sec on local Docker Compose. On AWS RDS over the public internet (no Direct Connect), throughput drops to 1,000-2,000 rows/sec due to network latency.

**Impact:**  
- Migrating 10M rows takes ~1.5-2.5 hours instead of 20-30 minutes
- Database connection overhead dominates: each row-batch round-trip = 50-100ms

**Workaround:**  
1. Use AWS VPN or Direct Connect for source → RDS network link (reduces latency from 100ms to 5-10ms)
2. Increase RDS connection pool size in SeaTunnel config (default: 10, recommend: 50-100)
3. Run SeaTunnel on an EC2 instance in the same VPC/AZ as RDS (not from local machine)

**Monitoring:**  
- Grafana metric: `tool_adapter_latency_seconds{tool="seatunnel"}` with p95 > 60s indicates congestion

**Planned Fix (Phase 10+):**  
1. Implement parallel multi-table load (run 3-5 tables concurrently instead of sequentially)
2. Add CDC (Change Data Capture) for incremental updates post-bulk-load
3. Use AWS DataSync for high-volume migrations (> 100GB)

---

### 4. Kubernetes Network Policy Strictness

**Severity:** LOW  
**Phase:** 8-9 (Deployment, Security)  
**Description:**  
Network policies enforce strict deny-all ingress/egress. Any pods added outside the predefined namespaces (ns-platform, ns-app) will be isolated and unable to communicate.

**Impact:**  
- Adding Prometheus scrape targets requires manual NetworkPolicy updates
- Third-party observability tools (Datadog, New Relic) require explicit egress rules
- Adding new microservices requires Helm chart modification and NetworkPolicy patch

**Workaround:**  
Edit `infra/k8s/network-policies.yaml` to add new pod selectors/namespaces:
```yaml
namespaceSelector:
  matchLabels:
    name: my-new-namespace  # Will still be blocked unless explicitly whitelisted
```

**Planned Fix (Phase 10+):**  
1. Parameterize NetworkPolicy with Helm values (no manual YAML edits)
2. Add auto-discovery hook for new namespaces with opt-in policy templates

---

### 5. LangSmith Trace Sampling in High-Volume Jobs

**Severity:** LOW  
**Phase:** 9 (Observability)  
**Description:**  
LangSmith traces every single call. On migrations with 1000+ LLM calls, trace collection overhead can add 5-10% latency, and cloud storage costs scale linearly.

**Impact:**  
- Large migrations (1000+ procedure translations) may see 10-20% slowdown during Phase 4
- LangSmith storage costs: ~$2 per 10,000 traces (scale beyond 100,000 traces/month)

**Workaround:**  
1. Reduce trace sampling in `observability/langsmith/tracer.py`: only trace 10% of LLM calls on large jobs
2. Disable LangSmith for local dev (set `LANGSMITH_API_KEY=` empty)
3. Use a local Jaeger instance for non-cloud tracing during testing

**Planned Fix (Phase 10+):**  
1. Implement adaptive sampling: trace 100% of errors, 10% of successes
2. Batch LangSmith uploads (5-10 traces per batch) instead of per-call
3. Add per-job trace retention policy (delete traces > 30 days old)

---

### 6. Terraform State Drift in Long-Lived Clusters

**Severity:** MEDIUM  
**Phase:** 8 (Deployment)  
**Description:**  
Terraform state files can drift if EKS nodes, RDS parameter groups, or VPC routes are manually modified outside Terraform. `terraform plan` may show unexpected deletions/recreations.

**Impact:**  
- Manual Helm updates (kubectl apply) conflict with Terraform-managed resources
- RDS snapshot restores break Terraform references
- Security group rule additions via AWS Console will be lost on next `terraform destroy`

**Workaround:**  
1. Always use `terraform plan` before `terraform apply` to review changes
2. Implement `terraform import` for manually created resources
3. Lock Terraform state to prevent concurrent modifications: `terraform state lock`
4. Use `terraform -lock=false` only for read-only operations

**Planned Fix (Phase 10+):**  
1. Implement automated state drift detection in CI/CD (run `terraform plan` nightly)
2. Add alerts to Grafana for resource creation/deletion outside Terraform

---

### 7. Pod Restart Cascade on Memory Pressure

**Severity:** MEDIUM  
**Phase:** 8-9 (Deployment, Observability)  
**Description:**  
If node memory exceeds 90%, Kubernetes evicts pods. The cascade can trigger multiple pod restarts within 60 seconds, causing brief service unavailability.

**Impact:**  
- Large migration jobs (processing 100,000+ rows in memory) can cause OOM kills
- Pod restart count exceeds thresholds (currently: max 3 restarts per pod before considered unhealthy)
- Deployment rollback may be triggered incorrectly if pod restarts coincide with rollout

**Workaround:**  
1. Monitor pod memory usage: `kubectl top pods -n ns-platform`
2. Increase node group size or switch to larger instance type (t3.xlarge → m5.2xlarge)
3. Add memory requests/limits in Helm values (currently: 256MB platform, 512MB app — may be tight for 100M+ row migrations)

**Planned Fix (Phase 10+):**  
1. Implement in-database row buffering (reduce in-memory row count)
2. Stream data instead of batch processing
3. Add PVC (persistent volume claim) for intermediate spill-to-disk on memory pressure

---

## Limitations

### Supported Dialects (by design, intentional scope)

**Supported:** Oracle XE, MySQL 8.0+, PostgreSQL 12+

**Not Supported (out of scope):**  
- SQL Server (requires TSQL parser, not in CrackSQL)
- Snowflake, BigQuery, Redshift (cloud-only, different paradigm)
- Legacy systems (Sybase, Informix) — deprecated tools

### Application Code Refactoring

**Status:** Phase 6 (Deliberately Skipped)

Application code refactoring (OpenRewrite + Aider) is designed but not implemented in Phase 1.0. Users must manually update application code for dialect-specific SQL syntax changes.

**Example:** Oracle-to-PostgreSQL code changes:
```java
// Oracle
String sql = "SELECT COUNT(*) FROM DUAL";  // Oracle doesn't have FROM clause for single-row queries

// PostgreSQL (manual change required)
String sql = "SELECT COUNT(*)";  // Standard SQL
```

**Planned for Phase 10+:**  
Full Code Agent implementation with OpenRewrite + Aider for automatic refactoring.

### Multi-Tenant Isolation

**Status:** Not Implemented

The platform assumes single-tenant use per EKS cluster. Multi-tenant support (isolated job data, RBAC per tenant, billing per tenant) is a Phase 10+ enhancement.

**Current Workaround:**  
Deploy separate EKS clusters per tenant and manage independently.

### Disaster Recovery for Metadata DB

**Status:** Manual Process

The platform's own metadata DB (PostgreSQL on RDS) has automated backups (7-day retention) but no automated failover. In case of metadata DB failure:

1. Restore from RDS snapshot (manual step, ~10 minutes)
2. Redeploy orchestrator pods (they auto-recover from checkpointer)
3. Resume paused jobs from last checkpoint

**Planned for Phase 10+:**  
Implement RDS Multi-AZ failover (automatic, <1 minute), read replicas for queries.

### Audit Trail Completeness

**Status:** Partial

ApprovalRecords and deployment logs are persisted, but not all system events are audit-logged. Missing events:

- Who viewed a migration plan (no access logs)
- Who triggered Bedrock calls (no cost allocation per user)
- Schema change history (what changed between plan v1 and v2)

**Planned for Phase 10+:**  
Implement comprehensive audit logging with PostgreSQL JSONB event stream.

---

## Performance Baseline

### Measured Performance (from Phase 10 E2E testing)

| Phase | Object Type | Metric | Value |
|-------|------------|--------|-------|
| 2 (Discovery) | 15 tables | Time | 12 seconds |
| 3 (Planning) | 30 objects | Time | 8 seconds |
| 4 (Translation) | 2 procedures | Time | 15 seconds |
| 4 (Translation) | 2 procedures | Bedrock latency p95 | 450ms |
| 5 (Data) | 6,050 rows | Throughput | 8,000 rows/sec |
| 5 (Data) | 6,050 rows | Time | 0.75 seconds |
| 7 (Validation) | 3 tables | Time | 8 seconds |
| 8 (Deployment) | Rolling update | Rollout time | 50 seconds |
| 8 (Deployment) | 2 replicas | Pod readiness | 35 seconds |
| 9 (Observability) | Trace collection | Overhead | <1% |

### Scaling Limits (untested, estimated)

| Dimension | Limit | Bottleneck |
|-----------|-------|-----------|
| Objects per migration | 10,000 | Bedrock rate limit (100 req/min); translate in batches |
| Rows per table | 100M | SeaTunnel memory/throughput; use parallel load |
| Jobs in flight | 5-10 | EKS pod capacity (adjust node group) |
| Bedrock cost per job | $50-100 | Large translation volumes; implement caching |
| LangSmith traces | 100,000/month | Trace storage costs; implement sampling |

---

## Workarounds for Common Scenarios

### Scenario 1: Schema with 100+ Procedures

**Problem:** Phase 4 translation takes 2+ hours due to Bedrock rate limits.

**Solution:**  
1. Split schema into logical groups (10-20 procedures per batch)
2. Run parallel migration jobs (one per group) on separate EKS pods
3. Merge results in Phase 5 (data migration is independent per table)

### Scenario 2: Oracle Migration Over Slow Network

**Problem:** SeaTunnel throughput drops to 500 rows/sec over high-latency WAN.

**Solution:**  
1. Pre-stage source database replica on AWS (RDS Oracle)
2. Run migration job from same AZ as replica
3. Replication lag: <1 second for incremental changes

### Scenario 3: Rolling Back Failed Deployment

**Problem:** Helm upgrade failed; need to revert to previous image.

**Solution:**  
```bash
# Automatic (Phase 8 deployment):
kubectl rollout undo deployment/capstone-platform -n ns-platform

# Manual override:
helm rollback capstone-platform -n ns-platform --revision 1
```

---

## Roadmap for Phase 10+ Enhancements

### Q1 2027: Production Hardening
- [x] Network policies (zero-trust networking)
- [x] Pod security policies (non-root, no escalation)
- [ ] Multi-tenant isolation
- [ ] Audit trail completeness
- [ ] RDS Multi-AZ automatic failover

### Q2 2027: Performance & Cost Optimization
- [ ] SeaTunnel parallel multi-table load
- [ ] Bedrock translation result caching (Redis)
- [ ] LangSmith adaptive sampling
- [ ] Cost budget alerts in Grafana

### Q3 2027: Feature Parity
- [ ] Phase 6: Application code refactoring (OpenRewrite + Aider)
- [ ] CDC (Change Data Capture) for incremental loads
- [ ] Snowflake/BigQuery dialect support

### Q4 2027: Operational Excellence
- [ ] State drift detection (nightly Terraform plan)
- [ ] Self-healing pod restarts (memory pressure mitigation)
- [ ] Automated capacity planning

---

## Reporting Issues

To report a new issue or limitation:

1. Check this document (may already be a known issue)
2. Reproduce on Phase 10 E2E tests: `pytest tests/e2e/test_complete_workflow.py -v`
3. File GitHub issue with: environment, reproduction steps, logs
4. Tag appropriately: `bug`, `limitation`, `performance`, `phase-N`

For production support, contact: [your-team-email]

---

**Last Updated:** 2026-10-05  
**Prepared By:** Capstone Platform Team  
**For:** Phase 10 Release (Demo & Deliverables)
