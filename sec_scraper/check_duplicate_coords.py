#!/usr/bin/env python3
"""Check for projects with duplicate coordinates in DIME database"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv('visualization.env')

async def check_duplicate_coordinates():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST'),
        port=int(os.getenv('POSTGRES_PORT')),
        user=os.getenv('POSTGRES_USER'),
        password=os.getenv('POSTGRES_PASSWORD'),
        database=os.getenv('POSTGRES_DB_DIME')
    )
    
    # Get all coordinates with duplicates
    rows = await conn.fetch('''
        SELECT latitude, longitude, COUNT(*) as count
        FROM projects
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        GROUP BY latitude, longitude
        HAVING COUNT(*) > 1
        ORDER BY count DESC
        LIMIT 20
    ''')
    
    print(f'🔍 Found {len(rows)} coordinate pairs with duplicates')
    print()
    
    total_duplicates = 0
    for row in rows:
        count = row['count']
        total_duplicates += count
        print(f'📍 Lat: {row["latitude"]}, Long: {row["longitude"]} - {count} projects')
        
        # Show sample projects at this location
        projects = await conn.fetch('''
            SELECT project_name, city 
            FROM projects 
            WHERE latitude = $1 AND longitude = $2
            LIMIT 5
        ''', row['latitude'], row['longitude'])
        
        for p in projects:
            city = p['city'] or 'Unknown'
            name = p['project_name'][:80] if p['project_name'] else 'Unnamed'
            print(f'   - {name} ({city})')
        
        if count > 5:
            print(f'   ... and {count - 5} more projects')
        print()
    
    print(f'📊 Total projects with duplicate coordinates: {total_duplicates}')
    
    # Get total projects
    total = await conn.fetchval('SELECT COUNT(*) FROM projects WHERE latitude IS NOT NULL AND longitude IS NOT NULL')
    print(f'📊 Total projects with coordinates: {total}')
    print(f'📊 Percentage with duplicates: {(total_duplicates/total*100):.2f}%')
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(check_duplicate_coordinates())

