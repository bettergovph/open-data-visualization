# Classification Dictionaries Summary

This document summarizes all dictionaries used for classifying projects to their correct districts.

## Overview

All location data (provinces, cities, municipalities, barangays) is now loaded dynamically from JSON configuration files instead of being hardcoded. This ensures the classification system uses the most up-to-date data and can handle all locations in the Philippines.

## Dictionary Structure

The `_build_location_dictionaries()` method creates a comprehensive set of dictionaries stored in `self.location_dicts`:

### 1. **`provinces`** (Set[str])
- **Purpose**: All known provinces in the Philippines
- **Source**: Extracted from `congressmen_data`, `district_lookup_dict`, and `districts.json`
- **Usage**: Used to match province names in project descriptions
- **Example**: `{'OCCIDENTAL MINDORO', 'ORIENTAL MINDORO', 'TARLAC', 'ILOCOS NORTE', ...}`

### 2. **`cities`** (Set[str])
- **Purpose**: All known cities (city districts)
- **Source**: Extracted from congressmen with `is_city_district=True` and districts.json
- **Usage**: Used to identify city districts vs province districts
- **Example**: `{'DAVAO CITY', 'QUEZON CITY', 'MANILA', 'ILOILO CITY', ...}`

### 3. **`municipalities`** (Set[str])
- **Purpose**: All known municipalities in province districts
- **Source**: Extracted from `congressmen_data.district_municipalities` and `districts.json`
- **Usage**: Used to match municipality names in project descriptions for province districts
- **Example**: `{'PALUAN', 'RIZAL', 'CALINTAAN', 'BASEY', ...}`

### 4. **`barangays`** (Set[str])
- **Purpose**: All known barangays in city districts
- **Source**: Extracted from `congressmen_data.barangays` and `districts.json`
- **Usage**: Used to match barangay names in project descriptions for city districts
- **Example**: `{'MATINA', 'TANDANG SORA', 'MARCELO GREEN', ...}`

### 5. **`directional_map`** (Dict[str, List[str]])
- **Purpose**: Maps base province names to their directional variants
- **Source**: Automatically generated from province names by removing directional modifiers
- **Usage**: Prevents incorrect matches (e.g., "Southern Leyte" should not match "Leyte")
- **Structure**: `{base_name: [variant1, variant2, ...]}`
- **Example**: 
  ```python
  {
    'ILOCOS': ['ILOCOS NORTE', 'ILOCOS SUR'],
    'LEYTE': ['LEYTE', 'SOUTHERN LEYTE'],
    'DAVAO': ['DAVAO DEL SUR', 'DAVAO DEL NORTE', 'DAVAO ORIENTAL', 'DAVAO OCCIDENTAL', 'DAVAO DE ORO'],
    'MINDORO': ['OCCIDENTAL MINDORO', 'ORIENTAL MINDORO'],
    'MAGUINDANAO': ['MAGUINDANAO', 'MAGUINDANAO DEL SUR', 'MAGUINDANAO DEL NORTE'],
    ...
  }
  ```
- **Usage**: When a project mentions "SOUTHERN LEYTE", the system checks `directional_map.get('LEYTE')` to ensure it only matches "SOUTHERN LEYTE" and not the base "LEYTE"

### 6. **`abbreviation_map`** (Dict[str, str])
- **Purpose**: Maps common abbreviations to full city/province names
- **Source**: Built from known cities in the data
- **Usage**: Handles single-letter abbreviations (e.g., "Q" -> "QUEZON CITY")
- **Example**:
  ```python
  {
    'Q': 'QUEZON CITY',
    'QC': 'QUEZON CITY',
    'M': 'MANILA',
    'MM': 'METRO MANILA',
    'C': 'CEBU CITY',
    'D': 'DAVAO CITY',
    'I': 'ILOILO CITY',
    'V': 'VALENZUELA CITY',
    'LP': 'LAS PIÑAS CITY',
    ...
  }
  ```

