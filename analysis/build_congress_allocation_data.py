#!/usr/bin/env python3
"""Build congressional-district allocations from the local FY2027 DPWH HGAB 3rd Reading."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
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
BOUNDARY_FILE = ROOT.parent / "nep" / "data_sources" / "arcgis_dpwh" / "archive" / "selected" / "city_municipal_boundaries" / "layers" / "City_Municipal_Boundaries_FeatureServer_0-0340fd6a" / "features.jsonl"
DISTRICT_LABELS = {"1st": "1st District", "2nd": "2nd District", "3rd": "3rd District",
                   "4th": "4th District", "5th": "5th District", "6th": "6th District",
                   "7th": "7th District", "8th": "8th District", "lone": "Lone District"}
DISTRICT_LABELS["9th"] = "9th District"
COORDINATE_PAIR = re.compile(r"(?<![\d.])([+-]?\d{1,3}\.\d+)\s*°?\s*[,;/]\s*([+-]?\d{1,3}\.\d+)(?![\d.])")
ORDINALS = {"first":"1st", "second":"2nd", "third":"3rd", "fourth":"4th", "fifth":"5th",
            "sixth":"6th", "seventh":"7th", "eighth":"8th", "ninth":"9th", "tenth":"10th"}
CALOOCAN_BARANGAY = re.compile(r"\b(?:barangay|brgy\.?|bgy\.?)\s*(?:no\.?\s*)?(\d{1,3})\b", re.I)
MANILA_BARANGAY = re.compile(
    r"\b(?:barangays?|brgys?\.?|bgys?\.?)\s*(?:nos?\.?\s*)?(\d{1,4})"
    r"(?:\s*(?:to|[-–])\s*(\d{1,4}))?",
    re.I,
)
MANILA_FOURTH_DISTRICT_ZONE_RANGE = re.compile(r"\bzones?\s*41\s*(?:to|[-–])\s*57\b", re.I)
MANILA_SIXTH_DISTRICT_ZONE_PAIR = re.compile(r"\bzones?\s*92\s*(?:&|and|,)\s*93\b", re.I)


def _caloocan_barangay_district(title: str):
    """Use Caloocan's current statutory numbered-barangay district split."""
    if "caloocan" not in str(title or "").casefold():
        return None
    match = CALOOCAN_BARANGAY.search(title)
    if not match:
        return None
    number = int(match.group(1))
    if 178 <= number <= 188:
        return "3rd District", number
    if number in {1, 2, 3, 4} or 77 <= number <= 85 or 132 <= number <= 177:
        return "1st District", number
    if 5 <= number <= 76 or 86 <= number <= 131:
        return "2nd District", number
    return None


def _manila_barangay_district(title: str):
    """Use Manila's constitutional numbered-barangay district boundaries."""
    title = str(title or "")
    if not re.search(r"\b(?:manila\s+city|city\s+of\s+manila)\b", title, re.I):
        return None
    matches = list(MANILA_BARANGAY.finditer(title))
    if not matches:
        return None

    numbers = []
    range_districts = set()
    for match in matches:
        first = int(match.group(1))
        last = int(match.group(2) or first)
        if not 1 <= first <= last <= 905:
            return None
        numbers.extend((first, last))
        range_districts.update(
            district for number in range(first, last + 1)
            if (district := _manila_barangay_seat(number)) is not None
        )
        # Support compact lists such as “Barangays 175 and 180” without
        # mistaking the following Zone number for another barangay.
        tail = title[match.end():]
        listed = re.match(r"\s+and\s+(\d{1,4})\b", tail, re.I)
        if listed:
            number = int(listed.group(1))
            numbers.append(number)
            range_districts.add(_manila_barangay_seat(number))

    districts = range_districts | {_manila_barangay_seat(number) for number in numbers}
    if len(districts) != 1 or None in districts:
        return None
    return next(iter(districts)), numbers


def _manila_barangay_seat(number: int):
    if 1 <= number <= 146:
        return "1st District"
    if 147 <= number <= 267:
        return "2nd District"
    if 268 <= number <= 394:
        return "3rd District"
    if 395 <= number <= 586:
        return "4th District"
    if 587 <= number <= 648 or 829 <= number <= 905:
        return "6th District"
    if 649 <= number <= 828:
        return "5th District"
    return None


