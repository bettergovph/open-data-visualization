import asyncio
import os
import re
from typing import List, Tuple
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


# Match either ' A. ' or ' A ' as initial tokens (space + single cap letter + optional dot + space)
INITIAL_PATTERN = re.compile(r"(?<=\s)[A-Z]\.?\s")

# Common role/position tokens to strip prior to splitting (uppercased compare)
ROLE_TOKENS = {
    'ENGINEER', 'ENGINEER I', 'ENGINEER II', 'ENGINEER III', 'ENGINEER IV',
    'BOTTOM', 'BAR', 'BOTTOM BAR', 'TOP', 'SECTION', 'UNIT', 'OFFICE', 'DIVISION',
}

PAREN_RE = re.compile(r"\s*\([^\)]*\)\s*")


def split_persons_by_initials(full_name: str) -> List[str]:
    """Split a concatenated name string into multiple person segments.

    Heuristic: each person segment ends at the surname immediately following an
    initial token ' X. ' (space, uppercase letter, dot, space). We require spaces
    around to avoid 'AB.' cases. Returns list of segments with original spacing preserved.
    """
    text = f" {full_name.strip()} "  # pad to simplify lookbehind and following token capture
    matches = list(INITIAL_PATTERN.finditer(text))
    if len(matches) < 2:
        return []

    segments: List[str] = []
    start_idx = 1  # skip the leading pad space

    for i, m in enumerate(matches):
        # m ends at the space after 'X. '
        after_initial = m.end()
        # Capture the next token (surname) after initial
        rest = text[after_initial:]
        surname_match = re.match(r"([^\s]+)", rest)
        if not surname_match:
            return []
        surname_end = after_initial + surname_match.end()
        end_idx = surname_end
        # Segment is from start_idx to end_idx
        seg = text[start_idx:end_idx].strip()
        segments.append(seg)
        start_idx = end_idx  # next segment starts right after the surname we just captured

    # Edge case: if trailing content after the last surname contains another person without an initial,
    # we keep it attached to the last person (conservative). Most cases are captured by initials.
    return segments


def to_first_last(segment: str) -> Tuple[str, str]:
    tokens = segment.strip().split()
    if len(tokens) == 1:
        return tokens[0], ''
    return ' '.join(tokens[:-1]), tokens[-1]


async def split_concatenated_rows(dry_run: bool = True) -> int:
    load_env_from_dotenv()
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )

    rows = await conn.fetch(
        """
        SELECT id, COALESCE(first_name,'') AS first_name, COALESCE(last_name,'') AS last_name,
               party, region, province, municipality_city, position, year, fat, government_branch, organization, winner
        FROM political_dynasties
        WHERE (first_name || ' ' || last_name) ~ '\\s[A-Z]\\.?\\s' -- at least one initial token with spaces
        """
    )

    candidates = []
    for r in rows:
        full = f"{r['first_name'].strip()} {r['last_name'].strip()}".strip()
        # Remove parenthetical notes like (ENGINEER II)
        full = PAREN_RE.sub(' ', full)
        # Remove role/position tokens (case-insensitive, word boundaries)
        tokens = full.split()
        cleaned_tokens = []
        for t in tokens:
            ut = t.upper()
            if ut in ROLE_TOKENS:
                continue
            cleaned_tokens.append(t)
        full = ' '.join(cleaned_tokens)
        segs = split_persons_by_initials(full)
        if len(segs) >= 2:
            candidates.append((r, segs))

    if dry_run:
        print(f"[DRY-RUN] Rows to split: {len(candidates)}")
        # show up to 10 examples
        for r, segs in candidates[:10]:
            print(f"ID {r['id']} -> {segs}")
        await conn.close()
        return len(candidates)

    changed = 0
    async with conn.transaction():
        for r, segs in candidates:
            first_seg_first, first_seg_last = to_first_last(segs[0])
            # Update original row with first segment
            await conn.execute(
                """
                UPDATE political_dynasties
                SET first_name = $1, last_name = $2
                WHERE id = $3
                """,
                first_seg_first, first_seg_last, r['id']
            )
            # Insert additional segments as new rows (clone other columns)
            for seg in segs[1:]:
                fn, ln = to_first_last(seg)
                await conn.execute(
                    """
                    INSERT INTO political_dynasties
                    (first_name,last_name,party,region,province,municipality_city,position,year,fat,government_branch,organization,winner)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                    """,
                    fn, ln, r['party'], r['region'], r['province'], r['municipality_city'], r['position'], r['year'], r['fat'], r['government_branch'], r['organization'], r['winner']
                )
            changed += 1

    await conn.close()
    return changed


async def main():
    dry_run_env = os.getenv('DRY_RUN', '1').strip()
    dry_run = dry_run_env not in ('0', 'false', 'False')
    n = await split_concatenated_rows(dry_run=dry_run)
    if dry_run:
        print(f"[DRY-RUN] Rows detected for split: {n}")
    else:
        print(f"Rows split: {n}")


if __name__ == '__main__':
    asyncio.run(main())


