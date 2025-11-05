#!/usr/bin/env python3
"""
Fix congressmen in database - add missing ones and update existing ones based on Perplexity results
Order: DB first, then API, then frontend
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv
from pathlib import Path


def load_env_from_dotenv():
    """Load environment variables from .env file"""
    root = Path(__file__).resolve().parent
    env_path = root / '.env'
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


async def get_dynasty_conn():
    """Get connection to Dynasty database"""
    return await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )


async def fix_congressmen_db():
    """Add/update congressmen in database based on Perplexity verification"""
    
    load_env_from_dotenv()
    load_dotenv()
    
    conn = await get_dynasty_conn()
    
    # Only update congressmen that exist in DB (with evidence from Perplexity CSV)
    # We have Perplexity CSV evidence for these existing entries:
    congressmen = [
        {
            'first_name': 'AURELIO',
            'last_name': 'GONZALES',
            'middle_name': 'DUEÑAS',
            'display': 'Aurelio Dueñas Gonzales Jr.',
            'district': 'Pampanga 3rd District',
            'province': 'Pampanga',
            'municipality': None,
            'region': 'REGION III',
            'party': 'Lakas-CMD',
            'position': 'MEMBER, HOUSE OF REPRESENTATIVES',
            'db_id': 4148110  # From evidence check
        },
        {
            'first_name': 'MANUEL JOSE',
            'last_name': 'DALIPE',
            'middle_name': 'MENDOZA',
            'display': 'Manuel Jose Mendoza Dalipe',
            'district': 'Zamboanga City 2nd District',
            'province': 'Zamboanga City',
            'municipality': None,
            'region': 'REGION IX',
            'party': 'Nationalist People\'s Coalition',
            'position': 'MEMBER, HOUSE OF REPRESENTATIVES',
            'db_id': 4157807  # From evidence check
        },
        {
            'first_name': 'EDWIN',
            'last_name': 'GARDIOLA',
            'middle_name': 'LOLENG',
            'display': 'Tirso Edwin Loleng Gardiola',
            'district': 'Construction Workers Solidarity (CWS) Party-list',
            'province': None,
            'municipality': None,
            'region': None,
            'party': '135, CWS',
            'position': 'REPRESENTATIVE, CWS PARTY-LIST',
            'db_id': 4162452  # From evidence check
        },
    ]
    
    print('='*80)
    print('FIXING CONGRESSMEN IN DATABASE')
    print('='*80)
    
    updated = 0
    inserted = 0
    
    for cm in congressmen:
        print(f'\n📋 Processing: {cm["display"]}')
        
        # Check if exists
        existing = await conn.fetchrow('''
            SELECT id, first_name, last_name, middle_name, position, province, region, party
            FROM political_dynasties
            WHERE (UPPER(first_name) LIKE $1 AND UPPER(last_name) LIKE $2)
              AND (
                UPPER(position) LIKE '%CONGRESSMAN%' 
                OR UPPER(position) LIKE '%CONGRESSMEN%' 
                OR UPPER(position) LIKE '%MEMBER, HOUSE OF REPRESENTATIVES%'
                OR UPPER(position) LIKE '%REPRESENTATIVE%PARTY-LIST%'
                OR UPPER(position) LIKE '%REPRESENTATIVE, %PARTY-LIST%'
              )
            ORDER BY id DESC
            LIMIT 1
        ''', f'%{cm["first_name"]}%', f'%{cm["last_name"]}%')
        
        # Only update if we have DB ID evidence
        if 'db_id' in cm:
            # Update by specific ID (we have evidence this exists)
            existing = await conn.fetchrow('SELECT id, first_name, last_name, middle_name, position, province, region, party FROM political_dynasties WHERE id = $1', cm['db_id'])
            
            if existing:
                print(f'   ✅ Found existing (ID: {existing["id"]})')
                
                # Check what needs updating (only update if Perplexity CSV provides evidence)
                updates = {}
                if existing.get('middle_name') != cm['middle_name'] and cm['middle_name']:
                    updates['middle_name'] = cm['middle_name']
                if existing.get('province') != cm['province'] and cm['province']:
                    updates['province'] = cm['province']
                if existing.get('region') != cm['region'] and cm['region']:
                    updates['region'] = cm['region']
                if existing.get('party') != cm['party'] and cm['party']:
                    updates['party'] = cm['party']
                if existing.get('position') != cm['position'] and cm['position']:
                    updates['position'] = cm['position']
                
                if updates:
                    set_clause = ', '.join([f'{k} = ${i+2}' for i, k in enumerate(updates.keys())])
                    values = [existing['id']] + list(updates.values())
                    
                    await conn.execute(f'''
                        UPDATE political_dynasties
                        SET {set_clause}
                        WHERE id = $1
                    ''', *values)
                    
                    print(f'   ✅ Updated: {", ".join(updates.keys())}')
                    updated += 1
                else:
                    print(f'   ✓ Already up to date')
            else:
                print(f'   ⚠️  DB ID {cm["db_id"]} not found - skipping')
        else:
            print(f'   ⚠️  No DB ID evidence - skipping (need evidence to insert/update)')
    
    print(f'\n{"="*80}')
    print(f'SUMMARY')
    print(f'{"="*80}')
    print(f'Updated: {updated}')
    print(f'Inserted: {inserted}')
    print(f'Total processed: {len(congressmen)}')
    
    await conn.close()


if __name__ == '__main__':
    asyncio.run(fix_congressmen_db())

