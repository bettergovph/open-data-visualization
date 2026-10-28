"""Conservative, hierarchy-aware attribution using only local geographic files.

This deliberately leaves incomplete or conflicting locations unresolved. It does
not infer a legislative seat from a DEO number, a road name, or a unique token.
An exact bridge ID may use the paired DEO and CONG_DIST fields in its ArcGIS
bridge record when title geography is unresolved. Agreement between local maps
is a screening rule, not official boundary proof.
"""
from __future__ import annotations

import json
import hashlib
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from ph_location_text import text_key, confirmed_name_key, place_key, geographic_title, barangay_key

VERSION = "qualified-location-consensus-v8-official-province-locality-crosswalk"


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

        # Administrative areas such as Malate are not Manila's numbered
        # barangays. Keep their parent-qualified mappings in a separate,
        # sourced crosswalk so homonyms elsewhere cannot supply a city district.
        self.administrative_localities = defaultdict(set)
        self.administrative_locality_sources = {}
        locality_file = data_root / "administrative_locality_crosswalk.json"
        if locality_file.exists():
            for row in json.loads(locality_file.read_text()).get("records", []):
                jurisdiction = text_key(row.get("jurisdiction"))
                locality = place_key(row.get("locality", ""))
                seat = seat_key(row.get("districtLabel", ""))
                if (jurisdiction, seat) in self.seats and locality:
                    index = self.seats[jurisdiction, seat]
                    self.administrative_localities[jurisdiction, locality].add(index)
                    self.administrative_locality_sources[jurisdiction, locality] = row

        # A small set of current law / Senate rule locality lists adjudicates
        # disagreements between the legacy and generated map crosswalks. These
        # are exact parent + locality keys; no fuzzy title match is accepted.
        self.authoritative_municipalities = defaultdict(dict)
        municipality_file = data_root / "congress_municipality_district_overrides.json"
        if municipality_file.exists():
            for jurisdiction, detail in json.loads(municipality_file.read_text()).get("jurisdictions", {}).items():
                jurisdiction = text_key(jurisdiction)
                for name, row in detail.get("municipalities", {}).items():
                    seat = seat_key(row.get("districtLabel", ""))
                    names = [name, *row.get("aliases", [])]
                    if (jurisdiction, seat) in self.seats:
                        for alias in names:
                            locality = place_key(alias)
                            if not locality:
                                continue
                            self.authoritative_municipalities[jurisdiction][locality] = {
                                **row,
                                "basis": row.get("basis", detail.get("basis", detail.get("sourceTitle"))),
                                "sources": row.get("sources", detail.get("sources", [])),
                                "limits": row.get("limits", detail.get("limits")),
                            }
                            self.town_aliases[locality].add(locality)

        # Current city-published legislative barangay lists resolve a few
        # known disagreements in the legacy/generated map crosswalks. These
        # entries are exact-name overrides only; the source and limits travel
        # with every resulting assignment.
        self.authoritative_barangays = defaultdict(dict)
        authoritative_file = data_root / "congress_barangay_district_overrides.json"
        if authoritative_file.exists():
            for jurisdiction, detail in json.loads(authoritative_file.read_text()).get("jurisdictions", {}).items():
                jurisdiction = text_key(jurisdiction)
                for name, row in detail.get("barangays", {}).items():
                    seat = seat_key(row.get("districtLabel", ""))
                    if (jurisdiction, seat) in self.seats and barangay_key(name):
                        self.authoritative_barangays[jurisdiction][barangay_key(name)] = row

        self.inventory_context = {}
        self.bridge_district_contexts = {}
        self.inventory_context_status = 'not_available'
        context_file = data_root / 'inventory_location_contexts.json'
        if context_file.exists():
            supplement = json.loads(context_file.read_text())
            dependencies = supplement.get('mapHashes', {})
            hierarchy_file = data_root.parents[1] / 'city_barangays_mapping.json'
            fresh = (set(dependencies) == {'districts.json', 'districts_generated.json', '20th_congress_representatives.json'}
                     and all(hashlib.sha256((data_root/name).read_bytes()).hexdigest() == digest for name,digest in dependencies.items())
                     and hierarchy_file.exists()
                     and hashlib.sha256(hierarchy_file.read_bytes()).hexdigest() == supplement.get('hierarchySha256'))
            if fresh:
                self.inventory_context = supplement.get('contexts', {})
                self.bridge_district_contexts = supplement.get('bridgeDistrictContexts', {})
                self.inventory_context_status = 'matching_dependencies'
            else:
                self.inventory_context_status = 'stale_dependencies_fallback_disabled'

    def municipality(self, parent, locality):
        official = self.authoritative_municipalities[parent].get(locality)
        if official:
            seat = seat_key(official.get("districtLabel", ""))
            if (parent, seat) not in self.seats:
                return None, "Official municipality seat is absent from the current roster"
            return self.seats[parent, seat], None
        # A province represented by one current legislative seat has no internal
        # municipal split to infer. With an exact municipality and province
        # field, the sole rostered seat is the only possible district.
        if self.roster[parent] == {"lone"}:
            return self.seats[parent, "lone"], None
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
        if ((not b or set().union(*b.values()) != self.roster[city])
                and not self.authoritative_barangays[city]):
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
            boundary = r"(?=$|\s*[,;()/]|\s*-|\s+and\s+(?:barangay|brgy)\b)"
            hits = [(name, seat) for name, seat in b.items()
                    if re.match(re.escape(name) + boundary, suffix)]
            sourced = [(name, row) for name, row in self.authoritative_barangays[city].items()
                       if re.match(re.escape(name) + boundary, suffix)]
            if sourced:
                longest = max(len(name) for name, _ in sourced)
                for name, row in sourced:
                    if len(name) != longest:
                        continue
                    seat = seat_key(row.get("districtLabel", ""))
                    if (city, seat) not in self.seats:
                        reasons.append("Authoritative barangay seat absent from current roster")
                        continue
                    indices.append(self.seats[city, seat])
                    evidence.append(dict(level="official legislative barangay crosswalk", name=name,
                                         city=city, district=row.get("districtLabel"),
                                         basis=row.get("basis"), sources=row.get("sources", []),
                                         limit=row.get("limits")))
                continue
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
        context = self.inventory_context.get(text_key(project.get('projectName', '')))
        bridge_context = self.bridge_district_contexts.get(text_key(project.get('projectName', '')))
        if bridge_context:
            expected = {(text_key(j), seat_key(s)) for j,s in bridge_context.get('seatKeys', [])}
            indices = {self.seats[pair] for pair in expected if pair in self.seats}
            if len(indices) == 1:
                source_evidence = {'basis': 'Exact bridge ID links this project to an ArcGIS record that lists a DEO and CONG_DIST; the district label maps to one current LEG roster entry.',
                    'bridgeId': bridge_context.get('bridgeId'), 'arcgisObjectId': bridge_context.get('objectId'),
                    'arcgisDEO': bridge_context.get('deo'), 'arcgisCONG_DIST': bridge_context.get('congDist'),
                    'sourceRegion': bridge_context.get('region'), 'sourceMunicipality': bridge_context.get('municipality'),
                    'sourceProvince': bridge_context.get('province'),
                    'limit': 'The DEO may cover multiple legislative districts. This is a bridge-record association, not proof of sponsorship or the funded work extent.'}
                if result['indices']:
                    source_evidence['comparison'] = 'agrees_with_title_geography' if set(result['indices']) == indices else 'conflicts_with_title_geography; title-based result retained'
                    result['evidence'].append(source_evidence)
                else:
                    result = {'indices': sorted(indices), 'reasons': [], 'evidence': [source_evidence]}
        if not result['indices'] and context:
            # Recheck screened asset locations through current maps. Never copy
            # old LEG polygon labels or stored representative names.
            located = self._resolve_geographic({'projectName': context['contextTitle']})
            expected = {(text_key(j), seat_key(s)) for j,s in context['seatKeys']}
            indices = {self.seats[pair] for pair in expected if pair in self.seats}
            if len(indices) == 1 and set(located['indices']) == indices:
                located['evidence'].append({'basis': context['basis'],
                    'contextTitle': context['contextTitle'], 'municipalObjectId': context['municipalObjectId'],
                    'inventoryEvidence': context['inventoryEvidence'],
                    'originalTextResolutionReasons': result['reasons'],
                    'limit': 'Inventory geographic context, not proof of funded quantities, sponsorship or historical district boundaries'})
                result = located
        return result

    def _resolve_geographic(self, project):
        title, metadata = geographic_title(project.get("projectName", ""))
        components = [x.strip(" .") for x in title.split(",")]
        # Some NCR project titles append the region after the city. Treat that
        # terminal region label as context only when the immediately preceding
        # complete field is itself an exact known city label.
        if (len(components) > 1
                and text_key(components[-1]) in {"metro manila", "national capital region", "ncr"}
                and any(components[-2] in aliases for aliases in self.labels.values())):
            components.pop()
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
            # Accept the exact administrative locality within the title's
            # city context, even if the project title has other text before it.
            # Requiring a delimiter after the locality avoids matching a
            # longer place or person name that merely starts with Malate.
            prefix_key = text_key(prefix)
            for (jurisdiction, locality), indices in self.administrative_localities.items():
                if jurisdiction != parent:
                    continue
                pattern = r"(?:^|[,;(])\s*" + re.escape(locality) + r"\s*(?=$|[,;)])"
                if re.search(pattern, prefix_key):
                    row = self.administrative_locality_sources[(jurisdiction, locality)]
                    return dict(indices=sorted(indices), reasons=[], evidence=[{
                        "level": "administrative_locality", "name": locality,
                        "city": parent, "district": row.get("districtLabel"),
                        "basis": row.get("basis"), "sources": row.get("sources", []),
                        "limit": row.get("limits")
                    }])
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
                official = self.authoritative_municipalities[parent].get(locality)
                evidence.append(dict(level="municipality", name=locality, province=parent,
                                     districtBasis=(official.get("basis") if official else
                                                    "Exact province + municipality; the current roster has one legislative district for this province"
                                                    if self.roster[parent] == {"lone"} else "Both local district maps agree"),
                                     district=(official.get("districtLabel") if official else None),
                                     sources=(official.get("sources", []) if official else
                                              ["https://www.congress.gov.ph/house-members"]
                                              if self.roster[parent] == {"lone"} else []),
                                     limit=(official.get("limits") if official else None),
                                     primaryDistricts=sorted(str(s) for s in self.primary_towns[parent].get(locality, set())),
                                     alternateDistricts=sorted(str(s) for s in self.alternate_towns[parent].get(locality, set()))))
        return dict(indices=[] if reasons else sorted(set(indices)), reasons=sorted(set(reasons)), evidence=evidence)
