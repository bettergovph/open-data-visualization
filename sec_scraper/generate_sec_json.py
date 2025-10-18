#!/usr/bin/env python3
"""
Generate static/sec_contractors_database.json from PostgreSQL contractors table
This ensures a unified source of SEC data
"""

import asyncio
import asyncpg
import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

async def generate_sec_json():
    """Generate SEC contractors JSON from PostgreSQL database"""
    print("🚀 Generating SEC contractors JSON from database...")

    # Connect to database
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database='philgeps'
    )

    try:
        # Get all contractors from database
        contractors = await conn.fetch('''
            SELECT 
                contractor_name,
                sec_number,
                date_registered,
                status,
                address,
                secondary_licenses,
                created_at,
                updated_at
            FROM contractors
            ORDER BY contractor_name
        ''')

        # Build JSON structure
        contractors_list = []
        contractors_with_sec = 0
        contractors_without_sec = 0
        contractors_suspicious = 0  # Searched but yielded NO results

        for contractor in contractors:
            # Convert to dict
            contractor_dict = {
                'original_contractor_name': contractor['contractor_name'],
                'company_name': contractor['contractor_name'],
                'sec_number': contractor['sec_number'] or '',
                'status': contractor['status'] or '',
                'date_registered': str(contractor['date_registered']) if contractor['date_registered'] else '',
                'registered_address': contractor['address'] or '',
                'secondary_license_details': contractor['secondary_licenses'] or 'No records of secondary licenses were found.',
                'reportorial_submissions': '',
                'source': 'database',
                'processed_at': contractor['created_at'].isoformat() if contractor['created_at'] else '',
                'updated_at': contractor['updated_at'].isoformat() if contractor['updated_at'] else ''
            }

            contractors_list.append(contractor_dict)

            # Count contractors by category
            if contractor['sec_number'] and contractor['sec_number'].strip():
                contractors_with_sec += 1
            else:
                contractors_without_sec += 1
                # Check if this is suspicious (searched but no results)
                if contractor['status'] == 'NO_SEC_RESULTS':
                    contractors_suspicious += 1

        # Build complete JSON structure
        output = {
            'summary': {
                'total_contractors': len(contractors),
                'with_sec_data': contractors_with_sec,
                'without_sec_data': contractors_without_sec,
                'suspicious_no_results': contractors_suspicious,
                'last_updated': datetime.now().isoformat(),
                'processing_batch': 'database_generated',
                'source': 'PostgreSQL philgeps.contractors table'
            },
            'contractors': contractors_list
        }

        # Write to JSON file
        os.makedirs('static', exist_ok=True)
        with open('static/sec_contractors_database.json', 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"✅ Generated static/sec_contractors_database.json")
        print(f"   • Total contractors: {len(contractors)}")
        print(f"   • With SEC data: {contractors_with_sec}")
        print(f"   • Without SEC data: {contractors_without_sec}")
        print(f"   • ⚠️ Suspicious (NO SEC RESULTS): {contractors_suspicious}")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(generate_sec_json())

