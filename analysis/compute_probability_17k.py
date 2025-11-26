import json
import math
import sys
from pathlib import Path
from collections import Counter
import random

def load_data():
    """Load Annex A-5 projects from the JSON file."""
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
            if p.get('source_sheet') == 'Annex A-5'
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
    simulations = 10000
    success_count = 0
    sim_m = 10000 # Increased M slightly for larger N, though still conservative
    
    for _ in range(simulations):
        draws = {random.randint(1, sim_m) for _ in range(n_draws)}
        if len(draws) <= k_unique:
            success_count += 1
            
    return success_count / simulations, sim_m

def benfords_law_test(amounts):
    leading_digits = []
    for amt in amounts:
        s = str(amt).replace('.', '').lstrip('0')
        if s:
            leading_digits.append(int(s[0]))
            
    total = len(leading_digits)
    counts = Counter(leading_digits)
    expected_probs = {d: math.log10(1 + 1/d) for d in range(1, 10)}
    expected_counts = {d: prob * total for d, prob in expected_probs.items()}
    
    chi_square = 0
    for d in range(1, 10):
        observed = counts.get(d, 0)
        expected = expected_counts[d]
        chi_square += ((observed - expected) ** 2) / expected
        
    return counts, expected_counts, chi_square

def generate_report(amounts, collision_prob, sim_m, benford_counts, benford_expected, chi_square):
    n = len(amounts)
    k = len(set(amounts))
    
    report = f"""# Probability Analysis: {n} Projects (Annex A-5)

## 1. Summary Statistics
- **Total Projects (N)**: {n}
- **Unique Amounts (K)**: {k}
- **Ratio (K/N)**: {k/n:.4f}

## 2. Collision Probability
- **Simulation (M={sim_m})**: {collision_prob:.6f}

## 3. Benford's Law Analysis
- **Chi-Square Statistic**: {chi_square:.4f}
- **Critical Value**: 15.51
- **Result**: {'REJECT' if chi_square > 15.51 else 'FAIL TO REJECT'}

### Distribution
| Digit | Observed | Expected | Diff % |
|-------|----------|----------|--------|
"""
    total = n
    for d in range(1, 10):
        obs = benford_counts.get(d, 0)
        obs_pct = (obs / total) * 100
        exp_pct = (benford_expected[d] / total) * 100
        report += f"| {d} | {obs} ({obs_pct:.1f}%) | {exp_pct:.1f}% | {obs_pct - exp_pct:+.1f}% |\n"

    report += "\n## 4. Top 10 Amounts\n"
    common = Counter(amounts).most_common(10)
    for amt, count in common:
        report += f"- {amt:,.2f}: {count} ({count/n*100:.2f}%)\n"
        
    return report

def main():
    amounts = load_data()
    print(f"Loaded {len(amounts)} amounts from Annex A-5.")
    
    prob, sim_m = calculate_collision_probability(len(amounts), len(set(amounts)))
    counts, expected, chi_sq = benfords_law_test(amounts)
    
    report = generate_report(amounts, prob, sim_m, counts, expected, chi_sq)
    
    output_path = Path(__file__).parent / "probability_report_17k.md"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)
        
    print(f"Chi-Square: {chi_sq:.2f}")
    print(f"Collision Prob: {prob}")
    print(f"Report saved to {output_path}")

if __name__ == "__main__":
    main()
