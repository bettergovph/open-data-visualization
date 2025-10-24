#!/usr/bin/env python3
"""
Advanced Name Matching System for Political Dynasty Research
Handles maiden names, married names, hyphenated surnames, and name variations
"""

import re
import asyncio
import asyncpg
from typing import List, Dict, Tuple, Optional, Set
from difflib import SequenceMatcher

class AdvancedNameMatcher:
    def __init__(self, db_conn=None):
        self.db_conn = db_conn
        self.name_cache = {}
        
    def normalize_name(self, name: str) -> str:
        """Normalize a name for comparison"""
        if not name:
            return ""
        
        # Convert to uppercase and clean
        name = name.upper().strip()
        
        # Remove common prefixes
        prefixes = ['H.E.', 'HON.', 'HONORABLE', 'DR.', 'PROF.', 'ATTY.', 'ENG.', 'ARCH.', 'MR.', 'MS.', 'MRS.']
        for prefix in prefixes:
            if name.startswith(prefix):
                name = name[len(prefix):].strip()
        
        # Remove extra spaces
        name = re.sub(r'\s+', ' ', name)
        
        return name
    
    def extract_name_parts(self, full_name: str) -> Dict[str, str]:
        """Extract first name, middle name, last name from full name"""
        normalized = self.normalize_name(full_name)
        parts = normalized.split()
        
        if len(parts) == 0:
            return {'first_name': '', 'middle_name': '', 'last_name': ''}
        elif len(parts) == 1:
            return {'first_name': parts[0], 'middle_name': '', 'last_name': ''}
        elif len(parts) == 2:
            return {'first_name': parts[0], 'middle_name': '', 'last_name': parts[1]}
        else:
            # For 3+ parts, assume last part is surname, first part is first name, rest is middle
            return {
                'first_name': parts[0],
                'middle_name': ' '.join(parts[1:-1]),
                'last_name': parts[-1]
            }
    
    def split_hyphenated_surname(self, surname: str) -> List[str]:
        """Split hyphenated surnames into individual surnames"""
        if not surname:
            return []
        
        # Split on hyphens and clean
        surnames = [s.strip() for s in surname.split('-') if s.strip()]
        return surnames
    
    def get_name_variations(self, full_name: str) -> List[str]:
        """Generate all possible name variations for matching"""
        variations = set()
        
        # Add original name
        variations.add(self.normalize_name(full_name))
        
        # Extract parts
        parts = self.extract_name_parts(full_name)
        first_name = parts['first_name']
        middle_name = parts['middle_name']
        last_name = parts['last_name']
        
        if not first_name or not last_name:
            return list(variations)
        
        # Add first name + last name
        variations.add(f"{first_name} {last_name}")
        
        # Add first name + middle initial + last name
        if middle_name:
            middle_initial = middle_name[0] if middle_name else ''
            variations.add(f"{first_name} {middle_initial} {last_name}")
            variations.add(f"{first_name} {middle_initial}. {last_name}")
        
        # Handle hyphenated surnames
        hyphenated_surnames = self.split_hyphenated_surname(last_name)
        if len(hyphenated_surnames) > 1:
            # Add each surname separately
            for surname in hyphenated_surnames:
                variations.add(f"{first_name} {surname}")
                if middle_name:
                    variations.add(f"{first_name} {middle_name} {surname}")
            
            # Add combinations
            for i in range(len(hyphenated_surnames)):
                for j in range(i+1, len(hyphenated_surnames)):
                    combined = f"{hyphenated_surnames[i]}-{hyphenated_surnames[j]}"
                    variations.add(f"{first_name} {combined}")
        
        return list(variations)
    
    def calculate_similarity(self, name1: str, name2: str) -> float:
        """Calculate similarity between two names"""
        if not name1 or not name2:
            return 0.0
        
        # Normalize both names
        norm1 = self.normalize_name(name1)
        norm2 = self.normalize_name(name2)
        
        # Exact match
        if norm1 == norm2:
            return 1.0
        
        # Use sequence matcher for fuzzy matching
        similarity = SequenceMatcher(None, norm1, norm2).ratio()
        
        # Boost similarity for partial matches
        if norm1 in norm2 or norm2 in norm1:
            similarity = max(similarity, 0.8)
        
        return similarity
    
    async def find_potential_matches(self, target_name: str, province: str = None) -> List[Dict]:
        """Find potential matches for a name in the database"""
        if not self.db_conn:
            return []
        
        try:
            # Get all name variations
            variations = self.get_name_variations(target_name)
            
            matches = []
            
            # Try exact matches first
            for variation in variations:
                if province:
                    query = """
                        SELECT DISTINCT id, first_name, last_name, province, position, year
                        FROM political_dynasties 
                        WHERE CONCAT(first_name, ' ', last_name) ILIKE $1 
                        AND province = $2
                        ORDER BY year DESC
                        LIMIT 10
                    """
                    results = await self.db_conn.fetch(query, f"%{variation}%", province)
                else:
                    query = """
                        SELECT DISTINCT id, first_name, last_name, province, position, year
                        FROM political_dynasties 
                        WHERE CONCAT(first_name, ' ', last_name) ILIKE $1 
                        ORDER BY year DESC
                        LIMIT 10
                    """
                    results = await self.db_conn.fetch(query, f"%{variation}%")
                
                for result in results:
                    full_name = f"{result['first_name']} {result['last_name']}"
                    similarity = self.calculate_similarity(target_name, full_name)
                    
                    if similarity > 0.6:  # Threshold for potential matches
                        matches.append({
                            'id': result['id'],
                            'first_name': result['first_name'],
                            'last_name': result['last_name'],
                            'province': result['province'],
                            'position': result['position'],
                            'year': result['year'],
                            'similarity': similarity,
                            'match_type': 'exact' if similarity == 1.0 else 'fuzzy'
                        })
            
            # Remove duplicates and sort by similarity
            unique_matches = {}
            for match in matches:
                key = f"{match['first_name']}_{match['last_name']}_{match['province']}"
                if key not in unique_matches or match['similarity'] > unique_matches[key]['similarity']:
                    unique_matches[key] = match
            
            return sorted(unique_matches.values(), key=lambda x: x['similarity'], reverse=True)
            
        except Exception as e:
            print(f"❌ Error finding matches for '{target_name}': {e}")
            return []
    
    async def find_marriage_connections(self, person_name: str, province: str = None) -> List[Dict]:
        """Find potential marriage connections for a person"""
        if not self.db_conn:
            return []
        
        try:
            # Extract surname from the person
            parts = self.extract_name_parts(person_name)
            surname = parts['last_name']
            
            if not surname:
                return []
            
            # Look for people with different surnames in the same province
            if province:
                query = """
                    SELECT DISTINCT first_name, last_name, province, position, year
                    FROM political_dynasties 
                    WHERE province = $1 
                    AND last_name != $2
                    AND fat = 1
                    ORDER BY year DESC
                    LIMIT 20
                """
                results = await self.db_conn.fetch(query, province, surname)
            else:
                query = """
                    SELECT DISTINCT first_name, last_name, province, position, year
                    FROM political_dynasties 
                    WHERE last_name != $1
                    AND fat = 1
                    ORDER BY year DESC
                    LIMIT 20
                """
                results = await self.db_conn.fetch(query, surname)
            
            return [dict(result) for result in results]
            
        except Exception as e:
            print(f"❌ Error finding marriage connections for '{person_name}': {e}")
            return []
    
    async def suggest_name_connections(self, person_name: str, province: str = None) -> Dict:
        """Suggest potential connections for a person"""
        matches = await self.find_potential_matches(person_name, province)
        marriage_connections = await self.find_marriage_connections(person_name, province)
        
        return {
            'person': person_name,
            'province': province,
            'potential_matches': matches,
            'marriage_connections': marriage_connections,
            'suggestions': {
                'same_person_different_name': [m for m in matches if m['similarity'] > 0.8],
                'possible_marriage': marriage_connections[:5],
                'family_members': [m for m in matches if m['similarity'] > 0.6]
            }
        }

# Test the name matcher
async def test_name_matcher():
    """Test the advanced name matcher"""
    # Database connection
    conn = await asyncpg.connect(
        host='localhost',
        port='5432',
        user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu',
        database='dynasty'
    )
    
    try:
        matcher = AdvancedNameMatcher(conn)
        
        # Test with STEPHANY UY-TAN
        print("🔍 Testing with STEPHANY UY-TAN...")
        suggestions = await matcher.suggest_name_connections("STEPHANY UY-TAN", "SAMAR")
        
        print(f"📊 Found {len(suggestions['potential_matches'])} potential matches")
        print(f"💍 Found {len(suggestions['marriage_connections'])} marriage connections")
        
        # Show top matches
        for match in suggestions['potential_matches'][:3]:
            print(f"   - {match['first_name']} {match['last_name']} (similarity: {match['similarity']:.2f})")
        
        return suggestions
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(test_name_matcher())
