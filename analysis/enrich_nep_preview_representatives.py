#!/usr/bin/env python3
"""Second-pass, workspace-only representative enrichment for NEP preview data.

Fills empty congressional_representatives arrays when a project title names a
locality that maps to a current 20th Congress seat in the local ODV datasets.
Ambiguous or overly broad matches are left blank. Existing assignments are
preserved. Run with --write to update the JSON files; default is a dry run.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "static" / "nep-preview"
ROSTER_PATH = ROOT / "static" / "data" / "20th_congress_representatives.json"
DISTRICTS_PATH = ROOT / "static" / "data" / "districts.json"


def norm(value: Any) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(c for c in value if not unicodedata.combining(c)).lower()
    value = value.replace("&", " and ")
    value = re.sub(r"\b(city of)\s+", "", value)
    value = re.sub(r"\b(of)\s+", "", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def district_key(value: Any) -> str:
    text = norm(value)
    m = re.search(r"\b(1st|2nd|3rd|[4-9]th|lone|solon|single)\b", text)
    return "lone" if m and m.group(1) in {"lone", "solon", "single"} else (m.group(1) if m else text)


def load_roster() -> tuple[dict[str, dict[str, str]], dict[str, list[str]]]:
    records = json.loads(ROSTER_PATH.read_text())
    known_provinces = {norm(name) for name in json.loads(DISTRICTS_PATH.read_text()).get("districts", {})}
    by_province: dict[str, dict[str, str]] = defaultdict(dict)
    for row in records:
        province = norm(row["province"])
        representative = str(row.get("representative") or "").strip()
        # The roster file includes a non-seat footnote row (“District / Special
        # election”). Keep only actual jurisdiction keys and person names.
        if province not in known_provinces or not representative or norm(representative) == "special election":
            continue
        by_province[province][district_key(row["district"])] = representative
    aliases = {province: reps for province, reps in by_province.items()}
    return by_province, aliases


def make_locality_index(roster: dict[str, dict[str, str]]) -> tuple[dict[str, list[tuple[str, list[str]]]], list[str]]:
    source = json.loads(DISTRICTS_PATH.read_text()).get("districts", {})
    places: dict[str, set[tuple[str, str]]] = defaultdict(set)

    for province_name, detail in source.items():
        province = norm(province_name)
        if province not in roster:
            continue
        for locality, district in detail.get("municipalities", {}).items():
            key = norm(locality)
            seat = district_key(district)
            if key and seat in roster[province]:
                places[key].add((province, seat))
        for district, barangays in detail.get("barangays", {}).items():
            seat = district_key(district)
            if seat not in roster[province] or not isinstance(barangays, list):
                continue
            for barangay in barangays:
                key = norm(barangay)
                if key:
                    places[key].add((province, seat))

    # Remove tiny tokens; they are too collision-prone without user review.
    index: dict[str, list[tuple[str, list[str]]]] = {}
    for place, seats in places.items():
        grouped: dict[str, set[str]] = defaultdict(set)
        for province, seat in seats:
            grouped[province].add(seat)
        index[place] = [(province, sorted(seat_keys)) for province, seat_keys in grouped.items()]
    provinces = sorted(roster, key=len, reverse=True)
    return index, provinces


def contains_phrase(haystack: str, phrase: str) -> bool:
    if not phrase:
        return False
    start = 0
    while (start := haystack.find(phrase, start)) >= 0:
        end = start + len(phrase)
        left_ok = start == 0 or not haystack[start - 1].isalnum()
        right_ok = end == len(haystack) or not haystack[end].isalnum()
        if left_ok and right_ok:
            return True
        start += 1
    return False


def infer_representatives(title: str, roster: dict[str, dict[str, str]],
                          locality_index: dict[str, list[tuple[str, list[str]]]],
                          province_names: list[str],
                          places_by_first_word: dict[str, list[str]]) -> list[str]:
    text = norm(title)
    if not text:
        return []
    named_provinces = {p for p in province_names if contains_phrase(text, p)}
    # A shorter province token embedded in a city/province alias is not a
    # second location (for example, "Quezon" inside "Quezon City").
    named_provinces = {p for p in named_provinces
                       if not any(p != longer and p in longer and contains_phrase(text, longer)
                                  for longer in named_provinces)}
    # "Metro Manila" is a region label, not an attribution to the City of Manila.
    if "manila" in named_provinces and contains_phrase(text, "metro manila") \
            and not contains_phrase(text, "manila city") and not contains_phrase(text, "city of manila"):
        named_provinces.remove("manila")
    # Extraction sometimes concatenates unrelated schedule locations. If the
    # title names several distinct provinces/cities, do not guess which applies.
    if len(named_provinces) > 1:
        return []
    matches: list[tuple[int, str, list[str]]] = []
    candidate_places = {place for word in set(text.split())
                        for place in places_by_first_word.get(word, ())}
    for place in candidate_places:
        provinces = locality_index[place]
        # Skip short labels unless the project title also identifies its province.
        if len(place) < 5 or not contains_phrase(text, place):
            continue
        candidates = [(province, seats) for province, seats in provinces
                      if not named_provinces or province in named_provinces]
        if len(candidates) != 1:
            continue
        province, seats = candidates[0]
        names = [roster[province][seat] for seat in seats if seat in roster[province]]
        if names:
            matches.append((len(place), province, names))

    if matches:
        # Keep the most specific matching locality names. If the title explicitly
        # covers several equally specific places, include their affected members.
        longest = max(m[0] for m in matches)
        selected = [m for m in matches if m[0] == longest]
        if not named_provinces and len({province for _, province, _ in selected}) > 1:
            return []
        names = list(dict.fromkeys(name for _, _, group in selected for name in group))
        return names if len(names) <= 4 else []

    # Province-only attribution is safe only for a single-seat province.
    single_seat = [p for p in named_provinces if len(roster.get(p, {})) == 1]
    if len(single_seat) == 1:
        return [next(iter(roster[single_seat[0]].values()))]
    return []


def traverse_candidates(document: Any, path: str = ""):
    """Yield mutable row dictionaries in NEP preview page data."""
    if isinstance(document, list):
        for row in document:
            if isinstance(row, dict) and "congressional_representatives" in row:
                yield path, row
            else:
                yield from traverse_candidates(row, path)
    elif isinstance(document, dict):
        for key, value in document.items():
            yield from traverse_candidates(value, f"{path}/{key}")


def title_for(path: str, row: dict[str, Any]) -> str:
    # HGAB 2nd/3rd comparison rows have nested project objects.
    if "/rows" in path and (row.get("third") or row.get("second")):
        project = row.get("third") or row.get("second") or {}
        return str(project.get("projectName") or "")
    if "/priorityRepeats" in path:
        return str(row.get("project") or "")
    if "/hbInsertions" in path or "/rows" in path or "/projects" in path or "/repeatCandidates" in path:
        return str(row.get("name") or row.get("projectName") or row.get("project") or "")
    if "/districtPrograms" in path or "/districts" in path:
        return str(row.get("largest_project_name") or "")
    if "/waterWatchlist" in path:
        return str(row.get("project_name") or "")
    if "/nonRoadBridgeTop" in path:
        return str(row.get("project_name") or "")
    if "/fiveMillionRows" in path:
        return str(row.get("project_name") or "")
    return str(row.get("projectName") or row.get("project_name") or row.get("name") or "")


FILES = [
    "dpwh-data.json",
    "dpwh-hgab-comparison.json",
    "hgab-revision-data.json",
    "nia-irrigation-data.json",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write enriched arrays to local JSON files")
    args = parser.parse_args()
    roster, _ = load_roster()
    locality_index, province_names = make_locality_index(roster)
    places_by_first_word: dict[str, list[str]] = defaultdict(list)
    for place in locality_index:
        places_by_first_word[place.split()[0]].append(place)
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])

    for filename in FILES:
        path = DATA / filename
        document = json.loads(path.read_text())
        changed = False
        for row_path, row in traverse_candidates(document):
            key = filename + row_path.split("/")[1] if "/" in row_path else filename
            current = row.get("congressional_representatives") or []
            totals[key][0] += 1
            if current:
                continue
            names = infer_representatives(title_for(row_path, row), roster, locality_index,
                                          province_names, places_by_first_word)
            if names:
                totals[key][1] += 1
                if args.write:
                    row["congressional_representatives"] = names
                    changed = True
        if args.write and changed:
            path.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n")

    mode = "wrote" if args.write else "would add"
    print(f"Second-pass representative matches ({mode}):")
    for label, (reviewed, added) in sorted(totals.items()):
        print(f"  {label}: {added} added from {reviewed} candidate rows")


if __name__ == "__main__":
    main()
