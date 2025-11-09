import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

async def check_db_manila():
    load_dotenv()
    conn = await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        user=os.getenv("POSTGRES_USER", "budget_admin"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        database=os.getenv("POSTGRES_DB_DYNASTY", "dynasty"),
    )
    await conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")

    # Get Manila district data
    result = await conn.fetchrow('SELECT data FROM district_entries WHERE name = $1', 'Manila')

    if result:
        data = result['data']
        print(f"Type of data: {type(data)}")
        print(f"Data: {data}")

        if isinstance(data, str):
            print("Data is a string, parsing...")
            parsed = json.loads(data)
            print(f"Parsed type: {type(parsed)}")
            print(f"Parsed barangays keys: {list(parsed.get('barangays', {}).keys())[:3]}")

    await conn.close()

asyncio.run(check_db_manila())
