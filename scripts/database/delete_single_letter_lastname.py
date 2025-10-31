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


async def delete_single_letter_lastname() -> int:
    load_env_from_dotenv()
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )

    count = await conn.fetchval(
        """
        SELECT COUNT(*) FROM political_dynasties
        WHERE TRIM(last_name) ~ '^[A-Za-z]$'
           OR TRIM(last_name) ~ '^[A-Za-z]\.$'
           OR UPPER(TRIM(last_name)) = 'AB'
        """
    )

    if count == 0:
        await conn.close()
        return 0

    async with conn.transaction():
        await conn.execute(
            """
            DELETE FROM political_dynasties
            WHERE TRIM(last_name) ~ '^[A-Za-z]$'
               OR TRIM(last_name) ~ '^[A-Za-z]\.$'
               OR UPPER(TRIM(last_name)) = 'AB'
            """
        )

    await conn.close()
    return int(count)


async def main():
    deleted = await delete_single_letter_lastname()
    print(f"Rows deleted (single-letter or letter-dot last names, plus 'AB'): {deleted}")


if __name__ == '__main__':
    asyncio.run(main())






