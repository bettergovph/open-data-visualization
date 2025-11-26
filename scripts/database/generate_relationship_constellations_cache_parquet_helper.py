"""
Helper functions for converting PostgreSQL queries to DuckDB/Parquet queries
Used by generate_relationship_constellations_cache.py
"""
import duckdb
from pathlib import Path

PARQUET_DIR = Path(__file__).parent.parent.parent / 'data' / 'parquet'
POLITICAL_DYNASTIES_PARQUET = PARQUET_DIR / 'political_dynasties.parquet'
RELATIONSHIPS_PARQUET = PARQUET_DIR / 'relationships.parquet'
PARTY_LIST_MEMBERS_PARQUET = PARQUET_DIR / 'party_list_members.parquet'
DYNASTY_DUCKDB = PARQUET_DIR / 'dynasty_data.duckdb'

class DuckDBQueryHelper:
    """Helper class to execute DuckDB queries on parquet files and DuckDB database"""
    
    def __init__(self):
        self.conn = duckdb.connect()
        # Attach DuckDB database if it exists
        if DYNASTY_DUCKDB.exists():
            self.conn.execute(f"ATTACH '{DYNASTY_DUCKDB}' AS dynasty_db (TYPE DUCKDB)")
    
    def execute(self, query, params=None):
        """Execute a query and return results as list of dicts"""
        # Replace table names with parquet/duckdb references
        query = self._replace_table_refs(query)
        
        if params:
            # DuckDB uses $1, $2, etc. for parameters
            result = self.conn.execute(query, params).fetchall()
        else:
            result = self.conn.execute(query).fetchall()
        
        # Get column names
        columns = [desc[0] for desc in self.conn.description]
        
        # Convert to list of dicts
        return [dict(zip(columns, row)) for row in result]
    
    def fetchval(self, query, params=None):
        """Execute a query and return a single value"""
        query = self._replace_table_refs(query)
        if params:
            result = self.conn.execute(query, params).fetchone()
        else:
            result = self.conn.execute(query).fetchone()
        return result[0] if result else None
    
    def fetchrow(self, query, params=None):
        """Execute a query and return a single row as dict"""
        results = self.execute(query, params)
        return results[0] if results else None
    
    def _replace_table_refs(self, query):
        """Replace PostgreSQL table references with DuckDB/Parquet references"""
        # Replace political_dynasties with parquet file
        query = query.replace(
            'FROM political_dynasties',
            f"FROM read_parquet('{POLITICAL_DYNASTIES_PARQUET}')"
        )
        query = query.replace(
            'JOIN political_dynasties',
            f"JOIN read_parquet('{POLITICAL_DYNASTIES_PARQUET}')"
        )
        
        # Replace relationships with parquet file
        query = query.replace(
            'FROM relationships',
            f"FROM read_parquet('{RELATIONSHIPS_PARQUET}')"
        )
        query = query.replace(
            'JOIN relationships',
            f"JOIN read_parquet('{RELATIONSHIPS_PARQUET}')"
        )
        
        # Replace party_list_members with parquet file if it exists
        if PARTY_LIST_MEMBERS_PARQUET.exists():
            query = query.replace('FROM party_list_members', f"FROM read_parquet('{PARTY_LIST_MEMBERS_PARQUET}')")
            query = query.replace('JOIN party_list_members', f"JOIN read_parquet('{PARTY_LIST_MEMBERS_PARQUET}')")
        # Replace tables that exist in dynasty_db
        elif DYNASTY_DUCKDB.exists():
            query = query.replace('FROM party_list_members', 'FROM dynasty_db.party_list_members')
            query = query.replace('JOIN party_list_members', 'JOIN dynasty_db.party_list_members')
        
        if DYNASTY_DUCKDB.exists():
            for table in ['contractor_dynasty_matches']:
                query = query.replace(f'FROM {table}', f'FROM dynasty_db.{table}')
                query = query.replace(f'JOIN {table}', f'JOIN dynasty_db.{table}')
        
        # Replace politician_contractors with parquet file (it's exported separately)
        from pathlib import Path
        PARQUET_DIR = Path(__file__).parent.parent.parent / 'data' / 'parquet'
        POLITICIAN_CONTRACTORS_PARQUET = PARQUET_DIR / 'politician_contractors.parquet'
        if POLITICIAN_CONTRACTORS_PARQUET.exists():
            query = query.replace('FROM politician_contractors', f"FROM read_parquet('{POLITICIAN_CONTRACTORS_PARQUET}')")
            query = query.replace('JOIN politician_contractors', f"JOIN read_parquet('{POLITICIAN_CONTRACTORS_PARQUET}')")
        
        return query
    
    def close(self):
        """Close the connection"""
        self.conn.close()

