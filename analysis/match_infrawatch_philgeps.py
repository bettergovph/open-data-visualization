"""Match Infrawatch projects to PhilGEPS contracts and store the matched IDs."""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
from collections import defaultdict
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional, Tuple

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


PHILGEPS_DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", 5432)),
    "database": os.getenv("POSTGRES_DB_PHILGEPS", "philgeps"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "password"),
}


ROWS_TABLE = "infrawatch_projects_rows"


CONTRACT_ID_KEYS = (
    "Contract ID",
    "Contract No",
    "Contract Number",
)

CONTRACTOR_KEYS = (
    "Contractor",
    "Contractor Name",
)

AMOUNT_KEYS = (
    "Contract Price",
    "Contract Amount",
)


TITLE_KEYS = (
    "Contract Details",
    "Project Name",
    "Project Title",
    "Project Description",
)


STOPWORDS = {
    "CONSTRUCTION",
    "REHABILITATION",
    "IMPROVEMENT",
    "OF",
    "THE",
    "PROJECT",
    "ROAD",
    "ROADS",
    "FLOOD",
    "CONTROL",
    "SYSTEM",
    "STRUCTURE",
    "WITH",
    "AND",
    "FOR",
    "BUILDING",
    "NATIONAL",
    "NETWORK",
    "SERVICES",
    "PROGRAM",
    "MFO",
    "MFO1",
    "MFO2",
    "MFO3",
    "MFO4",
    "REGIONAL",
    "ROADWAY",
    "REHAB",
    "EXPANSION",
    "BRIDGE",
    "BRIDGES",
    "STAGE",
    "PACKAGE",
    "PHILIPPINES",
    "PHILIPPINE",
    "RIVER",
}


DIRECTION_TOKENS = {
    "UPSTREAM",
    "DOWNSTREAM",
    "UPPER",
    "LOWER",
    "LEFT",
    "RIGHT",
    "NORTH",
    "SOUTH",
    "EAST",
    "WEST",
    "PHASE",
    "SEGMENT",
    "SECTION",
    "PACKAGE",
    "LOT",
    "STAGE",
}


TOKEN_LIMIT = 8
MAX_CANDIDATES = 100
TITLE_MATCH_THRESHOLD = 0.93
AMOUNT_TOLERANCE_FRACTION = 0.05
AMOUNT_TOLERANCE_MIN = 500000.0


def normalize_contract_no(value: Any) -> Optional[str]:
    if not value:
        return None
    text = str(value).upper()
    text = re.sub(r"[^A-Z0-9]", "", text)
    return text or None


def normalize_name(value: Any) -> Optional[str]:
    if not value:
        return None
    text = str(value).upper()
    # Drop values inside parentheses (usually IDs)
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    text = text.strip()
    return text or None


