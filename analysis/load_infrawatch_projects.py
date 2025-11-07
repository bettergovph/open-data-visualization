"""Load 2016-2025 infrastructure projects into the Infrawatch database."""

from __future__ import annotations

import asyncio
import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

import asyncpg
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from infrawatch_postgres_client import INFRAWATCH_DB_CONFIG  # noqa: E402


EXCEL_PATH = os.getenv(
    "INFRAWATCH_EXCEL_PATH",
    "/home/joebert/open-data-visualization/database/2016-2025 PH Infrastructure Projects.xlsx",
)

ROWS_TABLE = "infrawatch_projects_rows"
COLUMNS_TABLE = "infrawatch_projects_columns"
STATS_TABLE = "infrawatch_projects_stats"


def _clean_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return float(value)
    if isinstance(value, (int, bool)):
        return value
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, (pd.Timedelta,)):
        return str(value)
    if isinstance(value, (pd.Interval,)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_clean_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _clean_value(v) for k, v in value.items()}
    return str(value)


def _dataframe_to_records(df: pd.DataFrame) -> Dict[int, Dict[str, Any]]:
    df = df.replace({pd.NA: None})
    df = df.where(pd.notnull(df), None)
    return {
        int(idx): {str(col): _clean_value(val) for col, val in row.items() if val is not None}
        for idx, row in df.to_dict(orient="index").items()
    }


def _infer_column_type(series: pd.Series) -> str:
    non_null = series.dropna()
    if non_null.empty:
        return "text"
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_integer_dtype(series):
        return "integer"
    if pd.api.types.is_float_dtype(series):
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "timestamp"
    return "text"


def _sanitize_key(name: str) -> str:
    import re

    cleaned = re.sub(r"[^0-9a-zA-Z]+", "_", name.strip())
    cleaned = cleaned.strip("_").lower()
    return cleaned or "col"


def _collect_column_metadata(sheet: str, df: pd.DataFrame) -> List[Dict[str, Any]]:
    metadata: List[Dict[str, Any]] = []
    for idx, col in enumerate(df.columns):
        series = df[col]
        inferred_type = _infer_column_type(series)
        sample_value = None
        for item in series:
            if pd.notna(item):
                sample_value = _clean_value(item)
                break
        metadata.append(
            {
                "sheet_name": sheet,
                "column_name": str(col),
                "column_key": _sanitize_key(str(col)),
                "column_index": idx,
                "inferred_type": inferred_type,
                "sample_value": None if sample_value is None else str(sample_value),
            }
        )
    return metadata


async def ensure_tables(conn: asyncpg.Connection) -> None:
    await conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {ROWS_TABLE} (
            id BIGSERIAL PRIMARY KEY,
            sheet_name TEXT NOT NULL,
            row_index INTEGER NOT NULL,
            data JSONB NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            philgeps_contract_id BIGINT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_{ROWS_TABLE}_sheet_row
            ON {ROWS_TABLE} (sheet_name, row_index);

        CREATE TABLE IF NOT EXISTS {COLUMNS_TABLE} (
            sheet_name TEXT NOT NULL,
            column_name TEXT NOT NULL,
            column_key TEXT NOT NULL,
            column_index INTEGER,
            inferred_type TEXT,
            sample_value TEXT,
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (sheet_name, column_name)
        );

        CREATE TABLE IF NOT EXISTS {STATS_TABLE} (
            sheet_name TEXT PRIMARY KEY,
            row_count BIGINT NOT NULL,
            column_count INTEGER NOT NULL,
            refreshed_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
    )

    await conn.execute(
        f"""
        ALTER TABLE {ROWS_TABLE}
        ADD COLUMN IF NOT EXISTS philgeps_contract_id BIGINT;

        CREATE INDEX IF NOT EXISTS idx_{ROWS_TABLE}_philgeps
            ON {ROWS_TABLE} (philgeps_contract_id);
        """
    )


async def store_records(
    conn: asyncpg.Connection,
    sheet_name: str,
    records: Dict[int, Dict[str, Any]],
) -> int:
    await conn.execute(f"DELETE FROM {ROWS_TABLE} WHERE sheet_name=$1", sheet_name)
    if not records:
        return 0
    payload = [
        (sheet_name, row_idx, json.dumps(row, ensure_ascii=False, allow_nan=False))
        for row_idx, row in records.items()
    ]
    await conn.executemany(
        f"INSERT INTO {ROWS_TABLE} (sheet_name, row_index, data) VALUES ($1, $2, $3::jsonb)",
        payload,
    )
    return len(payload)


async def store_columns(
    conn: asyncpg.Connection,
    metadata: Iterable[Dict[str, Any]],
) -> None:
    rows = list(metadata)
    if not rows:
        return
    await conn.executemany(
        f"""
        INSERT INTO {COLUMNS_TABLE} (sheet_name, column_name, column_key, column_index, inferred_type, sample_value, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, NOW())
        ON CONFLICT (sheet_name, column_name)
        DO UPDATE SET
            column_key = EXCLUDED.column_key,
            column_index = EXCLUDED.column_index,
            inferred_type = EXCLUDED.inferred_type,
            sample_value = EXCLUDED.sample_value,
            updated_at = NOW();
        """,
        [
            (
                row["sheet_name"],
                row["column_name"],
                row["column_key"],
                row["column_index"],
                row["inferred_type"],
                row["sample_value"],
            )
            for row in rows
        ],
    )


async def store_stats(
    conn: asyncpg.Connection,
    sheet_name: str,
    row_count: int,
    column_count: int,
) -> None:
    await conn.execute(
        f"""
        INSERT INTO {STATS_TABLE} (sheet_name, row_count, column_count, refreshed_at)
        VALUES ($1, $2, $3, NOW())
        ON CONFLICT (sheet_name)
        DO UPDATE SET
            row_count = EXCLUDED.row_count,
            column_count = EXCLUDED.column_count,
            refreshed_at = NOW();
        """,
        sheet_name,
        row_count,
        column_count,
    )


async def load_sheet(conn: asyncpg.Connection, sheet_name: str, df: pd.DataFrame) -> int:
    records = _dataframe_to_records(df)
    inserted = await store_records(conn, sheet_name, records)
    await store_columns(conn, _collect_column_metadata(sheet_name, df))
    await store_stats(conn, sheet_name, inserted, len(df.columns))
    return inserted


async def main() -> None:
    if not os.path.exists(EXCEL_PATH):
        raise FileNotFoundError(f"Excel file not found: {EXCEL_PATH}")

    xls = pd.ExcelFile(EXCEL_PATH)
    conn = await asyncpg.connect(**INFRAWATCH_DB_CONFIG)
    try:
        await ensure_tables(conn)
        total_inserted = 0
        for sheet in xls.sheet_names:
            print(f"📄 Loading sheet: {sheet}")
            df = xls.parse(sheet)
            inserted = await load_sheet(conn, sheet, df)
            total_inserted += inserted
            print(f"✅ Inserted {inserted} rows from {sheet}")
        print(f"🎯 Completed loading. Total rows inserted: {total_inserted}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())


