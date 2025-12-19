
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import duckdb

_ROAD_MARKERS = (
    "ROAD",
    "RD",
    "RD.",
    "AVENUE",
    "AVE",
    "AVE.",
    "STREET",
    "ST",
    "ST.",
    "DRIVE",
    "DR",
    "DR.",
    "BLVD",
    "BLVD.",
    "BOULEVARD",
    "HIGHWAY",
    "HWY",
    "HWY.",
    "DIVERSION",
    "BYPASS",
    "EXPRESSWAY",
)


def _squash_ws(value: str) -> str:
    return " ".join((value or "").split()).strip()


def _fold_text(value: str) -> str:
    """Accent-insensitive folding for matching (e.g., PARAÑAQUE -> PARANAQUE)."""
    text = _squash_ws(str(value or ""))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text


def _normalize_province(value: str) -> str:
    v = _fold_text(value).upper()
    v = re.sub(r"\s*\([^)]*\)", "", v)
    return _squash_ws(v)


def _normalize_municipality(value: str) -> str:
    v = _fold_text(value).upper()
    v = v.replace("MUNICIPALITY OF ", "")
    v = v.replace("CITY OF ", "")
    v = v.replace(" CITY", "")
    v = re.sub(r"\s*\([^)]*\)", "", v)
    return _squash_ws(v)


def _normalize_barangay(value: str) -> str:
    v = _fold_text(value).upper()
    v = v.replace("BARANGAY ", "")
    v = v.replace("BRGY. ", "")
    v = v.replace("BRGY ", "")
    v = re.sub(r"\s*\([^)]*\)", "", v)
    return _squash_ws(v)


def _find_whole_phrase(text: str, phrase: str) -> int:
    if not text or not phrase:
        return -1

    start = 0
    phrase_len = len(phrase)
    while True:
        idx = text.find(phrase, start)
        if idx == -1:
            return -1

        before = text[idx - 1] if idx > 0 else " "
        after = text[idx + phrase_len] if (idx + phrase_len) < len(text) else " "

        if not before.isalnum() and not after.isalnum():
            return idx

        start = idx + 1


def _is_road_context(text: str, start_idx: int, end_idx: int) -> bool:
    """True if a match only appears as part of a road name.

    Examples:
    - 'MANILA NORTH ROAD' should treat 'MANILA' as road-context.
    - '... RD. LAOAG ...' should treat 'LAOAG' as road-context.
    """

    if not text:
        return False

    before = text[max(0, start_idx - 40) : start_idx]
    after = text[end_idx : end_idx + 40]

    before_clean = re.sub(r"[^A-Z0-9\s\.]", " ", before.upper())
    after_clean = re.sub(r"[^A-Z0-9\s\.]", " ", after.upper())

    # Road marker immediately before the match: "... ROAD <PLACE>"
    for marker in _ROAD_MARKERS:
        if re.search(rf"\b{re.escape(marker)}\b\s*$", before_clean.strip()):
            return True

    # Road marker shortly after the match: "<PLACE> ... ROAD"
    for marker in _ROAD_MARKERS:
        if re.search(rf"\b{re.escape(marker)}\b", after_clean):
            # Only treat as road context if marker appears very soon after (<= 3 tokens)
            tokens = after_clean.strip().split()
            for i, tok in enumerate(tokens[:4]):
                if tok == marker:
                    return True

    return False


