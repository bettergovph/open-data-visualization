#!/usr/bin/env python3
"""
Normalize name suffixes (JR, SR, JR., SR., I, II, III, IV, V, VI, VII, VIII, IX, X)
by moving them from `first_name`/`middle_name` into the end of `last_name`.

Examples:
- first_name: "JUAN JR." last_name: "DEL ROSARIO" -> first_name: "JUAN", last_name: "DEL ROSARIO JR."
- first_name: "PEDRO" middle_name: "A. III" last_name: "SANTOS" -> middle_name: "A.", last_name: "SANTOS III"
"""

import asyncio
import os
import re
import asyncpg
from dotenv import load_dotenv


SUFFIXES = {
    'JR', 'JR.', 'SR', 'SR.',
    'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X'
}


def split_suffix_from_end(text: str):
    text = (text or '').strip()
    if not text:
        return text, ''
    parts = [p for p in re.split(r"\s+", text) if p]
    if not parts:
        return '', ''
    # Check last token for suffix
    last = parts[-1].upper()
    # Normalize without trailing comma (e.g., "JR.,")
    last_clean = re.sub(r"[,]+$", "", last)
    if last_clean in SUFFIXES:
        # Preserve original punctuation of last token from original text
        suffix_original = parts[-1]
        base = ' '.join(parts[:-1])
        return base.strip(), suffix_original
    return text, ''


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
        rows = await conn.fetch(
            """
            SELECT id, first_name, middle_name, last_name
            FROM political_dynasties
            WHERE (
                first_name ~ '(JR\\.?|SR\\.?|I|II|III|IV|V|VI|VII|VIII|IX|X)\\s*$'
                OR middle_name ~ '(JR\\.?|SR\\.?|I|II|III|IV|V|VI|VII|VIII|IX|X)\\s*$'
            )
            AND last_name !~ '(JR\\.?|SR\\.?|I|II|III|IV|V|VI|VII|VIII|IX|X)\\s*$'
            LIMIT 100000
            """
        )

        print(f"🔧 Found {len(rows)} candidate rows with suffixes to normalize")
        updated = 0

        for r in rows:
            pid = r['id']
            first_name = r['first_name'] or ''
            middle_name = r['middle_name'] or ''
            last_name = r['last_name'] or ''

            new_first, suffix_from_first = split_suffix_from_end(first_name)
            new_middle, suffix_from_middle = split_suffix_from_end(middle_name)

            suffix = suffix_from_first or suffix_from_middle
            if suffix:
                new_last = (last_name + ' ' + suffix).strip()
                await conn.execute(
                    """
                    UPDATE political_dynasties
                    SET first_name = $1, middle_name = $2, last_name = $3
                    WHERE id = $4
                    """,
                    new_first or first_name, new_middle or middle_name, new_last, pid
                )
                updated += 1

        print(f"✅ Updated {updated} rows with normalized suffixes in last_name")

        # Second pass: fix records where last_name itself is a suffix (e.g., 'JR', 'III')
        rows2 = await conn.fetch(
            """
            SELECT id, first_name, middle_name, last_name
            FROM political_dynasties
            WHERE last_name ~ '^(JR\\.?|SR\\.?|I|II|III|IV|V|VI|VII|VIII|IX|X)\\s*$'
            LIMIT 100000
            """
        )

        print(f"🔧 Found {len(rows2)} rows where last_name is a suffix; attempting to recover last name from first_name")
        recovered = 0

        for r in rows2:
            pid = r['id']
            first_name = (r['first_name'] or '').strip()
            middle_name = (r['middle_name'] or '').strip()
            last_name = (r['last_name'] or '').strip()

            # Split potential suffix off first_name end
            first_base, suffix_from_first = split_suffix_from_end(first_name)
            suffix_token = (last_name or '').strip()
            trailing_suffix = suffix_from_first or ''

            # Determine candidate last name from the end of first_base
            tokens = [t for t in re.split(r"\s+", first_base) if t]
            if len(tokens) >= 2:
                candidate_last = tokens[-1]
                candidate_first = ' '.join(tokens[:-1])
                # If candidate_last is also a suffix, step back one more token when possible
                if candidate_last.upper().rstrip(',') in SUFFIXES and len(tokens) >= 3:
                    trailing_suffix = trailing_suffix or candidate_last
                    candidate_last = tokens[-2]
                    candidate_first = ' '.join(tokens[:-2])

                # Compose new last name (candidate_last + suffixes)
                new_last = candidate_last
                if trailing_suffix:
                    new_last = f"{new_last} {trailing_suffix}".strip()
                if suffix_token:
                    # Append original last_name suffix if distinct
                    if suffix_token.upper().rstrip(',') in SUFFIXES and suffix_token != trailing_suffix:
                        new_last = f"{new_last} {suffix_token}".strip()

                # Persist updates
                await conn.execute(
                    """
                    UPDATE political_dynasties
                    SET first_name = $1, last_name = $2
                    WHERE id = $3
                    """,
                    candidate_first or first_base or first_name,
                    new_last,
                    pid,
                )
                recovered += 1

        print(f"✅ Recovered last_name from first_name for {recovered} rows")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())


