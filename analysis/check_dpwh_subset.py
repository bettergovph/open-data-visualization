#!/usr/bin/env python3
"""
Utility script to verify whether all contract IDs in philgeps.dpwh_procurement
appear in infrawatch.infrawatch_projects.

Prints summary counts and lists missing IDs (if any).
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional, Sequence, Set

import asyncpg


async def fetch_contract_ids(
    dsn: dict,
    query: str,
) -> Set[str]:
    conn = await asyncpg.connect(**dsn)
    try:
        rows = await conn.fetch(query)
        return {row["contract_id"] for row in rows if row["contract_id"]}
    finally:
        await conn.close()


async def main(argv: Optional[Sequence[str]] = None) -> int:
    env = os.environ

    philgeps_dsn = {
        "host": env.get("POSTGRES_HOST", "localhost"),
        "port": int(env.get("POSTGRES_PORT", 5432)),
        "user": env.get("POSTGRES_USER", "budget_admin"),
        "password": env.get("POSTGRES_PASSWORD", ""),
        "database": env.get("POSTGRES_DB_PHILGEPS", "philgeps"),
    }
    infrawatch_dsn = {
        "host": env.get("POSTGRES_HOST", "localhost"),
        "port": int(env.get("POSTGRES_PORT", 5432)),
        "user": env.get("POSTGRES_USER", "budget_admin"),
        "password": env.get("POSTGRES_PASSWORD", ""),
        "database": env.get("POSTGRES_DB_INFRAWATCH", "infrawatch"),
    }

    dpwh_query = "SELECT contract_id FROM dpwh_procurement"
    infrawatch_query = "SELECT contract_id FROM infrawatch_projects"

    print("Fetching contract IDs from dpwh_procurement …")
    dpwh_ids = await fetch_contract_ids(philgeps_dsn, dpwh_query)
    print(f"  dpwh_procurement count: {len(dpwh_ids)}")

    print("Fetching contract IDs from infrawatch_projects …")
    infra_ids = await fetch_contract_ids(infrawatch_dsn, infrawatch_query)
    print(f"  infrawatch_projects count: {len(infra_ids)}")

    missing = sorted(dpwh_ids - infra_ids)
    if missing:
        print(f"\nMissing contracts in infrawatch_projects ({len(missing)}):")
        for cid in missing[:50]:
            print(f"  {cid}")
        if len(missing) > 50:
            print(f"  …and {len(missing) - 50} more.")
        return 1

    print("\nAll dpwh_procurement contract IDs are present in infrawatch_projects.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))


