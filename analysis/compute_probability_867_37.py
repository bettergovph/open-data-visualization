import json
import math
import sys
from pathlib import Path
from collections import Counter
import random
import statistics

def load_data():
    """Load Annex A-1 projects from the JSON file."""
    # Path relative to this script: ../static/data/budget_amendments_2026.json
    script_dir = Path(__file__).parent
    data_path = script_dir.parent / "static" / "data" / "budget_amendments_2026.json"
    
    if not data_path.exists():
        print(f"Error: Data file not found at {data_path}")
        sys.exit(1)
        
    try:
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        projects = [
            p for p in data.get('projects', []) 
            if p.get('source_sheet') == 'Annex A-1'
        ]
        
        amounts = []
        for p in projects:
            amt = p.get('final_amount') or p.get('original_amount') or 0
            if amt > 0:
                amounts.append(amt)
                
        return amounts
    except Exception as e:
        print(f"Error loading data: {e}")
        sys.exit(1)

def calculate_collision_probability(n_draws, k_unique, m_space_size=1000000):
    """
    Estimate the probability of observing <= k_unique values in n_draws 
    from a space of size m_space_size.
    
    Since exact calculation for large N is difficult, we use a conceptual argument
    and a simulation for a smaller (but still generous) space to demonstrate the rarity.
    """
    # Theoretical max entropy (uniform distribution) would expect ~N unique values if M >> N
    # The fact that K << N implies massive clustering.
    
    # Simulation
    # We'll simulate drawing N times from a space of size M and see how often we get <= K unique values.
    # If M is large (like actual budget amounts), the prob is 0.
    # We'll try with a "generous" small M to show even then it's unlikely, 
    # or just report that for any reasonable M, P is effectively 0.
    
    simulations = 10000
    success_count = 0
    
    # We'll use a smaller M for simulation to give "randomness" a fighting chance.
    # If M = 37, prob is 1. If M = 1000, prob is small.
    # Let's try M = 1000 (e.g., amounts rounded to nearest million, range 1M-1B)
    sim_m = 1000
    
    for _ in range(simulations):
        draws = {random.randint(1, sim_m) for _ in range(n_draws)}
        if len(draws) <= k_unique:
            success_count += 1
            
    return success_count / simulations, sim_m

def benfords_law_test(amounts):
    """Perform Benford's Law analysis on the leading digits."""
    leading_digits = []
    for amt in amounts:
        s = str(amt).replace('.', '').lstrip('0')
        if s:
            leading_digits.append(int(s[0]))
            
    total = len(leading_digits)
    counts = Counter(leading_digits)
    
    # Expected frequencies according to Benford's Law
    # P(d) = log10(1 + 1/d)
    expected_probs = {d: math.log10(1 + 1/d) for d in range(1, 10)}
    expected_counts = {d: prob * total for d, prob in expected_probs.items()}
    
    # Chi-square statistic
    chi_square = 0
    for d in range(1, 10):
        observed = counts.get(d, 0)
        expected = expected_counts[d]
        chi_square += ((observed - expected) ** 2) / expected
        
    return counts, expected_counts, chi_square

def generate_report(amounts, collision_prob, sim_m, benford_counts, benford_expected, chi_square):
    """Generate a Markdown report."""
    n = len(amounts)
    k = len(set(amounts))
    
    report = f"""# Probability Analysis: 867 Projects, 37 Unique Amounts

## 1. Summary Statistics
- **Total Projects (N)**: {n}
- **Unique Amounts (K)**: {k}
- **Ratio (K/N)**: {k/n:.4f} (Only {k/n*100:.2f}% of amounts are unique)

## 2. Collision Probability Analysis
The probability of observing only {k} unique values in {n} independent draws depends on the size of the "space" of possible amounts ($M$).

- **Assumption**: If budget amounts were random (even within a range), $M$ would be very large (e.g., millions of possible values down to the cent).
- **Simulation**:
    - We simulated drawing {n} times from a space of size $M={sim_m}$ (a very conservative assumption, effectively assuming amounts are already quantized).
    - **Result**: In 10,000 simulations, the event (Unique $\le$ {k}) occurred **{int(collision_prob * 10000)}** times.
    - **Estimated Probability**: {collision_prob:.6f} (under extremely generous assumptions).

**Conclusion**: Under any realistic assumption of random budget generation, the probability of this clustering occurring by chance is **effectively zero**. This strongly suggests the amounts were **not** generated randomly but were likely:
1.  **Copy-pasted** (duplicated entries).
2.  **Standardized** (fixed pricing for specific project types).
3.  **Artificial** (not derived from detailed cost estimates).

## 3. Benford's Law Analysis
We tested the leading digits of the {n} amounts against Benford's Law, which predicts the distribution of leading digits in naturally occurring numerical data.

### Chi-Square Test
- **Chi-Square Statistic**: {chi_square:.4f}
- **Critical Value (p=0.05, df=8)**: 15.51
- **Result**: {'**REJECT**' if chi_square > 15.51 else 'FAIL TO REJECT'} the null hypothesis that the data follows Benford's Law.
  *(A high Chi-Square value indicates the data does NOT follow Benford's Law, suggesting artificiality).*

### Distribution Table

| Digit | Observed Count | Observed % | Expected (Benford) % | Difference % |
|-------|----------------|------------|----------------------|--------------|
"""
    
    total = n
    for d in range(1, 10):
        obs = benford_counts.get(d, 0)
        obs_pct = (obs / total) * 100
        exp_pct = (benford_expected[d] / total) * 100
        diff = obs_pct - exp_pct
        report += f"| {d} | {obs} | {obs_pct:.2f}% | {exp_pct:.2f}% | {diff:+.2f}% |\n"
        
    report += "\n## 4. Top 10 Most Frequent Amounts\n"
    report += "| Amount | Count | % of Total |\n|--------|-------|------------|\n"
    
    common = Counter(amounts).most_common(10)
    for amt, count in common:
        report += f"| {amt:,.2f} | {count} | {(count/n)*100:.2f}% |\n"
        
    return report

def main():
    print("Loading data...")
    amounts = load_data()
    print(f"Loaded {len(amounts)} amounts.")
    
    print("Calculating collision probability (simulation)...")
    prob, sim_m = calculate_collision_probability(len(amounts), len(set(amounts)))
    
    print("Performing Benford's Law test...")
    counts, expected, chi_sq = benfords_law_test(amounts)
    
    print("Generating report...")
    report = generate_report(amounts, prob, sim_m, counts, expected, chi_sq)
    
    output_path = Path(__file__).parent / "probability_report.md"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)
        
    print(f"Analysis complete. Report saved to {output_path}")
    print("-" * 30)
    print(f"Chi-Square: {chi_sq:.2f}")
    print(f"Collision Prob (M={sim_m}): {prob}")

if __name__ == "__main__":
    main()
