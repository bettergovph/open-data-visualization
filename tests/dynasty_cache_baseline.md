# Dynasty Cache Baseline (Pre-Parallelization)

Generated from `static/data/dynasty-projects-cache.json` on **2025-11-07T16:56:50.172520**. Use these numbers to confirm that the parallelized generator reproduces identical results.

## Summary Totals

- Total unique projects: **22,817**
- Source coverage:
  - DIME: **2,040**
  - PhilGEPS: **2,272**
  - SSP: **1,527**
  - InfraWatch / Microsite: **18,330**
- Match types:
  - District matches: **21,617**
  - Contractor matches: **1,200**
- Aggregate costs (PHP):
  - Total cost (all projects): **₱837,692,746,866.21**
  - District cost: **₱699,679,983,868.21**
  - Contractor cost: **₱138,012,762,998.00**

## Top 10 by Project Count

| Congressman | Projects | Total Cost (₱) | Avg. Cost (₱) |
|-------------|---------:|---------------:|---------------:|
| Wilfredo S. Caminero | 2,415 | 56,210,812,492.53 | 23,275,698.75 |
| Ralph Recto | 1,996 | 29,649,747,586.66 | 14,854,582.96 |
| Isidro Ungab | 1,652 | 141,017,575,904.63 | 85,361,728.76 |
| Ferjenel Biron | 1,625 | 28,181,705,195.82 | 17,342,587.81 |
| Arthur C. Yap | 1,071 | 21,580,166,120.47 | 20,149,548.20 |
| Benhur L. Salimbangon | 1,010 | 18,027,169,388.69 | 17,848,682.56 |
| Elizaldy Salcedo Co | 978 | 113,263,179,796.08 | 115,811,022.29 |
| Juan Pablo Bondoc | 922 | 18,949,498,937.06 | 20,552,601.88 |
| Gwendolyn Garcia | 870 | 26,006,440,913.18 | 29,892,460.82 |
| Danilo Domingo | 847 | 28,619,084,415.80 | 33,788,765.54 |

## Top 10 by Total Cost

| Congressman | Projects | Total Cost (₱) | Avg. Cost (₱) |
|-------------|---------:|---------------:|---------------:|
| Isidro Ungab | 1,652 | 141,017,575,904.63 | 85,361,728.76 |
| Elizaldy Salcedo Co | 978 | 113,263,179,796.08 | 115,811,022.29 |
| Wilfredo S. Caminero | 2,415 | 56,210,812,492.53 | 23,275,698.75 |
| Ferdinand Martin Gomez Romualdez | 817 | 39,558,717,969.04 | 48,419,483.44 |
| Rufus Rodriguez | 679 | 37,012,965,313.50 | 54,510,994.57 |
| Evelina Escudero | 628 | 33,019,463,234.85 | 52,578,763.11 |
| Tirso Edwin Loleng Gardiola | 255 | 29,999,937,117.59 | 117,646,812.23 |
| Ralph Recto | 1,996 | 29,649,747,586.66 | 14,854,582.96 |
| Linabelle Villarica | 841 | 29,014,640,142.72 | 34,500,166.64 |
| Danilo Domingo | 847 | 28,619,084,415.80 | 33,788,765.54 |

## Usage Notes

1. Run the parallelized generator and compare its output against the figures above.
2. If any number diverges, capture the diff and investigate before adopting the parallel version.
3. Update this document with the latest baseline whenever the underlying datasets or scoring rules change.
