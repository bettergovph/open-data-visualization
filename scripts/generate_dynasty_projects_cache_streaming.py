#!/usr/bin/env python3
"""
Streaming variant of the dynasty-projects cache generator.

Instead of collecting every project in memory and performing expensive cross-source
joins, this script walks each upstream data source row-by-row (Flood → DIME → PhilGEPS →
Infrawatch), assigns congressman matches on the fly, and writes incremental checkpoint
files. This keeps the runtime closer to O(n) relative to total source rows and greatly
reduces the impact of crashes: progress is saved after each processed chunk.

All matching logic for municipalities / provinces / districts / barangays is inherited
from the original DynastyProjectsCacheGenerator so behaviour stays consistent.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import functools
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import asyncpg
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Re-use all matching and configuration helpers from the existing generator.
from infrawatch_postgres_client import get_infrawatch_connection
from scripts.generate_dynasty_projects_cache import DynastyProjectsCacheGenerator


class StreamingAccumulator:
    """Incrementally store congressman projects and running statistics."""

    def __init__(self, generator: DynastyProjectsCacheGenerator) -> None:
        self.generator = generator
        root_dir = Path(__file__).parent.parent
        static_data = root_dir / "static" / "data"

        self.output_root = static_data
        self.progress_path = self.output_root / "dynasty-streaming-progress.json"

        self.tmp_dir = static_data / "dynasty-streaming-tmp"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

        self.checkpoint_dir = static_data / "dynasty-streaming-checkpoints"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        self.congressman_files: Dict[str, Path] = {}
        self.congressman_stats: Dict[str, Dict[str, Any]] = defaultdict(self._init_congressman_stats)
        self.global_source_counter: Counter[str] = Counter()
        self.global_totals: Dict[str, Any] = {
            "total_projects": 0,
            "district_projects": 0,
            "contractor_projects": 0,
            "flood_control_projects": 0,
            "flood_control_cost": 0.0,
        }

        self.processed_congressmen: List[str] = []
        self.processed_rows: Dict[str, int] = defaultdict(int)

    @staticmethod
    def _init_congressman_stats() -> Dict[str, Any]:
        return {
            "count": 0,
            "total_cost": 0.0,
            "source_counts": Counter(),
            "flood_control_count": 0,
            "flood_control_cost": 0.0,
            "district_count": 0,
            "district_cost": 0.0,
            "contractor_count": 0,
            "contractor_cost": 0.0,
        }

    @staticmethod
    def _sanitize_congressman_slug(name: str) -> str:
        slug = name.lower()
        for ch in (" ", ".", ",", "'", '"', "(", ")", "/"):
            slug = slug.replace(ch, "-")
        slug = "-".join(filter(None, slug.split("-")))
        return slug or "unknown"

    @staticmethod
    def _parse_amount(value: Any) -> float:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.replace("₱", "").replace(",", "").strip()
            if not cleaned:
                return 0.0
            try:
                return float(cleaned)
            except ValueError:
                return 0.0
        return 0.0

    def _ensure_congressman_file(self, congressman: str) -> Path:
        if congressman not in self.congressman_files:
            slug = self._sanitize_congressman_slug(congressman)
            path = self.tmp_dir / f"{slug}.jsonl"
            if not path.exists():
                path.touch()
            self.congressman_files[congressman] = path
        return self.congressman_files[congressman]

    def _append_json_line(self, path: Path, payload: Dict[str, Any]) -> None:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def track_progress(self, source: str, processed_rows: int) -> None:
        self.processed_rows[source] = processed_rows
        progress_payload = {
            "generated_at": datetime.now().isoformat(),
            "processed_rows": dict(self.processed_rows),
            "processed_congressmen": list(self.processed_congressmen),
            "total_projects_streamed": self.global_totals["total_projects"],
        }
        self.generator._atomic_write_json(self.progress_path, progress_payload)

    def add_projects(self, projects: Iterable[Dict[str, Any]]) -> None:
        for project in projects:
            congressman = project.get("congressman")
            if not congressman:
                continue

            # Basic source bookkeeping
            source_label = self.generator._normalize_source_label(project.get("source", "Unknown"))
            project["source"] = source_label
            project["sources_list"] = [source_label]
            project["sources_count"] = 1

            # Flood-control tagging using existing helper.
            flood_control = bool(self.generator._is_flood_control_project(project))
            project["flood_control"] = flood_control

            amount = self._parse_amount(project.get("amount"))
            match_type = project.get("match_type") or "unknown"

            stats = self.congressman_stats[congressman]
            stats["count"] += 1
            stats["total_cost"] += amount
            stats["source_counts"][source_label] += 1

            if flood_control:
                stats["flood_control_count"] += 1
                stats["flood_control_cost"] += amount
                self.global_totals["flood_control_projects"] += 1
                self.global_totals["flood_control_cost"] += amount

            if match_type == "district":
                stats["district_count"] += 1
                stats["district_cost"] += amount
                self.global_totals["district_projects"] += 1
            elif match_type == "contractor":
                stats["contractor_count"] += 1
                stats["contractor_cost"] += amount
                self.global_totals["contractor_projects"] += 1

            self.global_totals["total_projects"] += 1
            self.global_source_counter[source_label] += 1

            # Persist to congressman-specific JSONL stream.
            file_path = self._ensure_congressman_file(congressman)
            self._append_json_line(file_path, project)

    def finalize(
        self,
        generator: DynastyProjectsCacheGenerator,
        config_data: Dict[str, Any],
        output_variant: str = "streaming",
    ) -> None:
        cache_base_dir = self.output_root

        chart_data: List[Dict[str, Any]] = []

        summary_contractors: Dict[str, Dict[str, Any]] = {}
        total_cost_all = 0.0

        for congressman, stats in sorted(self.congressman_stats.items()):
            slug = self._sanitize_congressman_slug(congressman)
            jsonl_path = self.congressman_files.get(congressman)
            if not jsonl_path or not jsonl_path.exists():
                continue

            projects: List[Dict[str, Any]] = []
            with open(jsonl_path, "r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        projects.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

            if not projects:
                continue

            # Summaries derived from running totals.
            congressman_summary = {
                "total": stats["count"],
                "dime": stats["source_counts"].get("DIME", 0),
                "philgeps": stats["source_counts"].get("PhilGEPS", 0),
                "ssp": stats["source_counts"].get("Flood Control", 0),
                "infrawatch": stats["source_counts"].get("Infrawatch", 0),
                "microsite": stats["source_counts"].get("Infrawatch", 0),
                "district_projects": stats["district_count"],
                "contractor_projects": stats["contractor_count"],
                "flood_control": stats["flood_control_count"],
                "flood_control_cost": stats["flood_control_cost"],
            }

            congressman_dashboard = {
                "total_cost_all": stats["total_cost"],
                "total_projects": stats["count"],
                "district_count": stats["district_count"],
                "district_cost": stats["district_cost"],
                "contractor_count": stats["contractor_count"],
                "contractor_cost": stats["contractor_cost"],
                "flood_control_count": stats["flood_control_count"],
                "flood_control_cost": stats["flood_control_cost"],
                "flood_control_district_count": None,
                "flood_control_district_cost": None,
                "flood_control_contractor_count": None,
                "flood_control_contractor_cost": None,
            }

            total_cost_all += stats["total_cost"]

            chart_data.append(
                {
                    "name": congressman,
                    "count": stats["count"],
                    "total_cost": stats["total_cost"],
                    "flood_control_count": stats["flood_control_count"],
                    "flood_control_cost": stats["flood_control_cost"],
                }
            )

            cache_dir = cache_base_dir / f"congressman-projects-{slug}"
            cache_dir.mkdir(parents=True, exist_ok=True)

            cache_payload = {
                "success": True,
                "congressman": congressman,
                "projects": projects,
                "summary": congressman_summary,
                "dashboard_stats": congressman_dashboard,
                "generated_at": datetime.now().isoformat(),
                "cache_version": "streaming-1.0",
            }

            summary_payload = {
                "congressman": congressman,
                "summary": congressman_summary,
                "total_cost": stats["total_cost"],
                "flood_control_cost": stats["flood_control_cost"],
                "generated_at": datetime.now().isoformat(),
            }

            generator._atomic_write_json(cache_dir / "all-projects-cache.json", cache_payload)
            generator._atomic_write_json(cache_dir / "summary.json", summary_payload)

            self.processed_congressmen.append(congressman)
            self.track_progress("finalize", len(self.processed_congressmen))

            summary_contractors[congressman] = {
                "count": stats["count"],
                "total_cost": stats["total_cost"],
                "cache_file": str((cache_dir / "all-projects-cache.json").relative_to(self.output_root)),
            }

        chart_data.sort(key=lambda item: item["count"], reverse=True)
        chart_top10_by_count = chart_data[:10]
        chart_top10_by_cost = sorted(chart_data, key=lambda item: item["total_cost"], reverse=True)[:10]

        overall_summary = {
            "total": self.global_totals["total_projects"],
            "dime": self.global_source_counter.get("DIME", 0),
            "philgeps": self.global_source_counter.get("PhilGEPS", 0),
            "ssp": self.global_source_counter.get("Flood Control", 0),
            "infrawatch": self.global_source_counter.get("Infrawatch", 0),
            "microsite": self.global_source_counter.get("Infrawatch", 0),
            "flood_control": self.global_totals["flood_control_projects"],
            "district_projects": self.global_totals["district_projects"],
            "contractor_projects": self.global_totals["contractor_projects"],
        }

        overall_dashboard = {
            "total_cost_all": total_cost_all,
            "total_projects": self.global_totals["total_projects"],
            "district_count": self.global_totals["district_projects"],
            "district_cost": None,
            "contractor_count": self.global_totals["contractor_projects"],
            "contractor_cost": None,
            "flood_control_count": self.global_totals["flood_control_projects"],
            "flood_control_cost": self.global_totals["flood_control_cost"],
            "flood_control_district_count": None,
            "flood_control_district_cost": None,
            "flood_control_contractor_count": None,
            "flood_control_contractor_cost": None,
        }

        combined_payload = {
            "success": True,
            "summary": overall_summary,
            "chart_data": chart_data,
            "chart_top10_by_count": chart_top10_by_count,
            "chart_top10_by_cost": chart_top10_by_cost,
            "dashboard_stats": overall_dashboard,
            "generated_at": datetime.now().isoformat(),
            "cache_version": "streaming-1.0",
            "contractors": summary_contractors,
        }

        generator._atomic_write_json(self.output_root / "dynasty-projects-cache.json", combined_payload)


class StreamingDynastyProjectsCacheGenerator(DynastyProjectsCacheGenerator):
    """Streaming-optimised generator retaining the original matching logic."""

    def __init__(self, chunk_size: int = 250) -> None:
        super().__init__()
        self.batch_size = int(os.getenv("DYNASTY_STREAM_BATCH", chunk_size))
        self.max_workers = int(os.getenv("DYNASTY_STREAM_WORKERS", "24"))
        if self.batch_size < self.max_workers:
            self.batch_size = self.max_workers
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)

    def _slice_batch(self, batch: List[Any]) -> List[List[Any]]:
        if not batch:
            return []
        if len(batch) <= self.max_workers:
            return [[item] for item in batch]
        slice_size = max(1, math.ceil(len(batch) / self.max_workers))
        slices: List[List[Any]] = []
        for index in range(0, len(batch), slice_size):
            slices.append(batch[index:index + slice_size])
        return slices[: self.max_workers] if len(slices) > self.max_workers else slices

    async def _process_batch(
        self,
        batch: List[Any],
        processor: Any,
        *args: Any,
    ) -> List[Dict[str, Any]]:
        if not batch:
            return []
        slices = self._slice_batch(batch)
        loop = asyncio.get_running_loop()
        tasks = [
            loop.run_in_executor(
                self.executor,
                functools.partial(processor, slice_chunk, *args),
            )
            for slice_chunk in slices
            if slice_chunk
        ]
        results = await asyncio.gather(*tasks)
        combined: List[Dict[str, Any]] = []
        for result in results:
            if result:
                combined.extend(result)
        return combined

    async def _stream_flood_projects(
        self,
        conn: asyncpg.Connection,
        aggregator: StreamingAccumulator,
        congressmen_data: Dict[str, Any],
        districts_data: Dict[str, Any],
    ) -> None:
        query = """
            SELECT
                project_global_id,
                project_name,
                contractor,
                contract_amount,
                province,
                municipality,
                raw_data,
                is_green_flag,
                has_red_flags,
                remarks,
                meilisearch_global_id
            FROM flagged_flood_projects
            ORDER BY id
        """
        processed = 0
        batch: List[asyncpg.Record] = []
        async with conn.transaction():
            async for row in conn.cursor(query, prefetch=self.batch_size):
                batch.append(row)
                if len(batch) >= self.batch_size:
                    projects = await self._process_batch(
                        batch,
                        self._process_flood_chunk,
                        congressmen_data,
                        districts_data,
                    )
                    aggregator.add_projects(projects)
                    processed += len(batch)
                    aggregator.track_progress("flood", processed)
                    batch.clear()
            if batch:
                projects = await self._process_batch(
                    batch,
                    self._process_flood_chunk,
                    congressmen_data,
                    districts_data,
                )
                aggregator.add_projects(projects)
                processed += len(batch)
                aggregator.track_progress("flood", processed)

    async def _stream_dime_projects(
        self,
        conn: asyncpg.Connection,
        aggregator: StreamingAccumulator,
        congressmen_data: Dict[str, Any],
        districts_data: Dict[str, Any],
    ) -> None:
        query = """
            SELECT
                project_name,
                contractors,
                cost,
                province,
                city,
                barangay,
                status,
                date_started,
                meilisearch_id
            FROM projects
        """
        processed = 0
        batch: List[asyncpg.Record] = []
        async with conn.transaction():
            async for row in conn.cursor(query, prefetch=self.batch_size):
                batch.append(row)
                if len(batch) >= self.batch_size:
                    projects = await self._process_batch(
                        batch,
                        self._process_dime_chunk,
                        congressmen_data,
                        districts_data,
                    )
                    aggregator.add_projects(projects)
                    processed += len(batch)
                    aggregator.track_progress("dime", processed)
                    batch.clear()
            if batch:
                projects = await self._process_batch(
                    batch,
                    self._process_dime_chunk,
                    congressmen_data,
                    districts_data,
                )
                aggregator.add_projects(projects)
                processed += len(batch)
                aggregator.track_progress("dime", processed)

    async def _stream_philgeps_projects(
        self,
        conn: asyncpg.Connection,
        aggregator: StreamingAccumulator,
        congressmen_data: Dict[str, Any],
        districts_data: Dict[str, Any],
    ) -> None:
        query = """
            SELECT
                award_title,
                awardee_name,
                contract_amount,
                area_of_delivery,
                award_date,
                award_status,
                meilisearch_id
            FROM contracts
        """
        processed = 0
        batch: List[asyncpg.Record] = []
        async with conn.transaction():
            async for row in conn.cursor(query, prefetch=self.batch_size):
                batch.append(row)
                if len(batch) >= self.batch_size:
                    projects = await self._process_batch(
                        batch,
                        self._process_philgeps_chunk,
                        congressmen_data,
                        districts_data,
                    )
                    aggregator.add_projects(projects)
                    processed += len(batch)
                    aggregator.track_progress("philgeps", processed)
                    batch.clear()
            if batch:
                projects = await self._process_batch(
                    batch,
                    self._process_philgeps_chunk,
                    congressmen_data,
                    districts_data,
                )
                aggregator.add_projects(projects)
                processed += len(batch)
                aggregator.track_progress("philgeps", processed)

    async def _stream_infrawatch_projects(
        self,
        conn: Optional[asyncpg.Connection],
        aggregator: StreamingAccumulator,
        congressmen_data: Dict[str, Any],
        districts_data: Dict[str, Any],
    ) -> None:
        if not conn:
            return

        try:
            structured_table_exists = await conn.fetchval("SELECT to_regclass('public.infrawatch_projects')")
        except Exception:
            structured_table_exists = None

        processed = 0
        batch: List[Dict[str, Any]] = []

        if structured_table_exists:
            query = """
                SELECT
                    p.contract_id,
                    p.contract_details,
                    p.contractor,
                    p.implementing_agency,
                    p.fund_source,
                    p.contract_price,
                    p.effectivity_date,
                    p.expiry_date,
                    p.contract_status,
                    p.accomplishment_pct,
                    p.infrawatch_row_id,
                    r.data AS raw_data,
                    r.philgeps_contract_id
                FROM infrawatch_projects p
                LEFT JOIN infrawatch_projects_rows r
                  ON r.id = p.infrawatch_row_id
                WHERE r.philgeps_contract_id IS NULL
                   OR p.infrawatch_row_id IS NULL
            """
            async with conn.transaction():
                async for row in conn.cursor(query, prefetch=self.batch_size):
                    normalized = dict(row)
                    batch.append(normalized)
                    if len(batch) >= self.batch_size:
                        normalized_rows = [{"data": record} for record in batch]
                        projects = await self._process_batch(
                            normalized_rows,
                            self._process_infrawatch_chunk,
                            congressmen_data,
                            districts_data,
                        )
                        aggregator.add_projects(projects)
                        processed += len(batch)
                        aggregator.track_progress("infrawatch", processed)
                        batch.clear()
        else:
            query = """
                SELECT data
                FROM infrawatch_projects_rows
                WHERE philgeps_contract_id IS NULL
            """
            async with conn.transaction():
                async for row in conn.cursor(query, prefetch=self.batch_size):
                    normalized = {"data": row.get("data")}
                    batch.append(normalized)
                    if len(batch) >= self.batch_size:
                        projects = await self._process_batch(
                            batch,
                            self._process_infrawatch_chunk,
                            congressmen_data,
                            districts_data,
                        )
                        aggregator.add_projects(projects)
                        processed += len(batch)
                        aggregator.track_progress("infrawatch", processed)
                        batch.clear()

        if batch:
            normalized_rows = [{"data": record} for record in batch]
            projects = await self._process_batch(
                normalized_rows,
                self._process_infrawatch_chunk,
                congressmen_data,
                districts_data,
            )
            aggregator.add_projects(projects)
            processed += len(batch)
            aggregator.track_progress("infrawatch", processed)

    async def generate_cache(self) -> None:
        print("🚀 Starting streaming dynasty-projects cache generation...")
        self._refresh_source_json()

        config_data, districts_data = await self.load_config()
        print(f"✅ Loaded config with {len(config_data.get('target_congressmen', []))} congressmen")

        common_db_kwargs = {
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_PORT", 5432)),
            "user": os.getenv("POSTGRES_USER", "budget_admin"),
            "password": os.getenv("POSTGRES_PASSWORD", ""),
        }

        dynasty_conn = await asyncpg.connect(**{**common_db_kwargs, "database": os.getenv("POSTGRES_DB_DYNASTY", "dynasty")})
        dime_conn = await asyncpg.connect(**{**common_db_kwargs, "database": os.getenv("POSTGRES_DB_DIME", "dime")})
        philgeps_conn = await asyncpg.connect(**{**common_db_kwargs, "database": os.getenv("POSTGRES_DB_PHILGEPS", "philgeps")})
        flood_conn = await asyncpg.connect(**{**common_db_kwargs, "database": os.getenv("POSTGRES_DB_FLOOD", "flood")})
        infrawatch_conn = await get_infrawatch_connection()

        aggregator = StreamingAccumulator(self)

        try:
            political_dynasties_available = True
            try:
                exists_query = """
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_name = 'political_dynasties'
                    )
                """
                political_dynasties_available = await dynasty_conn.fetchval(exists_query)
            except Exception:
                political_dynasties_available = False
            if not political_dynasties_available:
                print("⚠️  Dynasty DB missing political_dynasties table. Using config-only data.")

            congressmen_data = await self.get_congressmen_data(
                dynasty_conn,
                config_data,
                districts_data,
                political_dynasties_available,
            )
            print(f"✅ Loaded {len(congressmen_data)} congressmen for streaming pipeline")

            await self._stream_flood_projects(flood_conn, aggregator, congressmen_data, districts_data)
            await self._stream_dime_projects(dime_conn, aggregator, congressmen_data, districts_data)
            await self._stream_philgeps_projects(philgeps_conn, aggregator, congressmen_data, districts_data)
            await self._stream_infrawatch_projects(infrawatch_conn, aggregator, congressmen_data, districts_data)

            aggregator.finalize(self, config_data)
            print("✅ Streaming cache generation complete.")

            self._regenerate_top_congressmen_cache()
        finally:
            self.executor.shutdown(wait=True)
            await dynasty_conn.close()
            await dime_conn.close()
            await philgeps_conn.close()
            await flood_conn.close()
            if infrawatch_conn:
                await infrawatch_conn.close()


async def main() -> None:
    chunk_size = int(os.getenv("DYNASTY_STREAM_CHUNK", "250"))
    generator = StreamingDynastyProjectsCacheGenerator(chunk_size=chunk_size)
    await generator.generate_cache()


if __name__ == "__main__":
    asyncio.run(main())


