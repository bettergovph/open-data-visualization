"""Conservative, hierarchy-aware attribution using only local geographic files.

This deliberately leaves incomplete or conflicting locations unresolved. It does
not infer a legislative seat from a DEO number, a road name, or a unique token.
Agreement between local maps is a screening rule, not official boundary proof.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from ph_location_text import text_key, confirmed_name_key, place_key, geographic_title, barangay_key

VERSION = "qualified-location-consensus-v4-location-metadata"


def seat_key(value):
    match = re.fullmatch(r"(lone|[1-9](?:st|nd|rd|th))(?: district)?", text_key(value))
    return match.group(1) if match else None




class GeographicAttribution:
    def __init__(self, data_root: Path, seats):
        # Jurisdiction identities retain "City": Quezon and Quezon City differ.
        self.seats = {(text_key(s["province"]), seat_key(s["districtLabel"])): i
                      for i, s in enumerate(seats)}
        self.roster = defaultdict(set)
        for jurisdiction, seat in self.seats:
            self.roster[jurisdiction].add(seat)
        primary = json.loads((data_root / "districts.json").read_text())["districts"]
        generated = json.loads((data_root / "districts_generated.json").read_text())
        self.primary_towns = defaultdict(lambda: defaultdict(set))
        self.alternate_towns = defaultdict(lambda: defaultdict(set))
        self.primary_barangays = defaultdict(lambda: defaultdict(set))
        self.alternate_barangays = defaultdict(lambda: defaultdict(set))
        self.city_names = set()
        self.city_parents = defaultdict(set)
        city_lookup = {}
        for jurisdiction, detail in primary.items():
            if detail.get("barangays") and text_key(jurisdiction) in self.roster:
                city_lookup[place_key(jurisdiction)] = text_key(jurisdiction)
        hierarchy = data_root.parents[1] / "city_barangays_mapping.json"
        if hierarchy.exists():
            for parent, cities in json.loads(hierarchy.read_text()).items():
                for city in cities:
                    key = place_key(city)
                    jurisdiction = next((j for j in [key + " city", key] if j in self.roster), None)
                    if jurisdiction:
                        city_lookup[key] = jurisdiction
                        self.city_parents[jurisdiction].add(text_key(parent))
        self.city_lookup = city_lookup
        self.town_aliases = defaultdict(set)
        self.known_city_towns = set()
        for jurisdiction, detail in primary.items():
            parent = text_key(jurisdiction)
            for town, district in detail.get("municipalities", {}).items():
                town_key = place_key(town)
                self.primary_towns[parent][town_key].add(seat_key(district))
                self.town_aliases[town_key].add(text_key(town))
                if re.search(r"^city of\b|\bcity$", text_key(town)):
                    self.known_city_towns.add((parent, town_key))
            for district, barangays in detail.get("barangays", {}).items():
                if not isinstance(barangays, list):
                    continue
                self.city_names.add(parent)
                for barangay in barangays:
                    # A city cannot be its own barangay.
                    if place_key(barangay) != place_key(parent):
                        self.primary_barangays[parent][barangay_key(barangay)].add(seat_key(district))
        for jurisdiction, towns in generated.items():
            parent = text_key(jurisdiction)
            for town, district in towns.items():
                town_key = place_key(town)
                self.town_aliases[town_key].add(text_key(town))
                if re.search(r"^city of\b|\bcity$", text_key(town)):
                    self.known_city_towns.add((parent, town_key))
                if isinstance(district, str):
                    self.alternate_towns[parent][town_key].add(seat_key(district))
                elif isinstance(district, dict):
                    city = city_lookup.get(town_key)
                    if not city:
                        continue
                    self.city_names.add(city)
                    self.city_parents[city].add(parent)
                    for barangay, seat in district.get("barangays", {}).items():
                        self.alternate_barangays[city][barangay_key(barangay)].add(seat_key(seat))
        # The local barangay hierarchy identifies cities with their own seats;
        # it is not used as a legislative boundary map.
        self.city_names.update(city_lookup.values())
        self.province_names = set(self.primary_towns) | set(self.alternate_towns)
        self.city_names &= set(self.roster)
        self.jurisdictions = self.province_names | self.city_names
        self.labels = defaultdict(set)
        for jurisdiction in self.jurisdictions:
            common_town_name = any(place_key(jurisdiction) in towns for towns in self.alternate_towns.values())
            if jurisdiction not in self.city_names or jurisdiction.endswith(" city") or not common_town_name:
                self.labels[jurisdiction].add(jurisdiction)
            if jurisdiction in self.city_names:
                key = place_key(jurisdiction)
                self.labels[jurisdiction].update([key + " city", "city of " + key])
            else:
                self.labels[jurisdiction].add("province of " + jurisdiction)

    def municipality(self, parent, locality):
        a = self.primary_towns[parent].get(locality, set())
        b = self.alternate_towns[parent].get(locality, set())
        if len(a) != 1 or len(b) != 1:
            return None, "Municipality missing or ambiguous in one local crosswalk"
        if a != b:
            return None, "Municipality district conflicts between local crosswalks"
        seat = next(iter(a))
        if (parent, seat) not in self.seats:
            return None, "Mapped seat is absent from the current roster"
        return self.seats[parent, seat], None

    def location_list(self, component):
        """Accept complete locality fields, never a place substring in a title."""
        component = text_key(component).strip(" .")
        if re.search(r"\b(?:barangays?|brgys?|bgys?|brgy|bgy|sitio|purok)\b", component):
            return []
        if place_key(component) in self.town_aliases or place_key(component) in self.city_lookup:
            return [place_key(component)]
        pieces = re.split(r"\s+(?:and|&)\s+|\s*[/;]\s*|\s+-\s+", component)
        if len(pieces) > 1 and all(place_key(p) in self.town_aliases or place_key(p) in self.city_lookup for p in pieces):
            return [place_key(p) for p in pieces]
        return []

    def city(self, city, prefix):
        # A named single-seat city identifies its seat, without province spillover.
        if self.roster[city] == {"lone"}:
            return [self.seats[city, "lone"]], [], [dict(level="city", name=city, basis="Explicit single-seat city location")]
        a, b = self.primary_barangays[city], self.alternate_barangays[city]
        if not b or set().union(*b.values()) != self.roster[city]:
            return [], ["City barangay crosswalk does not cover all roster districts"], []
        evidence, indices, reasons = [], [], []
        # Only explicitly identified barangays qualify. Section/road/river names
        # without the barangay marker cannot supply a barangay-level location.
        markers = list(re.finditer(r"\b(?:barangays?|brgys?\.?|bgys?\.?)\s+", prefix))
        for marker in markers:
            suffix = prefix[marker.end():]
            # Normalize a complete marked barangay at a delimiter, keeping the
            # remaining title untouched. Crosswalk consensus still decides LEG.
            head = re.split(r"[,;()/]", suffix, maxsplit=1)[0].strip()
            canonical = confirmed_name_key(head.strip(" ."))
            if canonical != head.strip(" ."):
                suffix = canonical + suffix[len(head):]
            hits = [(name, seat) for name, seat in b.items()
                    if re.match(re.escape(name) + r"(?=$|[,;()/]|\s*-|\s+and\s+(?:barangay|brgy)\b)", suffix)]
            if not hits:
                reasons.append("Explicit barangay has no exact city-qualified crosswalk entry")
                continue
            longest = max(len(name) for name, _ in hits)
            for name, other in hits:
                if len(name) != longest:
                    continue
                existing = a.get(name, set())
                if len(existing) != 1 or existing != other:
                    reasons.append("Barangay missing or conflicting between local city crosswalks")
                    continue
                seat = next(iter(existing))
                if (city, seat) not in self.seats:
                    reasons.append("Barangay seat absent from current roster")
                    continue
                indices.append(self.seats[city, seat])
                evidence.append(dict(level="barangay", name=name, city=city, district=seat,
                                     basis="Exact marked barangay and explicit parent city; maps agree"))
        if not markers:
            reasons.append("Multi-seat city lacks an explicit mapped barangay")
        # Missing any named barangay keeps the entire line unresolved.
        return ([] if reasons else sorted(set(indices))), sorted(set(reasons)), evidence

    def resolve(self, project):
        title,metadata=geographic_title(project.get("projectName",""))
        result=self._resolve_geographic(dict(project,projectName=title))
        if metadata:
            result['evidence'].append({'basis':'Trailing station/coordinate metadata excluded from address matching only; original project title and construction scope retained','metadata':metadata})
        return result

    def _resolve_geographic(self, project):
        title, metadata = geographic_title(project.get("projectName", ""))
        components = [x.strip(" .") for x in title.split(",")]
        tail = components[-1]
        # A province and a city can share a bare roster/map label. A complete
        # locality + province field supplies province context without treating
        # the province itself as a city (e.g. Echague, Isabela).
        province_context = [p for p in self.province_names
                            if tail in {p, "province of " + p}
                            and len(components) > 1 and self.location_list(components[-2])]
        parents = [p for p, aliases in self.labels.items() if tail in aliases]
        if len(province_context) == 1:
            parents = province_context
        if len(parents) != 1:
            return dict(indices=[], reasons=["No exact administrative location at the end of the project title"], evidence=[])
        parent = parents[0]
        prefix = ",".join(components[:-1])
        if parent in self.city_names and parent not in province_context:
            indices, reasons, evidence = self.city(parent, prefix)
            return dict(indices=indices, reasons=reasons, evidence=evidence)
        if len(components) < 2:
            return dict(indices=[], reasons=["Province alone is insufficient to establish project location"], evidence=[])
        localities = self.location_list(components[-2])
        if not localities:
            return dict(indices=[], reasons=["Province named without an exact municipality/city location field"], evidence=[])
        indices, reasons, evidence = [], [], []
        for locality in localities:
            field = components[-2]
            if len(localities) == 1 and re.search(r"^city of\b|\bcity$", field) and (parent, locality) not in self.known_city_towns:
                reasons.append("Explicit city label is not corroborated for that province")
                continue
            city = self.city_lookup.get(locality)
            if city and parent in self.city_parents[city]:
                # Prove the parent relationship too, even for separately seated cities.
                found, errors, details = self.city(city, ",".join(components[:-2]))
                indices.extend(found); reasons.extend(errors); evidence.extend(details)
            else:
                index, reason = self.municipality(parent, locality)
                if reason:
                    reasons.append(reason)
                else:
                    indices.append(index)
                evidence.append(dict(level="municipality", name=locality, province=parent,
                                     primaryDistricts=sorted(str(s) for s in self.primary_towns[parent].get(locality, set())),
                                     alternateDistricts=sorted(str(s) for s in self.alternate_towns[parent].get(locality, set()))))
        return dict(indices=[] if reasons else sorted(set(indices)), reasons=sorted(set(reasons)), evidence=evidence)
