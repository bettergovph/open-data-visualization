import asyncio
import os
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


async def list_top_lastnames(limit: int = 100):
    load_env_from_dotenv()
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )

    rows = await conn.fetch(
        f"""
        SELECT UPPER(TRIM(last_name)) AS last_name, COUNT(*) AS occurrences
        FROM political_dynasties
        WHERE TRIM(COALESCE(last_name,'')) <> ''
        GROUP BY UPPER(TRIM(last_name))
        ORDER BY occurrences DESC, last_name ASC
        LIMIT {limit}
        """
    )
    await conn.close()

    return [(r['last_name'], r['occurrences']) for r in rows]


async def main():
    res = await list_top_lastnames()
    for ln, cnt in res:
        print(f"{ln},{cnt}")


if __name__ == '__main__':
    asyncio.run(main())






