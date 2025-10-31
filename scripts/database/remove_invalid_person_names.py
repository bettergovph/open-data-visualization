import asyncio
import os
import re
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


BLACKLIST_TERMS = {
    # Common non-person tokens seen in scraped docs
    'BY', 'FOLLOWING', 'CERNING', 'CONCERNING', 'REGARDING', 'PURSUANT', 'THE', 'AND', 'OF', 'ING',
    'MANUAL', 'SUBMISSION',
    'BAC', 'BIDS', 'AWARDS', 'COMMITTEE', 'CHAIRMAN', 'MEMBERS', 'SECRETARIAT',
    'REQUEST', 'FOR', 'QUOTATION', 'INVITATION', 'TO', 'BID',
}

# A conservative name pattern: letters with optional spaces/hyphens/apostrophes/periods
# e.g., "Juan", "ANNA MARIE", "O'BRIEN", "S. CRUZ", "DE LA CRUZ"
NAME_PATTERN = re.compile(r"^[A-Z .'-]+$")


def looks_like_person(value: str) -> bool:
    if not value:
        return False
    s = value.strip().upper()
    if not s:
        return False
    # too short to be meaningful
    if len(s) < 2:
        return False
    # must match allowed chars
    if not NAME_PATTERN.match(s):
        return False
    # single blacklist token
    if s in BLACKLIST_TERMS:
        return False
    # if consists only of common document words
    tokens = [t for t in re.split(r"\s+", s) if t]
    token_set = set(tokens)
    if token_set and token_set.issubset(BLACKLIST_TERMS):
        return False
    # must have at least one token with 2+ letters
    if not any(len(t) >= 2 and t.isalpha() for t in tokens):
        return False
    return True


async def remove_invalid_person_names(dry_run: bool = True) -> int:
    """Remove rows where both first_name and last_name fail person heuristics.

    Writes distinct offending name pairs to a txt file when not a dry run.
    """
    load_env_from_dotenv()
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )

    # Fetch a slice of potentially noisy rows where names contain non-alpha or are very short
    rows = await conn.fetch(
        """
        SELECT id, COALESCE(first_name, '') AS first_name, COALESCE(last_name, '') AS last_name, position
        FROM political_dynasties
        WHERE (first_name IS NOT NULL OR last_name IS NOT NULL)
        """
    )

    to_remove_ids = []
    removed_names = set()

    for r in rows:
        first_name = (r['first_name'] or '').strip()
        last_name = (r['last_name'] or '').strip()
        first_ok = looks_like_person(first_name)
        last_ok = looks_like_person(last_name)
        # Remove when neither side looks like a person
        if not first_ok and not last_ok:
            to_remove_ids.append(r['id'])
            removed_names.add(f"{first_name} | {last_name}")

    if dry_run or not to_remove_ids:
        await conn.close()
        return len(to_remove_ids)

    async with conn.transaction():
        BATCH = 5000
        for i in range(0, len(to_remove_ids), BATCH):
            batch = to_remove_ids[i:i + BATCH]
            await conn.execute("DELETE FROM political_dynasties WHERE id = ANY($1::int[])", batch)

    await conn.close()

    out_dir = Path(__file__).resolve().parent
    ts = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
    out_path = out_dir / f"removed_invalid_names_{ts}.txt"
    out_path.write_text("\n".join(sorted(removed_names)), encoding='utf-8')

    return len(to_remove_ids)


async def main():
    dry_run_env = os.getenv('DRY_RUN', '1').strip()
    dry_run = dry_run_env not in ('0', 'false', 'False')
    removed = await remove_invalid_person_names(dry_run=dry_run)
    if dry_run:
        print(f"[DRY-RUN] Rows that would be removed (invalid names): {removed}")
    else:
        print(f"Rows removed (invalid names): {removed}")


if __name__ == '__main__':
    asyncio.run(main())


