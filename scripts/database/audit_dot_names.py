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


async def main():
    load_env_from_dotenv()
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )

    first_dot = await conn.fetchval("SELECT COUNT(*) FROM political_dynasties WHERE TRIM(first_name)='.'")
    last_dot = await conn.fetchval("SELECT COUNT(*) FROM political_dynasties WHERE TRIM(last_name)='.'")
    first_empty = await conn.fetchval("SELECT COUNT(*) FROM political_dynasties WHERE TRIM(COALESCE(first_name,''))=''")
    last_empty = await conn.fetchval("SELECT COUNT(*) FROM political_dynasties WHERE TRIM(COALESCE(last_name,''))=''")

    print(f"first_name='.' count: {first_dot}")
    print(f"last_name='.' count: {last_dot}")
    print(f"first_name empty count: {first_empty}")
    print(f"last_name empty count: {last_empty}")

    print("\nSamples where first_name='.' (up to 10):")
    rows = await conn.fetch("SELECT id, first_name, last_name FROM political_dynasties WHERE TRIM(first_name)='.' LIMIT 10")
    for r in rows:
        print(dict(r))

    print("\nSamples where last_name='.' (up to 10):")
    rows = await conn.fetch("SELECT id, first_name, last_name FROM political_dynasties WHERE TRIM(last_name)='.' LIMIT 10")
    for r in rows:
        print(dict(r))

    await conn.close()


if __name__ == '__main__':
    asyncio.run(main())






