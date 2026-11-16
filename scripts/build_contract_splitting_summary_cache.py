#!/usr/bin/env python3
"""Build the lightweight, tracked JSON used by the Flood Control infographic."""

import json
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT / "database/dpwh/contract splitting/dpwh_projects_2021_2024.parquet"
CANDIDATES = ROOT / "database/dpwh/contract splitting/contract_splitting_candidates.parquet"
OUTPUT = ROOT / "static/data/contract_splitting_summary.json"


def main() -> None:
    connection = duckdb.connect()
    candidates_path = str(CANDIDATES).replace("'", "''")
    projects_path = str(PROJECTS).replace("'", "''")
    rows = connection.execute(
        f"""
        WITH candidates AS (
            SELECT DISTINCT lower(trim("Contract splitting candidates")) AS candidate
            FROM read_parquet('{candidates_path}')
            WHERE "Contract splitting candidates" IS NOT NULL
        ), grouped_projects AS (
            SELECT
                cluster_id,
                first(contractor) AS contractor,
                count(*) AS project_count
            FROM read_parquet('{projects_path}')
            WHERE cluster_id IS NOT NULL
            GROUP BY cluster_id
            HAVING count(*) > 1
        )
        SELECT
            projects.cluster_id,
            projects.contractor,
            projects.project_count
        FROM grouped_projects AS projects
        INNER JOIN candidates
            ON lower(trim(projects.contractor)) = candidates.candidate
        ORDER BY projects.cluster_id
        """,
    ).fetchall()
    connection.close()

    payload = {
        "success": True,
        "clusters": [
            {
                "cluster_id": int(cluster_id),
                "contractor": contractor,
                "project_count": int(project_count),
                "is_candidate": True,
            }
            for cluster_id, contractor, project_count in rows
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} candidate clusters to {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
