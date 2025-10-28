#!/usr/bin/env python3
"""
Contractor-District Correlation Analysis

Tests the hypothesis that projects are concentrated similarly across contractors and districts.

Statistical measures:
- Herfindahl-Hirschman Index (HHI) for concentration
- Gini Coefficient for inequality
- Chi-square test for independence
- Cramér's V for association strength
- Pearson/Spearman correlation for concentration patterns
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any
from collections import defaultdict
import numpy as np
from scipy import stats
from scipy.stats import chi2_contingency, spearmanr, pearsonr
import pandas as pd

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from flood_client import FloodControlClient


class ContractorDistrictAnalyzer:
    """Analyzes concentration and correlation between contractors and districts"""
    
    def __init__(self):
        self.projects = []
        self.contractor_district_matrix = defaultdict(lambda: defaultdict(int))
        self.district_totals = defaultdict(int)
        self.contractor_totals = defaultdict(int)
        self.total_projects = 0
        
    async def load_data(self):
        """Load flood control project data"""
        print("🔍 Loading flood control project data...")
        client = FloodControlClient()
        
        # Get all projects
        projects, metadata = await client.search_projects(query="", limit=20000, offset=0)
        self.projects = projects
        self.total_projects = len(projects)
        
        print(f"✅ Loaded {self.total_projects} projects")
        
        # Build contractor-district matrix
        for project in projects:
            contractor = project.Contractor or "Unknown Contractor"
            district = project.DistrictEngineeringOffice or "Unknown District"
            
            # Clean up contractor names (handle JV)
            contractor = contractor.strip()
            district = district.strip()
            
            self.contractor_district_matrix[contractor][district] += 1
            self.contractor_totals[contractor] += 1
            self.district_totals[district] += 1
        
        print(f"📊 Found {len(self.contractor_totals)} unique contractors")
        print(f"📊 Found {len(self.district_totals)} unique districts")
        
    def calculate_hhi(self, distribution: Dict[str, int]) -> float:
        """
        Calculate Herfindahl-Hirschman Index (HHI)
        
        HHI = Σ(market_share)² × 10,000
        
        Returns value from 0 (perfect competition) to 10,000 (monopoly)
        """
        total = sum(distribution.values())
        if total == 0:
            return 0.0
        
        hhi = sum((count / total) ** 2 for count in distribution.values()) * 10000
        return hhi
    
    def calculate_gini(self, values: List[float]) -> float:
        """
        Calculate Gini coefficient
        
        Returns value from 0 (perfect equality) to 1 (perfect inequality)
        """
        if len(values) == 0:
            return 0.0
        
        # Sort values
        sorted_values = np.sort(values)
        n = len(sorted_values)
        
        # Calculate Gini
        index = np.arange(1, n + 1)
        gini = (2 * np.sum(index * sorted_values)) / (n * np.sum(sorted_values)) - (n + 1) / n
        
        return gini
    
    def calculate_hhi_by_district(self) -> Dict[str, float]:
        """Calculate HHI for contractors within each district"""
        hhi_by_district = {}
        
        for district, contractors in self.district_totals.items():
            # Get contractor distribution in this district
            contractor_counts = {}
            for contractor in self.contractor_district_matrix:
                count = self.contractor_district_matrix[contractor].get(district, 0)
                if count > 0:
                    contractor_counts[contractor] = count
            
            hhi = self.calculate_hhi(contractor_counts)
            hhi_by_district[district] = hhi
        
        return hhi_by_district
    
    def calculate_hhi_by_contractor(self) -> Dict[str, float]:
        """Calculate HHI for districts within each contractor"""
        hhi_by_contractor = {}
        
        for contractor, districts_dict in self.contractor_district_matrix.items():
            hhi = self.calculate_hhi(districts_dict)
            hhi_by_contractor[contractor] = hhi
        
        return hhi_by_contractor
    
    def build_contingency_table(self) -> Tuple[pd.DataFrame, List[str], List[str]]:
        """Build contingency table for chi-square test"""
        # Get top contractors and districts with minimum threshold to avoid sparse data
        # Only include contractors with at least 5 projects
        top_contractors = sorted([(k, v) for k, v in self.contractor_totals.items() if v >= 5], 
                                key=lambda x: x[1], reverse=True)[:30]
        # Only include districts with at least 20 projects
        top_districts = sorted([(k, v) for k, v in self.district_totals.items() if v >= 20], 
                              key=lambda x: x[1], reverse=True)[:30]
        
        contractor_names = [c[0] for c in top_contractors]
        district_names = [d[0] for d in top_districts]
        
        # Build matrix
        matrix = []
        for contractor in contractor_names:
            row = []
            for district in district_names:
                count = self.contractor_district_matrix[contractor].get(district, 0)
                row.append(count)
            matrix.append(row)
        
        df = pd.DataFrame(matrix, index=contractor_names, columns=district_names)
        
        # Remove any rows or columns that are all zeros
        df = df.loc[(df != 0).any(axis=1)]  # Remove rows with all zeros
        df = df.loc[:, (df != 0).any(axis=0)]  # Remove columns with all zeros
        
        return df, list(df.index), list(df.columns)
    
    def chi_square_test(self, contingency_table: pd.DataFrame) -> Dict[str, Any]:
        """Perform chi-square test of independence"""
        chi2, p_value, dof, expected = chi2_contingency(contingency_table.values)
        
        # Calculate Cramér's V
        n = contingency_table.values.sum()
        min_dim = min(contingency_table.shape[0] - 1, contingency_table.shape[1] - 1)
        cramers_v = np.sqrt(chi2 / (n * min_dim))
        
        return {
            'chi2': chi2,
            'p_value': p_value,
            'degrees_of_freedom': dof,
            'cramers_v': cramers_v,
            'significant': p_value < 0.05
        }
    
    def correlation_analysis(self, hhi_district: Dict[str, float], 
                           hhi_contractor: Dict[str, float]) -> Dict[str, Any]:
        """Correlate HHI values to test concentration pattern similarity"""
        
        # For each contractor-district pair, get both HHI values
        pairs = []
        for contractor in self.contractor_district_matrix:
            for district in self.contractor_district_matrix[contractor]:
                count = self.contractor_district_matrix[contractor][district]
                if count > 0:  # Only pairs with actual projects
                    pairs.append({
                        'contractor': contractor,
                        'district': district,
                        'projects': count,
                        'hhi_contractor': hhi_contractor.get(contractor, 0),
                        'hhi_district': hhi_district.get(district, 0)
                    })
        
        df = pd.DataFrame(pairs)
        
        # Calculate correlations
        if len(df) > 0:
            pearson_r, pearson_p = pearsonr(df['hhi_contractor'], df['hhi_district'])
            spearman_r, spearman_p = spearmanr(df['hhi_contractor'], df['hhi_district'])
        else:
            pearson_r = pearson_p = spearman_r = spearman_p = 0.0
        
        return {
            'pearson_correlation': pearson_r,
            'pearson_p_value': pearson_p,
            'spearman_correlation': spearman_r,
            'spearman_p_value': spearman_p,
            'sample_size': len(df),
            'significant': pearson_p < 0.05
        }
    
    def print_results(self):
        """Print comprehensive analysis results"""
        print("\n" + "="*80)
        print("📊 CONTRACTOR-DISTRICT CORRELATION ANALYSIS")
        print("="*80)
        
        # Overall statistics
        print("\n📈 OVERALL STATISTICS")
        print(f"   Total Projects: {self.total_projects:,}")
        print(f"   Unique Contractors: {len(self.contractor_totals):,}")
        print(f"   Unique Districts: {len(self.district_totals):,}")
        print(f"   Average Projects per Contractor: {self.total_projects / len(self.contractor_totals):.2f}")
        print(f"   Average Projects per District: {self.total_projects / len(self.district_totals):.2f}")
        
        # HHI Analysis
        print("\n📊 CONCENTRATION ANALYSIS (HHI)")
        print("-" * 80)
        
        hhi_by_district = self.calculate_hhi_by_district()
        hhi_by_contractor = self.calculate_hhi_by_contractor()
        
        avg_hhi_district = np.mean(list(hhi_by_district.values()))
        avg_hhi_contractor = np.mean(list(hhi_by_contractor.values()))
        
        print(f"\n   Average HHI by District: {avg_hhi_district:.2f}")
        print(f"   Average HHI by Contractor: {avg_hhi_contractor:.2f}")
        print(f"\n   HHI Interpretation:")
        print(f"   < 1,500: Competitive market")
        print(f"   1,500-2,500: Moderate concentration")
        print(f"   > 2,500: High concentration")
        
        # Top concentrated districts
        print(f"\n   🏆 TOP 10 MOST CONCENTRATED DISTRICTS (by contractor HHI):")
        top_districts = sorted(hhi_by_district.items(), key=lambda x: x[1], reverse=True)[:10]
        for i, (district, hhi) in enumerate(top_districts, 1):
            projects = self.district_totals[district]
            print(f"   {i:2d}. {district[:50]:50s} HHI: {hhi:7.2f} ({projects:4d} projects)")
        
        # Top concentrated contractors
        print(f"\n   🏆 TOP 10 MOST CONCENTRATED CONTRACTORS (by district HHI):")
        top_contractors = sorted(hhi_by_contractor.items(), key=lambda x: x[1], reverse=True)[:10]
        for i, (contractor, hhi) in enumerate(top_contractors, 1):
            projects = self.contractor_totals[contractor]
            print(f"   {i:2d}. {contractor[:50]:50s} HHI: {hhi:7.2f} ({projects:4d} projects)")
        
        # Gini Coefficient
        print("\n📊 INEQUALITY ANALYSIS (Gini Coefficient)")
        print("-" * 80)
        
        contractor_gini = self.calculate_gini(list(self.contractor_totals.values()))
        district_gini = self.calculate_gini(list(self.district_totals.values()))
        
        print(f"   Gini Coefficient - Contractor Distribution: {contractor_gini:.4f}")
        print(f"   Gini Coefficient - District Distribution: {district_gini:.4f}")
        print(f"\n   Gini Interpretation:")
        print(f"   0.0: Perfect equality (all have same number of projects)")
        print(f"   1.0: Perfect inequality (one entity has all projects)")
        
        # Chi-square Test
        print("\n📊 INDEPENDENCE TEST (Chi-square)")
        print("-" * 80)
        
        contingency_table, contractors, districts = self.build_contingency_table()
        chi_results = self.chi_square_test(contingency_table)
        
        print(f"   Chi-square statistic: {chi_results['chi2']:.2f}")
        print(f"   P-value: {chi_results['p_value']:.6f}")
        print(f"   Degrees of freedom: {chi_results['degrees_of_freedom']}")
        print(f"   Cramér's V: {chi_results['cramers_v']:.4f}")
        print(f"\n   Result: Contractors and Districts are {'DEPENDENT' if chi_results['significant'] else 'INDEPENDENT'}")
        print(f"   (p < 0.05 indicates significant relationship)")
        print(f"\n   Cramér's V Interpretation:")
        print(f"   0.0-0.1: Weak association")
        print(f"   0.1-0.3: Moderate association")
        print(f"   > 0.3: Strong association")
        
        # Correlation Analysis
        print("\n📊 CONCENTRATION PATTERN CORRELATION")
        print("-" * 80)
        
        corr_results = self.correlation_analysis(hhi_by_district, hhi_by_contractor)
        
        print(f"   Pearson Correlation: {corr_results['pearson_correlation']:.4f}")
        print(f"   Pearson P-value: {corr_results['pearson_p_value']:.6f}")
        print(f"   Spearman Correlation: {corr_results['spearman_correlation']:.4f}")
        print(f"   Spearman P-value: {corr_results['spearman_p_value']:.6f}")
        print(f"   Sample Size: {corr_results['sample_size']:,} contractor-district pairs")
        print(f"\n   Result: Concentration patterns are {'CORRELATED' if corr_results['significant'] else 'NOT CORRELATED'}")
        print(f"   (p < 0.05 indicates significant correlation)")
        
        # Hypothesis Test Result
        print("\n" + "="*80)
        print("🎯 HYPOTHESIS TEST RESULTS")
        print("="*80)
        print(f"\n   Hypothesis: Projects are concentrated similarly across contractors and districts")
        print(f"\n   Evidence:")
        print(f"   1. Average HHI District: {avg_hhi_district:.2f} vs Contractor: {avg_hhi_contractor:.2f}")
        
        hhi_similar = abs(avg_hhi_district - avg_hhi_contractor) < 500
        print(f"      ➜ Concentration levels are {'SIMILAR' if hhi_similar else 'DIFFERENT'}")
        
        print(f"\n   2. Gini Coefficient - Contractor: {contractor_gini:.4f} vs District: {district_gini:.4f}")
        gini_similar = abs(contractor_gini - district_gini) < 0.1
        print(f"      ➜ Inequality patterns are {'SIMILAR' if gini_similar else 'DIFFERENT'}")
        
        print(f"\n   3. Chi-square test shows contractors and districts are {'DEPENDENT' if chi_results['significant'] else 'INDEPENDENT'}")
        print(f"      Association strength (Cramér's V): {chi_results['cramers_v']:.4f}")
        
        print(f"\n   4. Correlation between concentration patterns: {corr_results['pearson_correlation']:.4f}")
        print(f"      ➜ Patterns are {'CORRELATED' if corr_results['significant'] else 'NOT CORRELATED'}")
        
        # Final verdict
        evidence_count = sum([
            hhi_similar,
            gini_similar,
            chi_results['significant'],
            corr_results['significant']
        ])
        
        print(f"\n   {'='*76}")
        if evidence_count >= 3:
            print(f"   ✅ HYPOTHESIS SUPPORTED: Strong evidence that projects are concentrated")
            print(f"      similarly across contractors and districts ({evidence_count}/4 tests support)")
        elif evidence_count >= 2:
            print(f"   ⚠️  HYPOTHESIS PARTIALLY SUPPORTED: Moderate evidence ({evidence_count}/4 tests support)")
        else:
            print(f"   ❌ HYPOTHESIS NOT SUPPORTED: Weak evidence ({evidence_count}/4 tests support)")
        print(f"   {'='*76}")
        
        # Top contractor-district pairs
        print("\n📊 TOP 20 CONTRACTOR-DISTRICT PAIRS (by project count)")
        print("-" * 80)
        
        pairs = []
        for contractor in self.contractor_district_matrix:
            for district, count in self.contractor_district_matrix[contractor].items():
                pairs.append((contractor, district, count))
        
        pairs.sort(key=lambda x: x[2], reverse=True)
        
        for i, (contractor, district, count) in enumerate(pairs[:20], 1):
            contractor_share = (count / self.contractor_totals[contractor]) * 100
            district_share = (count / self.district_totals[district]) * 100
            print(f"   {i:2d}. {count:4d} projects")
            print(f"       Contractor: {contractor[:60]}")
            print(f"       District: {district[:60]}")
            print(f"       ({contractor_share:.1f}% of contractor's projects, {district_share:.1f}% of district's projects)")
            print()
        
        print("="*80)
        print("✅ Analysis Complete!")
        print("="*80)
    
    async def save_results(self, output_file: str = "static/data/contractor_district_correlation.json"):
        """Save detailed results to JSON file"""
        
        hhi_by_district = self.calculate_hhi_by_district()
        hhi_by_contractor = self.calculate_hhi_by_contractor()
        contingency_table, _, _ = self.build_contingency_table()
        chi_results = self.chi_square_test(contingency_table)
        corr_results = self.correlation_analysis(hhi_by_district, hhi_by_contractor)
        
        # Build comprehensive results
        results = {
            'metadata': {
                'generated_at': pd.Timestamp.now().isoformat(),
                'total_projects': self.total_projects,
                'unique_contractors': len(self.contractor_totals),
                'unique_districts': len(self.district_totals)
            },
            'concentration': {
                'avg_hhi_district': float(np.mean(list(hhi_by_district.values()))),
                'avg_hhi_contractor': float(np.mean(list(hhi_by_contractor.values()))),
                'gini_contractor': float(self.calculate_gini(list(self.contractor_totals.values()))),
                'gini_district': float(self.calculate_gini(list(self.district_totals.values()))),
                'hhi_by_district': {k: float(v) for k, v in sorted(hhi_by_district.items(), key=lambda x: x[1], reverse=True)},
                'hhi_by_contractor': {k: float(v) for k, v in sorted(hhi_by_contractor.items(), key=lambda x: x[1], reverse=True)[:100]}  # Top 100 only
            },
            'independence_test': {
                'chi_square': float(chi_results['chi2']),
                'p_value': float(chi_results['p_value']),
                'cramers_v': float(chi_results['cramers_v']),
                'significant': bool(chi_results['significant'])
            },
            'correlation': {
                'pearson_r': float(corr_results['pearson_correlation']),
                'pearson_p': float(corr_results['pearson_p_value']),
                'spearman_r': float(corr_results['spearman_correlation']),
                'spearman_p': float(corr_results['spearman_p_value']),
                'significant': bool(corr_results['significant'])
            }
        }
        
        # Save to file
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Results saved to: {output_path}")


async def main():
    """Main execution"""
    analyzer = ContractorDistrictAnalyzer()
    
    # Load data
    await analyzer.load_data()
    
    # Print results
    analyzer.print_results()
    
    # Save results
    await analyzer.save_results()


if __name__ == "__main__":
    asyncio.run(main())

