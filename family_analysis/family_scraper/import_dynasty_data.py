#!/usr/bin/env python3
"""
Import ASoG Political Dynasties Dataset Excel file into PostgreSQL database
"""

import asyncio
import asyncpg
import pandas as pd
import os
from dotenv import load_dotenv
from datetime import datetime

async def import_dynasty_data():
    """Import the Excel file into PostgreSQL dynasty database"""
    
    # Load environment variables
    load_dotenv()
    
    # Database connection parameters
    host = os.getenv('POSTGRES_HOST', 'localhost')
    port = int(os.getenv('POSTGRES_PORT', 5432))
    user = os.getenv('POSTGRES_USER', 'budget_admin')
    password = os.getenv('POSTGRES_PASSWORD', '')
    database = 'dynasty'  # New database for dynasty data
    
    print("🚀 Starting Political Dynasties data import...")
    
    try:
        # First, create the database if it doesn't exist
        # Connect to postgres database to create the dynasty database
        admin_conn = await asyncpg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database='postgres'  # Connect to default postgres database
        )
        
        # Check if dynasty database exists, create if not
        db_exists = await admin_conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", database
        )
        
        if not db_exists:
            print(f"📊 Creating database '{database}'...")
            await admin_conn.execute(f'CREATE DATABASE "{database}"')
            print(f"✅ Database '{database}' created successfully")
        else:
            print(f"✅ Database '{database}' already exists")
        
        await admin_conn.close()
        
        # Now connect to the dynasty database
        conn = await asyncpg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database
        )
        
        print("📖 Reading Excel file...")
        # Read the Excel file
        excel_file = 'database/ASoG-POLITICAL-DYNASTIES-DATASET-V2016.xlsx'
        
        # Check for multiple sheets
        xl_file = pd.ExcelFile(excel_file)
        print(f"📋 Available sheets: {xl_file.sheet_names}")
        
        # Try to find the sheet with actual data (not just metadata)
        data_sheet = None
        for sheet_name in xl_file.sheet_names:
            df_test = pd.read_excel(excel_file, sheet_name=sheet_name)
            print(f"📊 Sheet '{sheet_name}': {len(df_test)} rows, {len(df_test.columns)} columns")
            
            # Check if this sheet has substantial data (more than just metadata)
            if len(df_test) > 10 and len(df_test.columns) > 2:
                data_sheet = sheet_name
                print(f"✅ Found data sheet: '{sheet_name}'")
                break
        
        if data_sheet is None:
            # If no clear data sheet, use the first one with most rows
            data_sheet = xl_file.sheet_names[0]
            print(f"⚠️ No clear data sheet found, using first sheet: '{data_sheet}'")
        
        df = pd.read_excel(excel_file, sheet_name=data_sheet)
        
        print(f"📊 Excel file loaded from sheet '{data_sheet}': {len(df)} rows, {len(df.columns)} columns")
        print(f"📋 Columns: {list(df.columns)}")
        
        # Display first few rows to understand the structure
        print("\n📋 First 5 rows:")
        print(df.head())
        
        # Create the table
        print("\n🏗️ Creating table structure...")
        
        # Generate column definitions based on the DataFrame
        column_definitions = []
        for col in df.columns:
            # Clean column name (replace spaces and special chars with underscores)
            clean_col = col.replace(' ', '_').replace('-', '_').replace('(', '').replace(')', '').lower()
            
            # Determine data type based on the column content
            if df[col].dtype == 'object':  # String/text
                # Check if it's actually numeric data stored as strings
                try:
                    # Try to convert to numeric to see if it's actually numbers
                    numeric_series = pd.to_numeric(df[col], errors='coerce')
                    if not numeric_series.isna().all():  # If most values are numeric
                        if numeric_series.dtype in ['int64', 'int32']:
                            column_definitions.append(f'"{clean_col}" INTEGER')
                        else:
                            column_definitions.append(f'"{clean_col}" DECIMAL')
                    else:
                        # Check string length for VARCHAR vs TEXT
                        max_length = df[col].astype(str).str.len().max()
                        if pd.isna(max_length) or max_length < 255:
                            column_definitions.append(f'"{clean_col}" VARCHAR(255)')
                        else:
                            column_definitions.append(f'"{clean_col}" TEXT')
                except:
                    # If conversion fails, treat as text
                    max_length = df[col].astype(str).str.len().max()
                    if pd.isna(max_length) or max_length < 255:
                        column_definitions.append(f'"{clean_col}" VARCHAR(255)')
                    else:
                        column_definitions.append(f'"{clean_col}" TEXT')
            elif df[col].dtype in ['int64', 'int32']:
                column_definitions.append(f'"{clean_col}" INTEGER')
            elif df[col].dtype in ['float64', 'float32']:
                column_definitions.append(f'"{clean_col}" DECIMAL')
            elif 'datetime' in str(df[col].dtype):
                column_definitions.append(f'"{clean_col}" TIMESTAMP')
            else:
                column_definitions.append(f'"{clean_col}" TEXT')
        
        # Drop existing table if it exists (to recreate with correct structure)
        await conn.execute("DROP TABLE IF EXISTS political_dynasties")
        print("🗑️ Dropped existing table (if any)")
        
        # Create table SQL
        create_table_sql = f"""
        CREATE TABLE political_dynasties (
            id SERIAL PRIMARY KEY,
            {', '.join(column_definitions)},
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        
        await conn.execute(create_table_sql)
        print("✅ Table 'political_dynasties' created successfully")
        
        # Insert data
        print("📥 Inserting data into database...")
        
        # Prepare data for insertion
        records = []
        for _, row in df.iterrows():
            record = {}
            for col in df.columns:
                clean_col = col.replace(' ', '_').replace('-', '_').replace('(', '').replace(')', '').lower()
                value = row[col]
                
                # Handle NaN values
                if pd.isna(value):
                    record[clean_col] = None
                else:
                    # Convert to appropriate type based on column
                    if col == 'Year':  # Year should be integer
                        try:
                            record[clean_col] = int(value) if value is not None else None
                        except (ValueError, TypeError):
                            record[clean_col] = None
                    elif col == 'fat':  # fat column should be integer (0 or 1)
                        try:
                            record[clean_col] = int(value) if value is not None else None
                        except (ValueError, TypeError):
                            record[clean_col] = None
                    else:
                        # For all other columns, keep as string
                        record[clean_col] = str(value) if value is not None else None
            
            records.append(record)
        
        # Insert records in batches
        batch_size = 1000
        total_inserted = 0
        
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            
            if batch:
                # Get column names for the INSERT statement
                sample_record = batch[0]
                columns = list(sample_record.keys())
                
                # Create INSERT statement
                placeholders = ', '.join([f'${j+1}' for j in range(len(columns))])
                insert_sql = f"""
                INSERT INTO political_dynasties ({', '.join([f'"{col}"' for col in columns])})
                VALUES ({placeholders})
                """
                
                # Prepare batch data
                batch_data = []
                for record in batch:
                    batch_data.append([record[col] for col in columns])
                
                # Execute batch insert
                await conn.executemany(insert_sql, batch_data)
                total_inserted += len(batch)
                
                print(f"📥 Inserted {total_inserted}/{len(records)} records...")
        
        print(f"✅ Successfully imported {total_inserted} records")
        
        # Get final statistics
        total_count = await conn.fetchval("SELECT COUNT(*) FROM political_dynasties")
        print(f"📊 Final record count: {total_count}")
        
        # Show sample of imported data
        sample_data = await conn.fetch("SELECT * FROM political_dynasties LIMIT 3")
        print(f"\n📋 Sample imported data:")
        for i, record in enumerate(sample_data, 1):
            print(f"  Record {i}: {dict(record)}")
        
        print(f"\n🎉 Political Dynasties data import completed successfully!")
        print(f"   • Database: {database}")
        print(f"   • Table: political_dynasties")
        print(f"   • Records: {total_count}")
        print(f"   • Imported at: {datetime.now().isoformat()}")
        
    except Exception as e:
        print(f"❌ Error importing data: {e}")
        raise
    finally:
        if 'conn' in locals():
            await conn.close()

if __name__ == "__main__":
    asyncio.run(import_dynasty_data())
