"""
Import flagged flood-control projects from the Excel workbook into a Postgres database.

Steps performed by this script:
1. Load the specified Excel sheet (default: first sheet) from
   `database/Flood_Control_Tagged_v24_full.xlsx`.
2. Normalise each row into a JSON payload while extracting a few commonly
   referenced columns (project name, contractor, contract amount, province,
   municipality, remarks).
3. Attempt to match each row with the flood-control MeiliSearch index in order
   to locate a corresponding GlobalID. Matches are scored using a simple
   similarity ratio on the project description/title.
4. Upsert the rows into the `flagged_flood_projects` table inside the `flood`
   database (connection parameters are pulled from the environment and default
   to the existing POSTGRES_* variables plus `POSTGRES_DB_FLOOD`).

The table schema is created automatically if missing. Raw row data is stored as
JSONB so we keep the full worksheet payload for future reference.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from collections import defaultdict

import asyncpg
import pandas as pd
from difflib import SequenceMatcher

from flood_client import FloodControlClient, FloodControlProject


DEFAULT_EXCEL_PATH = Path(
    os.getenv(
        "FLOOD_CONTROL_TAGGED_XLSX",
        "/home/joebert/open-data-visualization/database/Flood_Control_Tagged_v24_full.xlsx",
    )
)

TARGET_TABLE = "flagged_flood_projects"
FLAG_LINK_TABLE = "flood_project_flag_links"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean_value(value: Any) -> Any:
    """Convert pandas/numpy types into JSON-serialisable Python values."""
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return float(value)
    if isinstance(value, (int, bool)):
        return value
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, (pd.Timedelta,)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_clean_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _clean_value(v) for k, v in value.items()}
    return str(value)


def _normalise_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Produce a cleaned row dict with trimmed string keys and cleaned values."""
    cleaned: Dict[str, Any] = {}
    for key, value in row.items():
        if key is None:
            continue
        cleaned[str(key).strip()] = _clean_value(value)
    return cleaned


def _normalise_label(value: Optional[str]) -> str:
    """Normalise sheet/column labels into lower-case snake strings."""
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "_", value.lower())


def _normalise_identifier(value: Any) -> Optional[str]:
    """Normalise identifiers such as GlobalID strings."""
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    text = str(value).strip()
    return text or None


def _extract_reason(row: Dict[str, Any], sheet_name: str) -> Optional[str]:
    """Pick the most relevant reason column for the given sheet/classification."""
    if not row:
        return None
    sheet_label = _normalise_label(sheet_name)
    keywords = [token for token in sheet_label.split("_") if token]
    for column, value in row.items():
        if not column:
            continue
        column_label = _normalise_label(column)
        if not column_label.startswith("reason_"):
            continue
        if any(keyword and keyword in column_label for keyword in keywords):
            return value
    return None


def _build_lookup_map(row: Dict[str, Any]) -> Dict[str, Any]:
    """Create a secondary lookup map with lower-cased keys to simplify matching."""
    return {key.lower(): value for key, value in row.items()}


def lookup(row_map: Dict[str, Any], *candidates: Iterable[str]) -> Optional[Any]:
    """Try several column name variants and return the first non-empty match."""
    for candidate in candidates:
        key = candidate.lower()
        if key in row_map:
            value = row_map[key]
            if value not in (None, "", "nan"):
                return value
    return None


