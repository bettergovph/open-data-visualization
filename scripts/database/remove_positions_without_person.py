import asyncio
import os
from pathlib import Path
from datetime import datetime

import asyncpg


def load_env_from_dotenv() -> None:
    """Load environment variables from the project's .env file without extra deps.

    Priority: keep existing env vars; only set if not already present.
    """
    # Assume repo root is two levels up from this script
    root = Path(__file__).resolve().parents[2]
    env_path = root / '.env'
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            continue
        key, val = line.split('=', 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


async def remove_positions_without_person(dry_run: bool = True) -> int:
    """Delete rows that have a position but no assigned person (both names empty).

    - Reads DB config from environment (.env is loaded automatically).
    - Collects distinct positions from the rows to be removed and writes them to a txt file
      when not a dry run.
    - Returns count of rows affected (or that would be affected if dry_run=True).
    """
    load_env_from_dotenv()

    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )

    # Candidates: rows where both names are empty/blank AND position present
    candidates_sql = """
        SELECT id, position
        FROM political_dynasties
        WHERE COALESCE(TRIM(position), '') <> ''
          AND (COALESCE(TRIM(first_name), '') = '' AND COALESCE(TRIM(last_name), '') = '')
    """

    rows = await conn.fetch(candidates_sql)
    to_remove_ids = [r['id'] for r in rows]
    removed_positions = sorted({(r['position'] or '').strip() for r in rows if (r['position'] or '').strip()})

    if dry_run or not to_remove_ids:
        await conn.close()
        return len(to_remove_ids)

    async with conn.transaction():
        # Delete by IDs in batches to avoid parameter explosion
        BATCH = 5000
        for i in range(0, len(to_remove_ids), BATCH):
            batch = to_remove_ids[i:i + BATCH]
            # Use ANY($1::int[])
            await conn.execute(
                "DELETE FROM political_dynasties WHERE id = ANY($1::int[])",
                batch
            )

    await conn.close()

    # Write removed positions to a timestamped txt file under scripts/database
    out_dir = Path(__file__).resolve().parent
    ts = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
    out_path = out_dir / f"removed_positions_{ts}.txt"
    out_path.write_text("\n".join(removed_positions), encoding='utf-8')

    return len(to_remove_ids)


async def main():
    dry_run_env = os.getenv('DRY_RUN', '1').strip()
    dry_run = dry_run_env not in ('0', 'false', 'False')
    removed = await remove_positions_without_person(dry_run=dry_run)
    if dry_run:
        print(f"[DRY-RUN] Rows that would be removed: {removed}")
    else:
        print(f"Rows removed: {removed}")


if __name__ == '__main__':
    asyncio.run(main())






