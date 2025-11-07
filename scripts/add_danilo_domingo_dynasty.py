#!/usr/bin/env python3
"""
Add or update Danilo Domingo in the political dynasties database.
"""

import asyncio
import asyncpg
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

CONGRESSMAN_DATA = {
    "first_name": "Danilo",
    "middle_name": "A.",
    "last_name": "Domingo",
    "nickname": "Danny",
    "aliases": ["Danilo Domingo", "Danilo A. Domingo", "Danny Domingo"],
    "party": "National Unity Party (NUP)",
    "position": "Representative, Bulacan 1st District",
    "province": "Bulacan",
    "municipality_city": "Malolos City",
    "region": "Region III (Central Luzon)",
    "district": "1st District",
    "dynasty_family_id": "Domingo"
}

async def add_or_update_congressman():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )

    try:
        record = await conn.fetchrow(
            "SELECT id FROM political_dynasties WHERE first_name = $1 AND last_name = $2",
            CONGRESSMAN_DATA["first_name"],
            CONGRESSMAN_DATA["last_name"]
        )

        if record:
            person_id = record["id"]
            print(f"✅ Danilo Domingo already exists (ID: {person_id}), updating details...")
            await conn.execute(
                """
                UPDATE political_dynasties
                SET nickname = $1,
                    middle_name = $2,
                    party = $3,
                    position = $4,
                    province = $5,
                    municipality_city = $6,
                    region = $7,
                    district = $8,
                    dynasty_family_id = $9,
                    aliases = $10,
                    last_updated = NOW()
                WHERE id = $11
                """,
                CONGRESSMAN_DATA["nickname"],
                CONGRESSMAN_DATA["middle_name"],
                CONGRESSMAN_DATA["party"],
                CONGRESSMAN_DATA["position"],
                CONGRESSMAN_DATA["province"],
                CONGRESSMAN_DATA["municipality_city"],
                CONGRESSMAN_DATA["region"],
                CONGRESSMAN_DATA["district"],
                CONGRESSMAN_DATA["dynasty_family_id"],
                CONGRESSMAN_DATA["aliases"],
                person_id
            )
            print("🔄 Updated existing record.")
        else:
            print("➕ Inserting Danilo Domingo into political_dynasties...")
            person_id = await conn.fetchval(
                """
                INSERT INTO political_dynasties (
                    first_name,
                    middle_name,
                    last_name,
                    nickname,
                    party,
                    position,
                    province,
                    municipality_city,
                    region,
                    district,
                    dynasty_family_id,
                    aliases,
                    last_updated
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
                RETURNING id
                """,
                CONGRESSMAN_DATA["first_name"],
                CONGRESSMAN_DATA["middle_name"],
                CONGRESSMAN_DATA["last_name"],
                CONGRESSMAN_DATA["nickname"],
                CONGRESSMAN_DATA["party"],
                CONGRESSMAN_DATA["position"],
                CONGRESSMAN_DATA["province"],
                CONGRESSMAN_DATA["municipality_city"],
                CONGRESSMAN_DATA["region"],
                CONGRESSMAN_DATA["district"],
                CONGRESSMAN_DATA["dynasty_family_id"],
                CONGRESSMAN_DATA["aliases"]
            )
            print(f"✅ Inserted Danilo Domingo with ID: {person_id}")

        print("📌 Reminder: Update family or political predecessor relationships separately if needed.")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(add_or_update_congressman())
