#!/usr/bin/env python3
"""
Lookup contractor–dynasty relationship entries that lack supporting URLs and
ask Perplexity to suggest credible references for them.

The script mirrors the pattern used by existing Perplexity helper scripts in
`scripts/`, and will:
    1. Read `company_affiliations` rows that have an empty `source_url`
       (these are the remaining records without proofs).
    2. For each record, build a focused research prompt and call the
       Perplexity chat completion API.
    3. Parse the JSON array returned by Perplexity and store the results
       alongside the raw response for auditing.
    4. Write everything to
       `family_analysis/perplexity_missing_sources/missing_relationship_sources_<timestamp>.json`
       so analysts can review and backfill the database.

Environmental requirements:
    - `PERPLEXITY_API_KEY` must be present.
    - PostgreSQL connection settings come from the usual `POSTGRES_*` env vars.

Example:
    $ export PERPLEXITY_API_KEY=sk-...
    $ python scripts/fetch_missing_relationship_sources.py
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import asyncpg
import requests


BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "family_analysis" / "perplexity_missing_sources"

PERPLEXITY_MODEL = os.getenv("PERPLEXITY_MODEL", "sonar-pro")
PERPLEXITY_TIMEOUT = int(os.getenv("PERPLEXITY_TIMEOUT_SECONDS", "180"))

SYSTEM_PROMPT = (
    "You are a precise Filipino investigative research assistant. "
    "Return only the data requested in well-formed JSON. "
    "Always cite credible primary sources such as SEC filings, official "
    "government releases, Rappler, Philippine Daily Inquirer, Philstar, "
    "GMA News, Manila Bulletin, or equivalent outlets."
)

MISSING_AFFILIATION_QUERY = """
SELECT
    id,
    company_name,
    person_name,
    role
FROM company_affiliations
WHERE COALESCE(source_url, '') = ''
ORDER BY id;
"""


def get_db_kwargs() -> Dict[str, Any]:
    """Load database connection parameters from environment variables."""
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", 5432)),
        "user": os.getenv("POSTGRES_USER", "budget_admin"),
        "password": os.getenv("POSTGRES_PASSWORD", ""),
        "database": os.getenv("POSTGRES_DB_DYNASTY", "dynasty"),
    }


async def fetch_missing_affiliations() -> List[Dict[str, Any]]:
    """Retrieve company affiliation rows that still have no supporting URL."""
    conn = await asyncpg.connect(**get_db_kwargs())
    try:
        rows = await conn.fetch(MISSING_AFFILIATION_QUERY)
        return [dict(row) for row in rows]
    finally:
        await conn.close()


def build_prompt(record: Dict[str, Any]) -> str:
    """Create a Perplexity prompt for a single missing affiliation entry."""
    company = record["company_name"].strip()
    placeholder_person = record["person_name"].strip() or "Unknown"
    role = record["role"].strip() or "Unknown role"

    return f"""# Contractor Relationship Proof Needed

We maintain a database that tracks how construction companies relate to public officials.
One entry is missing credible sources.

## Database Entry (needs verification)
- Company: {company}
- Placeholder person/recorded name: {placeholder_person}
- Recorded role: {role}

## Task for you
1. Identify the ACTUAL individual(s) tied to {company} in capacities such as owner, incorporator,
   director, officer, chairperson, or other executive roles. Focus on people connected to
   Philippine politics or politically exposed persons where possible.
2. Cite up to three credible articles, government documents, or filings that explicitly mention
   the relationship between the individual and {company}.
3. Return **only** a JSON array in a ```json fenced code block. Each object must contain:
   - "subject_name": full name of the individual
   - "role": role/title they hold in the company (owner, incorporator, etc.)
   - "relationship_description": concise explanation of the link
   - "source_title": article or document title
   - "source_url": direct URL to the source
   - "source_date": ISO date string (YYYY-MM-DD) if available, else empty string
   - "confidence": integer 1-10 reflecting reliability
4. Skip speculative content. If no credible sources exist, return an empty JSON array: ```json [] ```

Answer in English and ensure URLs are accessible.
"""


def call_perplexity(prompt: str) -> str:
    """Invoke Perplexity chat completion API with the supplied prompt."""
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        raise RuntimeError("PERPLEXITY_API_KEY not set in environment")

    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": PERPLEXITY_MODEL,
        "temperature": float(os.getenv("PERPLEXITY_TEMPERATURE", "0.1")),
        "top_p": 1.0,
        "max_tokens": 4000,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }

    response = requests.post(url, headers=headers, json=payload, timeout=PERPLEXITY_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    return data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""


JSON_BLOCK_PATTERN = re.compile(r"```json\s*([\s\S]*?)\s*```", re.IGNORECASE)


def extract_json_array(reply: str) -> List[Dict[str, Any]]:
    """Parse a JSON array from Perplexity's reply."""
    if not reply:
        return []

    for match in JSON_BLOCK_PATTERN.findall(reply):
        try:
            parsed = json.loads(match.strip())
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            continue

    # As a fallback, attempt to parse the entire reply.
    try:
        parsed = json.loads(reply)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass

    return []


def save_results(payload: Dict[str, Any]) -> Path:
    """Persist results to timestamped JSON inside the family_analysis folder."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = OUTPUT_DIR / f"missing_relationship_sources_{timestamp}.json"
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return output_path


def main() -> None:
    missing_records = asyncio.run(fetch_missing_affiliations())
    if not missing_records:
        print("🎉 No missing relationship proofs found. Nothing to do.")
        return

    print(f"🔎 Found {len(missing_records)} relationship entries without source URLs.\n")

    processed: List[Dict[str, Any]] = []
    for index, record in enumerate(missing_records, start=1):
        print("=" * 80)
        print(f"📋 [{index}/{len(missing_records)}] Processing ID {record['id']} • {record['company_name']}")
        prompt = build_prompt(record)
        try:
            reply = call_perplexity(prompt)
            suggestions = extract_json_array(reply)
            status = "✅ suggestions captured" if suggestions else "⚠️ no usable suggestions"
        except Exception as error:
            reply = f"ERROR: {error}"
            suggestions = []
            status = f"❌ API call failed: {error}"

        print(f"   {status}")

        processed.append(
            {
                "record": record,
                "prompt": prompt,
                "perplexity_reply": reply,
                "suggestions": suggestions,
            }
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": PERPLEXITY_MODEL,
        "records_pending": len(missing_records),
        "results": processed,
    }
    output_path = save_results(payload)
    print("\n💾 Saved Perplexity suggestions to:", output_path)
    print("Review the suggestions, then backfill the database and regenerate the checklist when ready.")


if __name__ == "__main__":
    main()





