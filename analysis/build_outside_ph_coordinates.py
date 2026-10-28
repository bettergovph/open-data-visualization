#!/usr/bin/env python3
"""Extract HGAB 3rd-reading project coordinates outside the Philippines envelope."""

from __future__ import annotations

import hashlib
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEP_ROOT = ROOT.parent / "nep"
HGAB_SOURCE = NEP_ROOT / "hb10858_3rd_dpwh_projects.json"
NEP_SOURCE = NEP_ROOT / "analysis_output" / "nep_dpwh_baseline.json"
FMR_SOURCES = {
    "NEP FMR": NEP_ROOT / "data_sources" / "fmr_analyst" / "nep_fmr_projects_normalized.csv",
    "HGAB FMR": NEP_ROOT / "data_sources" / "fmr_analyst" / "hgab_fmr_projects_normalized.csv",
}
OUTPUT = ROOT / "static" / "nep-preview" / "outside-ph-data.json"

# A deliberately broad geographic screening envelope. It is not a maritime
# boundary or a claim about the Philippines' sovereign limits.
LAT_MIN, LAT_MAX = 4.4, 21.5
LON_MIN, LON_MAX = 116.0, 127.5
PAIR = re.compile(
    r"(?<![\d.])([+-]?\d{1,3}\.\d+)\s*°?\s*[,;/]\s*"
    r"([+-]?\d{1,3}\.\d+)(?![\d.])"
)


def inside_envelope(lat: float, lon: float) -> bool:
    return LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX


def point_detail(raw: str, first: float, second: float) -> dict:
    if inside_envelope(first, second):
        latitude, longitude = first, second
        issue = None
    elif inside_envelope(second, first):
        latitude, longitude = second, first
        issue = None
    else:
        # Project titles use latitude, longitude ordering in this source.
        latitude, longitude = first, second
        reasons = []
        if not LAT_MIN <= latitude <= LAT_MAX:
            reasons.append(f"latitude {latitude:g} is outside {LAT_MIN:g}°–{LAT_MAX:g}° N")
        if not LON_MIN <= longitude <= LON_MAX:
            reasons.append(f"longitude {longitude:g} is outside {LON_MIN:g}°–{LON_MAX:g}° E")
        issue = "; ".join(reasons)
    return {
        "raw": raw,
        "latitude": latitude,
        "longitude": longitude,
        "issue": issue,
        "mapUrl": f"https://www.openstreetmap.org/?mlat={latitude:.8f}&mlon={longitude:.8f}#map=7/{latitude:.8f}/{longitude:.8f}",
    }


def title_projects(rows: list[dict], stage: str, coordinate_fields: tuple[str, ...]) -> tuple[list[dict], dict]:
    projects = []
    pair_count = 0
    bridge_title_count = 0
    outside_coordinate_count = 0
    for row in rows:
        title = str(row.get("projectName") or row.get("officialNepTitle") or "")
        if "bridge" in title.casefold():
            bridge_title_count += 1
        raw_pairs = {}
        for field in coordinate_fields:
            for match in PAIR.finditer(str(row.get(field) or "")):
                raw_pairs.setdefault(match.group(0), tuple(map(float, match.groups())))
        pair_count += len(raw_pairs)
        points = []
        for raw, (first, second) in raw_pairs.items():
            if inside_envelope(first, second) or inside_envelope(second, first):
                continue
            points.append(point_detail(raw, first, second))
        if not points:
            continue
        outside_coordinate_count += len(points)
        projects.append({
            "stage": stage,
            "id": row.get("id") or row.get("code"),
            "projectName": title,
            "office": row.get("office"),
            "region": row.get("region"),
            "amountPesos": int(row.get("amountPesos") or 0),
            "sourceVolume": row.get("sourceVolume") or ("NEP DPWH project baseline" if stage == "NEP" else None),
            "sourcePage": row.get("sourcePage"),
            "apiId": row.get("apiId") if stage == "NEP" else None,
            "points": points,
        })
    return projects, {
        "stage": stage,
        "rowsScanned": len(rows),
        "coordinatePairsScanned": pair_count,
        "projectRecordsOutsideEnvelope": len(projects),
        "coordinateStringsOutsideEnvelope": outside_coordinate_count,
        "bridgeTitleRowsScanned": bridge_title_count,
    }


