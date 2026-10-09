#!/usr/bin/env python3
"""Build congressional-district allocations from the local FY2027 DPWH HGAB 3rd Reading."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
import enrich_nep_preview_representatives as reps  # noqa: E402

HGAB_FILE = ROOT.parent / "nep" / "hb10858_3rd_dpwh_projects.json"
REVIEW_FILE = ROOT.parent / "nep" / "analysis_output" / "hb_nep_comparison_3rd.csv"
OUT_FILE = ROOT / "static" / "nep-preview" / "congress-data.json"
DISTRICT_LABELS = {"1st": "1st District", "2nd": "2nd District", "3rd": "3rd District",
                   "4th": "4th District", "5th": "5th District", "6th": "6th District",
                   "7th": "7th District", "8th": "8th District", "lone": "Lone District"}


def clean_name(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\[[^]]+\]", "", value or "")).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write congress-data.json")
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
    seat_by_name: dict[str, list[int]] = defaultdict(list)
    for i, row in enumerate(seats):
        seat_by_name[row["key"]].append(i)

    roster, _ = reps.load_roster()
    # Some single-seat cities in the 20th Congress roster have no municipality
    # entry in districts.json. Province/city-only project titles can still be
    # attributed safely when the roster shows exactly one seat there.
    for row in seat_rows:
        province = reps.norm(row["province"])
        seat = reps.district_key(row["districtLabel"])
        roster.setdefault(province, {})[seat] = row["representative"]
    locality_index, province_names = reps.make_locality_index(roster)
    places_by_first_word: dict[str, list[str]] = defaultdict(list)
    for place in locality_index:
        places_by_first_word[place.split()[0]].append(place)

    scenario_rows = {}
    for scenario in ("accommodating", "strict"):
        scenario_rows[scenario] = [
            {"district": f'{row["province"]} · {row["districtLabel"]}',
             "representative": row["representative"], "lineItems": 0, "totalPesos": 0}
            for row in seats
        ]
    source = json.loads(HGAB_FILE.read_text())
    projects = source["data"]["data"]
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
        names = reps.infer_representatives(title, roster, locality_index, province_names, places_by_first_word)
        indices = sorted({i for name in names for i in seat_by_name.get(reps.norm(clean_name(name)), [])})
        if not indices:
            unassigned += 1
            unassigned_amount += amount
            continue
        if len(indices) == 1:
            assigned_once += 1
            row = scenario_rows["strict"][indices[0]]
            row["lineItems"] += 1
            row["totalPesos"] += amount
        else:
            assigned_shared += 1
        for index in indices:
            row = scenario_rows["accommodating"][index]
            row["lineItems"] += 1
            row["totalPesos"] += amount

    for rows in scenario_rows.values():
        rows.sort(key=lambda x: (-x["totalPesos"], x["district"]))

    output = {
        "source": "FY2027 DPWH HGAB 3rd Reading local extraction",
        "roster": "20th Congress roster in ODV static/data/20th_congress_representatives.json",
        "extractionMethod": source.get("metadata", {}).get("extractionMethod", "local schedule extraction"),
        "sourceWarning": source.get("metadata", {}).get("warning", "Candidate extraction; check cited bill pages."),
        "unit": "pesos",
        "summary": {
            "candidateLineItems": len(projects), "candidateTotalPesos": candidate_total,
            "excludedScheduleLines": excluded_count, "excludedScheduleAmountPesos": excluded_total,
            "sourceLineItems": analyzed_count, "sourceTotalPesos": analyzed_total,
            "uniquelyAssignedLines": assigned_once, "sharedAssignedLines": assigned_shared,
            "unassignedLines": unassigned, "unassignedAmountPesos": unassigned_amount,
            "accommodatingAssignedPesos": sum(x["totalPesos"] for x in scenario_rows["accommodating"]),
            "strictAssignedPesos": sum(x["totalPesos"] for x in scenario_rows["strict"]),
            "sharedReplicatedAdditionalPesos": sum(x["totalPesos"] for x in scenario_rows["accommodating"])
            - sum(x["totalPesos"] for x in scenario_rows["strict"]),
            "districtCount": len(seats),
        },
        "accommodating": scenario_rows["accommodating"],
        "strict": scenario_rows["strict"],
    }
    print(json.dumps(output["summary"], indent=2))
    if args.write:
        OUT_FILE.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n")
        print(f"Wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