def parse_contract_amount(raw_amount: Any) -> Optional[float]:
    """Convert currency-like strings into numeric values."""
    if raw_amount is None:
        return None
    if isinstance(raw_amount, (int, float)):
        return float(raw_amount)
    if isinstance(raw_amount, str):
        cleaned = (
            raw_amount.replace("₱", "")
            .replace(",", "")
            .replace("PHP", "")
            .replace("php", "")
            .strip()
        )
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def similarity(a: str, b: str) -> float:
    """Return a similarity ratio between 0 and 1."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


# ---------------------------------------------------------------------------
# Database logic
# ---------------------------------------------------------------------------


async def ensure_table(conn: asyncpg.Connection) -> None:
    await conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TARGET_TABLE} (
            id BIGSERIAL PRIMARY KEY,
            sheet_name TEXT NOT NULL,
            row_index INTEGER NOT NULL,
            project_name TEXT,
            contractor TEXT,
            contract_amount NUMERIC,
            province TEXT,
            municipality TEXT,
            remarks TEXT,
            meilisearch_global_id TEXT,
            match_confidence REAL,
            raw_data JSONB NOT NULL,
            project_global_id TEXT,
            is_green_flag BOOLEAN DEFAULT FALSE,
            has_red_flags BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (sheet_name, row_index)
        );

        CREATE INDEX IF NOT EXISTS idx_{TARGET_TABLE}_meili
            ON {TARGET_TABLE} (meilisearch_global_id);
        """
    )
    await conn.execute(
        f"ALTER TABLE {TARGET_TABLE} ADD COLUMN IF NOT EXISTS project_global_id TEXT"
    )
    await conn.execute(
        f"ALTER TABLE {TARGET_TABLE} ADD COLUMN IF NOT EXISTS is_green_flag BOOLEAN DEFAULT FALSE"
    )
    await conn.execute(
        f"ALTER TABLE {TARGET_TABLE} ADD COLUMN IF NOT EXISTS has_red_flags BOOLEAN DEFAULT FALSE"
    )
    await conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{TARGET_TABLE}_global_id "
        f"ON {TARGET_TABLE} (project_global_id)"
    )


