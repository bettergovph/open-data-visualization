import asyncio
import os
from datetime import datetime
from pathlib import Path

import asyncpg


def load_env_from_dotenv() -> None:
    root = Path(__file__).resolve().parents[2]
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


TARGET_PARTY_LIST = [
    ("35", "ABANTE BISDAK"),
    ("51", "AKBAYAN"),
    ("14", "ARTE"),
    ("59", "BAYAN MUNA"),
    ("132", "GP"),
    ("62", "SBP"),
    ("47", "TINGOG"),
    ("21", "ACT TEACHERS"),
    ("88", "AGRI"),
    ("124", "AKO BISAYA"),
    ("26", "AKSYON DAPAT"),
    ("69", "AKTIBONG KAAGAPAY"),
    ("123", "API PARTY"),
    ("41", "ARISE"),
    ("94", "BH - BAGONG HENERASYON"),
    ("10", "BICOL SARO"),
    ("87", "BUNYOG"),
]


async def move_party_list_entries(dry_run: bool = True, include_numeric_codes: bool = True) -> dict:
    """Create table party_list if missing, insert distinct party-list entries with counts, then delete matching rows."""
    load_env_from_dotenv()
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )

    # Ensure table exists
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS party_list (
            id SERIAL PRIMARY KEY,
            code TEXT NOT NULL,
            party_name TEXT NOT NULL,
            occurrences INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        )
        """
    )
    # Ensure uniqueness on (code, party_name) for upsert
    await conn.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = 'party_list_code_party_name_key'
            ) THEN
                ALTER TABLE party_list ADD CONSTRAINT party_list_code_party_name_key UNIQUE (code, party_name);
            END IF;
        END$$;
        """
    )

    # Aggregate counts from political_dynasties for each target pair
    results = []
    total_rows = 0
    for code, party in TARGET_PARTY_LIST:
        n = await conn.fetchval(
            """
            SELECT COUNT(*) FROM political_dynasties
            WHERE UPPER(TRIM(first_name)) = $1 AND UPPER(TRIM(last_name)) = $2
            """,
            code.upper(), party.upper()
        )
        results.append((code, party, int(n)))
        total_rows += int(n)

    # Optionally include all entries where first_name is numeric code and last_name is non-empty
    numeric_results = []
    if include_numeric_codes:
        rows = await conn.fetch(
            """
            SELECT UPPER(TRIM(first_name)) AS code, UPPER(TRIM(last_name)) AS party_name, COUNT(*) AS cnt
            FROM political_dynasties
            WHERE TRIM(first_name) ~ '^\\d+$' AND COALESCE(TRIM(last_name), '') <> ''
            GROUP BY UPPER(TRIM(first_name)), UPPER(TRIM(last_name))
            """
        )
        for r in rows:
            code = r['code']
            party = r['party_name']
            cnt = int(r['cnt'])
            # Avoid double-counting items already in TARGET_PARTY_LIST aggregation
            if not any(code == c and party == p for c, p, _ in results):
                numeric_results.append((code, party, cnt))
                total_rows += cnt
        results.extend(numeric_results)

    if dry_run or total_rows == 0:
        await conn.close()
        return {"inserted": 0, "deleted": 0, "details": results}

    async with conn.transaction():
        # Insert or update party_list entries
        for code, party, count in results:
            if count == 0:
                continue
            await conn.execute(
                """
                INSERT INTO party_list (code, party_name, occurrences)
                VALUES ($1, $2, $3)
                ON CONFLICT (code, party_name) DO UPDATE SET occurrences = party_list.occurrences + EXCLUDED.occurrences
                """,
                code, party, count
            )
        # Remove from political_dynasties
        await conn.executemany(
            """
            DELETE FROM political_dynasties
            WHERE UPPER(TRIM(first_name)) = $1 AND UPPER(TRIM(last_name)) = $2
            """,
            [(c.upper(), p.upper()) for c, p, cnt in results if cnt > 0]
        )

    await conn.close()
    return {"inserted": sum(1 for _, _, cnt in results if cnt > 0), "deleted": total_rows, "details": results}


async def main():
    dry_run_env = os.getenv('DRY_RUN', '1').strip()
    dry_run = dry_run_env not in ('0', 'false', 'False')
    result = await move_party_list_entries(dry_run=dry_run, include_numeric_codes=True)
    if dry_run:
        print("[DRY-RUN] Party-list move summary:")
    else:
        print("Party-list move summary:")
    for code, party, cnt in result["details"]:
        print(f"{code},{party},{cnt}")
    print(f"Inserted entries: {result['inserted']}, Deleted rows: {result['deleted']}")


if __name__ == '__main__':
    asyncio.run(main())


