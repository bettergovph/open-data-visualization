#!/usr/bin/env python3
"""
Wikipedia Scraper for Political Dynasty Relationships
Automatically discovers and populates family connections from Wikipedia
"""

import asyncio
import asyncpg
import aiohttp
import json
import re
from bs4 import BeautifulSoup
from urllib.parse import quote, unquote
import os
from dotenv import load_dotenv
import time
from typing import Dict, List, Tuple, Optional

# Load environment variables
load_dotenv('visualization.env')

class WikipediaScraper:
    def __init__(self):
        self.session = None
        self.db_conn = None
        self.base_url = "https://en.wikipedia.org/api/rest_v1/page/summary/"
        self.search_url = "https://en.wikipedia.org/w/api.php"
        self.rate_limit_delay = 2.0  # Delay between requests to be respectful
        
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
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
        if self.db_conn:
            await self.db_conn.close()

    async def search_wikipedia(self, query: str) -> Optional[Dict]:
        """Search Wikipedia for a person"""
        try:
            params = {
                'action': 'query',
                'format': 'json',
                'list': 'search',
                'srsearch': query,
                'srlimit': 5
            }
            
            async with self.session.get(self.search_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'query' in data and 'search' in data['query'] and data['query']['search']:
                        return data['query']['search'][0]  # Return first result
                    else:
                        print(f"⚠️ No search results for '{query}'")
                elif response.status == 403:
                    print(f"🚫 Rate limited or blocked for '{query}'")
                    await asyncio.sleep(5.0)  # Longer delay if blocked
                else:
                    print(f"❌ HTTP {response.status} for '{query}'")
                await asyncio.sleep(self.rate_limit_delay)
        except Exception as e:
            print(f"❌ Error searching Wikipedia for '{query}': {e}")
        return None

    async def get_page_content(self, title: str) -> Optional[str]:
        """Get full Wikipedia page content"""
        try:
            url = f"https://en.wikipedia.org/w/api.php"
            params = {
                'action': 'query',
                'format': 'json',
                'titles': title,
                'prop': 'extracts',
                'exintro': False,
                'explaintext': True
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    pages = data.get('query', {}).get('pages', {})
                    for page_id, page_data in pages.items():
                        if 'extract' in page_data:
                            return page_data['extract']
                await asyncio.sleep(self.rate_limit_delay)
        except Exception as e:
            print(f"❌ Error getting content for '{title}': {e}")
        return None

    def extract_relationships(self, content: str, person_name: str) -> List[Dict]:
        """Extract family relationships from Wikipedia content"""
        relationships = []
        
        # Common relationship patterns
        patterns = [
            # Marriage patterns
            (r'married to ([^,\.]+)', 'spouse'),
            (r'wife of ([^,\.]+)', 'spouse'),
            (r'husband of ([^,\.]+)', 'spouse'),
            (r'spouse.*?([A-Z][a-z]+ [A-Z][a-z]+)', 'spouse'),
            
            # Parent-child patterns
            (r'son of ([^,\.]+)', 'child'),
            (r'daughter of ([^,\.]+)', 'child'),
            (r'father of ([^,\.]+)', 'parent'),
            (r'mother of ([^,\.]+)', 'parent'),
            (r'child of ([^,\.]+)', 'child'),
            (r'parent of ([^,\.]+)', 'parent'),
            
            # Sibling patterns
            (r'brother of ([^,\.]+)', 'sibling'),
            (r'sister of ([^,\.]+)', 'sibling'),
            (r'sibling of ([^,\.]+)', 'sibling'),
            
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
                    relationships.append({
                        'related_person': related_person,
                        'relationship_type': relationship_type,
                        'context': match.group(0)
                    })
        
        return relationships

    async def find_database_matches(self, related_person: str) -> List[Dict]:
        """Find matching records in our database"""
        try:
            # Try exact name match first
            matches = await self.db_conn.fetch("""
                SELECT id, first_name, last_name, position, province, year
                FROM political_dynasties 
                WHERE CONCAT(first_name, ' ', last_name) ILIKE $1
                ORDER BY year DESC
                LIMIT 5
            """, f"%{related_person}%")
            
            if matches:
                return [dict(match) for match in matches]
            
            # Try partial matches
            name_parts = related_person.split()
            if len(name_parts) >= 2:
                first_name = name_parts[0]
                last_name = name_parts[-1]
                
                matches = await self.db_conn.fetch("""
                    SELECT id, first_name, last_name, position, province, year
                    FROM political_dynasties 
                    WHERE first_name ILIKE $1 AND last_name ILIKE $2
                    ORDER BY year DESC
                    LIMIT 5
                """, f"%{first_name}%", f"%{last_name}%")
                
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

    async def process_person(self, person_id: int, first_name: str, last_name: str, province: str) -> Dict:
        """Process a single person to find Wikipedia relationships"""
        full_name = f"{first_name} {last_name}"
        print(f"🔍 Processing: {full_name} from {province}")
        
        # Search Wikipedia
        wiki_result = await self.search_wikipedia(f"{full_name} {province} Philippines")
        if not wiki_result:
            return {'person': full_name, 'status': 'not_found', 'relationships': []}
        
        title = wiki_result['title']
        print(f"📄 Found Wikipedia page: {title}")
        
        # Get page content
        content = await self.get_page_content(title)
        if not content:
            return {'person': full_name, 'status': 'no_content', 'relationships': []}
        
        # Extract relationships
        relationships = self.extract_relationships(content, full_name)
        print(f"🔗 Found {len(relationships)} potential relationships")
        
        processed_relationships = []
        for rel in relationships:
            related_person = rel['related_person']
            relationship_type = rel['relationship_type']
            
            # Find database matches
            db_matches = await self.find_database_matches(related_person)
            
            if db_matches:
                connection_type = self.map_relationship_type(relationship_type)
                if connection_type:
                    processed_relationships.append({
                        'related_person': related_person,
                        'relationship_type': relationship_type,
                        'connection_type': connection_type,
                        'db_matches': db_matches,
                        'context': rel['context']
                    })
                    print(f"✅ Found match: {related_person} → {relationship_type}")
                else:
                    print(f"⚠️ Unknown relationship type: {relationship_type}")
            else:
                print(f"❌ No database match for: {related_person}")
        
        return {
            'person': full_name,
            'status': 'processed',
            'relationships': processed_relationships
        }

    async def update_connections(self, person_id: int, relationships: List[Dict]):
        """Update database with discovered relationships"""
        for rel in relationships:
            if rel['db_matches']:
                # Use the first (most recent) match
                target_person = rel['db_matches'][0]
                target_id = target_person['id']
                connection_type = rel['connection_type']
                
                try:
                    # Update the current person's connection
                    await self.db_conn.execute("""
                        UPDATE political_dynasties 
                        SET connection_type = $1, connection_id = $2,
                            connection = $3
                        WHERE id = $4
                    """, connection_type, target_id, 
                        f"Wikipedia: {rel['relationship_type']} of {rel['related_person']}", 
                        person_id)
                    
                    # Update the target person's reverse connection
                    reverse_connection_type = self.get_reverse_connection_type(connection_type)
                    if reverse_connection_type:
                        await self.db_conn.execute("""
                            UPDATE political_dynasties 
                            SET connection_type = $1, connection_id = $2,
                                connection = $3
                            WHERE id = $4
                        """, reverse_connection_type, person_id,
                            f"Wikipedia: {rel['relationship_type']} of {rel['related_person']}", 
                            target_id)
                    
                    print(f"✅ Updated connection: {person_id} → {target_id}")
                    
                except Exception as e:
                    print(f"❌ Error updating connection: {e}")

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
        }
        return reverse_mapping.get(connection_type)

    async def scrape_political_families(self, limit: int = 50):
        """Main function to scrape political families"""
        print(f"🚀 Starting Wikipedia scraper for {limit} political families...")
        
        # Get prominent political families from database
        families = await self.db_conn.fetch("""
            SELECT 
                MIN(p.id) as id, p.first_name, p.last_name, p.province,
                COUNT(*) as position_count
            FROM political_dynasties p
            WHERE p.fat = 1  -- Only dynasty members
            GROUP BY p.first_name, p.last_name, p.province
            HAVING COUNT(*) >= 2  -- At least 2 positions
            ORDER BY position_count DESC, p.last_name, p.first_name
            LIMIT $1
        """, limit)
        
        print(f"📊 Found {len(families)} prominent political families to process")
        
        results = []
        for i, family in enumerate(families, 1):
            print(f"\n{'='*60}")
            print(f"📋 Processing {i}/{len(families)}: {family['first_name']} {family['last_name']}")
            
            result = await self.process_person(
                family['id'], 
                family['first_name'], 
                family['last_name'], 
                family['province']
            )
            
            if result['relationships']:
                await self.update_connections(family['id'], result['relationships'])
            
            results.append(result)
            
            # Rate limiting
            await asyncio.sleep(self.rate_limit_delay)
        
        # Save results to file
        with open('wikipedia_scraping_results.json', 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n🎉 Scraping complete! Results saved to wikipedia_scraping_results.json")
        return results

async def main():
    """Main execution function"""
    async with WikipediaScraper() as scraper:
        await scraper.scrape_political_families(limit=20)  # Start with 20 families

if __name__ == "__main__":
    asyncio.run(main())
