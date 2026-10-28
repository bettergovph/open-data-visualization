#!/usr/bin/env python3
"""Extract HGAB 3rd-reading project coordinates outside the Philippines envelope."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "nep" / "hb10858_3rd_dpwh_projects.json"
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


def main() -> None:
    source_bytes = SOURCE.read_bytes()
    source = json.loads(source_bytes)
    metadata = source.get("metadata", {})
    files = metadata.get("sourceFiles", [])
    if "10858" not in str(metadata.get("source", "")) or not any(
        "3RD READING" in str(item.get("file", "")).upper() for item in files
    ):
        raise ValueError("Expected the HB 10858 HGAB source dataset")

    projects = []
    for row in source["data"]["data"]:
        title = str(row.get("projectName") or "")
        points = []
        for match in PAIR.finditer(title):
            first, second = map(float, match.groups())
            if inside_envelope(first, second) or inside_envelope(second, first):
                continue
            points.append(point_detail(match.group(0), first, second))
        if not points:
            continue
        projects.append({
            "id": row.get("id"),
            "projectName": title,
            "office": row.get("office"),
            "region": row.get("region"),
            "amountPesos": int(row.get("amountPesos") or 0),
            "sourceVolume": row.get("sourceVolume"),
            "sourcePage": row.get("sourcePage"),
            "points": points,
        })

    projects.sort(key=lambda p: (int(p.get("sourcePage") or 0), str(p.get("id") or "")))
    result = {
        "title": "HGAB 3rd-reading project coordinates outside the Philippines envelope",
        "source": "House Bill No. 10858, FY2027, 3rd-reading DPWH project schedule",
        "sourceFile": SOURCE.name,
        "sourceSha256": hashlib.sha256(source_bytes).hexdigest(),
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
    print(json.dumps({"projectCount": result["projectCount"], "coordinateCount": result["coordinateCount"], "output": str(OUTPUT)}, indent=2))


if __name__ == "__main__":
    main()