async def ensure_flag_link_table(conn: asyncpg.Connection) -> None:
    await conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {FLAG_LINK_TABLE} (
            id BIGSERIAL PRIMARY KEY,
            project_global_id TEXT NOT NULL,
            classification TEXT NOT NULL,
            classification_type TEXT NOT NULL CHECK (classification_type IN ('red', 'green')),
            reason TEXT,
            source_sheet TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (project_global_id, classification)
        );

        CREATE INDEX IF NOT EXISTS idx_{FLAG_LINK_TABLE}_project
            ON {FLAG_LINK_TABLE} (project_global_id);
        """
    )


async def upsert_row(
    conn: asyncpg.Connection,
    sheet_name: str,
    row_index: int,
    payload: Dict[str, Any],
    project_name: Optional[str],
    contractor: Optional[str],
    contract_amount: Optional[float],
    province: Optional[str],
    municipality: Optional[str],
    remarks: Optional[str],
    meili_id: Optional[str],
    confidence: Optional[float],
    project_global_id: Optional[str],
    is_green_flag: bool,
    has_red_flags: bool,
) -> None:
    await conn.execute(
        f"""
        INSERT INTO {TARGET_TABLE} (
            sheet_name,
            row_index,
            project_name,
            contractor,
            contract_amount,
            province,
            municipality,
            remarks,
            meilisearch_global_id,
            match_confidence,
            raw_data,
            project_global_id,
            is_green_flag,
            has_red_flags,
            created_at,
            updated_at
        )
        VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12, $13, $14, NOW(), NOW()
        )
        ON CONFLICT (sheet_name, row_index)
        DO UPDATE SET
            project_name = EXCLUDED.project_name,
            contractor = EXCLUDED.contractor,
            contract_amount = EXCLUDED.contract_amount,
            province = EXCLUDED.province,
            municipality = EXCLUDED.municipality,
            remarks = EXCLUDED.remarks,
            meilisearch_global_id = EXCLUDED.meilisearch_global_id,
            match_confidence = EXCLUDED.match_confidence,
            raw_data = EXCLUDED.raw_data,
            project_global_id = EXCLUDED.project_global_id,
            is_green_flag = EXCLUDED.is_green_flag,
            has_red_flags = EXCLUDED.has_red_flags,
            updated_at = NOW();
        """,
        sheet_name,
        row_index,
        project_name,
        contractor,
        contract_amount,
        province,
        municipality,
        remarks,
        meili_id,
        confidence,
        json.dumps(payload, ensure_ascii=False),
        project_global_id,
        is_green_flag,
        has_red_flags,
    )


async def replace_project_flags(
    conn: asyncpg.Connection,
    project_global_id: str,
    flags: List[Dict[str, Optional[str]]],
) -> None:
    """Replace the classification flags for a project in the link table."""
    await conn.execute(
        f"DELETE FROM {FLAG_LINK_TABLE} WHERE project_global_id = $1",
        project_global_id,
    )

    if not flags:
        return

    records = [
        (
            project_global_id,
            flag["classification"],
            flag["classification_type"],
            flag.get("reason"),
            flag.get("source_sheet", flag["classification"]),
        )
        for flag in flags
        if flag.get("classification") and flag.get("classification_type")
    ]

    if not records:
        return

    await conn.executemany(
        f"""
        INSERT INTO {FLAG_LINK_TABLE} (
            project_global_id,
            classification,
            classification_type,
            reason,
            source_sheet,
            created_at,
            updated_at
        )
        VALUES ($1, $2, $3, $4, $5, NOW(), NOW())
        ON CONFLICT (project_global_id, classification)
        DO UPDATE SET
            classification_type = EXCLUDED.classification_type,
            reason = EXCLUDED.reason,
            source_sheet = EXCLUDED.source_sheet,
            updated_at = NOW();
        """,
        records,
    )


def build_green_flag_map(df: Optional[pd.DataFrame]) -> Dict[str, Dict[str, Optional[str]]]:
    """Return a mapping of GlobalID -> green flag metadata."""
    if df is None:
        return {}

    mapping: Dict[str, Dict[str, Optional[str]]] = {}
    records = df.to_dict(orient="records")
    for original_row in records:
        row = _normalise_row(original_row)
        lookup_map = _build_lookup_map(row)
        global_id = _normalise_identifier(
            lookup(
                lookup_map,
                "globalid",
                "global id",
                "meilisearch id",
                "meilisearch_id",
            )
        )
        if not global_id:
            continue
        mapping[global_id] = {
            "classification": "Green_Flag",
            "classification_type": "green",
            "reason": _extract_reason(row, "Green_Flag"),
            "source_sheet": "Green_Flag",
        }
    return mapping


def build_red_flag_map(
    frames: Dict[str, pd.DataFrame]
) -> Dict[str, List[Dict[str, Optional[str]]]]:
    """Return a mapping of GlobalID -> list of red flag metadata."""
    mapping: Dict[str, List[Dict[str, Optional[str]]]] = defaultdict(list)

    for sheet_name, df in frames.items():
        if df is None:
            continue
        records = df.to_dict(orient="records")
        for original_row in records:
            row = _normalise_row(original_row)
            lookup_map = _build_lookup_map(row)
            global_id = _normalise_identifier(
                lookup(
                    lookup_map,
                    "globalid",
                    "global id",
                    "meilisearch id",
                    "meilisearch_id",
                )
            )
            if not global_id:
                continue

            mapping[global_id].append(
                {
                    "classification": sheet_name,
                    "classification_type": "red",
                    "reason": _extract_reason(row, sheet_name),
                    "source_sheet": sheet_name,
                }
            )

    return mapping


# ---------------------------------------------------------------------------
# MeiliSearch matching
# ---------------------------------------------------------------------------


async def match_row_with_meilisearch(
    client: FloodControlClient,
    row_map: Dict[str, Any],
    project_name: Optional[str],
    candidate_global_ids: Iterable[str],
    *,
    similarity_threshold: float = 0.6,
    top_k: int = 5,
) -> Tuple[Optional[str], Optional[float]]:
    """Try to find the GlobalID for the row."""
    # 1. Direct GlobalID hints
    for candidate in candidate_global_ids:
        if not candidate:
            continue
        candidate_str = str(candidate).strip()
        if not candidate_str:
            continue
        project = await client.get_project_by_id(candidate_str)
        if project:
            return candidate_str, 1.0

    # 2. Fallback to fuzzy search by project description/title
    if not project_name:
        return None, None

    projects, _metadata = await client.search_projects(
        query=project_name, limit=top_k
    )

    best: Optional[FloodControlProject] = None
    best_score = 0.0

    reference = project_name
    for proj in projects:
        if not proj.ProjectDescription:
            continue
        score = similarity(reference, proj.ProjectDescription)
        if score > best_score:
            best_score = score
            best = proj

    if best and best.GlobalID and best_score >= similarity_threshold:
        return best.GlobalID, best_score

    return None, best_score if best_score > 0 else None


# ---------------------------------------------------------------------------
# Main routine
# ---------------------------------------------------------------------------


def resolve_sheet(excel: pd.ExcelFile, sheet: Optional[str]) -> str:
    if sheet is None:
        return "Main" if "Main" in excel.sheet_names else excel.sheet_names[0]
    if sheet.isdigit():
        index = int(sheet)
        if index < 0 or index >= len(excel.sheet_names):
            raise ValueError(
                f"Sheet index {index} is out of bounds (found {len(excel.sheet_names)} sheets)."
            )
        return excel.sheet_names[index]
    if sheet in excel.sheet_names:
        return sheet
    raise ValueError(
        f"Sheet '{sheet}' not found in workbook. Available sheets: {excel.sheet_names}"
    )


@dataclass
class Config:
    excel_path: Path
    sheet: Optional[str]
    dry_run: bool
    max_rows: Optional[int]


def parse_args() -> Config:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--excel",
        type=Path,
        default=DEFAULT_EXCEL_PATH,
        help="Path to the tagged flood control Excel workbook.",
    )
    parser.add_argument(
        "--sheet",
        type=str,
        default=None,
        help="(Deprecated) Previously limited import to a single sheet; kept for backward compatibility.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect data and matching without writing to the database.",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Optional limit on the number of rows to process (useful for testing).",
    )
    args = parser.parse_args()
    return Config(
        excel_path=args.excel,
        sheet=args.sheet,
        dry_run=args.dry_run,
        max_rows=args.max_rows,
    )


async def run_import(cfg: Config) -> None:
    if not cfg.excel_path.exists():
        raise FileNotFoundError(f"Excel workbook not found: {cfg.excel_path}")

    excel = pd.ExcelFile(cfg.excel_path)
    frames: Dict[str, pd.DataFrame] = {}
    for name in excel.sheet_names:
        frame = excel.parse(name)
        frame = frame.replace({pd.NA: None})
        frame = frame.where(pd.notnull(frame), None)
        frames[name] = frame

    main_sheet = resolve_sheet(excel, cfg.sheet)
    if main_sheet not in frames:
        raise ValueError(
            f"Sheet '{main_sheet}' not found in workbook. Available sheets: {excel.sheet_names}"
        )

    main_df = frames[main_sheet]
    total_main_rows = len(main_df)
    if cfg.max_rows is not None:
        main_df = main_df.head(cfg.max_rows)

    rows = main_df.to_dict(orient="records")

    green_map = build_green_flag_map(frames.get("Green_Flag"))
    red_frames = {
        name: frame
        for name, frame in frames.items()
        if name not in {main_sheet, "Green_Flag"}
    }
    red_map = build_red_flag_map(red_frames)
    total_red_records = sum(len(flags) for flags in red_map.values())

    print(f"Loaded workbook '{cfg.excel_path.name}' with {len(frames)} sheets.")
    if cfg.max_rows is not None and cfg.max_rows < total_main_rows:
        print(
            f"Processing {len(rows)} rows from '{main_sheet}' (truncated from {total_main_rows} via --max-rows)."
        )
    else:
        print(f"Processing {len(rows)} rows from '{main_sheet}'.")
    print(
        f"Found {len(green_map)} green-flag entries and {total_red_records} red-flag entries across {len(red_frames)} classification sheets."
    )

    if cfg.dry_run:
        print("⚠️ Dry-run mode: no database writes will be performed.")

    db_config = {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", 5432)),
        "user": os.getenv("POSTGRES_USER", "budget_admin"),
        "password": os.getenv("POSTGRES_PASSWORD", ""),
        "database": os.getenv("POSTGRES_DB_FLOOD", "flood"),
    }

    conn: Optional[asyncpg.Connection] = None
    client = FloodControlClient()

    processed_red_projects = set()
    processed_green_projects = set()
    total_red_flags_applied = 0

    try:
        if not cfg.dry_run:
            conn = await asyncpg.connect(**db_config)
            await ensure_table(conn)
            await ensure_flag_link_table(conn)

        for idx, original_row in enumerate(rows):
            row = _normalise_row(original_row)
            lookup_map = _build_lookup_map(row)

            project_name = lookup(
                lookup_map,
                "projectdescription",
                "project description",
                "projecttitle",
                "project title",
                "project name",
            )
            contractor = lookup(
                lookup_map,
                "contractor",
                "awardee",
                "awardee name",
            )
            province = lookup(lookup_map, "province")
            municipality = lookup(
                lookup_map,
                "municipality",
                "city/municipality",
                "city/ municipality",
            )
            remarks = lookup(
                lookup_map,
                "remarks",
                "notes",
                "comment",
            )

            contract_amount_raw = lookup(
                lookup_map,
                "contractcost",
                "contract cost",
                "contract amount",
                "amount",
            )
            contract_amount = parse_contract_amount(contract_amount_raw)

            project_global_id = _normalise_identifier(
                lookup(
                    lookup_map,
                    "globalid",
                    "global id",
                    "meilisearch id",
                    "meilisearch_id",
                )
            )

            candidate_ids = [project_global_id] if project_global_id else []
            meili_id, confidence = await match_row_with_meilisearch(
                client,
                lookup_map,
                project_name=project_name if isinstance(project_name, str) else None,
                candidate_global_ids=candidate_ids,
            )

            effective_global_id = project_global_id or meili_id
            flag_key = effective_global_id

            red_entries = red_map.get(flag_key, []) if flag_key else []
            green_entry = green_map.get(flag_key) if flag_key else None

            has_red_flags = bool(red_entries)
            if has_red_flags and flag_key:
                processed_red_projects.add(flag_key)
                total_red_flags_applied += len(red_entries)

            is_green_flag = bool(green_entry) and not has_red_flags
            if is_green_flag and flag_key:
                processed_green_projects.add(flag_key)

            project_flags: List[Dict[str, Optional[str]]] = []
            if has_red_flags:
                project_flags.extend(red_entries)
                if green_entry:
                    logger.debug(
                        "Project %s appears in both green and red flag sheets; red flags take precedence.",
                        flag_key,
                    )
            elif green_entry:
                project_flags.append(green_entry)

            if cfg.dry_run:
                flag_labels = [
                    f"{flag['classification_type']}:{flag['classification']}" for flag in project_flags
                ]
                print(
                    f"[DRY-RUN] Row {idx}: project={project_name!r} contractor={contractor!r} "
                    f"meili_id={meili_id!r} confidence={confidence!r} flags={flag_labels}"
                )
                continue

            assert conn is not None
            await upsert_row(
                conn=conn,
                sheet_name=main_sheet,
                row_index=idx,
                payload=row,
                project_name=project_name if isinstance(project_name, str) else None,
                contractor=contractor if isinstance(contractor, str) else None,
                contract_amount=contract_amount,
                province=province if isinstance(province, str) else None,
                municipality=municipality if isinstance(municipality, str) else None,
                remarks=remarks if isinstance(remarks, str) else None,
                meili_id=meili_id,
                confidence=confidence,
                project_global_id=effective_global_id,
                is_green_flag=is_green_flag,
                has_red_flags=has_red_flags,
            )

            if flag_key:
                await replace_project_flags(conn, flag_key, project_flags)

            if idx and idx % 100 == 0:
                print(f"Processed {idx} rows...")

        print(f"✅ Completed processing {len(rows)} rows from '{main_sheet}'.")
        if processed_green_projects:
            print(f"   Marked {len(processed_green_projects)} projects as clean/green.")
        if processed_red_projects:
            print(
                f"   Applied {total_red_flags_applied} red-flag classifications across {len(processed_red_projects)} projects."
            )

    finally:
        if conn:
            await conn.close()


def main() -> None:
    cfg = parse_args()
    asyncio.run(run_import(cfg))


if __name__ == "__main__":
    main()