def to_amount(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not math.isnan(value):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    try:
        text = str(value)
        text = text.replace("₱", "").replace(",", "")
        text = text.strip()
        if not text:
            return None
        return float(text)
    except Exception:
        return None


def build_amount_key(amount: Optional[float]) -> Optional[float]:
    if amount is None:
        return None
    return round(amount, 2)


def normalize_title(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = str(value).upper()
    text = text.replace("/", " ")
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def tokenize_title(title: Optional[str]) -> List[str]:
    if not title:
        return []
    tokens: List[str] = []
    seen = set()
    for token in title.split():
        if len(token) <= 2:
            continue
        normalized = token
        if normalized in STOPWORDS:
            continue
        if normalized not in seen:
            tokens.append(normalized)
            seen.add(normalized)
    return tokens


async def load_philgeps_indexes(
    conn: asyncpg.Connection,
) -> Tuple[
    Dict[str, List[Dict[str, Any]]],
    Dict[Tuple[str, float], List[Dict[str, Any]]],
    Dict[str, List[Dict[str, Any]]],
]:
    rows = await conn.fetch(
        """
        SELECT id, contract_no, awardee_name, contract_amount, award_title, notice_title
        FROM contracts
        WHERE contract_no IS NOT NULL
           OR awardee_name IS NOT NULL
           OR award_title IS NOT NULL
           OR notice_title IS NOT NULL
        """
    )

    ids_by_contract_no: Dict[str, List[Dict[str, Any]]] = {}
    ids_by_contractor_amount: Dict[Tuple[str, float], List[Dict[str, Any]]] = {}
    token_index: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for row in rows:
        normalized_no = normalize_contract_no(row.get("contract_no"))
        normalized_name = normalize_name(row.get("awardee_name"))
        amount_value = to_amount(row.get("contract_amount"))
        amount_key = build_amount_key(amount_value)
        title_raw = row.get("award_title") or row.get("notice_title")
        title_normalized = normalize_title(title_raw)
        tokens_list = tokenize_title(title_normalized)
        direction_tokens = {
            token for token in (title_normalized.split() if title_normalized else []) if token in DIRECTION_TOKENS
        }

        payload = {
            "id": row.get("id"),
            "contract_no": row.get("contract_no"),
            "contract_amount": amount_value,
            "title": title_normalized,
            "tokens": tokens_list,
            "direction_tokens": direction_tokens,
        }

        if normalized_no:
            ids_by_contract_no.setdefault(normalized_no, []).append(payload)

        if normalized_name and amount_key is not None:
            ids_by_contractor_amount.setdefault((normalized_name, amount_key), []).append(payload)

        if title_normalized and tokens_list:
            for token in tokens_list[:TOKEN_LIMIT]:
                token_index[token].append(payload)

    return ids_by_contract_no, ids_by_contractor_amount, token_index


def extract_value(record: Dict[str, Any], keys: Iterable[str]) -> Optional[Any]:
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return None


async def fetch_batches(conn: asyncpg.Connection, batch_size: int = 3000):
    last_id = 0
    while True:
        rows = await conn.fetch(
            f"""
            SELECT id, data
            FROM {ROWS_TABLE}
            WHERE id > $1 AND (philgeps_contract_id IS NULL OR philgeps_contract_id = 0)
            ORDER BY id
            LIMIT $2
            """,
            last_id,
            batch_size,
        )
        if not rows:
            break
        last_id = rows[-1]["id"]
        yield rows


async def main() -> None:
    print("🔄 Building PhilGEPS indexes…")
    phil_conn = await asyncpg.connect(**PHILGEPS_DB_CONFIG)
    try:
        contract_index, contractor_amount_index, title_index = await load_philgeps_indexes(phil_conn)
        print(f"✅ Loaded {len(contract_index)} unique contract numbers from PhilGEPS")
        print(f"✅ Loaded {len(contractor_amount_index)} contractor+amount keys")
        print(f"✅ Indexed {len(title_index)} title tokens")
    finally:
        await phil_conn.close()

    inf_conn = await asyncpg.connect(**INFRAWATCH_DB_CONFIG)
    try:
        updates: List[Tuple[int, int]] = []
        matched_contract_id = 0
        matched_contractor_amount = 0
        matched_title = 0

        async for batch in fetch_batches(inf_conn):
            for row in batch:
                row_id = row["id"]
                raw_data = row["data"] or {}
                if isinstance(raw_data, str):
                    try:
                        data = json.loads(raw_data)
                    except json.JSONDecodeError:
                        continue
                else:
                    data = raw_data

                contract_no_raw = extract_value(data, CONTRACT_ID_KEYS)
                contractor_raw = extract_value(data, CONTRACTOR_KEYS)
                amount_raw = extract_value(data, AMOUNT_KEYS)

                matched_id: Optional[int] = None

                if contract_no_raw:
                    normalized = normalize_contract_no(contract_no_raw)
                    if normalized and normalized in contract_index:
                        options = contract_index[normalized]
                        if len(options) == 1:
                            matched_id = options[0]["id"]
                        else:
                            amount_key = build_amount_key(to_amount(amount_raw))
                            if amount_key is not None:
                                for option in options:
                                    phil_amount = build_amount_key(option.get("contract_amount"))
                                    if phil_amount == amount_key:
                                        matched_id = option["id"]
                                        break
                        if matched_id:
                            matched_contract_id += 1

                if matched_id is None and contractor_raw:
                    contractor_key = normalize_name(contractor_raw)
                    amount_key = build_amount_key(to_amount(amount_raw))
                    if contractor_key and amount_key is not None:
                        candidates = contractor_amount_index.get((contractor_key, amount_key), [])
                        if len(candidates) == 1:
                            matched_id = candidates[0]["id"]
                            matched_contractor_amount += 1

                if matched_id is None:
                    title_raw = extract_value(data, TITLE_KEYS)
                    normalized_title = normalize_title(title_raw)
                    tokens = tokenize_title(normalized_title)
                    if normalized_title and tokens:
                        candidate_list: List[Dict[str, Any]] = []
                        seen_ids = set()
                        for token in tokens[:TOKEN_LIMIT]:
                            for candidate in title_index.get(token, []):
                                cid = candidate["id"]
                                if cid not in seen_ids:
                                    candidate_list.append(candidate)
                                    seen_ids.add(cid)
                                if len(candidate_list) >= MAX_CANDIDATES:
                                    break
                            if len(candidate_list) >= MAX_CANDIDATES:
                                break

                        if candidate_list:
                            direction_tokens = {
                                token for token in normalized_title.split() if token in DIRECTION_TOKENS
                            }
                            amount_value = to_amount(amount_raw)
                            best_ratio = 0.0
                            best_candidate_id: Optional[int] = None

                            for candidate in candidate_list:
                                candidate_title = candidate.get("title")
                                if not candidate_title:
                                    continue

                                candidate_direction_tokens = set(candidate.get("direction_tokens", set()))
                                if direction_tokens and direction_tokens - candidate_direction_tokens:
                                    continue

                                ratio = SequenceMatcher(None, normalized_title, candidate_title).ratio()
                                if ratio < TITLE_MATCH_THRESHOLD:
                                    continue

                                candidate_amount = candidate.get("contract_amount")
                                if (
                                    amount_value is not None
                                    and candidate_amount is not None
                                ):
                                    diff = abs(amount_value - candidate_amount)
                                    allowed = max(
                                        AMOUNT_TOLERANCE_MIN,
                                        amount_value * AMOUNT_TOLERANCE_FRACTION,
                                    )
                                    if diff > allowed:
                                        continue

                                if ratio > best_ratio:
                                    best_ratio = ratio
                                    best_candidate_id = candidate["id"]

                            if best_candidate_id:
                                matched_id = best_candidate_id
                                matched_title += 1

                if matched_id:
                    updates.append((matched_id, row_id))

            if updates:
                await inf_conn.executemany(
                    f"UPDATE {ROWS_TABLE} SET philgeps_contract_id = $1 WHERE id = $2",
                    updates,
                )
                updates.clear()

        print(f"🎯 Matches via Contract ID: {matched_contract_id}")
        print(f"🎯 Matches via Contractor+Amount: {matched_contractor_amount}")
        print(f"🎯 Matches via Title Similarity: {matched_title}")
    finally:
        await inf_conn.close()


if __name__ == "__main__":
    asyncio.run(main())


