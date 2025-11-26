import asyncio
import asyncpg
import json

async def check_manila():
    conn = await asyncpg.connect(
        host='localhost',
        database='dynasty',
        user='postgres',
        password='postgres'
    )

    # Get Manila district data
    result = await conn.fetchrow('SELECT data FROM district_entries WHERE name = $1', 'Manila')

    if result:
        data = json.loads(result['data'])
        print('Current Manila districts in database:')
        for district, barangays in data.get('barangays', {}).items():
            print(f'{district}: {len(barangays)} barangays - {barangays[:3]}...')
    else:
        print('No Manila entry found in database')

    await conn.close()

asyncio.run(check_manila())


















