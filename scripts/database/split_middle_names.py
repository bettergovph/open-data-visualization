#!/usr/bin/env python3
"""
Split middle names from `first_name` into `middle_name` for `political_dynasties`.

Rules:
- If `middle_name` is NULL/empty and `first_name` has >1 token, move tokens after the first into `middle_name`.
- Preserve capitalization as-is.
- Handles PH-style initials like "A." or "A.B." as middle_name tokens.
"""

import asyncio
import os
import re
import asyncpg
from dotenv import load_dotenv


def split_first_and_middle(name: str):
    name = (name or '').strip()
    parts = [p for p in re.split(r"\s+", name) if p]
    if len(parts) <= 1:
        return name, ''
    return parts[0], ' '.join(parts[1:])


async def main():
    load_dotenv()
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )

    try:
        # Ensure middle_name column exists
        await conn.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='political_dynasties' AND column_name='middle_name'
                ) THEN
                    ALTER TABLE political_dynasties ADD COLUMN middle_name TEXT;
                END IF;
            END$$;
            """
        )

        rows = await conn.fetch(
            """
            SELECT id, first_name, middle_name, last_name
            FROM political_dynasties
            WHERE (middle_name IS NULL OR middle_name = '')
              AND first_name ~ '\\s'
            LIMIT 100000
            """
        )

        print(f"🔧 Found {len(rows)} rows with potential middle names to split")
        updated = 0

        for r in rows:
            pid = r['id']
            first_name = r['first_name'] or ''
            new_first, new_middle = split_first_and_middle(first_name)
            if new_middle:
                await conn.execute(
                    """
                    UPDATE political_dynasties
                    SET first_name = $1, middle_name = $2
                    WHERE id = $3
                    """,
                    new_first, new_middle, pid
                )
                updated += 1

        print(f"✅ Updated {updated} rows with separated middle names")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())








