# Hardcoded Classification Logic Report (DuckDB Dynasty Cache)

Scope: `scripts/generate_dynasty_projects_cache_duckdb.py`

This report lists places where classification/matching behavior depends on hardcoded values (string lists, regexes, special-case branches, fixed mappings), rather than deriving behavior purely from the location hierarchy data (e.g., `static/data/unified_locations.parquet`, `static/data/districts.json`).

## 1) Manila / Metro Manila Special Handling

- `scripts/generate_dynasty_projects_cache_duckdb.py:43` `BARANGAY_NUMBER_PATTERNS` includes Manila-specific regex parsing for barangay numbers.
- `scripts/generate_dynasty_projects_cache_duckdb.py:3885` `_initialize_manila_tokens()` builds Manila barangay token maps from `districts.json`.
- `scripts/generate_dynasty_projects_cache_duckdb.py` uses province/region phrase suffix maps to prevent nested matches (e.g., `"metro manila"` should not count as municipality=`"manila"` by itself).
- `scripts/build_unified_location_db.py` adds NCR region aliases (`"METRO MANILA"`, `"NATIONAL CAPITAL REGION"`) into `static/data/unified_locations.parquet` so region-phrase detection is data-driven.

Risk: Manila/NCR text is common in road/location strings; without standalone/nested-phrase handling, `"manila"` can overmatch inside `"metro manila"`.

## 2) Province Disambiguation Logic

Previously the script carried duplicated hardcoded disambiguation regex lists (Davao/Zamboanga/etc.) in multiple places.

This has been migrated to data-driven multi-word province phrase detection sourced from the location hierarchy:

- `LocationMatcher` builds `province_phrase_patterns` from `unified_locations.parquet` province values.
- Worker matching builds `province_phrase_patterns` from `WORKER_STATE['unique_provinces']` (also sourced from the same hierarchy).
- `_find_best_location_match()` caches `_province_phrase_patterns` from loaded `location_entries`.

Risk: if the hierarchy data is incomplete/wrong, disambiguation will be incomplete/wrong as well (but it will at least be consistent across the script).

## 3) Road-Suffix Exclusion Lists (Road Context Heuristic)

Multiple hardcoded road suffix lists exist to prevent false matches from road names:

- `scripts/generate_dynasty_projects_cache_duckdb.py:289` `LocationMatcher._word_boundary_match()` uses a hardcoded `suffixes = [...]`.
- `scripts/generate_dynasty_projects_cache_duckdb.py:507` worker-side `suffixes = [...]` duplicates a similar list.

Risk: if new road markers appear (e.g., “FLOODWAY”, “C-6”, “EXPY”), false positives can return unless suffix lists are updated.

## 4) Fallback to Hardcoded Province “Substring” List

- `scripts/generate_dynasty_projects_cache_duckdb.py:1627` `_load_substring_provinces()` attempts to read `provinces-substring.json`.
- `scripts/generate_dynasty_projects_cache_duckdb.py:1636` falls back to a hardcoded set: `{'agusan','cagayan','camarines',...}`.

Risk: if the JSON file is missing/corrupt, the fallback silently changes behavior (and may be incomplete/outdated).

## 5) Hardcoded “Strict Provinces” List

- `scripts/generate_dynasty_projects_cache_duckdb.py:6659` hardcoded `strict_provinces = ['BUKIDNON', 'PALAWAN', 'RIZAL', 'CEBU', 'DAVAO', 'ILOILO']`.

Risk: “strictness” becomes uneven and non-explainable for users (“why is X strict but Y not?”).

## 6) Abbreviation / Shortcode Mapping for Cities

- `scripts/generate_dynasty_projects_cache_duckdb.py:4849` `abbreviation_map` uses hardcoded shortcuts:
  - `'Q'/'QC' -> QUEZON CITY`
  - `'M' -> MANILA`, `'MM' -> METRO MANILA`
  - `'C' -> CEBU CITY`, `'D' -> DAVAO CITY`, etc.
  - Includes special handling for `LAS PIÑAS CITY` vs `LAS PINAS CITY`.

Risk: collisions are explicitly tolerated (e.g., `'M'` used by Manila/Makati/Mandaluyong); this can produce non-deterministic results depending on city iteration order.

## 7) City-/Province-Specific Exceptions in Extraction / Validation

Examples (not exhaustive):

- `scripts/generate_dynasty_projects_cache_duckdb.py:928` “Davao City fix” branch.
- `scripts/generate_dynasty_projects_cache_duckdb.py:5301` special handling for Davao City classification (city district vs province).
- `scripts/generate_dynasty_projects_cache_duckdb.py:4462` special handling for Iloilo City (lone district).
- `scripts/generate_dynasty_projects_cache_duckdb.py:5192` requirement for city district classification when no “CITY” word is present.

Risk: these are hard to test comprehensively and tend to accrete as “bugfixes” over time.

## 8) District-Specific External Geography Files (Avoid)

Avoid maintaining any district/barangay lists outside the location hierarchy (`static/data/districts.json` → `static/data/unified_locations.parquet`).

If a district needs barangay coverage, it should be added to `static/data/districts.json` (and then rebuilt into `static/data/unified_locations.parquet`), not loaded from one-off JSON files.

## 9) Region Tokens / Region Handling (Heuristic)

- `scripts/generate_dynasty_projects_cache_duckdb.py:5056` includes a hardcoded `regions = ['NCR', 'NATIONAL CAPITAL REGION', 'METRO MANILA', 'CARAGA', 'CAR', ...]`.

Risk: region tokens may change or expand; treating “Metro Manila” as a region string is correct but requires careful handling to avoid “Manila city” overmatches.

## 10) `ñ` / Diacritics Handling (Encoding + Matching)

The datasets contain accented characters (notably `ñ`) in both city names and free-text fields:

- Examples: `LAS PIÑAS`, `PARAÑAQUE`, plus occasional mojibake variants like `LAS PIĄAS` depending on data source/encoding.
- If normalization is not accent-insensitive, matching can silently fail (e.g., `PARANAQUE` text won’t match `PARAÑAQUE` in the location DB, or vice versa).

**Recommendation**

- Ensure all matching logic performs accent-folding (Unicode NFKD + strip combining marks) as a pre-step before tokenization/word-boundary matching.
- Keep display strings unmodified (retain original `ñ`) while using a folded key for matching/grouping.

## 11) Directional Province Matching Rules

- `scripts/generate_dynasty_projects_cache_duckdb.py:6550` extensive directional modifier logic (SUR/NORTE/OCCIDENTAL/ORIENTAL etc.).

This is “hardcoded logic” (rules + directional vocabulary), even though it’s general.

## Notes / Suggested Refactors

1. Deduplicate disambiguation + road suffix lists (single source of truth).
2. Prefer deriving region/province/city vocabulary from the location DB (and/or `districts.json`) instead of hardcoded region lists.
3. Keep “Metro Manila”/NCR handling data-driven via hierarchy:
   - Region-only mentions should reduce confidence and require more specific matches (barangay/municipality) before assigning a district.
4. Replace city abbreviation mapping with a data-driven approach (e.g., generate abbreviations only for unique cities).