def _manila_zone_district(title: str):
    """Resolve only Manila zone groups with direct, corroborated district evidence."""
    title = str(title or "")
    if not re.search(r"\b(?:manila\s+city|city\s+of\s+manila)\b", title, re.I):
        return None
    if MANILA_FOURTH_DISTRICT_ZONE_RANGE.search(title):
        return "4th District", [41, 57]
    if MANILA_SIXTH_DISTRICT_ZONE_PAIR.search(title):
        return "6th District", [92, 93]
    return None


def _title_point(title: str):
    points = set()
    for match in COORDINATE_PAIR.finditer(title):
        first, second = float(match[1]), float(match[2])
        if 4 <= first <= 22 and 116 <= second <= 127:
            points.add((second, first, match[0]))
        elif 116 <= first <= 127 and 4 <= second <= 22:
            points.add((first, second, match[0]))
    if len(points) != 1:
        return None
    lon, lat, raw = next(iter(points))
    decimals = min(len(part.split(".")[1]) for part in re.findall(r"[+-]?\d+\.\d+", raw))
    return (lon, lat, raw) if decimals >= 4 else None


def _place_key(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", clean_name(value).casefold()))


def _utm51_to_wgs84(easting: float, northing: float):
    """Convert the archived DPWH boundary layer's EPSG:32651 vertices."""
    a=6378137.0; f=1/298.257223563; e2=f*(2-f); ep2=e2/(1-e2); k0=.9996
    x=(easting-500000.0)/k0; y=northing/k0; m=y
    mu=m/(a*(1-e2/4-3*e2**2/64-5*e2**3/256))
    e1=(1-math.sqrt(1-e2))/(1+math.sqrt(1-e2))
    j1=3*e1/2-27*e1**3/32; j2=21*e1**2/16-55*e1**4/32
    j3=151*e1**3/96; j4=1097*e1**4/512
    fp=mu+j1*math.sin(2*mu)+j2*math.sin(4*mu)+j3*math.sin(6*mu)+j4*math.sin(8*mu)
    sf=math.sin(fp); cf=math.cos(fp); tf=math.tan(fp)
    n1=a/math.sqrt(1-e2*sf*sf); r1=a*(1-e2)/(1-e2*sf*sf)**1.5
    c1=ep2*cf*cf; t1=tf*tf; d=x/n1
    lat=fp-(n1*tf/r1)*(d*d/2-(5+3*t1+10*c1-4*c1*c1-9*ep2)*d**4/24+(61+90*t1+298*c1+45*t1*t1-252*ep2-3*c1*c1)*d**6/720)
    lon=math.radians(123)+(d-(1+2*t1+c1)*d**3/6+(5-2*c1+28*t1-3*c1*c1+8*ep2+24*t1*t1)*d**5/120)/cf
    return math.degrees(lon), math.degrees(lat)


def _inside_rings(lon: float, lat: float, rings) -> bool:
    inside=False
    for ring in rings:
        hit=False
        for i in range(len(ring)):
            x1,y1=ring[i-1]; x2,y2=ring[i]
            if (y1>lat)!=(y2>lat) and lon<(x2-x1)*(lat-y1)/(y2-y1)+x1:
                hit=not hit
        if hit:
            inside=not inside
    return inside


def _locality_aliases(attributes):
    aliases=set()
    for field in ("MUNICIPAL", "MUN_DBM"):
        value=_place_key(attributes.get(field) or "")
        if not value:
            continue
        aliases.add(value)
        aliases.add(re.sub(r"\s+\([^)]*\)$", "", value))
        aliases.add(re.sub(r"^(?:city|municipality) of\s+", "", value))
        aliases.add(re.sub(r"\s+city$", "", value))
    return {value for value in aliases if len(value)>3}


def _coordinate_district_features(projects):
    """Load only named-locality polygons that can match a printed project point."""
    if not BOUNDARY_FILE.exists():
        return []
    titles=[]
    for project in projects:
        point=_title_point(str(project.get("projectName") or ""))
        if point:
            titles.append((_place_key(project.get("projectName") or ""), point))
    features=[]
    with BOUNDARY_FILE.open(encoding="utf-8") as handle:
        for line in handle:
            feature=json.loads(line); attrs=feature.get("attributes",{})
            district=attrs.get("CONG_DIST")
            aliases=_locality_aliases(attrs)
            aliases={alias for alias in aliases if any((" "+alias+" ") in (" "+title+" ") for title,_ in titles)}
            if not district or not aliases:
                continue
            rings=[]
            for raw_ring in feature.get("geometry",{}).get("rings",[]):
                ring=[_utm51_to_wgs84(float(p[0]),float(p[1])) for p in raw_ring]
                if len(ring)>=4:
                    rings.append(ring)
            if not rings:
                continue
            xs=[p[0] for ring in rings for p in ring]; ys=[p[1] for ring in rings for p in ring]
            features.append({"aliases":aliases,"district":district,"rings":rings,
                             "bounds":(min(xs),min(ys),max(xs),max(ys)),
                             "locality":attrs.get("MUNICIPAL") or attrs.get("MUN_DBM"),
                             "province":attrs.get("PROV_DBM")})
    return features


def _coordinate_district(project, features, seat_indices):
    title=str(project.get("projectName") or "")
    point=_title_point(title)
    if not point:
        return None
    lon,lat,raw=point; title_key=" "+_place_key(title)+" "
    matches=[]
    for feature in features:
        if not any((" "+alias+" ") in title_key for alias in feature["aliases"]):
            continue
        x1,y1,x2,y2=feature["bounds"]
        if not (x1<=lon<=x2 and y1<=lat<=y2):
            continue
        if _inside_rings(lon,lat,feature["rings"]):
            matches.append(feature)
    raw_districts={feature["district"] for feature in matches}
    if len(raw_districts)!=1:
        return None
    raw_district=next(iter(raw_districts))
    parsed=re.fullmatch(r"\s*(.*?)\s*\(\s*([A-Za-z]+)\s+District\s*\)\s*",raw_district,re.I)
    if not parsed:
        return None
    ordinal=ORDINALS.get(parsed.group(2).casefold(),parsed.group(2).casefold())
    # Preserve a separately rostered city seat when the boundary layer names
    # one (for example Quezon City vs Quezon Province). Strip "City" only as
    # a fallback for a jurisdiction that has no city-specific roster seat.
    jurisdiction=parsed.group(1).strip()
    district_label=f"{ordinal} District" if ordinal!="lone" else "Lone District"
    index=seat_indices.get((_place_key(jurisdiction),district_label))
    if index is None:
        jurisdiction=re.sub(r"\s+City$", "", jurisdiction, flags=re.I).strip()
        index=seat_indices.get((_place_key(jurisdiction),district_label))
    if index is None:
        return None
    matching_localities=sorted({str(feature["locality"]) for feature in matches})
    return {"index":index,"district":raw_district,"localities":matching_localities,
            "coordinateRaw":raw,"boundarySource":"DPWH ArcGIS City-Municipal Boundaries"}


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
    seat_indices = {(_place_key(seat["province"]), seat["districtLabel"]): i for i, seat in enumerate(seats)}

    scenario_rows = {}
    for scenario in ("strict",):
        scenario_rows[scenario] = [
            {"district": f'{row["province"]} · {row["districtLabel"]}',
             "representative": row["representative"], "lineItems": 0, "totalPesos": 0}
            for row in seats
        ]
    source = json.loads(HGAB_FILE.read_text())
    projects = source["data"]["data"]
    coordinate_features = _coordinate_district_features(projects)
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
    mixed_signal_project_ids = []
    unresolved_reasons = defaultdict(lambda: {"lineItems": 0, "totalPesos": 0})
    shared_source_amount = 0
    coordinate_assignments = 0
    coordinate_assignment_amount = 0

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
        if any("conflicting DEO and CONG_DIST" in str(reason)
               for reason in decision.get("reasons", [])):
            mixed_signal_project_ids.append(str(project.get("id") or ""))
        if project.get("id") in overrides:
            extra = overrides[project["id"]]
            if extra["projectName"] != title or int(extra["amountPesos"]) != amount:
                raise ValueError("Location supplement does not match the current source record")
            decision["evidence"] += extra.get("evidence", [])
            if extra.get("holdUnresolved"):
                decision["indices"] = []
                decision["reasons"] = sorted(set(decision["reasons"] + extra["reasons"]))
        caloocan = _caloocan_barangay_district(title)
        if caloocan and not overrides.get(project.get("id"), {}).get("holdUnresolved"):
            district_label, barangay_number = caloocan
            index = next((i for i, seat in enumerate(seats)
                          if _place_key(seat["province"]) in {_place_key("Caloocan"), _place_key("Caloocan City")}
                          and seat["districtLabel"] == district_label), None)
            if index is not None:
                decision["indices"] = [index]
                decision["reasons"] = []
                decision["evidence"].append({
                    "level": "explicit numbered Caloocan barangay statutory crosswalk",
                    "barangayNumber": barangay_number,
                    "basis": "Project title names a numbered Caloocan barangay; the current district split is set by RA 11545 and RA 6714.",
                    "sources": [
                        "https://elibrary.judiciary.gov.ph/thebookshelf/showdocs/2/93190",
                        "https://elibrary.judiciary.gov.ph/thebookshelf/showdocs/2/14424",
                    ],
                })
        if not overrides.get(project.get("id"), {}).get("holdUnresolved"):
            manila_barangay = _manila_barangay_district(title)
            manila_zone = _manila_zone_district(title)
            manila_clues = []
            if manila_barangay:
                district_label, barangay_numbers = manila_barangay
                manila_clues.append((district_label, {
                    "level": "explicit numbered Manila barangay statutory crosswalk",
                    "barangayNumbers": barangay_numbers,
                    "basis": "Numbered barangay range follows the six Manila legislative-district ranges in Article VI, Section 2 of the 1987 Constitution.",
                    "sources": ["https://elibrary.judiciary.gov.ph/thebookshelf/showdocs/11/51975"],
                }))
            if manila_zone:
                district_label, zone_numbers = manila_zone
                if district_label == "4th District":
                    zone_basis = "The title's fully stated Zones 41–57 span is District IV under the documented zone crosswalk; City Council resolutions independently identify sample zones within the span as District IV."
                    zone_sources = [
                        "https://doi.nrct.go.th/ListDoi/Download/583273?Resolve_DOI=10.14456%2Frjsh.2021.7",
                        "https://citycouncilofmanila.com.ph/city_resolutions/page/21/",
                        "https://citycouncilofmanila.com.ph/city_resolutions/page/23/",
                    ]
                else:
                    zone_basis = "The title names both Zones 92 and 93; official City Council records identify both zones in District VI."
                    zone_sources = [
                        "https://citycouncilofmanila.com.ph/council_number/13th-city-council/page/7/",
                        "https://citycouncilofmanila.com.ph/city_resolutions/page/26/",
                    ]
                manila_clues.append((district_label, {
                    "level": "explicit Manila administrative-zone crosswalk",
                    "zoneNumbers": zone_numbers,
                    "basis": zone_basis,
                    "sources": zone_sources,
                }))
            if manila_clues:
                manila_districts = {label for label, _ in manila_clues}
                index = next((i for i, seat in enumerate(seats)
                              if _place_key(seat["province"]) in {_place_key("Manila"), _place_key("Manila City")}
                              and seat["districtLabel"] in manila_districts), None)
                if len(manila_districts) > 1 or (decision["indices"] and
                                                  (index is None or decision["indices"] != [index])):
                    decision["indices"] = []
                    decision["reasons"] = sorted(set(decision["reasons"] + [
                        "Manila district evidence conflicts; left unassigned pending review"
                    ]))
                elif index is not None:
                    decision["indices"] = [index]
                    decision["reasons"] = []
                decision["evidence"].extend(evidence for _, evidence in manila_clues)
        coordinate_evidence = None
        held_unresolved = bool(overrides.get(project.get("id"), {}).get("holdUnresolved"))
        if not decision["indices"] and not held_unresolved:
            coordinate_evidence = _coordinate_district(project, coordinate_features, seat_indices)
            if coordinate_evidence:
                decision["indices"] = [coordinate_evidence["index"]]
                decision["reasons"] = []
                decision["evidence"].append({
                    "level": "printed-coordinate boundary match",
                    "localities": coordinate_evidence["localities"],
                    "district": coordinate_evidence["district"],
                    "coordinate": coordinate_evidence["coordinateRaw"],
                    "boundarySource": coordinate_evidence["boundarySource"],
                    "basis": "Unique district polygon containing the printed point; a matching locality name appears in the project title",
                })
                coordinate_assignments += 1
                coordinate_assignment_amount += amount
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

    unassigned_by_region = defaultdict(lambda: {"lineItems": 0, "totalPesos": 0})
    for row in audit_rows:
        if row["status"] != "unresolved":
            continue
        region = str(row.get("region") or "").strip()
        group = ("Metro Manila (NCR)" if region in {"National Capital Region", "NCR"}
                 else region or "Region not specified")
        unassigned_by_region[group]["lineItems"] += 1
        unassigned_by_region[group]["totalPesos"] += row["amountPesos"]
    unassigned_by_region = [
        {"group": group, **values}
        for group, values in sorted(unassigned_by_region.items(),
                                    key=lambda item: (-item[1]["totalPesos"], item[0]))
    ]
    if (sum(row["lineItems"] for row in unassigned_by_region) != unassigned
            or sum(row["totalPesos"] for row in unassigned_by_region) != unassigned_amount):
        raise ValueError("Unassigned region rollup does not reconcile with the source totals")

    output = {
        "source": "FY2027 DPWH HGAB 3rd Reading local extraction",
        "roster": "20th Congress roster in ODV static/data/20th_congress_representatives.json",
        "extractionMethod": source.get("metadata", {}).get("extractionMethod", "local schedule extraction"),
        "sourceWarning": source.get("metadata", {}).get("warning", "Candidate extraction; check cited bill pages."),
        "unit": "pesos",
        "attributionMethod": VERSION + "+city-jurisdiction-preserved-v1+caloocan-numbered-barangay-crosswalk-v1+manila-constitutional-barangay-and-zone-crosswalk-v1",
        "inventoryLocationEvidenceStatus": geography.inventory_context_status,
        "attributionWarning": "Conservative location-based coverage, not complete district budgets or evidence of a representative's sponsorship. Exact municipality + province fields normally require agreement between both local district maps; exact localities listed in the sourced current-law / Senate district crosswalk may resolve map conflicts, and a province with one current rostered legislative district maps to that sole seat. Multi-seat cities require explicit location evidence: numbered Manila barangays use statutory ranges, Manila zones and named administrative localities use cited crosswalks that identify one district, and numbered Caloocan barangays use current statutory crosswalks. Shared lines, conflicts and missing scope stay outside the ranking. For otherwise unresolved projects, a printed coordinate can support a district assignment only when the title names a locality, the point falls inside its matching DPWH boundary feature, and that feature identifies exactly one current roster seat. An exact bridge ID may use the ArcGIS record's CONG_DIST only when its paired DEO district does not conflict; mixed DEO/CONG_DIST records remain irreconcilable and unresolved. Coordinates and boundary classifications are not independently verified project locations. A zero means no accepted attribution, not no allocation.",
        "unresolvedReasons": [{"reason": k, **v} for k, v in sorted(unresolved_reasons.items(), key=lambda kv: -kv[1]["totalPesos"])],
        "unassignedByRegion": unassigned_by_region,
        "mixedSignalProjectIds": mixed_signal_project_ids,
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
            "printedCoordinateBoundaryAssignments": coordinate_assignments,
            "printedCoordinateBoundaryAssignmentPesos": coordinate_assignment_amount,
            "strictCoverageBeforePrintedCoordinatePct": round(100 * (analyzed_total - unassigned_amount - shared_source_amount - coordinate_assignment_amount) / analyzed_total, 2) if analyzed_total else 0,
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
    if coordinate_assignments:
        output["attributionMethod"] += "+printed-coordinate-locality-boundary-v1"
    if geography.inventory_context_status == 'matching_dependencies':
        output['attributionWarning'] += ' Additional qualified context comes from exact inventory assets checked wholly inside one municipality, then screened through current local maps. For exact bridge IDs, the ArcGIS CONG_DIST may support assignment when title geography is unresolved only if its paired DEO district agrees; conflicting pairs remain irreconcilable and unresolved. Inventory positions and source-listed districts are not proof of funded quantities or project sponsorship; borderline and conflicting locations remain unresolved.'
    print(json.dumps(output["summary"], indent=2))
    if args.write:
        OUT_FILE.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n")
        print(f"Wrote {OUT_FILE}")
    if args.audit:
        sources = [HGAB_FILE, REVIEW_FILE, reps.ROSTER_PATH, ROOT / "static/data/districts.json",
                   ROOT / "static/data/districts_generated.json", ROOT / "city_barangays_mapping.json",
                   ROOT / "static/data/administrative_locality_crosswalk.json",
                   BOUNDARY_FILE, Path(__file__), ROOT / "analysis/strict_congress_geography.py"]
        if args.geographic_decisions:
            sources.append(args.geographic_decisions)
        if (ROOT / 'static/data/inventory_location_contexts.json').exists():
            sources.append(ROOT / 'static/data/inventory_location_contexts.json')
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
