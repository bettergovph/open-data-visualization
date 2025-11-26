#!/usr/bin/env python3
"""Verify party_list_members.parquet file"""

import duckdb
from pathlib import Path

parquet_path = Path('data/parquet/party_list_members.parquet')
conn = duckdb.connect()
try:
    # Check schema
    cols = conn.execute(f'DESCRIBE SELECT * FROM read_parquet(\'{parquet_path}\')').fetchall()
    print('📋 party_list_members.parquet columns:')
    for col in cols:
        print(f'  - {col[0]} ({col[1]})')
    
    # Get count
    count = conn.execute(f'SELECT COUNT(*) FROM read_parquet(\'{parquet_path}\')').fetchone()[0]
    print(f'\n📊 Total records: {count}')
    
    # Check sample data
    sample = conn.execute(f'SELECT * FROM read_parquet(\'{parquet_path}\') LIMIT 10').fetchall()
    print(f'\n📋 Sample data (first 10 records):')
    for row in sample:
        print(f'  ID {row[0]}: person_id={row[1]}, party_code={row[2]}, party_list_number={row[3]}, party_name={row[4]}')
    
    # Check unique party names
    unique_parties = conn.execute(f'''
        SELECT DISTINCT party_name, party_list_number, COUNT(*) as count
        FROM read_parquet('{parquet_path}')
        WHERE party_name IS NOT NULL
        GROUP BY party_name, party_list_number
        ORDER BY count DESC
    ''').fetchall()
    
    print(f'\n📋 Unique party names ({len(unique_parties)} found):')
    for party in unique_parties[:10]:
        print(f'  - {party[0]} (party_list_number={party[1]}, count={party[2]})')
finally:
    conn.close()









