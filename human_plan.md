Database Migration PhaseThe AI Agent's ToolImplementation Strategy

1. Assessment & Discovery✅ Custom schema.sql generator + SQL/DDL parser (sqlglot)The Assessment Agent generates schema.sql per dialect via native DDL export (e.g. pg_dump --schema-only, DBMS_METADATA.GET_DDL, mysqldump --no-data), then parses it with a SQL/DDL parser to build the object catalog and dependency graph mapping exact execution orders.

2. Infrastructure Setup🟡 Terraform (Future Extension)Currently out of scope. In the future, an Infrastructure Agent will use Terraform to provision the target cloud databases and VPCs.

3. Schema & Logic Translation✅ CrackSQLThe Schema Agent translates the DDL, Stored Procedures, and Triggers from the source dialect to the target dialect using a hybrid AST/LLM approach.

4. Data Transfer✅ Apache SeaTunnelThe Data Agent generates configuration files and executes SeaTunnel Zeta to bulk-load historical data and stream ongoing CDC changes.

5. Application Refactoring✅ OpenRewrite & AiderFor enterprise Java/Spring backends, the Code Agent triggers OpenRewrite to automatically swap ORM dialects and JDBC drivers via AST manipulation. For C++ applications or Python microservices, the agent drives Aider (an open-source AI coding CLI) to hunt down and translate raw SQL strings or SQLAlchemy configurations directly within the source tree.

6. Validation & Reconciliation✅ Custom Python ChecksumsA Validation Agent runs custom Python scripts. It batches rows from both the source and target databases, hashes the results (e.g., using Pandas or PySpark), and compares the checksums to mathematically guarantee zero data loss.

7. Cutover & Rollback✅ Kubernetes (kubectl)The Deployment Agent executes a Kubernetes rolling update (kubectl set env or updating ConfigMaps) to gradually spin up application pods configured with the new database driver and endpoint. The old pods (pointing to the legacy database) are terminated once the new ones pass health checks. If the Validation Agent detects database connection errors, it triggers an instant kubectl rollout undo to revert all pods back to the legacy database.