# Probability Analysis: 867 Projects, 37 Unique Amounts

## 1. Summary Statistics
- **Total Projects (N)**: 867
- **Unique Amounts (K)**: 37
- **Ratio (K/N)**: 0.0427 (Only 4.27% of amounts are unique)

## 2. Collision Probability Analysis
The probability of observing only 37 unique values in 867 independent draws depends on the size of the "space" of possible amounts ($M$).

- **Assumption**: If budget amounts were random (even within a range), $M$ would be very large (e.g., millions of possible values down to the cent).
- **Simulation**:
    - We simulated drawing 867 times from a space of size $M=1000$ (a very conservative assumption, effectively assuming amounts are already quantized).
    - **Result**: In 10,000 simulations, the event (Unique $\le$ 37) occurred **0** times.
    - **Estimated Probability**: 0.000000 (under extremely generous assumptions).

**Conclusion**: Under any realistic assumption of random budget generation, the probability of this clustering occurring by chance is **effectively zero**. This strongly suggests the amounts were **not** generated randomly but were likely:
1.  **Copy-pasted** (duplicated entries).
2.  **Standardized** (fixed pricing for specific project types).
3.  **Artificial** (not derived from detailed cost estimates).

## 3. Benford's Law Analysis
We tested the leading digits of the 867 amounts against Benford's Law, which predicts the distribution of leading digits in naturally occurring numerical data.

### Chi-Square Test
- **Chi-Square Statistic**: 713.8370
- **Critical Value (p=0.05, df=8)**: 15.51
- **Result**: **REJECT** the null hypothesis that the data follows Benford's Law.
  *(A high Chi-Square value indicates the data does NOT follow Benford's Law, suggesting artificiality).*

### Distribution Table

| Digit | Observed Count | Observed % | Expected (Benford) % | Difference % |
|-------|----------------|------------|----------------------|--------------|
| 1 | 592 | 68.28% | 30.10% | +38.18% |
| 2 | 119 | 13.73% | 17.61% | -3.88% |
| 3 | 124 | 14.30% | 12.49% | +1.81% |
| 4 | 10 | 1.15% | 9.69% | -8.54% |
| 5 | 5 | 0.58% | 7.92% | -7.34% |
| 6 | 4 | 0.46% | 6.69% | -6.23% |
| 7 | 5 | 0.58% | 5.80% | -5.22% |
| 8 | 2 | 0.23% | 5.12% | -4.88% |
| 9 | 6 | 0.69% | 4.58% | -3.88% |

## 4. Top 10 Most Frequent Amounts
| Amount | Count | % of Total |
|--------|-------|------------|
| 15,000,000.00 | 549 | 63.32% |
| 30,000,000.00 | 121 | 13.96% |
| 20,000,000.00 | 75 | 8.65% |
| 10,000,000.00 | 28 | 3.23% |
| 25,000,000.00 | 25 | 2.88% |
| 22,500,000.00 | 8 | 0.92% |
| 9,000,000.00 | 6 | 0.69% |
| 45,000,000.00 | 5 | 0.58% |
| 40,000,000.00 | 5 | 0.58% |
| 7,500,000.00 | 4 | 0.46% |
