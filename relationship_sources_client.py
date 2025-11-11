"""Client utilities for retrieving contractor-dynasty relationship source links.

This module centralizes database lookups for investigative sources that back up
relationship tables (all_names_politician_relationships, bac_politician_relationships,
engineer_politician_relationships, company_affiliations).  It can be reused by the
FastAPI layer as well as offline scripts that need a checklist of missing source URLs.
"""

from __future__ import annotations

import asyncio
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

import asyncpg
import csv
import json
from io import StringIO
from pathlib import Path


DOMAIN_MAPPING: Dict[str, str] = {
    "rappler.com": "Rappler",
    "newsinfo.inquirer.net": "Philippine Daily Inquirer",
    "business.inquirer.net": "Philippine Daily Inquirer",
    "inquirer.net": "Philippine Daily Inquirer",
    "manilastandard.net": "Manila Standard",
    "manilatimes.net": "Manila Times",
    "philstar.com": "Philippine STAR",
    "wikipedia.org": "Wikipedia",
    "wikiwand.com": "Wikiwand",
    "peoplaid.com": "PeoPlaid",
    "kwebanibarok.com": "Kwebanibarok",
    "dof.gov.ph": "DOF Philippines",
    "pdplaban.org.ph": "PDP Laban",
    "reddit.com": "Reddit",
    "philatlas.com": "PhilAtlas",
}

NAME_NORMALIZATION: Dict[str, str] = {
    "Inquirer": "Philippine Daily Inquirer",
    "Philippine Daily Inquirer": "Philippine Daily Inquirer",
    "Philippine Daily Inquirer News": "Philippine Daily Inquirer",
    "Philippine Inquirer": "Philippine Daily Inquirer",
    "The Philippine Daily Inquirer": "Philippine Daily Inquirer",
    "Manila Standard": "Manila Standard",
    "The Manila Times": "Manila Times",
    "Manila Times": "Manila Times",
    "Rappler": "Rappler",
    "Wikipedia": "Wikipedia",
    "PhilAtlas": "PhilAtlas",
}

REQUIRED_DEFAULTS: Dict[str, List[Dict[str, str]]] = {
    "Rappler": [
        {
            "title": "Rappler Investigative Coverage",
            "url": "https://www.rappler.com/newsbreak/investigative/",
            "date": "",
        }
    ],
    "Philippine Daily Inquirer": [
        {
            "title": "Philippine Daily Inquirer News",
            "url": "https://www.inquirer.net/",
            "date": "",
        }
    ],
    "Manila Standard": [
        {
            "title": "Manila Standard - News",
            "url": "https://manilastandard.net/",
            "date": "",
        }
    ],
    "Manila Times": [
        {
            "title": "The Manila Times",
            "url": "https://www.manilatimes.net/",
            "date": "",
        }
    ],
    "Wikipedia": [
        {
            "title": "Wikipedia: Politics of the Philippines",
            "url": "https://en.wikipedia.org/wiki/Politics_of_the_Philippines",
            "date": "",
        }
    ],
    "PhilAtlas": [
        {
            "title": "PhilAtlas Province Profiles",
            "url": "https://www.philatlas.com/",
            "date": "",
        }
    ],
}


RELATIONSHIP_QUERIES: Tuple[Dict[str, str], ...] = (
    {
        "table": "all_names_politician_relationships",
        "sql": """
            SELECT
                id,
                person_first_name || ' ' || person_last_name AS subject_name,
                person_position AS subject_position,
                politician_name AS related_entity,
                relationship_type,
                relationship_description,
                news_article_title AS source_title,
                source_url,
                TO_CHAR(created_at, 'YYYY-MM-DD') AS source_date,
                confidence_level
            FROM all_names_politician_relationships
        """,
    },
    {
        "table": "bac_politician_relationships",
        "sql": """
            SELECT
                id,
                bac_first_name || ' ' || bac_last_name AS subject_name,
                bac_position AS subject_position,
                politician_name AS related_entity,
                relationship_type,
                relationship_description,
                news_article_title AS source_title,
                source_url,
                TO_CHAR(created_at, 'YYYY-MM-DD') AS source_date,
                confidence_level
            FROM bac_politician_relationships
        """,
    },
    {
        "table": "engineer_politician_relationships",
        "sql": """
            SELECT
                id,
                engineer_first_name || ' ' || engineer_last_name AS subject_name,
                engineer_position AS subject_position,
                politician_name AS related_entity,
                relationship_type,
                relationship_description,
                news_article_title AS source_title,
                source_url,
                TO_CHAR(created_at, 'YYYY-MM-DD') AS source_date,
                confidence_level
            FROM engineer_politician_relationships
        """,
    },
    {
        "table": "company_affiliations",
        "sql": """
            SELECT
                id,
                person_name AS subject_name,
                role AS subject_position,
                company_name AS related_entity,
                'Company affiliation' AS relationship_type,
                NULL AS relationship_description,
                NULL AS source_title,
                source_url,
                TO_CHAR(created_at, 'YYYY-MM-DD') AS source_date,
                confidence_level
            FROM company_affiliations
        """,
    },
)


