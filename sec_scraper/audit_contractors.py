#!/usr/bin/env python3
"""
Audit philgeps.contractors for unsplit names and invalid entries
"""

import asyncpg
import asyncio
import os
from dotenv import load_dotenv
import re

load_dotenv('.env')

# Common generic words that shouldn't be standalone contractor names
COMMON_WORDS = {
    'SUPPLY', 'CONSTRUCTION', 'BUILDERS', 'TRADING', 'ENTERPRISE', 'ENTERPRISES',
    'INC', 'CORP', 'CORPORATION', 'CO', 'COMPANY', 'LTD', 'LIMITED',
    'THE', 'AND', 'FOR', 'OF', 'GENERAL', 'SERVICES', 'DEVELOPMENT'
}

def needs_splitting(name):
    """Check if contractor name needs to be split"""
    issues = []
    
    # Check for FORMERLY/FORMER indicators
    if re.search(r'\b(FORMERLY|FORMER|PREVIOUSLY|PREV)\b', name, re.IGNORECASE):
        issues.append('HAS_FORMER_NAME')
    
    # Check for JV indicator (/)
    if '/' in name:
        issues.append('HAS_JV_SLASH')
    
    # Check for parentheses with former
    if '(' in name and ')' in name:
        if re.search(r'\([^)]*(?:FORMERLY|FORMER)[^)]*\)', name, re.IGNORECASE):
            issues.append('HAS_PAREN_FORMER')
        # Check for other parenthetical content that might need splitting
        elif re.search(r'\([^)]{10,}\)', name):  # Long content in parens
            issues.append('HAS_LONG_PAREN')
    
    return issues

def is_invalid_name(name):
    """Check if name is invalid (single common word, too short, etc.)"""
    issues = []
    
    # Check if name is too short
    if len(name) < 5:
        issues.append('TOO_SHORT')
    
    # Check if single word
    words = name.split()
    if len(words) == 1:
        # Check if it's a common word
        if name.upper() in COMMON_WORDS:
            issues.append('SINGLE_COMMON_WORD')
        else:
            issues.append('SINGLE_WORD')
    
    # Check if ALL words are common
    if len(words) > 0:
        non_common_words = [w for w in words if w.upper() not in COMMON_WORDS]
        if len(non_common_words) == 0:
            issues.append('ALL_COMMON_WORDS')
    
    # Check for malformed JSON fragments
    if '", "' in name or 'logoUrl' in name or 'nameAbbreviation' in name:
        issues.append('JSON_FRAGMENT')
    
    return issues

async def main():
    print("🔍 Auditing philgeps.contractors table...\n")
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_PHILGEPS', 'philgeps')
    )
    
    # Get all contractors
    contractors = await conn.fetch('SELECT id, contractor_name, source FROM contractors ORDER BY id')
    
    await conn.close()
    
    print(f"📊 Total contractors in database: {len(contractors)}\n")
    
    # Audit results
    needs_split = []
    invalid = []
    clean = []
    
    for row in contractors:
        contractor_id = row['id']
        name = row['contractor_name']
        source = row['source']
        
        split_issues = needs_splitting(name)
        invalid_issues = is_invalid_name(name)
        
        if split_issues:
            needs_split.append({
                'id': contractor_id,
                'name': name,
                'source': source,
                'issues': split_issues
            })
        elif invalid_issues:
            invalid.append({
                'id': contractor_id,
                'name': name,
                'source': source,
                'issues': invalid_issues
            })
        else:
            clean.append(name)
    
    # Report findings
    print(f"✅ Clean contractors: {len(clean)}")
    print(f"⚠️  Needs splitting: {len(needs_split)}")
    print(f"❌ Invalid names: {len(invalid)}\n")
    
    if needs_split:
        print(f"🔧 CONTRACTORS THAT NEED SPLITTING ({len(needs_split)}):")
        print(f"   Showing first 30:\n")
        for item in needs_split[:30]:
            issues_str = ', '.join(item['issues'])
            print(f"   ID {item['id']:5} [{issues_str:20}] {item['name'][:80]}")
        
        if len(needs_split) > 30:
            print(f"\n   ... and {len(needs_split) - 30} more")
    
    print()
    
    if invalid:
        print(f"❌ INVALID CONTRACTOR NAMES ({len(invalid)}):")
        print(f"   Showing first 30:\n")
        for item in invalid[:30]:
            issues_str = ', '.join(item['issues'])
            print(f"   ID {item['id']:5} [{issues_str:25}] {item['name'][:70]}")
        
        if len(invalid) > 30:
            print(f"\n   ... and {len(invalid) - 30} more")
    
    print(f"\n📊 Summary:")
    print(f"   Total: {len(contractors)}")
    print(f"   Clean: {len(clean)} ({len(clean)/len(contractors)*100:.1f}%)")
    print(f"   Needs splitting: {len(needs_split)} ({len(needs_split)/len(contractors)*100:.1f}%)")
    print(f"   Invalid: {len(invalid)} ({len(invalid)/len(contractors)*100:.1f}%)")

if __name__ == '__main__':
    asyncio.run(main())

