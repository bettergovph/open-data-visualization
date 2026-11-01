#!/usr/bin/env python3
"""Build a compact evidence snapshot for the flood-control pattern report."""
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLOOD = ROOT / "static/data/flood_control_data_with_jv.json"
MPB = ROOT / "static/nep-preview/mpb-data.json"
OUT = ROOT / "static/nep-preview/flood-control-pattern-data.json"


def main():
    projects = json.loads(FLOOD.read_text())["projects"]
    mpb = json.loads(MPB.read_text())
    years = sorted({int(row["InfraYear"]) for row in projects if row.get("InfraYear")})
    annual = []
    for year in years:
        rows = [row for row in projects if int(row.get("InfraYear") or 0) == year]
        bulacan = [row for row in rows if (row.get("Province") or "").upper() == "BULACAN"]
        annual.append({
            "year": year,
            "nationalProjects": len(rows),
            "nationalContractCost": round(sum(float(row.get("ContractCost") or 0) for row in rows), 2),
            "bulacanProjects": len(bulacan),
            "bulacanContractCost": round(sum(float(row.get("ContractCost") or 0) for row in bulacan), 2),
            "bulacanProjectSharePct": round(100 * len(bulacan) / len(rows), 2) if rows else 0,
            "bulacanCostSharePct": round(100 * sum(float(row.get("ContractCost") or 0) for row in bulacan) / sum(float(row.get("ContractCost") or 0) for row in rows), 2) if rows else 0,
        })

    bulacan_all = [row for row in projects if (row.get("Province") or "").upper() == "BULACAN"]
    localities = defaultdict(lambda: {"projects": 0, "contractCost": 0.0})
    contractors = defaultdict(lambda: {"projects": 0, "contractCost": 0.0})
    for row in bulacan_all:
        if int(row.get("InfraYear") or 0) not in (2022, 2023, 2024):
            continue
        municipality = row.get("Municipality") or "Unspecified"
        contractor = row.get("Contractor") or "Unspecified"
        amount = float(row.get("ContractCost") or 0)
        localities[municipality]["projects"] += 1
        localities[municipality]["contractCost"] += amount
        contractors[contractor]["projects"] += 1
        contractors[contractor]["contractCost"] += amount

    summary = mpb["summary"]
    amount_frequency = Counter()
    for row in mpb.get("insertions", []):
        amount = int(row.get("amountPesos") or 0)
        if amount > 0:
            amount_frequency[amount] += 1
    top_amounts = [{"amountPesos": amount, "candidateLines": count} for amount, count in amount_frequency.most_common(12)]

    data = {
        "generatedFrom": {
            "floodContracts": "static/data/flood_control_data_with_jv.json",
            "mpbAnalysis": "static/nep-preview/mpb-data.json",
            "floodScope": "DPWH flood-control contract records in the local ODV snapshot",
            "mpbScope": "FY2027 HGAB 3rd-reading MPB budget lines and comparison candidates",
        },
        "flood": {
            "totalProjects": len(projects),
            "annual": annual,
            "bulacanTopLocalities": [
                {"name": name, **{k: round(v, 2) if k == "contractCost" else v for k, v in values.items()}}
                for name, values in sorted(localities.items(), key=lambda pair: pair[1]["contractCost"], reverse=True)[:10]
            ],
            "bulacanTopContractors": [
                {"name": name, **{k: round(v, 2) if k == "contractCost" else v for k, v in values.items()}}
                for name, values in sorted(contractors.items(), key=lambda pair: pair[1]["contractCost"], reverse=True)[:10]
            ],
        },
        "mpb": {
            **summary,
            "candidateAmountSharePct": round(100 * summary["insertionPesos"] / summary["hgabPesos"], 2),
            "candidateLineSharePct": round(100 * summary["insertionCandidates"] / summary["hgabLines"], 2),
            "ambiguousLineSharePct": round(100 * summary["ambiguousLines"] / summary["hgabLines"], 2),
            "distributionGroups": len(mpb.get("distribution", [])),
            "regions": len({item.get("region") for item in mpb.get("distribution", []) if item.get("region")}),
            "largestGroups": sorted(mpb.get("distribution", []), key=lambda item: item.get("amountPesos", 0), reverse=True)[:8],
            "repeatedCandidateAmounts": top_amounts,
            "coordinateSummary": mpb.get("coordinateProximity", {}).get("summary", {}),
        },
        "reading": {
            "bulacanSignals": [
                "A large 2022–2023 increase in recorded project count and contract value, followed by a high 2024 level.",
                "Bulacan became the largest single-province concentration in the 2022–2024 contract snapshot.",
                "Several Bulacan municipalities repeatedly appear among the largest local totals.",
            ],
            "mpbConclusion": "MPB is a strong next review target for repeated allocations and recurring sites. Current evidence does not show that MPB reproduces the Bulacan flood-control pattern as a whole: the datasets cover different stages, the MPB list is spread across many office-region groups, and comparable year-over-year MPB totals are not present in this snapshot.",
        },
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