### 7. **`location_context_map`** (Dict[str, List[Tuple[str, str]]])
- **Purpose**: Maps location names (municipalities/barangays) to their parent provinces/cities
- **Source**: Built from `congressmen_data`, `district_lookup_dict`, and `districts.json`
- **Usage**: Disambiguates duplicate location names (e.g., "Matina" in Davao City vs Iloilo)
- **Structure**: `{location_name: [(province_city, type), ...]}`
- **Example**:
  ```python
  {
    'MATINA': [
      ('DAVAO CITY', 'barangay'),
      ('ILOILO', 'municipality')  # hypothetical
    ],
    'RIZAL': [
      ('OCCIDENTAL MINDORO', 'municipality'),
      ('RIZAL', 'province')  # Rizal province itself
    ],
    'PALUAN': [
      ('OCCIDENTAL MINDORO', 'municipality')
    ],
    ...
  }
  ```
- **Usage**: When a project mentions "Matina, Davao", the system:
  1. Looks up `location_context_map.get('MATINA')`
  2. Finds multiple contexts: `[('DAVAO CITY', 'barangay'), ('ILOILO', 'municipality')]`
  3. Checks the project text for "DAVAO" or "ILOILO"
  4. Matches to "DAVAO CITY" (barangay) since "DAVAO" is mentioned in the text

## Additional Lookup Dictionaries

### 8. **`district_lookup_dict`** (Dict[Tuple[str, str], List[Tuple[str, Dict]]])
- **Purpose**: O(1) lookup for congressmen by (province, municipality/barangay)
- **Structure**: `{(province_upper, location_upper): [(congressman_name, congressman_data), ...]}`
- **Usage**: Fast matching of projects to congressmen based on location
- **Example**: `{('DAVAO CITY', 'MATINA'): [('Paolo Duterte', {...}), ...]}`

### 9. **`contractor_lookup_dict`** (Dict[str, List[Tuple[str, Dict]]])
- **Purpose**: O(1) lookup for congressmen by contractor name
- **Structure**: `{contractor_name_upper: [(congressman_name, congressman_data), ...]}`
- **Usage**: Fast matching of projects to congressmen based on contractor
- **Example**: `{'S-ANG CONSTRUCTION': [('Gardiola', {...}), ...]}`

### 10. **`self.district_lookup`** (Dict[str, Dict])
- **Purpose**: Global district lookup with municipalities and barangays
- **Structure**: `{district_key: {'municipalities': set, 'barangays': set, 'is_city': bool}}`
- **Usage**: Validates extracted municipality/barangay names against known districts
- **Example**: 
  ```python
  {
    'Davao City 1st District': {
      'municipalities': set(),
      'barangays': {'MATINA', 'TALOMO', ...},
      'is_city': True
    },
    'Occidental Mindoro Lone District': {
      'municipalities': {'PALUAN', 'RIZAL', 'CALINTAAN', ...},
      'barangays': set(),
      'is_city': False
    }
  }
  ```

## Classification Flow

1. **Extract Location from Text**: Uses `_extract_location_from_text()` with:
   - `known_provinces` (from `location_dicts['provinces']`)
   - `known_cities` (from `location_dicts['cities']`)
   - `location_context_map` (from `location_dicts['location_context_map']`)
   - `directional_map` (from `location_dicts['directional_map']`)
   - `abbreviation_map` (from `location_dicts['abbreviation_map']`)

2. **Disambiguate Duplicate Locations**: Uses `location_context_map` to resolve conflicts:
   - If "Matina" appears in multiple provinces/cities
   - Check project text for province/city mentions
   - Match to the correct context

3. **Match to District**: Uses `district_lookup_dict` for O(1) lookup:
   - Key: `(province, municipality/barangay)`
   - Returns: List of matching congressmen

4. **Validate**: Uses `self.district_lookup` to ensure extracted location exists in the matched district

## Benefits

1. **No Hardcoding**: All location data comes from JSON files
2. **Comprehensive**: Handles all provinces, cities, municipalities, and barangays in the system
3. **Disambiguation**: Can differentiate between duplicate location names
4. **Directional Handling**: Prevents incorrect matches for provinces with directional variants
5. **Performance**: O(1) lookups for fast classification
6. **Maintainability**: Updates to JSON files automatically reflect in classification

## Data Sources

- **`dynasty-projects-config.json`**: Congressmen configuration with provinces, municipalities, barangays
- **`districts.json`**: District definitions with municipalities and barangays
- **DuckDB tables**: Exported from PostgreSQL for faster loading







