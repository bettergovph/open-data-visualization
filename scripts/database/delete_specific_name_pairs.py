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


TARGET_PAIRS = [
    ("IN", "WORDS"),
    ("NAME", "CONTRACT"),
    ("IN", "FIGURES"),
    ("CONTRACT", "NAME"),
    ("C.D.", "FUND"),
    ("TOTAL", "WORDS"),
    ("LOCATION", "CONTRACT"),
    ("C.D.", "RANGE"),
    ("CONTRACT", "LOCATION"),
    ("YOU", "WEBSITES"),
    ("PHP", "FIGURES"),
    ("COMMITTEE", "WORKS"),
    ("CONTRACT", "DURATION"),
    ("PARTMENT", "ID"),
    ("CONTRACT", "ID"),
    ("EMAIL", "ADDRESS"),
    ("DPWH.GOV.PH", "ISSUE"),
    ("UREMENT", "BELOW"),
    ("RECEIPT", "DEADLINE"),
    ("IMUM", "FOLLOWING"),
    ("S", "IS"),
    ("BRIEF", "DESCRIPTION"),
    ("THE", "IS"),
    ("DOCUMENTS", "BID"),
    ("FLOOD", "CONTROL"),
    ("SOURCE", "FUND"),
    ("THE", "ARE"),
    ("STA.", "WORKS"),
    ("ST", "OF"),
    ("PHILGEPS", "SUBMISSION"),
    ("ASSET", "PROGRAM"),
    ("WITH", "BRIDGES"),
    ("ROAD", "SAFETY"),
    ("BRIEF", "ROAD"),
    ("BICWOPLC", "BUILDINGS"),
    ("PCAB", "RANGE"),
    ("BRGY.", "WORKS"),
    ("THE", "BE"),
    ("EPARTMENT", "ID"),
    ("WE", "THAT"),
    ("IN", "US"),
    ("FURTHER", "FOLLOWING"),
    ("PLACE", "BRIDGES"),
    ("FORM", "SECURITY"),
    ("TO", "CONTRACT"),
    ("BID", "SECURITY"),
    ("SCOPE", "WORK"),
    ("ARTMENT", "ID"),
    ("TARLAC", "LOCATION"),
    ("C", "ADDRESS"),
    ("CD", "RANGE"),
    ("CLAUSE", "CLAUSE"),
    ("THE", "REQUIREMENTS"),
    ("SCOPE", "WORKS"),
    ("CUREMENT", "DATE"),
    ("GROUND", "NAME"),
    ("FLOOD", "PROGRAM"),
    ("BARANGAY", "LOCATIONS"),
    ("LAUSE", "CLAUSE"),
    ("L.S.", "WORDS"),
    ("PLACE", "BUILDINGS"),
    ("AY", "LOCATION"),
    ("ELECTRONIC", "SUBMISSION"),
    ("MUM", "FOLLOWING"),
    ("ELECTRONIC", "EMAIL"),
    ("DALEN", "ADDRESS"),
    ("RD", "ADDRESS"),
    ("RACTORS", "S"),
    ("T", "ENTITY"),
    ("ISSUANCE", "DOCUMENTS"),
    ("NET", "LENGTH"),
    ("HIGHWAYS", "NAME"),
    ("OPENING", "BIDS"),
    ("BID", "CONFERENCE"),
    ("GPPB", "DOCUMENTS"),
    ("BELOW", "IS"),
    ("DPWH.GOV.PH", "POSTING"),
    ("IN", "FIGURE"),
    ("DROPPING", "BIDS"),
    ("IN", "OF"),
    ("BELOW", "IS"),
    ("PESOS", "FIGURES"),
    ("DOCUMEN", "BID"),
    ("TITUTION", "BY"),
    ("TMENT", "ID"),
    ("ENT", "SHEET"),
    ("AUSE", "CLAUSE"),
    ("AS", "FOLLOWS"),
    ("CONTRACT", "NO."),
    ("CTS", "ASSIGNMENT"),
    ("IF", "NECESSARY"),
    ("LOCATION", "NUMBER"),
    ("REVISED", "ON"),
    ("S", "DATE"),
    ("SAN", "LOCATION"),
    ("QUIREMENTS", "FOLLOWING"),
    ("SOURCE", "FUNDS"),
    ("KG", "WORDS"),
    ("ASPHALT", "ROADS"),
    ("STRUCTIONS", "PRICES"),
    ("APPROVED", "BY"),
    ("GAY", "LOCATION"),
    ("IN", "RDS"),
    ("GRAND", "WORDS"),
    ("WITH", "SUBJECT"),
    ("NAME", "BIDDER"),
    ("PREPARED", "BY"),
    ("OR", "NO."),
    ("M", "STRUCTURES"),
    ("CITY", "IS"),
    ("P.M.", "PLACE"),
    ("CIVILWORKSFORMS", "ISSUE"),
    ("TO", "SSP"),
    ("PART", "B"),
    ("WITHOUT", "BRIDGES"),
    ("PART", "C"),
    ("IN", "DS"),
    ("OF", "CWR"),
    ("PART", "E"),
    ("LE.", "NOTE"),
    ("NFCC", "NOTE"),
    ("C.D", "RANGE"),
    ("ENT", "SC"),
    ("RACTOR", "SECTOR"),
    ("STO.", "WORKS"),
    ("RIEF", "ROAD"),
    ("FUND", "RANGE"),
    ("SIMILAR", "WORK"),
    ("FOR", "VISIT"),
    ("PART", "D"),
    ("PHILGEPS", "WEBSITE"),
    ("NETWORK", "PROGRAM"),
]

