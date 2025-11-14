#!/usr/bin/env python3
"""
Generate lightweight autocomplete file for relationship chains.
This script only creates the autocomplete file without generating the full cache.
It reads existing person-specific JSON files to build the autocomplete list.
"""

import os
import json
import asyncio
import asyncpg
from pathlib import Path
from typing import Dict, List, Any
from dotenv import load_dotenv

def load_env_from_dotenv():
    """Load environment variables from .env file"""
    env_path = Path(__file__).parent.parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)

async def generate_autocomplete_file():
    """Generate lightweight autocomplete file from existing person files"""
    load_env_from_dotenv()
    load_dotenv()
    
    cache_dir = Path("static/data")
    person_cache_dir = cache_dir / "relationship_chains_by_person"
    autocomplete_file = cache_dir / "relationship_chains_autocomplete.json"
    
    print("🔍 Generating autocomplete file from existing person files...")
    
    # Check if person files directory exists
    if not person_cache_dir.exists():
        print(f"❌ Person cache directory not found: {person_cache_dir}")
        print("   Please run the full cache generation script first to create person files.")
        return
    
    # Collect data from person files
    person_autocomplete = []
    chains_by_person = {}
    
    person_files = list(person_cache_dir.glob("*.json"))
    print(f"📁 Found {len(person_files)} person files")
    
    # Process files in batches to avoid memory issues
    batch_size = 100
    total_chains = 0
    
    for i, person_file in enumerate(person_files):
        try:
            # Read file and extract only what we need
            with open(person_file, 'r', encoding='utf-8') as f:
                person_data = json.load(f)
            
            # Extract person info and chain count (don't keep chains in memory)
            person_info = person_data.get('person', {})
            chains = person_data.get('chains', [])
            chain_count = len(chains)
            
            # Clear chains from memory immediately
            del chains
            if 'chains' in person_data:
                del person_data['chains']
            
            normalized_name = person_info.get('normalized_name')
            if not normalized_name:
                # Try to infer from filename
                normalized_name = person_file.stem.replace('_', ' ')
            
            display_name = person_info.get('display_name', normalized_name)
            
            if normalized_name and chain_count > 0:
                person_autocomplete.append({
                    "normalized_name": normalized_name,
                    "display_name": display_name,
                    "chain_count": chain_count
                })
                
                # For chains_by_person, store count (frontend can check if > 0)
                chains_by_person[normalized_name] = chain_count
            
            total_chains += chain_count
            
            if (i + 1) % batch_size == 0:
                print(f"  Processed {i + 1}/{len(person_files)} files...", flush=True)
        
        except Exception as e:
            print(f"⚠️  Error reading {person_file.name}: {e}")
            continue
    
    # Sort autocomplete by chain count (descending) then by name
    person_autocomplete.sort(key=lambda x: (-x['chain_count'], x['display_name']))
    
    print(f"✅ Collected {len(person_autocomplete)} persons")
    print(f"   Total chains: {sum(p['chain_count'] for p in person_autocomplete)}")
    
    # Create autocomplete data
    autocomplete_data = {
        "person_autocomplete": person_autocomplete,
        "chains_by_person": chains_by_person
    }
    
    # Write autocomplete file
    with open(autocomplete_file, 'w', encoding='utf-8') as f:
        json.dump(autocomplete_data, f, indent=2, ensure_ascii=False)
    
    file_size = autocomplete_file.stat().st_size / 1024  # KB
    print(f"✅ Autocomplete file generated: {autocomplete_file}")
    print(f"   File size: {file_size:.1f} KB")
    print(f"   Persons: {len(person_autocomplete)}")
    print(f"   Chains index: {len(chains_by_person)} entries")

if __name__ == "__main__":
    asyncio.run(generate_autocomplete_file())

