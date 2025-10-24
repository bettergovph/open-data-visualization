#!/usr/bin/env python3
"""
Targeted Wikipedia Scraper for Political Dynasty Relationships
Focuses on well-known politicians and uses better search strategies
"""

import asyncio
import asyncpg
import aiohttp
import json
import re
from urllib.parse import quote, unquote
import os
from dotenv import load_dotenv
import time
from typing import Dict, List, Tuple, Optional

# Load environment variables
load_dotenv('visualization.env')

class TargetedWikipediaScraper:
    def __init__(self):
        self.session = None
        self.db_conn = None
        self.search_url = "https://en.wikipedia.org/w/api.php"
        self.rate_limit_delay = 3.0  # More conservative rate limiting
        
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
                                    print(f"✅ Found relevant result: {result['title']}")
                                    return result
                            # If no specific political result, return first result
                            print(f"✅ Found result: {results[0]['title']}")
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

    def extract_relationships(self, content: str, person_name: str) -> List[Dict]:
        """Extract family relationships from Wikipedia content"""
        relationships = []
        
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
                # Still save the relationship even if no database match
                processed_relationships.append({
                    'related_person': related_person,
                    'relationship_type': relationship_type,
                    'connection_type': None,
                    'db_matches': [],
                    'context': rel['context']
                })
        
        return {
            'person': full_name,
            'status': 'processed',
            'relationships': processed_relationships
        }

    async def scrape_well_known_politicians(self, limit: int = 10):
        """Scrape well-known politicians who are more likely to have Wikipedia pages"""
        print(f"🚀 Starting targeted Wikipedia scraper for {limit} well-known politicians...")
        
        # Get politicians with high position counts and specific titles
        families = await self.db_conn.fetch("""
            SELECT 
                MIN(p.id) as id, p.first_name, p.last_name, p.province,
                COUNT(*) as position_count,
                STRING_AGG(DISTINCT p.position, ', ') as positions
            FROM political_dynasties p
            WHERE p.fat = 1  -- Only dynasty members
            AND p.position IN ('GOVERNOR', 'MAYOR', 'MEMBER, HOUSE OF REPRESENTATIVES', 'SENATOR')
            GROUP BY p.first_name, p.last_name, p.province
            HAVING COUNT(*) >= 3  -- At least 3 positions
            ORDER BY position_count DESC, p.last_name, p.first_name
            LIMIT $1
        """, limit)
        
        print(f"📊 Found {len(families)} well-known politicians to process")
        
        results = []
        for i, family in enumerate(families, 1):
            print(f"\n{'='*60}")
            print(f"📋 Processing {i}/{len(families)}: {family['first_name']} {family['last_name']}")
            print(f"📊 Positions: {family['positions']}")
            
            result = await self.process_person(
                family['id'], 
                family['first_name'], 
                family['last_name'], 
                family['province']
            )
            
            results.append(result)
            
            # Rate limiting
            await asyncio.sleep(self.rate_limit_delay)
        
        # Save results to file
        with open('targeted_wikipedia_scraping_results.json', 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n🎉 Targeted scraping complete! Results saved to targeted_wikipedia_scraping_results.json")
        return results

async def main():
    """Main execution function"""
    async with TargetedWikipediaScraper() as scraper:
        await scraper.scrape_well_known_politicians(limit=5)  # Start with 5 well-known politicians

if __name__ == "__main__":
    asyncio.run(main())
