#!/usr/bin/env python3
"""
Create standard views for GAA budget years 2017-2021
Follows the same pattern as 2022-2025
"""

import psycopg2


class GAAViewGenerator:
    def __init__(self):
        self.db_config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'budget_analysis',
            'user': 'budget_admin',
            'password': 'wuQ5gBYCKkZiOGb61chLcByMu'
        }
    
    def create_columns_metadata_view(self, conn, year):
        """Create columns metadata view"""
        cursor = conn.cursor()
        view_name = f"budget_{year}_columns_metadata"
        
        # Drop if exists
        cursor.execute(f"DROP VIEW IF EXISTS {view_name}")
        
        # Create view
        sql = f"""
        CREATE VIEW {view_name} AS
        SELECT 
            column_name,
            data_type,
            is_nullable,
            column_default,
            character_maximum_length,
            numeric_precision,
            numeric_scale,
            ordinal_position
        FROM information_schema.columns
        WHERE table_name = 'budget_{year}'
        AND column_name NOT IN ('id', 'source_file', 'created_at')
        ORDER BY ordinal_position
        """
        
        cursor.execute(sql)
        conn.commit()
        cursor.close()
        print(f"   ✅ Created {view_name}")
    
    def create_individual_value_views(self, conn, year, column_name):
        """Create view for individual column distinct values"""
        cursor = conn.cursor()
        view_name = f"budget_{year}_{column_name}_values"
        
        # Drop if exists
        cursor.execute(f"DROP VIEW IF EXISTS {view_name}")
        
        # Create view
        sql = f"""
        CREATE VIEW {view_name} AS
        SELECT 
            {column_name} AS value,
            COUNT(*) AS count
        FROM budget_{year}
        WHERE {column_name} IS NOT NULL 
        AND {column_name} <> 'INVALID'
        AND {column_name} <> ''
        GROUP BY {column_name}
        ORDER BY COUNT(*) DESC, {column_name}
        """
        
        cursor.execute(sql)
        conn.commit()
        cursor.close()
        print(f"   ✅ Created {view_name}")
    
    def get_text_columns(self, conn, year):
        """Get list of text columns for a table"""
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'budget_{year}'
            AND data_type = 'text'
            AND column_name NOT IN ('source_file', 'created_at')
            ORDER BY ordinal_position
        """)
        columns = [row[0] for row in cursor.fetchall()]
        cursor.close()
        return columns
    
    def create_filter_values_view(self, conn, year):
        """Create combined filter values view"""
        cursor = conn.cursor()
        view_name = f"budget_{year}_filter_values"
        
        # Get text columns
        text_columns = self.get_text_columns(conn, year)
        
        if not text_columns:
            print(f"   ⚠️  No text columns found for budget_{year}")
            cursor.close()
            return
        
        # Drop if exists
        cursor.execute(f"DROP VIEW IF EXISTS {view_name}")
        
        # Build UNION ALL query
        union_parts = []
        for col in text_columns:
            union_parts.append(f"""
            SELECT 
                '{col}'::text AS column_name,
                {col} AS value,
                COUNT(*) AS count
            FROM budget_{year}
            WHERE {col} IS NOT NULL 
            AND {col} <> 'INVALID'
            AND {col} <> ''
            GROUP BY {col}
            """)
        
        # Also add region_code if it exists
        cursor.execute(f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'budget_{year}'
            AND column_name = 'uacs_reg_id'
        """)
        if cursor.fetchone():
            union_parts.append(f"""
            SELECT 
                'uacs_reg_id'::text AS column_name,
                uacs_reg_id::text AS value,
                COUNT(*) AS count
            FROM budget_{year}
            WHERE uacs_reg_id IS NOT NULL 
            AND uacs_reg_id <> -1
            GROUP BY uacs_reg_id
            """)
        
        sql = f"""
        CREATE VIEW {view_name} AS
        {' UNION ALL '.join(union_parts)}
        ORDER BY 1, 3 DESC, 2
        """
        
        cursor.execute(sql)
        conn.commit()
        cursor.close()
        print(f"   ✅ Created {view_name}")
    
    def create_views_for_year(self, year):
        """Create all views for a specific year"""
        print(f"\n{'='*80}")
        print(f" Creating views for GAA {year}")
        print(f"{'='*80}")
        
        conn = psycopg2.connect(**self.db_config)
        
        try:
            # 1. Columns metadata
            self.create_columns_metadata_view(conn, year)
            
            # 2. Get text columns
            text_columns = self.get_text_columns(conn, year)
            
            # 3. Create individual value views for each text column
            print(f"\n   Creating individual value views for {len(text_columns)} columns...")
            for col in text_columns:
                self.create_individual_value_views(conn, year, col)
            
            # 4. Create combined filter values view
            print(f"\n   Creating combined filter values view...")
            self.create_filter_values_view(conn, year)
            
            print(f"\n   ✅ All views created for {year}")
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    def run(self):
        """Create views for all missing years"""
        print("=" * 80)
        print(" GAA VIEW GENERATOR (2017-2021)")
        print("=" * 80)
        print("\nCreating standard views for years 2017-2021...")
        
        for year in [2017, 2018, 2019, 2020, 2021]:
            self.create_views_for_year(year)
        
        print(f"\n{'='*80}")
        print(" VIEW GENERATION COMPLETE")
        print(f"{'='*80}")
        
        # Summary
        print(f"\n📊 Summary:")
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.views 
            WHERE table_schema = 'public'
            AND table_name LIKE 'budget_%'
        """)
        total_views = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        
        print(f"   Total budget views in database: {total_views}")


if __name__ == "__main__":
    generator = GAAViewGenerator()
    generator.run()

