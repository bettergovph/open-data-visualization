import os
import asyncio

import asyncpg


async def mark_dpwh_related_positions_unknown(dry_run: bool = True) -> int:
    """
    Mark DPWH-related, non-reference positions as 'UNKNOWN' in political_dynasties.

    A position is considered for update when:
      - It is non-empty, and
      - It does NOT exist in the reference table government_positions.position_name, and
      - It contains DPWH-related keywords (uppercased), e.g., 'DPWH', 'DISTRICT ENGINEER', common document codes.

    Returns the number of rows that would be updated (dry_run=True) or were updated (dry_run=False).
    """
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )

    # Extensive blacklist of non-position/procurement-ish signals (ANY match will flag)
    blacklist_like_clauses = [
        "position ILIKE '%CONTRACT ID%'",
        "position ILIKE '%CONTRACT NO%'",
        "position ILIKE '%PR NO%'",
        "position ILIKE '%PR#%'",
        "position ILIKE '%PO NO%'",
        "position ILIKE '%PO#%'",
        "position ILIKE '%RFQ%'",
        "position ILIKE '%CANVASS%'",
        "position ILIKE '%QUOTATION%'",
        "position ILIKE '%BID%'",
        "position ILIKE '%LOT %'",
        "position ILIKE '%PROJECT %'",
        "position ILIKE '%PROJECT:%'",
        "position ILIKE '%JO %'",
        "position ILIKE '%MOA%'",
        "position ILIKE '%NO.%'",
        "position ILIKE '%REF.%'",
        "position ILIKE '%END-USER%'",
        "position ILIKE '%SUPPLIER%'",
        # DPWH meta terms that are not roles
        "position ILIKE '%UNIT%'",
        "position ILIKE '%SECTION%'",
        "position ILIKE '%DIVISION%'",
        "position ILIKE '%OFFICE%'",
        "position ILIKE '%AREA %'",
        "position ILIKE '%CLUSTER%'",
        "position ILIKE '%PACKAGE%'",
        "position ILIKE '%SUBPROJECT%'",
        "position ILIKE '%SUB-PROJECT%'",
    ]

    # Extensive whitelist of words/phrases that indicate actual positions (ANY match will spare)
    whitelist_like_clauses = [
        "position ILIKE 'CHIEF%'",
        "position ILIKE 'HEAD%'",
        "position ILIKE '%ENGINEER%'",  # includes DISTRICT ENGINEER, etc.
        "position ILIKE 'DIRECTOR%'",
        "position ILIKE '%OFFICER%'",
        "position ILIKE 'ADMINISTRATOR%'",
        "position ILIKE 'MANAGER%'",
        "position ILIKE 'SUPERVISOR%'",
        "position ILIKE 'INSPECTOR%'",
        "position ILIKE 'PRESIDENT%'",
        "position ILIKE 'VICE PRESIDENT%'",
        "position ILIKE 'CHAIRMAN%'",
        "position ILIKE 'CHAIRPERSON%'",
        "position ILIKE 'MEMBER%'",
        "position ILIKE 'SECRETARY%'",
        "position ILIKE 'UNDERSECRETARY%'",
        "position ILIKE 'ASSISTANT SECRETARY%'",
        "position ILIKE 'COMMISSIONER%'",
        "position ILIKE 'GOVERNOR%'",
        "position ILIKE 'VICE GOVERNOR%'",
        "position ILIKE 'MAYOR%'",
        "position ILIKE 'VICE MAYOR%'",
        "position ILIKE 'COUNCILOR%'",
        "position ILIKE 'REPRESENTATIVE%'",
        "position ILIKE 'SENATOR%'",
        "position ILIKE '%JUDGE%'",
        "position ILIKE '%JUSTICE%'",
        "position ILIKE 'AUDITOR%'",
        "position ILIKE 'TREASURER%'",
        # Include BAC as a recognized committee/role term as requested
        "position ILIKE 'BAC%'",
        "position ILIKE '%BIDS AND AWARDS COMMITTEE%'",
        # Common LGU positions
        "position ILIKE 'SK %'",
        "position ILIKE 'BARANGAY %'",
    ]

    where_blacklist = " OR ".join(blacklist_like_clauses)
    where_whitelist = " OR ".join(whitelist_like_clauses)

    # Only touch rows where the position is not part of the curated reference list
    base_where = f"""
        position IS NOT NULL AND position != ''
        AND NOT EXISTS (
            SELECT 1 FROM government_positions gp WHERE gp.position_name = political_dynasties.position
        )
        AND ({where_blacklist})
        AND NOT ({where_whitelist})
    """

    if dry_run:
        query = f"SELECT COUNT(*) FROM political_dynasties WHERE {base_where}"
        count = await conn.fetchval(query)
        await conn.close()
        return int(count)
    else:
        async with conn.transaction():
            update_sql = f"""
                UPDATE political_dynasties
                SET position = 'UNKNOWN'
                WHERE {base_where}
            """
            status = await conn.execute(update_sql)
        await conn.close()
        # status is like 'UPDATE 1234'
        try:
            return int(status.split()[-1])
        except Exception:
            return 0


async def main():
    dry_run_env = os.getenv('DRY_RUN', '1').strip()
    dry_run = dry_run_env not in ('0', 'false', 'False')
    updated = await mark_dpwh_related_positions_unknown(dry_run=dry_run)
    if dry_run:
        print(f"[DRY-RUN] Rows that would be updated to UNKNOWN: {updated}")
    else:
        print(f"Rows updated to UNKNOWN: {updated}")


if __name__ == '__main__':
    asyncio.run(main())


