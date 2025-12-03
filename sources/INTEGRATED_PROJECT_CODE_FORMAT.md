# Integrated Project Code Format

## Overview

The DPWH Integrated Project Code follows a standardized format defined in DO 172 s2016. This document explains the code structure and how to classify projects.

## Code Format: YYRDSSSS

The integrated project code consists of 8 characters:

- **YY** = Year (2 digits, e.g., 17 for 2017)
- **R** = Region letter (1 letter, A-Z, Z for Central Office)
- **D** = District letter (1 letter, A-Z, varies by region)
- **SSSS** = Sequence number (4 digits, e.g., 0001)

### Example

**17DB0001** breaks down as:
- **17** = Year 2017
- **D** = Region IV-A
- **B** = Batangas 1st DEO
- **0001** = Sequence number 1

## Region Mapping

Region letters map to region names:

| Letter | Region Name |
|--------|-------------|
| A | Region I |
| B | Region II |
| C | Region III |
| D | Region IV-A |
| E | Region IV-B |
| F | Region V |
| G | Region VI |
| H | Region VII |
| I | Region VIII |
| J | Region IX |
| K | Region X |
| L | Region XI |
| M | Region XII |
| N | Region XIII |
| O | NCR |
| P | CAR |
| Q | ARMM |
| R | NIR |
| Z | Central Office |

## District/DEO Mapping

Within each region, district letters map to specific District Engineering Offices (DEOs). The mapping is stored in `database/dpwh-project-code-mapping.json`.

### Example: Region D (Region IV-A)

| District Letter | DEO Name |
|----------------|----------|
| B | Batangas 1st DEO |
| C | Batangas 3rd DEO |
| D | Batangas 4th DEO |
| E | Batangas 2nd DEO |
| F | Cavite DEO |
| G | Cavite 2nd DEO |
| H | Laguna 1st DEO |
| I | Laguna 2nd DEO |
| J | Quezon 2nd DEO |
| K | Quezon 1st DEO |
| L | Quezon 4th DEO |
| M | Quezon 3rd DEO |
| N | Rizal 1st DEO |
| O | Rizal 2nd DEO |
| P | Laguna 3rd DEO |
| Q | Cavite Sub DEO |

**Note:** Not all letters are used in every region. For example, Region D does not have a district "A".

## Classification Process

To classify a project code:

1. **Parse the code**: Extract YY, R, D, and SSSS components
2. **Map region**: Look up region letter in mapping to get region name
3. **Map district**: Look up district letter within the region to get DEO name
4. **Return classification**: Region name, DEO name, year, and sequence

### Classification Output

```json
{
  "full_code": "17DB0001",
  "year": "17",
  "region_letter": "D",
  "region": "Region IV-A",
  "district_letter": "B",
  "district_deo": "Batangas 1st DEO",
  "sequence": "0001"
}
```

## Special Cases

- **Central Office (Z)**: Region Z has no districts
- **ARMM (Q)**: Region Q has no districts listed
- **Missing districts**: Some regions don't use all letter combinations (e.g., Region D has no district A)

## References

- **DO 172 s2016**: https://www.dpwh.gov.ph/dpwh/sites/default/files/issuances/DO_172_s2016.pdf
- **Mapping file**: `database/dpwh-project-code-mapping.json`
- **Parser script**: `sources/parse_do172_and_test.py`