@dataclass
class RelationshipRecord:
    table: str
    id: int
    subject_name: Optional[str]
    subject_position: Optional[str]
    related_entity: Optional[str]
    relationship_type: Optional[str]
    relationship_description: Optional[str]
    source_title: Optional[str]
    source_url: Optional[str]
    source_date: Optional[str]
    confidence_level: Optional[int]

    def as_checklist_entry(self, source_key: Optional[str]) -> Dict[str, Any]:
        return {
            "table": self.table,
            "id": self.id,
            "subject": {
                "name": self.subject_name,
                "position": self.subject_position,
            },
            "related_entity": self.related_entity,
            "relationship_type": self.relationship_type,
            "relationship_description": self.relationship_description,
            "confidence_level": self.confidence_level,
            "source": {
                "has_source": bool(self.source_url),
                "url": self.source_url or None,
                "title": self.source_title or None,
                "date": self.source_date or None,
                "normalized_source": source_key,
            },
        }


class RelationshipSourcesClient:
    """Async client used for retrieving contractor-dynasty relationship sources."""

    def __init__(
        self,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
    ) -> None:
        self._connection_kwargs = {
            "host": host or os.getenv("POSTGRES_HOST", "localhost"),
            "port": port or int(os.getenv("POSTGRES_PORT", 5432)),
            "user": user or os.getenv("POSTGRES_USER", "budget_admin"),
            "password": password or os.getenv("POSTGRES_PASSWORD", ""),
            "database": database or os.getenv("POSTGRES_DB_DYNASTY", "dynasty"),
        }

    async def _connect(self) -> asyncpg.Connection:
        return await asyncpg.connect(**self._connection_kwargs)

    @staticmethod
    def _get_domain(url: str) -> str:
        if not url:
            return ""
        parsed = urlparse(url)
        domain = (parsed.netloc or "").lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain

    def _normalize_source_name(self, source_name: Optional[str], url: Optional[str]) -> str:
        domain = self._get_domain(url or "")
        if domain:
            if domain in DOMAIN_MAPPING:
                return DOMAIN_MAPPING[domain]
            for known_domain, mapped in DOMAIN_MAPPING.items():
                if domain.endswith(known_domain):
                    return mapped
        if source_name:
            cleaned = source_name.strip()
            if cleaned:
                return NAME_NORMALIZATION.get(cleaned, cleaned)
        if domain:
            return domain
        return "Unknown"

    def _load_family_analysis_records(self) -> List[Dict[str, Any]]:
        base_dir = Path(__file__).resolve().parent / "family_analysis"
        if not base_dir.exists():
            return []

        csv_patterns = [
            "family_parser/llm_relationships_*.csv",
            "family_parser/all_names_relationships_csvs/*.csv",
            "family_parser/bac_relationships_csvs/*.csv",
            "family_parser/engineer_relationships_csvs/*.csv",
            "family_parser/contractor_officers_csvs/*.csv",
            "family_parser/party_list_representatives_batch_*.csv",
            "family_parser/verify_contractor_*.csv",
        ]
        records: List[Dict[str, Any]] = []

        def parse_int(value: Optional[str]) -> Optional[int]:
            if value is None:
                return None
            try:
                return int(str(value).strip())
            except (TypeError, ValueError):
                return None

        def add_record(record: Dict[str, Any]) -> None:
            url = record.get("source_url")
            if not url or not str(url).lower().startswith("http"):
                return
            records.append(record)

        # CSV sources
        for pattern in csv_patterns:
            for path in base_dir.glob(pattern):
                try:
                    with path.open("r", encoding="utf-8", newline="") as handle:
                        reader = csv.DictReader(handle)
                        if not reader.fieldnames or not any("source" in (field or "").lower() and "url" in (field or "").lower() for field in reader.fieldnames):
                            continue
                        for index, row in enumerate(reader, start=1):
                            url = (row.get("source_url") or row.get("Source_URL") or "").strip()
                            if not url or not url.lower().startswith("http"):
                                continue
                            subject = (
                                row.get("person1_name")
                                or row.get("person_name")
                                or row.get("subject_name")
                                or row.get("official_name")
                                or row.get("name")
                            )
                            related = (
                                row.get("person2_name")
                                or row.get("related_person_name")
                                or row.get("company_name")
                                or row.get("organization_name")
                                or row.get("related_entity")
                            )
                            relationship_type = row.get("relationship_type") or row.get("role") or row.get("position") or row.get("relationship")
                            relationship_description = row.get("relationship_description") or row.get("notes") or row.get("description")
                            source_title = relationship_description or relationship_type or related or subject or path.stem
                            add_record(
                                {
                                    "record_id": f"family_csv::{path.relative_to(base_dir)}::{index}",
                                    "source_type": "family_analysis_csv",
                                    "file": str(path.relative_to(base_dir)),
                                    "row_index": index,
                                    "subject_name": subject,
                                    "subject_position": row.get("person1_position") or row.get("role") or row.get("position_title"),
                                    "related_entity": related,
                                    "relationship_type": relationship_type,
                                    "relationship_description": relationship_description,
                                    "confidence_level": parse_int(row.get("confidence_level")),
                                    "source_url": url,
                                    "source_title": source_title,
                                    "source_date": (row.get("source_date") or row.get("date") or row.get("published_date") or "").strip(),
                                }
                            )
                except Exception:
                    continue

        # JSON (Perplexity) sources with embedded CSV
        json_dir = base_dir / "family_parser" / "rappler_contractors_perplexity"
        if json_dir.exists():
            for path in json_dir.glob("*.json"):
                try:
                    with path.open("r", encoding="utf-8") as handle:
                        data = json.load(handle)
                    response = data.get("response") or ""
                    start = response.find("```csv")
                    if start == -1:
                        continue
                    start += len("```csv")
                    end = response.find("```", start)
                    if end == -1:
                        continue
                    csv_text = response[start:end].strip()
                    if not csv_text:
                        continue
                    reader = csv.DictReader(StringIO(csv_text))
                    if not reader.fieldnames or "source_url" not in reader.fieldnames:
                        continue
                    for index, row in enumerate(reader, start=1):
                        url = (row.get("source_url") or "").strip()
                        if not url or not url.lower().startswith("http"):
                            continue
                        subject = row.get("person_name")
                        related = row.get("related_person_name") or row.get("related_entity")
                        relationship_type = row.get("relationship_type")
                        relationship_description = row.get("notes") or row.get("relationship_type")
                        source_title = relationship_description or related or subject or path.stem
                        add_record(
                            {
                                "record_id": f"family_json::{path.relative_to(base_dir)}::{index}",
                                "source_type": "family_analysis_json",
                                "file": str(path.relative_to(base_dir)),
                                "row_index": index,
                                "subject_name": subject,
                                "subject_position": None,
                                "related_entity": related,
                                "relationship_type": relationship_type,
                                "relationship_description": relationship_description,
                                "confidence_level": parse_int(row.get("confidence_level")),
                                "source_url": url,
                                "source_title": source_title,
                                "source_date": "",
                            }
                        )
                except Exception:
                    continue

        return records

    async def fetch_relationship_records(self) -> List[RelationshipRecord]:
        conn = await self._connect()
        try:
            records: List[RelationshipRecord] = []
            for config in RELATIONSHIP_QUERIES:
                rows = await conn.fetch(config["sql"])
                for row in rows:
                    records.append(
                        RelationshipRecord(
                            table=config["table"],
                            id=row["id"],
                            subject_name=(row.get("subject_name") or "").strip() or None,
                            subject_position=(row.get("subject_position") or "").strip() or None,
                            related_entity=(row.get("related_entity") or "").strip() or None,
                            relationship_type=(row.get("relationship_type") or "").strip() or None,
                            relationship_description=(row.get("relationship_description") or "").strip() or None,
                            source_title=(row.get("source_title") or "").strip() or None,
                            source_url=(row.get("source_url") or "").strip() or None,
                            source_date=(row.get("source_date") or "").strip() or None,
                            confidence_level=row.get("confidence_level"),
                        )
                    )
            return records
        finally:
            await conn.close()

    async def fetch_relationship_articles(self) -> Dict[str, List[Dict[str, Any]]]:
        records = await self.fetch_relationship_records()
        articles_by_source: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        seen_urls: set[Tuple[str, str]] = set()

        for record in records:
            url = record.source_url
            if not url:
                continue
            source_key = self._normalize_source_name(None, url)
            article = {
                "title": record.source_title or record.related_entity or url,
                "url": url,
                "date": record.source_date or "",
                "table": record.table,
                "relationship_type": record.relationship_type,
                "relationship_description": record.relationship_description,
                "subject_name": record.subject_name,
                "subject_position": record.subject_position,
                "related_entity": record.related_entity,
            }
            dedupe_key = (source_key, url)
            if dedupe_key in seen_urls:
                continue
            seen_urls.add(dedupe_key)
            articles_by_source[source_key].append(article)

        family_records = self._load_family_analysis_records()
        for record in family_records:
            url = record.get("source_url")
            if not url:
                continue
            source_key = self._normalize_source_name(None, url)
            article = {
                "title": record.get("source_title") or record.get("relationship_description") or record.get("relationship_type") or record.get("related_entity") or url,
                "url": url,
                "date": record.get("source_date") or "",
                "table": record.get("source_type", "family_analysis"),
                "relationship_type": record.get("relationship_type"),
                "relationship_description": record.get("relationship_description"),
                "subject_name": record.get("subject_name"),
                "related_entity": record.get("related_entity"),
                "source_file": record.get("file"),
            }
            dedupe_key = (source_key, url)
            if dedupe_key in seen_urls:
                continue
            seen_urls.add(dedupe_key)
            articles_by_source[source_key].append(article)

        for source_key, defaults in REQUIRED_DEFAULTS.items():
            if not articles_by_source.get(source_key):
                for article in defaults:
                    dedupe_key = (source_key, article["url"])
                    if dedupe_key in seen_urls:
                        continue
                    seen_urls.add(dedupe_key)
                    articles_by_source[source_key].append(article)

        for article_list in articles_by_source.values():
            article_list.sort(key=lambda item: (item.get("date") or "", item.get("title") or ""), reverse=True)

        return dict(sorted(articles_by_source.items()))

    async def fetch_relationship_checklist(self) -> Dict[str, Any]:
        records = await self.fetch_relationship_records()
        checklist: List[Dict[str, Any]] = []
        for record in records:
            normalized_source = self._normalize_source_name(None, record.source_url) if record.source_url else None
            checklist.append(record.as_checklist_entry(normalized_source))

        family_records = self._load_family_analysis_records()
        for record in family_records:
            url = record.get("source_url")
            normalized_source = self._normalize_source_name(None, url) if url else None
            checklist.append(
                {
                    "table": record.get("source_type", "family_analysis"),
                    "id": record.get("record_id"),
                    "subject": {
                        "name": record.get("subject_name"),
                        "position": record.get("subject_position"),
                    },
                    "related_entity": record.get("related_entity"),
                    "relationship_type": record.get("relationship_type"),
                    "relationship_description": record.get("relationship_description"),
                    "confidence_level": record.get("confidence_level"),
                    "source": {
                        "has_source": bool(url),
                        "url": url,
                        "title": record.get("source_title"),
                        "date": record.get("source_date"),
                        "normalized_source": normalized_source,
                        "file": record.get("file"),
                    },
                }
            )
        checklist.sort(key=lambda item: (item["table"], str(item["id"])))
        return checklist

    async def build_checklist_report(self) -> Dict[str, Any]:
        checklist = await self.fetch_relationship_checklist()
        total = len(checklist)
        with_source = sum(1 for entry in checklist if entry["source"]["has_source"])
        without_source = total - with_source
        return {
            "total_records": total,
            "with_source": with_source,
            "without_source": without_source,
            "records": checklist,
        }


async def fetch_relationship_articles() -> Dict[str, List[Dict[str, Any]]]:
    client = RelationshipSourcesClient()
    return await client.fetch_relationship_articles()


async def fetch_relationship_checklist() -> Dict[str, Any]:
    client = RelationshipSourcesClient()
    return await client.build_checklist_report()


def generate_checklist_json(output_path: str) -> None:
    async def _run() -> None:
        report = await fetch_relationship_checklist()
        from datetime import datetime, timezone

        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            **report,
        }

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    asyncio.run(_run())


