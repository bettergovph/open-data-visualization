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


async def generate_top_500_context():
    load_env_from_dotenv()
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )

    # Get top 500 first_name + last_name combinations by count
    name_rows = await conn.fetch(
        """
        SELECT UPPER(TRIM(first_name)) AS first_name, UPPER(TRIM(last_name)) AS last_name, COUNT(*) AS occurrences
        FROM political_dynasties
        WHERE TRIM(COALESCE(first_name,'')) <> ''
          AND TRIM(COALESCE(last_name,'')) <> ''
        GROUP BY UPPER(TRIM(first_name)), UPPER(TRIM(last_name))
        ORDER BY occurrences DESC, last_name ASC, first_name ASC
        LIMIT 500
        """
    )
    
    # Build sets for filtering
    top_first_names = {r['first_name'] for r in name_rows}
    top_last_names = {r['last_name'] for r in name_rows}
    
    # Get distinct positions that have records matching top 500 name combinations
    position_rows = await conn.fetch(
        """
        SELECT DISTINCT position
        FROM political_dynasties
        WHERE position IS NOT NULL 
          AND position != '' 
          AND position NOT ILIKE 'OTHER' 
          AND position NOT ILIKE 'UNKNOWN'
          AND UPPER(TRIM(first_name)) = ANY($1::text[])
          AND UPPER(TRIM(last_name)) = ANY($2::text[])
        ORDER BY position ASC
        """,
        list(top_first_names),
        list(top_last_names)
    )
    
    await conn.close()
    
    # Write to LLM context file
    output_file = Path(__file__).resolve().parents[2] / "dynasty_top_500_names_context.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("TOP 500 FIRST + LAST NAME COMBINATIONS (after cleaning)\n")
        f.write("=" * 80 + "\n\n")
        for i, r in enumerate(name_rows, 1):
            f.write(f"{i}. {r['first_name']} {r['last_name']} ({r['occurrences']} occurrences)\n")
        
        f.write("\n\nVALID POSITIONS (filtered by top 500 name combinations)\n")
        f.write("=" * 80 + "\n\n")
        for i, r in enumerate(position_rows, 1):
            f.write(f"{i}. {r['position']}\n")
        
        f.write(f"\n\nTotal valid positions: {len(position_rows)}\n")
        f.write(f"Total top name combinations: {len(name_rows)}\n")
    
    print(f"✅ Generated context file: {output_file}")
    print(f"   - Top 500 name combinations: {len(name_rows)}")
    print(f"   - Valid positions: {len(position_rows)}")
    
    return top_first_names, top_last_names, [r['position'] for r in position_rows]


async def main():
    await generate_top_500_context()


if __name__ == '__main__':
    asyncio.run(main())

