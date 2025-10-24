#!/usr/bin/env python3
"""
Update the API to use the new normalized relationships table.
This replaces the old connection_id/connection_type logic with proper many-to-many relationships.
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def update_api_for_relationships():
    """Update the dynasty family API to use the relationships table"""
    
    # Read the current API file
    with open('/home/joebert/open-data-visualization/visualization.py', 'r') as f:
        content = f.read()
    
    # Replace the old connected members query with the new relationships-based query
    old_query = '''                    # Find people who are connected to this family (including transitive connections)
                    # This includes people whose connection_id points to any family member OR to connected members
                    connected_query = """
                        WITH RECURSIVE connected_people AS (
                            -- Base case: people directly connected to family members
                            SELECT 
                                id,
                                first_name,
                                last_name,
                                position,
                                province,
                                municipality_city,
                                year,
                                fat,
                                connection,
                                connection_type,
                                connection_id,
                                nickname,
                                1 as level
                            FROM political_dynasties 
                            WHERE connection_id = ANY($1)
                            
                            UNION ALL
                            
                            -- Recursive case: people connected to already found connected people
                            SELECT 
                                p.id,
                                p.first_name,
                                p.last_name,
                                p.position,
                                p.province,
                                p.municipality_city,
                                p.year,
                                p.fat,
                                p.connection,
                                p.connection_type,
                                p.connection_id,
                                p.nickname,
                                cp.level + 1
                            FROM political_dynasties p
                            INNER JOIN connected_people cp ON p.connection_id = cp.id
                            WHERE cp.level < 3  -- Limit to 3 levels of connections
                        )
                        SELECT DISTINCT
                            id,
                            first_name,
                            last_name,
                            position,
                            province,
                            municipality_city,
                            year,
                            fat,
                            connection,
                            connection_type,
                            connection_id,
                            nickname
                        FROM connected_people
                        WHERE CONCAT(first_name, ' ', last_name) NOT IN (
                            SELECT CONCAT(first_name, ' ', last_name) 
                            FROM political_dynasties 
                            WHERE last_name = $2 AND province = $3
                        )
                        ORDER BY year DESC, first_name
                    """'''
    
    new_query = '''                    # Find people who are connected to this family using the relationships table
                    # This includes people connected through the normalized relationships table
                    connected_query = """
                        WITH RECURSIVE connected_people AS (
                            -- Base case: people directly connected to family members via relationships table
                            SELECT DISTINCT
                                p.id,
                                p.first_name,
                                p.last_name,
                                p.position,
                                p.province,
                                p.municipality_city,
                                p.year,
                                p.fat,
                                r.relationship_description as connection,
                                r.relationship_type,
                                r.related_person_id as connection_id,
                                p.nickname,
                                1 as level
                            FROM political_dynasties p
                            JOIN relationships r ON p.id = r.person_id
                            WHERE r.related_person_id = ANY($1)
                            
                            UNION ALL
                            
                            -- Recursive case: people connected to already found connected people
                            SELECT DISTINCT
                                p.id,
                                p.first_name,
                                p.last_name,
                                p.position,
                                p.province,
                                p.municipality_city,
                                p.year,
                                p.fat,
                                r.relationship_description as connection,
                                r.relationship_type,
                                r.related_person_id as connection_id,
                                p.nickname,
                                cp.level + 1
                            FROM political_dynasties p
                            JOIN relationships r ON p.id = r.person_id
                            INNER JOIN connected_people cp ON r.related_person_id = cp.id
                            WHERE cp.level < 3  -- Limit to 3 levels of connections
                        )
                        SELECT DISTINCT
                            id,
                            first_name,
                            last_name,
                            position,
                            province,
                            municipality_city,
                            year,
                            fat,
                            connection,
                            relationship_type as connection_type,
                            connection_id,
                            nickname
                        FROM connected_people
                        WHERE CONCAT(first_name, ' ', last_name) NOT IN (
                            SELECT CONCAT(first_name, ' ', last_name) 
                            FROM political_dynasties 
                            WHERE last_name = $2 AND province = $3
                        )
                        ORDER BY year DESC, first_name
                    """'''
    
    # Replace the old query with the new one
    updated_content = content.replace(old_query, new_query)
    
    # Write the updated content back to the file
    with open('/home/joebert/open-data-visualization/visualization.py', 'w') as f:
        f.write(updated_content)
    
    print("✅ API updated to use normalized relationships table")
    print("🔄 The API now uses proper many-to-many relationships instead of single connection columns")
    print("📊 This allows politicians to have multiple relationships (father, husband, son, etc.)")

if __name__ == "__main__":
    asyncio.run(update_api_for_relationships())