class LocationEnricher:
    def __init__(self, db_path="static/data/unified_locations.parquet"):
        self.db_path = Path(db_path)
        self.loaded = False

        # Province -> municipality_norm -> list[info] (may include multiple districts due to barangays)
        self.prov_mun_infos = defaultdict(lambda: defaultdict(list))

        # Province -> municipality_norm -> barangay_norm -> info
        self.prov_mun_brgy = defaultdict(lambda: defaultdict(dict))

        # Municipality_norm -> set(province_norm)
        self.mun_provinces = defaultdict(set)

        # Municipality_norm -> representative info (only used for unique municipalities)
        self.unique_municipality = {}

        # Municipality_norm -> representative info (safe municipality-only matches)
        # Only populated for municipalities/cities that:
        # - exist in exactly 1 province, and
        # - map to exactly 1 (district, congressman) across all their barangays
        self.safe_single_municipality = {}

    def load_db(self):
        """Load unified location database for enrichment"""
        print(f"Loading Unified Location Database from {self.db_path}...")
        if not self.db_path.exists():
            print(f"⚠️  Unified Location DB not found at {self.db_path}. Skipping enrichment.")
            return False

        con = duckdb.connect(database=":memory:")
        con.execute(f"CREATE OR REPLACE TABLE unified_locations AS SELECT * FROM read_parquet('{self.db_path}')")

        rows = con.execute(
            "SELECT province, municipality, barangay, district, congressman FROM unified_locations"
        ).fetchall()
        con.close()

        mun_first_info = {}
        mun_districts = defaultdict(set)  # mun_norm -> set((prov_norm, district, congressman))
        for province, municipality, barangay, district, congressman in rows:
            prov_norm = _normalize_province(province)
            mun_norm = _normalize_municipality(municipality)
            brgy_norm = _normalize_barangay(barangay)
            if not prov_norm or not mun_norm:
                continue

            info = {
                "province": _normalize_province(province),
                "municipality": _squash_ws(str(municipality or "")).upper().strip(),
                "district": district,
                "congressman": congressman,
            }

            self.prov_mun_infos[prov_norm][mun_norm].append(info)
            if brgy_norm:
                self.prov_mun_brgy[prov_norm][mun_norm][brgy_norm] = info

            self.mun_provinces[mun_norm].add(prov_norm)
            mun_first_info.setdefault(mun_norm, info)
            mun_districts[mun_norm].add((prov_norm, str(district or "").strip(), str(congressman or "").strip()))

        # Unique municipality entries are only safe if the municipality exists in exactly one province.
        self.unique_municipality = {
            mun_norm: mun_first_info[mun_norm]
            for mun_norm, provinces in self.mun_provinces.items()
            if len(provinces) == 1
        }

        # Municipality-only exception:
        # Allow municipality-only district assignment ONLY when it's effectively a "lone district"
        # municipality/city (i.e., no district ambiguity for that municipality) and it's unique
        # across the country (one province only). This avoids edge cases like "SAN", "SANTA", etc.
        blocked = {
            "SAN",
            "SANTA",
            "SANTO",
            "BAGUMBAYAN",
            "MANILA",
            "QUEZON",
            "LEYTE",
            "SAMAR",
        }
        self.safe_single_municipality = {}
        for mun_norm, provinces in self.mun_provinces.items():
            if len(provinces) != 1:
                continue
            if len(mun_norm) < 6:
                continue
            if mun_norm in blocked:
                continue
            distinct = {(d, c) for (_p, d, c) in mun_districts.get(mun_norm) or set()}
            if len(distinct) != 1:
                continue
            info = mun_first_info.get(mun_norm)
            if info:
                self.safe_single_municipality[mun_norm] = info

        print(f"✅ Location DB loaded. Indexed {len(rows)} rows.")
        print(f"✅ Found {len(self.unique_municipality)} unique municipalities/cities.")
        self.loaded = True
        return True

    def _apply_info(self, project, info):
        project["province"] = info.get("province")
        project["municipality"] = info.get("municipality")
        project["district"] = info.get("district") or "Unknown"
        project["congressman"] = info.get("congressman") or "Unknown"
        return project

    def enrich_project(self, project):
        """Enrich a single project with District/Congressman info.

        General rule for resolving competing hints:
        barangay > municipality > province > region.

        Road-name rule:
        Do not treat a token as a location match if it only appears inside a road name
        (e.g. 'MANILA NORTH ROAD', 'RD. LAOAG') unless confirmed by other hierarchy elements.
        """

        if not self.loaded:
            return project

        # Strategy 0 (highest confidence): use structured location dict if present.
        loc = project.get("location")
        if isinstance(loc, dict):
            prov_norm = _normalize_province(loc.get("province"))
            mun_norm = _normalize_municipality(loc.get("municipality"))
            brgy_norm = _normalize_barangay(loc.get("barangay"))
            region_norm = _normalize_province(loc.get("region"))

            # General rule: require at least 2 levels in the hierarchy to assign a district.
            # Accepted examples:
            # - province + municipality
            # - municipality + barangay (even if province is missing, but resolvable uniquely)
            if mun_norm and brgy_norm and not prov_norm:
                # Resolve (municipality, barangay) across provinces; accept only if exactly one match exists.
                matches = []
                for candidate_prov in self.mun_provinces.get(mun_norm) or []:
                    info = (
                        self.prov_mun_brgy.get(candidate_prov, {})
                        .get(mun_norm, {})
                        .get(brgy_norm)
                    )
                    if info:
                        matches.append(info)
                if len(matches) == 1:
                    return self._apply_info(project, matches[0])

            # Exception: municipality-only is allowed if it uniquely maps to a single district (lone district)
            # and exists in only one province across the country.
            if mun_norm and not prov_norm and not brgy_norm:
                info = self.safe_single_municipality.get(mun_norm)
                if info:
                    return self._apply_info(project, info)

            if prov_norm and mun_norm and brgy_norm:
                info = self.prov_mun_brgy.get(prov_norm, {}).get(mun_norm, {}).get(brgy_norm)
                if info:
                    return self._apply_info(project, info)

            if prov_norm and mun_norm:
                infos = self.prov_mun_infos.get(prov_norm, {}).get(mun_norm) or []
                if len({(i.get("district"), i.get("congressman")) for i in infos}) == 1 and infos:
                    return self._apply_info(project, infos[0])

        # Fallback: scan text (name/description + serialized dicts).
        parts = [
            str(project.get("name", "") or ""),
            str(project.get("description", "") or ""),
        ]
        if isinstance(project.get("location"), dict):
            parts.append(json.dumps(project.get("location") or {}, ensure_ascii=False))
        else:
            parts.append(str(project.get("location", "") or ""))
        if isinstance(project.get("hierarchy"), dict):
            parts.append(json.dumps(project.get("hierarchy") or {}, ensure_ascii=False))
        else:
            parts.append(str(project.get("hierarchy", "") or ""))

        text = _fold_text(" ".join(parts)).upper()
        text_norm = text.replace("CITY OF ", "").replace(" CITY", "")

        # 1) Find all provinces mentioned.
        found_provinces = set()
        for prov_norm in self.prov_mun_infos.keys():
            if _find_whole_phrase(text_norm, prov_norm) != -1:
                found_provinces.add(prov_norm)

        # 2) Candidate search: province + municipality, then barangay refinement.
        best = None
        best_score = -1

        for prov_norm in found_provinces:
            muni_map = self.prov_mun_infos.get(prov_norm, {})
            for mun_norm, infos in muni_map.items():
                if len(mun_norm) < 4:
                    continue

                mun_idx = _find_whole_phrase(text_norm, mun_norm)
                if mun_idx == -1:
                    continue

                mun_is_road = _is_road_context(text_norm, mun_idx, mun_idx + len(mun_norm))
                if mun_is_road:
                    # Municipality mentioned only as part of a road name; require another indicator.
                    # We'll still allow it if we can find a barangay under this municipality.
                    pass

                # Try barangay match (preferred).
                brgy_map = self.prov_mun_brgy.get(prov_norm, {}).get(mun_norm, {}) or {}
                best_brgy_info = None
                for brgy_norm, brgy_info in brgy_map.items():
                    if len(brgy_norm) < 4:
                        continue
                    brgy_idx = _find_whole_phrase(text_norm, brgy_norm)
                    if brgy_idx == -1:
                        continue
                    if _is_road_context(text_norm, brgy_idx, brgy_idx + len(brgy_norm)):
                        continue
                    best_brgy_info = brgy_info
                    break

                if best_brgy_info:
                    score = 100  # barangay match wins
                    if score > best_score:
                        best = best_brgy_info
                        best_score = score
                    continue

                # If municipality is road-context and we didn't find a barangay, skip it.
                if mun_is_road:
                    continue

                # If this municipality has a single district across all barangays, it's safe.
                distinct = {(i.get("district"), i.get("congressman")) for i in infos}
                if len(distinct) == 1 and infos:
                    score = 50  # municipality match
                    if score > best_score:
                        best = infos[0]
                        best_score = score

        if best:
            return self._apply_info(project, best)

        # 3) Municipality-only exception from free text (only if it's a safe lone-district municipality).
        for mun_norm, info in self.safe_single_municipality.items():
            mun_idx = _find_whole_phrase(text_norm, mun_norm)
            if mun_idx == -1:
                continue
            if _is_road_context(text_norm, mun_idx, mun_idx + len(mun_norm)):
                continue
            if found_provinces and _normalize_province(info.get("province")) not in found_provinces:
                continue
            return self._apply_info(project, info)

        return project

    def enrich_list(self, projects):
        """Enrich a list of projects in-place"""
        if not self.loaded: 
            if not self.load_db():
                return projects
        
        enriched_count = 0
        for p in projects:
            old_cong = p.get('congressman')
            self.enrich_project(p)
            if p.get('congressman') and p.get('congressman') != 'Unknown' and p.get('congressman') != old_cong:
                enriched_count += 1
                
        print(f"Enriched {enriched_count} projects with location info.")
        return projects
