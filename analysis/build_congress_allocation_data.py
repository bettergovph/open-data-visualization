#!/usr/bin/env python3
"""Build congressional-district allocations from the local FY2027 DPWH HGAB 3rd Reading."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
import enrich_nep_preview_representatives as reps  # noqa: E402
from strict_congress_geography import GeographicAttribution, VERSION  # noqa: E402

HGAB_FILE = ROOT.parent / "nep" / "hb10858_3rd_dpwh_projects.json"
REVIEW_FILE = ROOT.parent / "nep" / "analysis_output" / "hb_nep_comparison_3rd.csv"
OUT_FILE = ROOT / "static" / "nep-preview" / "congress-data.json"
DISTRICT_LABELS = {"1st": "1st District", "2nd": "2nd District", "3rd": "3rd District",
                   "4th": "4th District", "5th": "5th District", "6th": "6th District",
                   "7th": "7th District", "8th": "8th District", "lone": "Lone District"}
DISTRICT_LABELS["9th"] = "9th District"


def clean_name(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\[[^]]+\]", "", value or "")).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write congress-data.json")
    parser.add_argument("--audit", type=Path, help="write project-level geographic decisions to private JSON and CSV files")
    parser.add_argument("--geographic-decisions", type=Path, default=ROOT / "static/data/congress_location_scope_reviews.json", help="reviewed location evidence supplement; IDs, titles and amounts must match")
    args = parser.parse_args()

    roster_raw = json.loads(reps.ROSTER_PATH.read_text())
    seat_rows = []
    for row in roster_raw:
        province, district = str(row.get("province", "")).strip(), reps.district_key(row.get("district"))
        name = clean_name(str(row.get("representative", "")))
        if district not in DISTRICT_LABELS or not province or not name or reps.norm(name) == "special election":
            continue
        seat_rows.append({"province": province, "districtLabel": DISTRICT_LABELS[district],
                          "representative": name, "key": reps.norm(name)})

    # Keep only one row per named seat and build a name-to-seat lookup.
    seats = {}
    for row in seat_rows:
        key = (reps.norm(row["province"]), row["districtLabel"])
        seats[key] = row
    seats = sorted(seats.values(), key=lambda x: (reps.norm(x["province"]), x["districtLabel"]))
    geography = GeographicAttribution(ROOT / "static/data", seats)

    scenario_rows = {}
    for scenario in ("strict",):
        scenario_rows[scenario] = [
            {"district": f'{row["province"]} · {row["districtLabel"]}',
             "representative": row["representative"], "lineItems": 0, "totalPesos": 0}
            for row in seats
        ]
    source = json.loads(HGAB_FILE.read_text())
    projects = source["data"]["data"]
    supplement = json.loads(args.geographic_decisions.read_text()) if args.geographic_decisions and args.geographic_decisions.exists() else {}
    overrides = supplement.get("decisions", {})
    expected_source = supplement.get("summary", {}).get("hgabSha256")
    if expected_source and hashlib.sha256(HGAB_FILE.read_bytes()).hexdigest() != expected_source:
        raise ValueError("Location review belongs to a different HGAB source snapshot; regenerate the review")
    project_ids = {p["id"] for p in projects}
    if set(overrides) - project_ids:
        raise ValueError("Location supplement contains unknown source IDs")
    excluded_keys = set()
    if REVIEW_FILE.exists():
        with REVIEW_FILE.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if row.get("comparison", "").startswith("Likely schedule heading/total"):
                    excluded_keys.add((str(row.get("sourcePage") or ""),
                                       str(row.get("amountPesos") or ""),
                                       reps.norm(row.get("projectName") or "")))
    assigned_once = assigned_shared = unassigned = 0
    unassigned_amount = 0
    candidate_total = 0
    excluded_total = 0
    excluded_count = 0
    analyzed_total = 0
    analyzed_count = 0
    audit_rows = []
    unresolved_reasons = defaultdict(lambda: {"lineItems": 0, "totalPesos": 0})
    shared_source_amount = 0

    for project in projects:
        title = str(project.get("projectName") or "")
        amount = int(round(float(project.get("amountPesos") or 0)))
        candidate_total += amount
        exclusion_key = (str(project.get("sourcePage") or ""), str(amount), reps.norm(title))
        if exclusion_key in excluded_keys:
            excluded_count += 1
            excluded_total += amount
            continue
        analyzed_count += 1
        analyzed_total += amount
        decision = geography.resolve(project)
        if project.get("id") in overrides:
            extra = overrides[project["id"]]
            if extra["projectName"] != title or int(extra["amountPesos"]) != amount:
                raise ValueError("Location supplement does not match the current source record")
            decision["evidence"] += extra.get("evidence", [])
            if extra.get("holdUnresolved"):
                decision["indices"] = []
                decision["reasons"] = sorted(set(decision["reasons"] + extra["reasons"]))
        indices = decision["indices"]
        audit_rows.append({"id": project.get("id"), "projectName": title, "amountPesos": amount,
                           "sourceVolume": project.get("sourceVolume"), "sourcePage": project.get("sourcePage"),
                           "region": project.get("region"), "office": project.get("office"),
                           "districts": [scenario_rows["strict"][i]["district"] for i in indices],
                           "representatives": [scenario_rows["strict"][i]["representative"] for i in indices],
                           "status": "shared" if len(indices) > 1 else "unique" if indices else "unresolved",
                           "reasons": decision["reasons"], "geographicEvidence": decision["evidence"]})
        if not indices:
            unassigned += 1
            unassigned_amount += amount
            reason = "; ".join(decision["reasons"]) or "No district established"
            unresolved_reasons[reason]["lineItems"] += 1
            unresolved_reasons[reason]["totalPesos"] += amount
            continue
        if len(indices) == 1:
            assigned_once += 1
            row = scenario_rows["strict"][indices[0]]
            row["lineItems"] += 1
            row["totalPesos"] += amount
        else:
            assigned_shared += 1
            shared_source_amount += amount

    for rows in scenario_rows.values():
        rows.sort(key=lambda x: (-x["totalPesos"], x["district"]))

    output = {
        "source": "FY2027 DPWH HGAB 3rd Reading local extraction",
        "roster": "20th Congress roster in ODV static/data/20th_congress_representatives.json",
        "extractionMethod": source.get("metadata", {}).get("extractionMethod", "local schedule extraction"),
        "sourceWarning": source.get("metadata", {}).get("warning", "Candidate extraction; check cited bill pages."),
        "unit": "pesos",
        "attributionMethod": VERSION,
        "attributionWarning": "Conservative location-based coverage, not complete district budgets or evidence of a representative's sponsorship. Exact municipality + province fields require agreement between both local district maps. Multi-seat cities require explicitly named barangays and agreeing maps. Shared lines, conflicts and missing scope stay outside the ranking. Local map agreement is a screening rule, not independent official boundary verification. A zero means no accepted attribution, not no allocation.",
        "unresolvedReasons": [{"reason": k, **v} for k, v in sorted(unresolved_reasons.items(), key=lambda kv: -kv[1]["totalPesos"])],
        "summary": {
            "candidateLineItems": len(projects), "candidateTotalPesos": candidate_total,
            "excludedScheduleLines": excluded_count, "excludedScheduleAmountPesos": excluded_total,
            "sourceLineItems": analyzed_count, "sourceTotalPesos": analyzed_total,
            "uniquelyAssignedLines": assigned_once, "sharedAssignedLines": assigned_shared,
            "unassignedLines": unassigned, "unassignedAmountPesos": unassigned_amount,
            "sharedSourceAmountPesos": shared_source_amount,
            "assignedSourceAmountPesos": analyzed_total - unassigned_amount,
            "strictAssignedPesos": sum(x["totalPesos"] for x in scenario_rows["strict"]),
            "strictExcludedLines": unassigned + assigned_shared,
            "strictExcludedAmountPesos": unassigned_amount + shared_source_amount,
            "strictCoveragePct": round(100 * (analyzed_total - unassigned_amount - shared_source_amount) / analyzed_total, 2) if analyzed_total else 0,
            "districtCount": len(seats),
        },
        "strict": scenario_rows["strict"],
    }
    if assigned_once + assigned_shared + unassigned != analyzed_count:
        raise ValueError("Congressional row reconciliation failed")
    if output["summary"]["strictAssignedPesos"] + shared_source_amount + unassigned_amount != analyzed_total:
        raise ValueError("Congressional allocation reconciliation failed")
    if supplement:
        output["locationDatabaseReview"] = supplement["summary"]
        output["attributionMethod"] += "+location-db-scope-review-v1"
        output["attributionWarning"] += " The private location evidence database supplies qualified-place evidence and scope exclusions. Undated LEG claims and historical GAA project names do not establish new current district assignments."
    print(json.dumps(output["summary"], indent=2))
    if args.write:
        OUT_FILE.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n")
        print(f"Wrote {OUT_FILE}")
    if args.audit:
        sources = [HGAB_FILE, REVIEW_FILE, reps.ROSTER_PATH, ROOT / "static/data/districts.json",
                   ROOT / "static/data/districts_generated.json", ROOT / "city_barangays_mapping.json",
                   Path(__file__), ROOT / "analysis/strict_congress_geography.py"]
        if args.geographic_decisions:
            sources.append(args.geographic_decisions)
        provenance = [{"file": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                      for path in sources if path.exists()]
        args.audit.write_text(json.dumps({"method": VERSION, "warning": output["attributionWarning"],
                                          "sources": provenance, "summary": output["summary"],
                                          "projects": audit_rows}, ensure_ascii=False, indent=2) + "\n")
        print(f"Wrote {args.audit}")
        audit_csv = args.audit.with_suffix(".csv")
        with audit_csv.open("w", encoding="utf-8-sig", newline="") as handle:
            fields = ["id", "projectName", "amountPesos", "region", "office", "sourceVolume", "sourcePage",
                      "status", "districts", "representatives", "reasons", "geographicEvidence"]
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in audit_rows:
                writer.writerow({k: json.dumps(row[k], ensure_ascii=False) if isinstance(row[k], list) else row[k] for k in fields})
        print(f"Wrote {audit_csv}")


if __name__ == "__main__":
    main()
