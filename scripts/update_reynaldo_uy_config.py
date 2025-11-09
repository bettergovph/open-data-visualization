import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

async def update_reynaldo_uy():
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

    result = await conn.fetchrow(
        "SELECT id, province, district_number, barangays FROM dynasty_projects_congressmen_config WHERE display_name = $1",
        'Reynaldo Uy'
    )
    if not result:
        print('Reynaldo Uy not found in config table')
        await conn.close()
        return
    print('Before:', dict(result))

    await conn.execute(
        """
        UPDATE dynasty_projects_congressmen_config
        SET province = $1,
            district_number = $2,
            is_city_district = FALSE,
            barangays = $3
        WHERE display_name = $4
        """,
        'Samar',
        '1st District',
        json.dumps([]),
        'Reynaldo Uy'
    )

    updated = await conn.fetchrow(
        "SELECT id, province, district_number, barangays FROM dynasty_projects_congressmen_config WHERE display_name = $1",
        'Reynaldo Uy'
    )
    print('After:', dict(updated))

    await conn.close()

asyncio.run(update_reynaldo_uy())
