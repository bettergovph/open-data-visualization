import asyncio
import os
from pathlib import Path
import re

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


def load_dictionary_words() -> set:
    words = set()
    # Prefer system dictionary if present
    for path in ["/usr/share/dict/words", "/usr/share/dict/american-english", "/usr/share/dict/english"]:
        p = Path(path)
        if p.exists():
            for w in p.read_text(encoding='utf-8', errors='ignore').splitlines():
                w = w.strip().lower()
                if w and w.isalpha():
                    words.add(w)
            break
    # Fallback minimal list if system dict missing
    if not words:
        baseline = [
            'road','bridge','contract','location','address','range','fund','works','work','date','city','subject',
            'name','prepared','approved','number','length','issue','posting','visit','program'
        ]
        words.update(baseline)
    return words


ONLY_ALPHA = re.compile(r"^[A-Za-z][A-Za-z\-']*[A-Za-z]$|^[A-Za-z]$")


async def delete_dictionary_names() -> int:
    load_env_from_dotenv()
    words = load_dictionary_words()

    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )

    # Fetch candidate rows where both names are alphabetic (to avoid deleting surnames with punctuation)
    rows = await conn.fetch(
        """
        SELECT id, first_name, last_name
        FROM political_dynasties
        WHERE TRIM(COALESCE(first_name,'')) <> ''
          AND TRIM(COALESCE(last_name,'')) <> ''
        """
    )

    to_delete_ids = []
    for r in rows:
        fn = (r['first_name'] or '').strip()
        ln = (r['last_name'] or '').strip()
        # Only consider simple alpha tokens (allow hyphen/apostrophe in between)
        if not ONLY_ALPHA.match(fn) or not ONLY_ALPHA.match(ln):
            continue
        if fn.lower() in words and ln.lower() in words:
            to_delete_ids.append(r['id'])

    if not to_delete_ids:
        await conn.close()
        print("Rows deleted (dictionary names): 0")
        return 0

    async with conn.transaction():
        BATCH = 5000
        for i in range(0, len(to_delete_ids), BATCH):
            batch = to_delete_ids[i:i + BATCH]
            await conn.execute("DELETE FROM political_dynasties WHERE id = ANY($1::int[])", batch)

    await conn.close()
    print(f"Rows deleted (dictionary names): {len(to_delete_ids)}")
    return len(to_delete_ids)


async def main():
    await delete_dictionary_names()


if __name__ == '__main__':
    asyncio.run(main())






