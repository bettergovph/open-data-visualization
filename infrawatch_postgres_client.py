"""Infrawatch PostgreSQL client helpers."""

import os
from typing import Optional

import asyncpg
from dotenv import load_dotenv


load_dotenv()


INFRAWATCH_DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", 5432)),
    "database": os.getenv("POSTGRES_DB_INFRAWATCH", "infrawatch"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "password"),
}


async def get_infrawatch_connection() -> Optional[asyncpg.Connection]:
    """Return an asyncpg connection to the Infrawatch database."""

    try:
        return await asyncpg.connect(**INFRAWATCH_DB_CONFIG)
    except Exception as exc:  # pragma: no cover - best effort logging
        print(f"💥 [Infrawatch] Error connecting to database: {exc}")
        return None


__all__ = ["INFRAWATCH_DB_CONFIG", "get_infrawatch_connection"]



