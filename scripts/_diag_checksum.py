from tool_adapters.checksum_adapter import ChecksumAdapter

a = ChecksumAdapter()
cfg = a.prepare({
    "table_name": "DEPARTMENTS",
    "source_dialect": "oracle",
    "target_dialect": "postgresql",
    "source_connection": {"host": "localhost", "port": 1521, "username": "sample_user", "password": "oracle_dev_password", "database": "XEPDB1"},
    "target_connection": {"host": "localhost", "port": 5433, "username": "postgres", "password": "postgres_dev_password", "database": "sample_source"},
    "source_namespace": "sample_user",
    "target_namespace": "sample",
})
r = a.run(cfg)
print("success=", r.success)
print("error=", r.error)
print("output=", r.output)
