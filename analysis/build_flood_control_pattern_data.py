#!/usr/bin/env python3
"""Build a compact evidence snapshot for the flood-control pattern report."""
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLOOD = ROOT / "static/data/flood_control_data_with_jv.json"
MPB = ROOT / "static/nep-preview/mpb-data.json"
INTEGRATED = ROOT / "static/nep-preview/integrated-district-data.json"
OUT = ROOT / "static/nep-preview/flood-control-pattern-data.json"


def main():
    projects = json.loads(FLOOD.read_text())["projects"]
    mpb = json.loads(MPB.read_text())
    integrated = json.loads(INTEGRATED.read_text())
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

    district_rows = integrated.get("annual", [])
    ilocos_id = "leg:ilocos-norte:1st"
    ilocos_series = []
    by_district_period = {}
    for row in district_rows:
        by_district_period[(row.get("districtId"), row.get("year"), row.get("stage"))] = row
        if row.get("districtId") == ilocos_id:
            ilocos_series.append({
                "year": row.get("year"),
                "stage": row.get("stage"),
                "lineItems": row.get("lineItems", 0),
                "totalPesos": row.get("totalPesos", 0),
                "categories": row.get("categories", {}),
            })
    ilocos_series.sort(key=lambda row: (row["year"], row["stage"]))
    ilocos_22 = by_district_period.get((ilocos_id, 2022, "GAA"), {})
    ilocos_23 = by_district_period.get((ilocos_id, 2023, "GAA"), {})
    all_categories = sorted({
        category
        for row in district_rows
        for category in row.get("categories", {})
    })
    family_growth = []
    for row in district_rows:
        if row.get("year") != 2022 or row.get("stage") != "GAA":
            continue
        after = by_district_period.get((row.get("districtId"), 2023, "GAA"))
        if not after:
            continue
        for category, before_values in row.get("categories", {}).items():
            before_amount = int(before_values.get("totalPesos") or 0)
            before_count = int(before_values.get("lineItems") or 0)
            after_values = after.get("categories", {}).get(category, {})
            after_amount = int(after_values.get("totalPesos") or 0)
            after_count = int(after_values.get("lineItems") or 0)
            # Exclude tiny baselines from the cross-district rise table. Keep all
            # Ilocos Norte category rows separately, including the small bridge base.
            if before_amount < 100_000_000 or after_amount <= before_amount:
                continue
            family_growth.append({
                "category": category,
                "district": row.get("district"),
                "beforePesos": before_amount,
                "afterPesos": after_amount,
                "changePesos": after_amount - before_amount,
                "changePct": round(100 * (after_amount / before_amount - 1), 1),
                "beforeLineItems": before_count,
                "afterLineItems": after_count,
            })
    top_family_growth = {}
    for category in all_categories:
        top_family_growth[category] = sorted(
            [row for row in family_growth if row["category"] == category],
            key=lambda row: row["changePesos"],
            reverse=True,
        )[:5]

    ilocos_family_comparison = []
    for category in all_categories:
        before = ilocos_22.get("categories", {}).get(category)
        after = ilocos_23.get("categories", {}).get(category)
        if not before and not after:
            continue
        before_amount = int((before or {}).get("totalPesos") or 0)
        after_amount = int((after or {}).get("totalPesos") or 0)
        ilocos_family_comparison.append({
            "category": category,
            "beforePesos": before_amount,
            "afterPesos": after_amount,
            "changePesos": after_amount - before_amount,
            "changePct": round(100 * (after_amount / before_amount - 1), 1) if before_amount else None,
            "beforeLineItems": int((before or {}).get("lineItems") or 0),
            "afterLineItems": int((after or {}).get("lineItems") or 0),
        })
    ilocos_total_change_pct = round(100 * (ilocos_23["totalPesos"] / ilocos_22["totalPesos"] - 1), 1)

    hgab_current = [row for row in district_rows if row.get("year") == 2027 and row.get("stage") == "HGAB 3rd"]
    history_comparisons = []
    for row in hgab_current:
        for category, current_values in row.get("categories", {}).items():
            current_amount = int(current_values.get("totalPesos") or 0)
            history_points = []
            for year in range(2020, 2027):
                historical_row = by_district_period.get((row.get("districtId"), year, "GAA"))
                historical_values = (historical_row or {}).get("categories", {}).get(category)
                history_points.append({
                    "year": year,
                    "stage": "GAA",
                    "amountPesos": int(historical_values["totalPesos"]) if historical_values else None,
                    "lineItems": int(historical_values["lineItems"]) if historical_values else None,
                })
            observed = [point for point in history_points if point["amountPesos"] is not None and point["amountPesos"] > 0]
            if not observed:
                continue
            historical_average = sum(point["amountPesos"] for point in observed) / len(observed)
            historical_maximum = max(point["amountPesos"] for point in observed)
            historical_peak_year = next(point["year"] for point in observed if point["amountPesos"] == historical_maximum)
            history_comparisons.append({
                "district": row.get("district"),
                "districtId": row.get("districtId"),
                "category": category,
                "currentAmountPesos": current_amount,
                "currentLineItems": int(current_values.get("lineItems") or 0),
                "historyPoints": history_points,
                "historicalYearsAvailable": len(observed),
                "historicalAveragePesos": round(historical_average, 2),
                "historicalMaximumPesos": historical_maximum,
                "historicalPeakYear": historical_peak_year,
                "changeVsAveragePct": round(100 * (current_amount / historical_average - 1), 1) if historical_average else None,
                "excessOverMaximumPesos": current_amount - historical_maximum,
                "changeVsMaximumPct": round(100 * (current_amount / historical_maximum - 1), 1) if historical_maximum else None,
            })
    current_above_max = [
        row for row in history_comparisons
        if row["historicalYearsAvailable"] >= 2
        and row["currentAmountPesos"] >= 100_000_000
        and row["excessOverMaximumPesos"] > 0
    ]
    current_above_max.sort(key=lambda row: row["excessOverMaximumPesos"], reverse=True)
    top_current_by_family = {}
    for category in all_categories:
        top_current_by_family[category] = [
            row for row in current_above_max if row["category"] == category
        ][:5]

    data = {
        "generatedFrom": {
            "floodContracts": "static/data/flood_control_data_with_jv.json",
            "mpbAnalysis": "static/nep-preview/mpb-data.json",
            "districtAnnualAnalysis": "static/nep-preview/integrated-district-data.json",
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
        "districtFamilyScan": {
            "comparison": "FY2022 GAA to FY2023 GAA; unique district assignments in the integrated project-family analysis",
            "baselineMinimumPesos": 100000000,
            "categories": all_categories,
            "ilocosNorteFirst": {
                "district": "Ilocos Norte · 1st District",
                "representative": ilocos_23.get("representative"),
                "before": {"year": 2022, "stage": "GAA", "lineItems": ilocos_22.get("lineItems"), "totalPesos": ilocos_22.get("totalPesos")},
                "after": {"year": 2023, "stage": "GAA", "lineItems": ilocos_23.get("lineItems"), "totalPesos": ilocos_23.get("totalPesos")},
                "totalChangePct": ilocos_total_change_pct,
                "families": ilocos_family_comparison,
                "series": ilocos_series,
            },
            "topIncreasesByFamily": top_family_growth,
            "currentVsHistory": history_comparisons,
            "currentAboveHistoricalMax": current_above_max[:40],
            "topCurrentAboveHistoricalMaxByFamily": top_current_by_family,
            "coverage": integrated.get("coverage", []),
            "method": integrated.get("method", {}),
        },
        "reading": {
            "bulacanSignals": [
                "A large 2022–2023 increase in recorded project count and contract value, followed by a high 2024 level.",
                "Bulacan became the largest single-province concentration in the 2022–2024 contract snapshot.",
                "Several Bulacan municipalities repeatedly appear among the largest local totals.",
            ],
            "mpbConclusion": "The cross-family district scan identifies Ilocos Norte 1st as a clear FY2022-to-FY2023 increase candidate: Flood control, multi-purpose buildings, roads, and bridges all rise in the integrated district totals. That resemblance is a pattern lead, not confirmation of a Bulacan-style mechanism; annual project classifications, attribution coverage, project scope and implementation context still need verification.",
        },
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
