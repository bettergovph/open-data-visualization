# Dynasty Cache Baseline (Pre-Parallelization)

Generated from `static/data/dynasty-projects-cache.json` on **2025-11-07T15:46:15.068911**. Use these numbers to confirm that the parallelized generator reproduces identical results.

## Summary Totals

- Total unique projects: **20,617**
- Source coverage:
  - DIME: **1,851**
  - PhilGEPS: **2,086**
  - SSP: **1,365**
  - InfraWatch / Microsite: **16,506**
- Match types:
  - District matches: **19,392**
  - Contractor matches: **1,225**
- Aggregate costs (PHP):
  - Total cost (all projects): **₱764,957,550,208.90**
  - District cost: **₱624,817,764,956.18**
  - Contractor cost: **₱140,139,785,252.72**

## Top 10 by Project Count

| Congressman | Projects | Total Cost (₱) | Avg. Cost (₱) |
|-------------|---------:|---------------:|---------------:|
| Wilfredo S. Caminero | 2,415 | 56,210,812,492.53 | 23,275,698.75 |
| Ralph Recto | 1,998 | 29,680,155,243.71 | 14,854,932.55 |
| Isidro Ungab | 1,652 | 141,017,575,904.63 | 85,361,728.76 |
| Ferjenel Biron | 1,625 | 28,181,705,195.82 | 17,342,587.81 |
| Benhur L. Salimbangon | 1,010 | 18,027,169,388.69 | 17,848,682.56 |
| Elizaldy Salcedo Co | 978 | 113,263,179,796.08 | 115,811,022.29 |
| Juan Pablo Bondoc | 922 | 18,949,498,937.06 | 20,552,601.88 |
| Gwendolyn Garcia | 870 | 26,006,440,913.18 | 29,892,460.82 |
| Danilo Domingo | 847 | 28,619,084,415.80 | 33,788,765.54 |
| Linabelle Villarica | 841 | 29,014,640,142.72 | 34,500,166.64 |

## Top 10 by Total Cost

| Congressman | Projects | Total Cost (₱) | Avg. Cost (₱) |
|-------------|---------:|---------------:|---------------:|
| Isidro Ungab | 1,652 | 141,017,575,904.63 | 85,361,728.76 |
| Elizaldy Salcedo Co | 978 | 113,263,179,796.08 | 115,811,022.29 |
| Wilfredo S. Caminero | 2,415 | 56,210,812,492.53 | 23,275,698.75 |
| Ferdinand Martin Gomez Romualdez | 794 | 38,440,354,190.09 | 48,413,544.32 |
| Rufus Rodriguez | 679 | 37,012,965,313.50 | 54,510,994.57 |
| Tirso Edwin Loleng Gardiola | 272 | 31,621,359,600.71 | 116,254,998.53 |
| Ralph Recto | 1,998 | 29,680,155,243.71 | 14,854,932.55 |
| Linabelle Villarica | 841 | 29,014,640,142.72 | 34,500,166.64 |
| Danilo Domingo | 847 | 28,619,084,415.80 | 33,788,765.54 |
| Ferjenel Biron | 1,625 | 28,181,705,195.82 | 17,342,587.81 |

## Usage Notes

1. Run the parallelized generator and compare its output against the figures above.
2. If any number diverges, capture the diff and investigate before adopting the parallel version.
3. Update this document with the latest baseline whenever the underlying datasets or scoring rules change.
