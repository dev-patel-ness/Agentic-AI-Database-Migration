import psycopg

conn = psycopg.connect(
    host="localhost", port=5432, dbname="migration_metadata",
    user="postgres", password="postgres_dev_password",
)
cur = conn.cursor()
cur.execute(
    "SELECT id, created_at FROM migration_jobs ORDER BY created_at DESC LIMIT 3"
)
rows = cur.fetchall()
for row in rows:
    print(row)

latest_job = rows[0][0]
print("--- latest job:", latest_job, "---")
cur.execute(
    "SELECT oce.object_type, oce.object_name, tr.applied_status, tr.target_ddl, tr.applied_error "
    "FROM translation_results tr JOIN object_catalog_entries oce ON oce.id = tr.source_object_id "
    "WHERE tr.job_id = %s ORDER BY tr.created_at",
    (str(latest_job),),
)
for row in cur.fetchall():
    print(row)
