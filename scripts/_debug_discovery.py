#!/usr/bin/env python3
"""Debug schema discovery."""
import os, sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()
from dialects.connections import connect

config = {
    'host': 'localhost',
    'port': 5433,
    'user': 'postgres',
    'password': 'postgres_dev_password',
    'database': 'sample_source'
}

print("Connecting to PostgreSQL...")
with connect('postgresql', config) as conn:
    cursor = conn.cursor()
    
    # Check schemas
    cursor.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'sample'")
    schema = cursor.fetchone()
    print(f"Schema 'sample' exists: {bool(schema)}")
    
    # Check tables
    cursor.execute("""
        SELECT table_schema, table_name FROM information_schema.tables 
        WHERE table_schema = 'sample' ORDER BY table_name
    """)
    tables = cursor.fetchall()
    print(f"Found {len(tables)} tables:")
    for schema_name, table_name in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {schema_name}.{table_name}")
        count = cursor.fetchone()[0]
        print(f"  {schema_name}.{table_name}: {count} rows")
