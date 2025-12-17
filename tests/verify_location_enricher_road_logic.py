import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.location_enricher import LocationEnricher  # noqa: E402


def main() -> None:
    enricher = LocationEnricher("static/data/unified_locations.parquet")
    assert enricher.load_db()

    # Road-name contradiction: "MANILA NORTH ROAD" should not force Manila/NCR if
    # a more specific location hierarchy (municipality + province) appears elsewhere.
    project = {
        "name": "Rehab of Manila North Road (Sta. 0+000 - 1+000) - Laoag City, Ilocos Norte",
        "description": "",
        "location": "",
    }
    enricher.enrich_project(project)
    assert project.get("province") == "ILOCOS NORTE"
    assert project.get("district") and project.get("district") != "Unknown"

    # If a place name only appears as a road name and there is no other confirming
    # location indicator, prefer leaving it unclassified over a wrong district.
    project2 = {
        "name": "Manila North Road widening and rehabilitation",
        "description": "",
        "location": "",
    }
    enricher.enrich_project(project2)
    assert project2.get("district") in (None, "Unknown")

    # Region-only structured location should never infer a city/district from text.
    project3 = {
        "name": "Drainage improvement - Manila",
        "description": "",
        "location": {"region": "NCR", "province": None, "municipality": None, "barangay": None},
    }
    enricher.enrich_project(project3)
    assert project3.get("district") in (None, "Unknown")

    # Lone-district municipality exception: a municipality-only mention can be enough if that
    # municipality uniquely maps to a single district nationwide.
    project4 = {
        "name": "Drainage improvement - Navotas City",
        "description": "",
        "location": "",
    }
    enricher.enrich_project(project4)
    assert project4.get("district") not in (None, "Unknown")

    print("ok")


if __name__ == "__main__":
    main()
