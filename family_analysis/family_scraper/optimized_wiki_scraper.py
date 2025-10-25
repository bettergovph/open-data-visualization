#!/usr/bin/env python3
"""
Wikipedia-Based Political Dynasty Relationship Verifier
Strictly uses Wikipedia to verify and discover family relationships
Only adds relationships that are documented and verified through Wikipedia sources
"""

import asyncio
import asyncpg
import aiohttp
import json
import re
from urllib.parse import quote, unquote
import os
from dotenv import load_dotenv
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import time
from typing import Dict, List, Tuple, Optional
from advanced_name_matcher import AdvancedNameMatcher

# Load environment variables
load_dotenv('visualization.env')

class OptimizedWikipediaScraper:
    def __init__(self):
        self.session = None
        self.db_conn = None
        self.search_url = "https://en.wikipedia.org/w/api.php"
        self.rate_limit_delay = 2.0  # Conservative rate limiting
        self.name_matcher = None
        
    async def __aenter__(self):
        headers = {
            'User-Agent': 'BetterGovPH Political Dynasty Research Bot 1.0 (https://visualizations.bettergov.ph)',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9'
        }
        self.session = aiohttp.ClientSession(headers=headers)
        self.db_conn = await asyncpg.connect(
            host='localhost',
            port='5432',
            user='budget_admin',
            password='wuQ5gBYCKkZiOGb61chLcByMu',
            database='dynasty'
        )
        self.name_matcher = AdvancedNameMatcher(self.db_conn)
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
        if self.db_conn:
            await self.db_conn.close()

    async def get_prioritized_dynasties(self) -> List[Dict]:
        """Get top political dynasties prioritized by influence and power"""
        print("🎯 Prioritizing top political dynasties by influence...")
        
        # Get dynasties ranked by political power and influence
        dynasties = await self.db_conn.fetch("""
            WITH dynasty_stats AS (
                SELECT 
                    CONCAT(first_name, ' ', last_name) as family_name,
                    province,
                    COUNT(*) as total_positions,
                    COUNT(DISTINCT year) as years_active,
                    COUNT(DISTINCT position) as unique_positions,
                    MAX(CASE 
                        WHEN position LIKE '%MEMBER, HOUSE OF REPRESENTATIVES%' THEN 7
                        WHEN position LIKE '%GOVERNOR%' THEN 6
                        WHEN position LIKE '%VICE GOVERNOR%' THEN 5
                        WHEN position LIKE '%MAYOR%' THEN 4
                        WHEN position LIKE '%VICE MAYOR%' THEN 3
                        WHEN position LIKE '%COUNCILOR%' THEN 2
                        ELSE 1
                    END) as highest_position_level,
                    STRING_AGG(DISTINCT position, ', ') as positions_held
                FROM political_dynasties 
                WHERE fat = 1
                GROUP BY CONCAT(first_name, ' ', last_name), province
            ),
            ranked_dynasties AS (
                SELECT *,
                    -- Calculate influence score
                    (total_positions * 0.3 + 
                     years_active * 0.2 + 
                     unique_positions * 0.2 + 
                     highest_position_level * 0.3) as influence_score
                FROM dynasty_stats
            )
            SELECT 
                family_name,
                province,
                total_positions,
                years_active,
                unique_positions,
                highest_position_level,
                positions_held,
                influence_score
            FROM ranked_dynasties
            WHERE influence_score >= 3.0  -- Include more dynasties for broader coverage
            AND family_name NOT IN (
                -- Exclude dynasties that already have Wikipedia relationships
                SELECT DISTINCT 
                    CASE 
                        WHEN pd1.id IS NOT NULL THEN pd1.first_name || ' ' || pd1.last_name
                        ELSE pd2.first_name || ' ' || pd2.last_name
                    END
                FROM relationships r
                LEFT JOIN political_dynasties pd1 ON r.person_id = pd1.id
                LEFT JOIN political_dynasties pd2 ON r.related_person_id = pd2.id
                WHERE r.relationship_description LIKE 'Wikipedia:%'
            )
            ORDER BY influence_score DESC, total_positions DESC, years_active DESC
            LIMIT 5000  -- Try 5000 more dynasties that haven't been processed yet
        """)
        
        print(f"📊 Found {len(dynasties)} high-influence political dynasties")
        for i, dynasty in enumerate(dynasties[:10], 1):
            print(f"  {i:2d}. {dynasty['family_name']} ({dynasty['province']}) - Score: {dynasty['influence_score']:.1f}")
        
        return [dict(dynasty) for dynasty in dynasties]

    async def get_dynasty_members(self, family_name: str, province: str) -> List[Dict]:
        """Get all family members for a specific dynasty"""
        members = await self.db_conn.fetch("""
            SELECT DISTINCT
                first_name, last_name, position, year,
                MIN(id) as id
            FROM political_dynasties 
            WHERE fat = 1 
            AND province = $1 
            AND CONCAT(first_name, ' ', last_name) = $2
            GROUP BY first_name, last_name, position, year
            ORDER BY last_name, first_name, year DESC
        """, province, family_name)
        
        return [dict(member) for member in members]

    async def get_dynasty_members_threaded(self, db_conn, family_name: str, province: str) -> List[Dict]:
        """Get all family members for a specific dynasty (threaded version)"""
        members = await db_conn.fetch("""
            SELECT DISTINCT
                first_name, last_name, position, year,
                MIN(id) as id
            FROM political_dynasties 
            WHERE fat = 1 
            AND province = $1 
            AND CONCAT(first_name, ' ', last_name) = $2
            GROUP BY first_name, last_name, position, year
            ORDER BY last_name, first_name, year DESC
        """, province, family_name)
        
        return [dict(member) for member in members]

    async def process_person_threaded(self, db_conn, person_id: int, first_name: str, last_name: str, province: str, target_families: List[str]) -> Dict:
        """Process a single person to find Wikipedia relationships (threaded version)"""
        full_name = f"{first_name} {last_name}"
        print(f"🔍 Processing: {full_name} from {province}")
        
        # Search Wikipedia
        wiki_data = await self.search_wikipedia(full_name)
        if not wiki_data:
            return {'person': full_name, 'status': 'no_wikipedia', 'relationships': []}
        
        content = await self.get_wikipedia_content(wiki_data['title'])
        if not content:
            return {'person': full_name, 'status': 'no_content', 'relationships': []}
        
        # Extract relationships
        relationships = self.extract_relationships(content, full_name, target_families)
        print(f"🔗 Found {len(relationships)} potential relationships")
        
        # Extract nickname
        nickname = self.extract_nickname(content, full_name)
        if nickname:
            try:
                await db_conn.execute("""
                    UPDATE political_dynasties 
                    SET nickname = $1 
                    WHERE id = $2
                """, nickname, person_id)
                print(f"🏷️ Found nickname: '{nickname}' for {full_name}")
                print(f"✅ Updated nickname '{nickname}' for person ID {person_id}")
            except Exception as e:
                print(f"❌ Error updating nickname: {e}")
        
        # Update database with relationships
        await self.update_database_connections_threaded(db_conn, person_id, relationships)
        
        return {
            'person': full_name,
            'status': 'processed',
            'relationships': relationships
        }

    async def update_database_connections_threaded(self, db_conn, person_id: int, relationships: List[Dict]):
        """Update database with discovered relationships (threaded version)"""
        for rel in relationships:
            if rel['db_matches'] and rel['connection_type']:
                # Use the first (most recent) match
                target_person = rel['db_matches'][0]
                target_id = target_person['id']
                connection_type = rel['connection_type']
                
                try:
                    # Insert into the relationships table (forward relationship)
                    await db_conn.execute("""
                        INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (person_id, related_person_id, relationship_type) DO UPDATE SET
                            relationship_description = EXCLUDED.relationship_description
                    """, person_id, target_id, connection_type, 
                        f"Wikipedia: {rel['relationship_type']} of {rel['related_person']}")
                    
                    # Insert reverse relationship
                    reverse_connection_type = self.get_reverse_connection_type(connection_type)
                    if reverse_connection_type:
                        await db_conn.execute("""
                            INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description)
                            VALUES ($1, $2, $3, $4)
                            ON CONFLICT (person_id, related_person_id, relationship_type) DO UPDATE SET
                                relationship_description = EXCLUDED.relationship_description
                        """, target_id, person_id, reverse_connection_type,
                            f"Wikipedia: {rel['relationship_type']} of {rel['person']}")
                    
                    print(f"✅ Updated relationship: {rel['person']} -> {rel['related_person']} ({rel['relationship_type']})")
                    
                except Exception as e:
                    print(f"❌ Error updating relationship: {e}")

    async def search_wikipedia(self, query: str) -> Optional[Dict]:
        """Search Wikipedia for a person with multiple strategies"""
        strategies = [
            f"{query} Philippines",
            f"{query} politician",
            f"{query} mayor",
            f"{query} governor",
            query  # Just the name
        ]
        
        for strategy in strategies:
            try:
                params = {
                    'action': 'query',
                    'format': 'json',
                    'list': 'search',
                    'srsearch': strategy,
                    'srlimit': 3
                }
                
                async with self.session.get(self.search_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'query' in data and 'search' in data['query'] and data['query']['search']:
                            results = data['query']['search']
                            # Look for results that seem relevant
                            for result in results:
                                title = result['title'].lower()
                                if any(keyword in title for keyword in ['mayor', 'governor', 'congressman', 'senator', 'representative']):
                                    return result
                            # If no specific political result, return first result
                            return results[0]
                    elif response.status == 403:
                        print(f"🚫 Rate limited, waiting 10 seconds...")
                        await asyncio.sleep(10.0)
                        continue
                    else:
                        print(f"❌ HTTP {response.status} for strategy: {strategy}")
                        
                await asyncio.sleep(self.rate_limit_delay)
                
            except Exception as e:
                print(f"❌ Error with strategy '{strategy}': {e}")
                continue
        
        return None

    async def get_page_content(self, title: str) -> Optional[str]:
        """Get full Wikipedia page content"""
        try:
            params = {
                'action': 'query',
                'format': 'json',
                'titles': title,
                'prop': 'extracts',
                'exintro': 'false',
                'explaintext': 'true'
            }
            
            async with self.session.get(self.search_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    pages = data.get('query', {}).get('pages', {})
                    for page_id, page_data in pages.items():
                        if 'extract' in page_data:
                            return page_data['extract']
                else:
                    print(f"❌ HTTP {response.status} getting content for '{title}'")
                await asyncio.sleep(self.rate_limit_delay)
        except Exception as e:
            print(f"❌ Error getting content for '{title}': {e}")
        return None

    def extract_relationships(self, content: str, person_name: str, target_families: List[str]) -> List[Dict]:
        """Extract family relationships from Wikipedia content, focusing on target families"""
        relationships = []
        
        # Extract surnames from target families
        target_surnames = []
        for family in target_families:
            name_parts = family.split()
            if len(name_parts) > 1:
                # Get the last name (surname)
                surname = name_parts[-1]
                target_surnames.append(surname.lower())
        
        # More comprehensive relationship patterns
        patterns = [
            # Marriage patterns
            (r'married to ([^,\.]+)', 'spouse'),
            (r'wife of ([^,\.]+)', 'spouse'),
            (r'husband of ([^,\.]+)', 'spouse'),
            (r'spouse.*?([A-Z][a-z]+ [A-Z][a-z]+)', 'spouse'),
            (r'wedding.*?([A-Z][a-z]+ [A-Z][a-z]+)', 'spouse'),
            
            # Parent-child patterns
            (r'son of ([^,\.]+)', 'child'),
            (r'daughter of ([^,\.]+)', 'child'),
            (r'father of ([^,\.]+)', 'parent'),
            (r'mother of ([^,\.]+)', 'parent'),
            (r'child of ([^,\.]+)', 'child'),
            (r'parent of ([^,\.]+)', 'parent'),
            (r'born to ([^,\.]+)', 'child'),
            
            # Sibling patterns
            (r'brother of ([^,\.]+)', 'sibling'),
            (r'sister of ([^,\.]+)', 'sibling'),
            (r'sibling of ([^,\.]+)', 'sibling'),
            (r'brother.*?([A-Z][a-z]+ [A-Z][a-z]+)', 'sibling'),
            (r'sister.*?([A-Z][a-z]+ [A-Z][a-z]+)', 'sibling'),
            
            # Extended family
            (r'cousin of ([^,\.]+)', 'cousin'),
            (r'nephew of ([^,\.]+)', 'nephew'),
            (r'niece of ([^,\.]+)', 'niece'),
            (r'uncle of ([^,\.]+)', 'uncle'),
            (r'aunt of ([^,\.]+)', 'aunt'),
        ]
        
        content_lower = content.lower()
        
        for pattern, relationship_type in patterns:
            matches = re.finditer(pattern, content_lower, re.IGNORECASE)
            for match in matches:
                related_person = match.group(1).strip()
                # Clean up the name
                related_person = re.sub(r'\s+', ' ', related_person)
                related_person = related_person.title()
                
                if related_person and len(related_person) > 3:  # Basic validation
                    # Check if this person might be from one of our target families
                    # by checking if any target surname appears in the related person's name
                    is_target_family = any(surname in related_person.lower() 
                                         for surname in target_surnames)
                    
                    relationships.append({
                        'related_person': related_person,
                        'relationship_type': relationship_type,
                        'context': match.group(0),
                        'is_target_family': is_target_family
                    })
        
        return relationships

    def extract_nickname(self, content: str, person_name: str) -> Optional[str]:
        """Extract nickname from Wikipedia content"""
        # Look for patterns like "Stephen James 'Jimboy' Tan" or "Stephen James \"Jimboy\" Tan"
        nickname_patterns = [
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+["\']([^"\']+)["\']\s+([A-Z][a-z]+)',
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+\(([^)]+)\)\s+([A-Z][a-z]+)',
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+["\']([^"\']+)["\']',
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+\(([^)]+)\)',
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+"([^"]+)"',
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+\'([^\']+)\'',
        ]
        
        for pattern in nickname_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                if len(match.groups()) >= 2:
                    potential_nickname = match.group(2).strip()
                    # Filter out common false positives
                    if (len(potential_nickname) > 1 and 
                        len(potential_nickname) < 20 and
                        not potential_nickname.lower() in ['jr', 'sr', 'ii', 'iii', 'iv', 'phd', 'md', 'dds', 'esq', 'ret', 'deceased']):
                        return potential_nickname
        
        return None

    async def update_nickname(self, person_id: int, nickname: str):
        """Update nickname in database for a specific person"""
        try:
            await self.db_conn.execute("""
                UPDATE political_dynasties 
                SET nickname = $1
                WHERE id = $2
            """, nickname, person_id)
            print(f"✅ Updated nickname '{nickname}' for person ID {person_id}")
        except Exception as e:
            print(f"❌ Error updating nickname: {e}")

    async def find_database_matches(self, related_person: str, province: str) -> List[Dict]:
        """Find matching records in our database using advanced name matching"""
        try:
            # Use the advanced name matcher
            matches = await self.name_matcher.find_potential_matches(related_person, province)
            
            # Convert to the expected format
            db_matches = []
            for match in matches:
                if match['similarity'] > 0.7:  # High confidence threshold
                    db_matches.append({
                        'id': match['id'],
                        'first_name': match['first_name'],
                        'last_name': match['last_name'],
                        'position': match['position'],
                        'province': match['province'],
                        'year': match['year'],
                        'similarity': match['similarity']
                    })
            
            if db_matches:
                print(f"✅ Advanced matching found {len(db_matches)} matches for '{related_person}'")
                return db_matches
            
            # Fallback to basic matching if advanced matching fails
            name_parts = related_person.split()
            if len(name_parts) >= 2:
                last_name = name_parts[-1]
                matches = await self.db_conn.fetch("""
                    SELECT id, first_name, last_name, position, province, year
                    FROM political_dynasties 
                    WHERE last_name ILIKE $1
                    AND province = $2
                    ORDER BY year DESC
                    LIMIT 5
                """, f"%{last_name}%", province)
                
                return [dict(match) for match in matches]
                
        except Exception as e:
            print(f"❌ Error finding database matches for '{related_person}': {e}")
        
        return []

    def map_relationship_type(self, wiki_relationship: str) -> Optional[int]:
        """Map Wikipedia relationship to our connection_type codes"""
        mapping = {
            'spouse': 7,  # Husband/Wife
            'child': 3,   # Son
            'parent': 1, # Father
            'sibling': 5, # Brother
            'cousin': 19, # Cousin
            'nephew': 17, # Nephew
            'niece': 18,  # Niece
            'uncle': 15,  # Uncle
            'aunt': 16,   # Aunt
        }
        return mapping.get(wiki_relationship)

    def get_reverse_connection_type(self, connection_type: int) -> Optional[int]:
        """Get the reverse of a connection type"""
        reverse_mapping = {
            1: 3,   # Father → Son
            2: 4,   # Mother → Daughter  
            3: 1,   # Son → Father
            4: 2,   # Daughter → Mother
            5: 5,   # Brother → Brother
            6: 6,   # Sister → Sister
            7: 8,   # Husband → Wife
            8: 7,   # Wife → Husband
            15: 17, # Uncle → Nephew
            16: 18, # Aunt → Niece
            17: 15, # Nephew → Uncle
            18: 16, # Niece → Aunt
            19: 19, # Cousin → Cousin
        }
        return reverse_mapping.get(connection_type)

    async def update_database_connections(self, person_id: int, relationships: List[Dict]):
        """Update database with discovered relationships"""
        for rel in relationships:
            if rel['db_matches'] and rel['connection_type']:
                # Use the first (most recent) match
                target_person = rel['db_matches'][0]
                target_id = target_person['id']
                connection_type = rel['connection_type']
                
                try:
                    # Insert into the relationships table (forward relationship)
                    await self.db_conn.execute("""
                        INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (person_id, related_person_id, relationship_type) DO UPDATE SET
                            relationship_description = EXCLUDED.relationship_description
                    """, person_id, target_id, connection_type, 
                        f"Wikipedia: {rel['relationship_type']} of {rel['related_person']}")
                    
                    # Insert reverse relationship
                    reverse_connection_type = self.get_reverse_connection_type(connection_type)
                    if reverse_connection_type:
                        await self.db_conn.execute("""
                            INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description)
                            VALUES ($1, $2, $3, $4)
                            ON CONFLICT (person_id, related_person_id, relationship_type) DO UPDATE SET
                                relationship_description = EXCLUDED.relationship_description
                        """, target_id, person_id, reverse_connection_type,
                            f"Wikipedia: {rel['relationship_type']} of {rel['person']}")
                    
                    print(f"✅ Updated relationship: {rel['person']} -> {rel['related_person']} ({rel['relationship_type']})")
                    
                except Exception as e:
                    print(f"❌ Error updating relationship: {e}")

    async def process_person(self, person_id: int, first_name: str, last_name: str, province: str, target_families: List[str]) -> Dict:
        """Process a single person to find Wikipedia relationships"""
        full_name = f"{first_name} {last_name}"
        print(f"🔍 Processing: {full_name} from {province}")
        
        # Search Wikipedia
        wiki_result = await self.search_wikipedia(full_name)
        if not wiki_result:
            return {'person': full_name, 'status': 'not_found', 'relationships': []}
        
        title = wiki_result['title']
        print(f"📄 Found Wikipedia page: {title}")
        
        # Get page content
        content = await self.get_page_content(title)
        if not content:
            return {'person': full_name, 'status': 'no_content', 'relationships': []}
        
        # Extract relationships
        relationships = self.extract_relationships(content, full_name, target_families)
        print(f"🔗 Found {len(relationships)} potential relationships")
        
        # Extract nickname
        nickname = self.extract_nickname(content, full_name)
        if nickname:
            print(f"🏷️ Found nickname: '{nickname}' for {full_name}")
            # Update nickname in database
            await self.update_nickname(person_id, nickname)
        
        processed_relationships = []
        for rel in relationships:
            related_person = rel['related_person']
            relationship_type = rel['relationship_type']
            is_target_family = rel['is_target_family']
            
            # Find database matches within the same province
            db_matches = await self.find_database_matches(related_person, province)
            
            if db_matches:
                connection_type = self.map_relationship_type(relationship_type)
                if connection_type:
                    processed_relationships.append({
                        'related_person': related_person,
                        'relationship_type': relationship_type,
                        'connection_type': connection_type,
                        'db_matches': db_matches,
                        'context': rel['context'],
                        'is_target_family': is_target_family
                    })
                    print(f"✅ Found match: {related_person} → {relationship_type}")
                else:
                    print(f"⚠️ Unknown relationship type: {relationship_type}")
            else:
                if is_target_family:
                    print(f"🎯 Target family but no database match: {related_person}")
                else:
                    print(f"❌ No database match for: {related_person}")
                
                # Still save the relationship even if no database match
                processed_relationships.append({
                    'related_person': related_person,
                    'relationship_type': relationship_type,
                    'connection_type': None,
                    'db_matches': [],
                    'context': rel['context'],
                    'is_target_family': is_target_family
                })
        
        # Update database with discovered connections
        if processed_relationships:
            await self.update_database_connections(person_id, processed_relationships)
        
        return {
            'person': full_name,
            'status': 'processed',
            'relationships': processed_relationships
        }

    async def scrape_prioritized_dynasties(self, limit: int = 25):
        """Scrape top political dynasties prioritized by influence"""
        print(f"🚀 Starting prioritized Wikipedia scraper for top {limit} political dynasties...")
        
        # Get top political dynasties by influence
        dynasties = await self.get_prioritized_dynasties()
        print(f"📊 Found {len(dynasties)} high-influence political dynasties")
        
        # Limit the number of dynasties to process
        target_dynasties = dynasties[:limit]
        
        all_results = []
        
        # Process dynasties in parallel with 20 threads
        print(f"🚀 Processing {len(target_dynasties)} dynasties with 20 parallel threads...")
        
        async def process_dynasty(dynasty_data, index):
            # Create separate database connection for this thread
            thread_db_conn = await asyncpg.connect(
                host='localhost',
                port='5432',
                user='budget_admin',
                password='wuQ5gBYCKkZiOGb61chLcByMu',
                database='dynasty'
            )
            
            try:
                family_name = dynasty_data['family_name']
                province = dynasty_data['province']
                influence_score = dynasty_data['influence_score']
                
                print(f"\n{'='*80}")
                print(f"👑 Processing {index+1}/{len(target_dynasties)}: {family_name}")
                print(f"📍 Province: {province}")
                print(f"⭐ Influence Score: {influence_score:.1f}")
                print(f"📊 Positions: {dynasty_data['total_positions']}, Years: {dynasty_data['years_active']}")
                
                # Get all family members for this specific dynasty
                family_members = await self.get_dynasty_members_threaded(thread_db_conn, family_name, province)
                
                # Process each family member
                dynasty_results = []
                for member in family_members:
                    full_name = f"{member['first_name']} {member['last_name']}"
                    
                    # Skip if we already processed this person
                    if any(r['person'] == full_name for r in dynasty_results):
                        continue
                    
                    result = await self.process_person_threaded(
                        thread_db_conn,
                        member['id'],
                        member['first_name'],
                        member['last_name'],
                        province,
                        [family_name]  # Pass the current dynasty as target family
                    )
                    
                    dynasty_results.append(result)
                    
                    # Rate limiting
                    await asyncio.sleep(self.rate_limit_delay)
                
                return dynasty_data, dynasty_results
                
            finally:
                await thread_db_conn.close()
        
        # Create semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(20)
        
        async def process_with_semaphore(dynasty_data, index):
            async with semaphore:
                return await process_dynasty(dynasty_data, index)
        
        # Process all dynasties concurrently
        tasks = [process_with_semaphore(dynasty_data, i) for i, dynasty_data in enumerate(target_dynasties)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for result in results:
            if isinstance(result, Exception):
                print(f"❌ Error processing dynasty: {result}")
                continue
                
            dynasty_data, dynasty_results = result
            
            # Add dynasty info to results
            dynasty_summary = {
                'family_name': dynasty_data['family_name'],
                'province': dynasty_data['province'],
                'influence_score': dynasty_data['influence_score'],
                'results': dynasty_results
            }
            
            all_results.append(dynasty_summary)
            
            # Show summary for this dynasty
            total_relationships = sum(len(r['relationships']) for r in dynasty_results)
            target_relationships = sum(
                len([rel for rel in r['relationships'] if rel.get('is_target_family', False)])
                for r in dynasty_results
            )
            
            print(f"📊 Dynasty Summary: {total_relationships} total relationships, {target_relationships} target family relationships")
        
        # Save results to file
        with open('optimized_wikipedia_scraping_results.json', 'w') as f:
            json.dump(all_results, f, indent=2, default=str)
        
        print(f"\n🎉 Optimized scraping complete! Results saved to optimized_wikipedia_scraping_results.json")
        
        # Wikipedia scraping complete - quality over quantity
        print(f"\n✅ High-quality Wikipedia relationship verification complete")
        print(f"🎯 Focus: Accuracy over quantity - only verified relationships added")
        
        return all_results


async def main():
    """Main execution function"""
    async with OptimizedWikipediaScraper() as scraper:
        await scraper.scrape_prioritized_dynasties(limit=5000)  # Process top 5000 dynasties that haven't been tried yet

if __name__ == "__main__":
    asyncio.run(main())
