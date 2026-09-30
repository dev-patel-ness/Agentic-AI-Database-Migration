-- PostgreSQL metadata database initialization
-- Creates the platform's metadata schema including PGVector support

-- Enable PGVector extension
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Migration Jobs table
CREATE TABLE IF NOT EXISTS migration_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    source_dialect VARCHAR(50) NOT NULL,
    target_dialect VARCHAR(50) NOT NULL,
    source_config JSONB NOT NULL,
    target_config JSONB NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'CREATED',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_by VARCHAR(255),
    updated_by VARCHAR(255),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Object Catalog - tracks discovered database objects
CREATE TABLE IF NOT EXISTS object_catalog_entries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES migration_jobs(id) ON DELETE CASCADE,
    object_type VARCHAR(50) NOT NULL,
    object_name VARCHAR(255) NOT NULL,
    schema_name VARCHAR(255),
    definition TEXT,
    dependencies TEXT[], -- Array of dependent object names
    is_system BOOLEAN DEFAULT FALSE,
    complexity_score FLOAT,
    risk_level VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Note: LangGraph's Postgres checkpointer (orchestrator/checkpointer.py) owns
-- and creates its own `checkpoints` / `checkpoint_blobs` / `checkpoint_writes` /
-- `checkpoint_migrations` tables via `PostgresSaver.setup()` — do not define a
-- hand-rolled `checkpoints` table here, it collides with that schema.

-- Approval Records - audit trail for HITL decisions
CREATE TABLE IF NOT EXISTS approval_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES migration_jobs(id) ON DELETE CASCADE,
    phase VARCHAR(100) NOT NULL,
    approval_type VARCHAR(50) NOT NULL,
    request_data JSONB,
    approval_decision VARCHAR(50),
    approval_reason TEXT,
    approved_by VARCHAR(255),
    approved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Discovery Results - output of schema discovery/assessment phase
CREATE TABLE IF NOT EXISTS discovery_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES migration_jobs(id) ON DELETE CASCADE,
    table_count INT,
    view_count INT,
    procedure_count INT,
    function_count INT,
    trigger_count INT,
    total_objects INT,
    discovery_status VARCHAR(50),
    discovery_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Translation Results - output of schema/logic translation phase
CREATE TABLE IF NOT EXISTS translation_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES migration_jobs(id) ON DELETE CASCADE,
    source_object_id UUID REFERENCES object_catalog_entries(id),
    source_ddl TEXT,
    target_ddl TEXT,
    translation_status VARCHAR(50),
    confidence_score FLOAT,
    errors TEXT[],
    warnings TEXT[],
    -- Phase 5: whether target_ddl was actually executed against the target DB
    -- (views/procedures/functions/triggers/foreign_keys -- SeaTunnel only
    -- auto-creates tables), applied once the Data Agent has created the
    -- target tables. NULL until an apply attempt is made.
    applied_status VARCHAR(50),
    applied_error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- Data Migration Results - output of data migration phase
CREATE TABLE IF NOT EXISTS data_migration_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES migration_jobs(id) ON DELETE CASCADE,
    table_name VARCHAR(255),
    source_row_count BIGINT,
    target_row_count BIGINT,
    rows_migrated BIGINT,
    migration_status VARCHAR(50),
    duration_seconds INT,
    throughput_rows_per_sec FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Validation Results - output of validation phase
CREATE TABLE IF NOT EXISTS validation_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES migration_jobs(id) ON DELETE CASCADE,
    table_name VARCHAR(255),
    validation_status VARCHAR(50),
    row_count_match BOOLEAN,
    hash_match BOOLEAN,
    mismatches INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Knowledge Base - stores embeddings for migration rules and patterns.
-- 1024 dims to match Titan Text Embeddings v2 (agents/assessment_agent/embeddings.py),
-- the same model used for discovery_embeddings below -- keeps every embedding
-- column in this DB on one consistent model/dimension.
CREATE TABLE IF NOT EXISTS knowledge_base_entries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    source_dialect VARCHAR(50),
    target_dialect VARCHAR(50),
    content TEXT NOT NULL,
    embedding VECTOR(1024),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Discovery Embeddings - Titan Text Embeddings v2 (1024-dim) for each
-- discovered object, used for RAG retrieval by the Planner/Schema agents.
CREATE TABLE IF NOT EXISTS discovery_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES migration_jobs(id) ON DELETE CASCADE,
    object_type VARCHAR(50) NOT NULL,
    object_name VARCHAR(255) NOT NULL,
    embedding VECTOR(1024),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_discovery_embeddings_job_id ON discovery_embeddings(job_id);

-- Create indexes for performance
CREATE INDEX idx_migration_jobs_status ON migration_jobs(status);
CREATE INDEX idx_migration_jobs_created_at ON migration_jobs(created_at);
CREATE INDEX idx_object_catalog_job_id ON object_catalog_entries(job_id);
CREATE INDEX idx_approval_records_job_id ON approval_records(job_id);
CREATE INDEX idx_kb_embedding ON knowledge_base_entries USING ivfflat (embedding vector_cosine_ops);

GRANT CONNECT ON DATABASE migration_metadata TO postgres;
GRANT USAGE ON SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;