def coordinate_arrays(value):
    if isinstance(value, list):
        if len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
            yield float(value[0]), float(value[1])
        else:
            for item in value:
                yield from coordinate_arrays(item)


def fmr_projects(path: Path, stage: str) -> tuple[list[dict], dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    projects = []
    points_scanned = 0
    outside_count = 0
    for row in rows:
        try:
            coords = json.loads(row.get("coordinates_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            coords = []
        points = []
        for longitude, latitude in coordinate_arrays(coords):
            points_scanned += 1
            if inside_envelope(latitude, longitude):
                continue
            raw = f"{latitude:g}, {longitude:g}"
            points.append(point_detail(raw, latitude, longitude))
        if not points:
            continue
        outside_count += len(points)
        projects.append({
            "stage": stage,
            "id": row.get("project_id"),
            "projectName": row.get("title"),
            "office": None,
            "region": row.get("region"),
            "amountPesos": int(float(str(row.get("amount_php") or 0).replace(",", ""))),
            "sourceVolume": row.get("source_pdf"),
            "sourcePage": row.get("printed_page") or row.get("pdf_page"),
            "points": points,
        })
    return projects, {
        "stage": stage,
        "rowsScanned": len(rows),
        "coordinatePointsScanned": points_scanned,
        "projectRecordsOutsideEnvelope": len(projects),
        "coordinatePointsOutsideEnvelope": outside_count,
    }


def main() -> None:
    hgab_bytes = HGAB_SOURCE.read_bytes()
    source = json.loads(hgab_bytes)
    metadata = source.get("metadata", {})
    files = metadata.get("sourceFiles", [])
    if "10858" not in str(metadata.get("source", "")) or not any(
        "3RD READING" in str(item.get("file", "")).upper() for item in files
    ):
        raise ValueError("Expected the HB 10858 HGAB source dataset")
    nep_bytes = NEP_SOURCE.read_bytes()
    nep = json.loads(nep_bytes)
    hgab_projects, hgab_scan = title_projects(source["data"]["data"], "HGAB 3rd", ("projectName", "sourceText"))
    nep_projects, nep_scan = title_projects(nep["data"]["data"], "NEP", ("projectName", "officialNepTitle"))
    projects = hgab_projects + nep_projects
    fmr_scans = []
    fmr_hashes = {}
    for stage, path in FMR_SOURCES.items():
        fmr_projects_found, scan = fmr_projects(path, stage)
        projects.extend(fmr_projects_found)
        fmr_scans.append(scan)
        fmr_hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    projects.sort(key=lambda p: (0 if p["stage"] == "HGAB 3rd" else 1 if p["stage"] == "NEP" else 2, int(p.get("sourcePage") or 0), str(p.get("id") or "")))
    result = {
        "title": "NEP and HGAB 3rd project coordinates outside the Philippines envelope",
        "source": "FY2027 DPWH project records from NEP and House Bill No. 10858, HGAB 3rd reading",
        "sources": [
            {"stage": "HGAB 3rd", "file": HGAB_SOURCE.name, "sha256": hashlib.sha256(hgab_bytes).hexdigest()},
            {"stage": "NEP", "file": NEP_SOURCE.name, "sha256": hashlib.sha256(nep_bytes).hexdigest()},
            {"stage": "NEP FMR / HGAB FMR", "files": fmr_hashes},
        ],
        "sourceScans": [hgab_scan, nep_scan],
        "fmrScans": fmr_scans,
        "screeningEnvelope": {
            "latitudeNorth": [LAT_MIN, LAT_MAX],
            "longitudeEast": [LON_MIN, LON_MAX],
            "note": "Broad coordinate sanity envelope only; not an exact national or maritime boundary.",
        },
        "projectCount": len(projects),
        "coordinateCount": sum(len(p["points"]) for p in projects),
        "projects": projects,
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps({"projectCount": result["projectCount"], "coordinateCount": result["coordinateCount"], "sourceScans": result["sourceScans"], "fmrScans": result["fmrScans"], "output": str(OUTPUT)}, indent=2))


if __name__ == "__main__":
    main()