# Also delete any rows whose last_name matches these tokens (case-insensitive)
LASTNAME_BLACKLIST = {
    "BELOW",
    "HEAD",
    "LOCATIONS",
    "BUILDINGS",
    "CONTRACTOR",
    "CONTRACT",
    "ADDRESS",
    "S",
    "ENTITY",
    "DOCUMENTS",
    "LENGTH",
    "NAME",
    "BIDS",
    "CONFERENCE",
    "POSTING",
    "FIGURE",
    "OF",
    "IS",
    "FIGURES",
    "BID",
    "BY",
    "ID",
    "SHEET",
    "CLAUSE",
    "FOLLOWS",
    "NO.",
    "ASSIGNMENT",
    "NECESSARY",
    "NUMBER",
    "ON",
    "DATE",
    "LOCATION",
    "FOLLOWING",
    "FUNDS",
    "WORDS",
    "ROADS",
    "PRICES",
    "SUBJECT",
    "BIDDER",
    "STRUCTURES",
    "PLACE",
    "ISSUE",
    "C",
    "DS",
    "CWR",
    "E",
    "NOTE",
    "RANGE",
    "SC",
    "SECTOR",
    "WORKS",
    "ROAD",
    "WORK",
    "VISIT",
    "D",
    "WEBSITE",
    "A III",
    "AASHTO",
    "AB",
    "A II",
    "AARRAADDAA",
    "AARRCCHHIITTEECCTT II",
    "ABC",
    "ABOVE",
    "ABOVE II",
    "DISTRICT",
    "ENGINEER II",
    "ENGINEER",
}


async def delete_specific_pairs(dry_run: bool = True) -> int:
    load_env_from_dotenv()
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )

    # Build a temp table of target pairs for clean matching
    await conn.execute("CREATE TEMP TABLE tmp_pairs(first_name text, last_name text)")
    # Insert records without COPY to avoid temp table visibility issues
    await conn.executemany(
        "INSERT INTO tmp_pairs(first_name, last_name) VALUES($1, $2)",
        [(fn, ln) for fn, ln in TARGET_PAIRS]
    )

    count_sql = """
        SELECT COUNT(*)
        FROM political_dynasties d
        JOIN tmp_pairs p
          ON UPPER(TRIM(d.first_name)) = p.first_name
         AND UPPER(TRIM(d.last_name)) = p.last_name
    """
    to_delete = await conn.fetchval(count_sql)

    # Count rows matching last_name blacklist
    if LASTNAME_BLACKLIST:
        placeholders = ",".join([f"${i+1}" for i in range(len(LASTNAME_BLACKLIST))])
        ln_params = [name for name in LASTNAME_BLACKLIST]
        ln_count = await conn.fetchval(
            f"""
            SELECT COUNT(*) FROM political_dynasties
            WHERE UPPER(TRIM(last_name)) IN ({placeholders})
            """,
            *ln_params
        )
        to_delete += int(ln_count)

    # Count rows where last_name matches regex: DISTRICT ... ABO (anything between), case-insensitive
    district_abo_count = await conn.fetchval(
        """
        SELECT COUNT(*) FROM political_dynasties
        WHERE TRIM(last_name) ~* '^DISTRICT\s+.*\s+ABO$' OR TRIM(last_name) ~* '^DISTRICT\s*ABO$'
        """
    )
    to_delete += int(district_abo_count)

    # Count rows where last_name is a single character OR starts with a dot
    regex_count = await conn.fetchval(
        """
        SELECT COUNT(*) FROM political_dynasties
        WHERE TRIM(last_name) ~ '^[A-Za-z]$' OR TRIM(last_name) LIKE '.%'
        """
    )
    to_delete += int(regex_count)

    if dry_run or to_delete == 0:
        await conn.close()
        return int(to_delete)

    async with conn.transaction():
        await conn.execute(
            """
            DELETE FROM political_dynasties d
            USING tmp_pairs p
            WHERE UPPER(TRIM(d.first_name)) = p.first_name
              AND UPPER(TRIM(d.last_name)) = p.last_name
            """
        )
        if LASTNAME_BLACKLIST:
            placeholders = ",".join([f"${i+1}" for i in range(len(LASTNAME_BLACKLIST))])
            ln_params = [name for name in LASTNAME_BLACKLIST]
            await conn.execute(
                f"""
                DELETE FROM political_dynasties
                WHERE UPPER(TRIM(last_name)) IN ({placeholders})
                """,
                *ln_params
            )
        # Delete last_name matching regex: DISTRICT ... ABO
        await conn.execute(
            """
            DELETE FROM political_dynasties
            WHERE TRIM(last_name) ~* '^DISTRICT\s+.*\s+ABO$' OR TRIM(last_name) ~* '^DISTRICT\s*ABO$'
            """
        )
        # Delete rows with one-letter last names or dot-prefixed last names
        await conn.execute(
            """
            DELETE FROM political_dynasties
            WHERE TRIM(last_name) ~ '^[A-Za-z]$' OR TRIM(last_name) LIKE '.%'
            """
        )

    await conn.close()

    # Log file with what was targeted and how many rows removed
    out_dir = Path(__file__).resolve().parent
    ts = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
    (out_dir / f"deleted_specific_pairs_{ts}.txt").write_text(
        "\n".join([f"{fn},{ln}" for fn, ln in TARGET_PAIRS]), encoding='utf-8'
    )

    return int(to_delete)


async def main():
    dry_run_env = os.getenv('DRY_RUN', '1').strip()
    dry_run = dry_run_env not in ('0', 'false', 'False')
    n = await delete_specific_pairs(dry_run=dry_run)
    if dry_run:
        print(f"[DRY-RUN] Rows that would be deleted for specific pairs: {n}")
    else:
        print(f"Rows deleted for specific pairs: {n}")


if __name__ == '__main__':
    asyncio.run(main())


