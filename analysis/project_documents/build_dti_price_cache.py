#!/usr/bin/env python3
"""Build the static, locally cached BetterGov DTI construction-price reference."""
import csv
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).with_name("dti_reference") / "2025_11_NCR.csv"
OUTPUT = ROOT / "static/nep-preview/dti-construction-price-reference.json"
SOURCE_REPO = "https://github.com/quin1sue/priceguidesph-bettergov"
SOURCE_COMMIT = "148ee149ccaecd751a5755144b52c25fb1a10e8e"
SOURCE_PATH = "ekono-backend/src/data/construction_datasets/2025_11_NCR.csv"
SOURCE_FILE = f"{SOURCE_REPO}/blob/{SOURCE_COMMIT}/{SOURCE_PATH}"
PAGE_URL = "https://price-guides.bettergov.ph/construction-prices"


def amount(value):
    value = str(value or "").strip().replace(",", "").replace("₱", "")
    if not value or value.upper() in {"NO SRP", "**", "-"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def main():
    raw = SOURCE.read_bytes()
    parsed = csv.reader(raw.decode("utf-8-sig").splitlines())
    sentinels = {
        "product category", "monthly comparative price data", "ncr coverage",
        "ncr coverage*", "construction materials",
    }
    records = []
    for line_number, row in enumerate(parsed, 1):
        if len(row) < 6:
            continue
        category, commodity = (row[0].strip(), row[1].strip())
        if not category or not commodity or category.casefold() in sentinels:
            continue
        records.append({
            "id": f"dti-ncr-2025-11-{line_number:04d}",
            "category": category,
            "commodity": commodity,
            "brand": row[2].strip() if len(row) > 2 else "",
            "unit": row[3].strip() if len(row) > 3 else "",
            "size": row[4].strip() if len(row) > 4 else "",
            "currentPricePesos": amount(row[5]),
            "previousMonthPricePesos": amount(row[6]) if len(row) > 6 else None,
            "monthChangePct": amount(row[7]) if len(row) > 7 else None,
            "threeMonthsAgoPricePesos": amount(row[10]) if len(row) > 10 else None,
            "threeMonthChangePct": amount(row[11]) if len(row) > 11 else None,
        })
    document = {
        "schemaVersion": 1,
        "title": "DTI-monitored construction materials prices · NCR",
        "source": "Department of Trade and Industry data as mirrored by BetterGov Price Guides",
        "sourcePage": PAGE_URL,
        "sourceFile": SOURCE_FILE,
        "sourceRepositoryCommit": SOURCE_COMMIT,
        "sourceCsvSha256": hashlib.sha256(raw).hexdigest(),
        "reportDate": "2025-11-01",
        "region": "National Capital Region",
        "recordCount": len(records),
        "pricedRecordCount": sum(r["currentPricePesos"] is not None for r in records),
        "records": records,
        "scopeNote": "Historical NCR monitored product prices. Product, brand, package size, reported unit, location, and date must match before comparing with a POW row. A manual selection is not a finding of unreasonable pricing.",
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
    }
    temporary = OUTPUT.with_name(OUTPUT.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(OUTPUT)
    print(json.dumps({"output": str(OUTPUT), "recordCount": len(records),
                      "pricedRecordCount": document["pricedRecordCount"],
                      "reportDate": document["reportDate"]}, indent=2))


if __name__ == "__main__":
    main()
