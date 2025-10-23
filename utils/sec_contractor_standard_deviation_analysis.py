#!/usr/bin/env python3
"""
SEC Contractor Project Distribution Standard Deviation Analysis

This script analyzes contractor project counts from the SEC database
and generates standard deviation analysis for the /contractors page.

Usage:
    python3 utils/sec_contractor_standard_deviation_analysis.py
"""

import asyncio
import asyncpg
import json
import statistics
import os
from pathlib import Path
from datetime import datetime

async def get_sec_contractor_project_counts():
    """Get contractor project counts from SEC database"""
    print("🔍 Fetching SEC contractor project counts from database...")
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_SEC', 'sec')
    )
    
    try:
        # Query to get contractor project counts from SEC database
        # This will count projects across all databases (Flood, DIME, PhilGEPS) for each contractor
        query = """
        WITH contractor_projects AS (
            -- Count projects from all sources for each contractor
            SELECT 
                c.contractor_name,
                COUNT(DISTINCT 
                    CASE 
                        WHEN f.id IS NOT NULL THEN 'flood_' || f.id::text
                        WHEN d.id IS NOT NULL THEN 'dime_' || d.id::text  
                        WHEN p.id IS NOT NULL THEN 'philgeps_' || p.id::text
                    END
                ) as project_count
            FROM contractors c
            LEFT JOIN flood_control f ON LOWER(TRIM(c.contractor_name)) = LOWER(TRIM(f.contractor))
            LEFT JOIN dime d ON LOWER(TRIM(c.contractor_name)) = LOWER(TRIM(UNNEST(d.contractors)))
            LEFT JOIN philgeps p ON LOWER(TRIM(c.contractor_name)) = LOWER(TRIM(p.awardee_name))
            WHERE c.contractor_name IS NOT NULL 
                AND TRIM(c.contractor_name) != ''
            GROUP BY c.contractor_name
            HAVING COUNT(DISTINCT 
                CASE 
                    WHEN f.id IS NOT NULL THEN 'flood_' || f.id::text
                    WHEN d.id IS NOT NULL THEN 'dime_' || d.id::text  
                    WHEN p.id IS NOT NULL THEN 'philgeps_' || p.id::text
                END
            ) > 0
        )
        SELECT contractor_name, project_count
        FROM contractor_projects
        ORDER BY project_count DESC;
        """
        
        rows = await conn.fetch(query)
        contractor_counts = {row['contractor_name']: row['project_count'] for row in rows}
        
        print(f"✅ Found {len(contractor_counts)} SEC contractors with project data")
        return contractor_counts
        
    except Exception as e:
        print(f"❌ Error fetching SEC contractor data: {e}")
        return {}
    finally:
        await conn.close()

def calculate_standard_deviation_analysis(contractor_counts):
    """Calculate standard deviation analysis for contractor project counts"""
    print("📈 Calculating standard deviation analysis...")
    
    if not contractor_counts:
        return None
    
    # Get project counts as a list
    project_counts = list(contractor_counts.values())
    
    # Calculate basic statistics
    total_contractors = len(project_counts)
    mean_projects = statistics.mean(project_counts)
    median_projects = statistics.median(project_counts)
    std_deviation = statistics.stdev(project_counts) if len(project_counts) > 1 else 0
    min_projects = min(project_counts)
    max_projects = max(project_counts)
    
    # Calculate standard deviation ranges
    std_bars = {
        '1sd': {
            'label': '1 Standard Deviation',
            'lower': mean_projects - std_deviation,
            'upper': mean_projects + std_deviation,
            'color': '#28a745',
            'percentage': 68.27
        },
        '1_5sd': {
            'label': '1.5 Standard Deviations', 
            'lower': mean_projects - (1.5 * std_deviation),
            'upper': mean_projects + (1.5 * std_deviation),
            'color': '#ffc107',
            'percentage': 86.64
        },
        '2sd': {
            'label': '2 Standard Deviations',
            'lower': mean_projects - (2 * std_deviation),
            'upper': mean_projects + (2 * std_deviation),
            'color': '#fd7e14',
            'percentage': 95.45
        },
        '2_5sd': {
            'label': '2.5 Standard Deviations',
            'lower': mean_projects - (2.5 * std_deviation),
            'upper': mean_projects + (2.5 * std_deviation),
            'color': '#dc3545',
            'percentage': 98.76
        },
        '3sd': {
            'label': '3 Standard Deviations',
            'lower': mean_projects - (3 * std_deviation),
            'upper': mean_projects + (3 * std_deviation),
            'color': '#6f42c1',
            'percentage': 99.73
        }
    }
    
    # Categorize contractors into standard deviation ranges
    contractor_categories = {
        'within_1sd': {'count': 0, 'contractors': []},
        'within_1_5sd': {'count': 0, 'contractors': []},
        'within_2sd': {'count': 0, 'contractors': []},
        'within_2_5sd': {'count': 0, 'contractors': []},
        'within_3sd': {'count': 0, 'contractors': []},
        'outliers': {'count': 0, 'contractors': []}
    }
    
    # Categorize each contractor
    for contractor, count in contractor_counts.items():
        if count >= std_bars['1sd']['lower'] and count <= std_bars['1sd']['upper']:
            contractor_categories['within_1sd']['count'] += 1
            contractor_categories['within_1sd']['contractors'].append(contractor)
        elif count >= std_bars['1_5sd']['lower'] and count <= std_bars['1_5sd']['upper']:
            contractor_categories['within_1_5sd']['count'] += 1
            contractor_categories['within_1_5sd']['contractors'].append(contractor)
        elif count >= std_bars['2sd']['lower'] and count <= std_bars['2sd']['upper']:
            contractor_categories['within_2sd']['count'] += 1
            contractor_categories['within_2sd']['contractors'].append(contractor)
        elif count >= std_bars['2_5sd']['lower'] and count <= std_bars['2_5sd']['upper']:
            contractor_categories['within_2_5sd']['count'] += 1
            contractor_categories['within_2_5sd']['contractors'].append(contractor)
        elif count >= std_bars['3sd']['lower'] and count <= std_bars['3sd']['upper']:
            contractor_categories['within_3sd']['count'] += 1
            contractor_categories['within_3sd']['contractors'].append(contractor)
        else:
            contractor_categories['outliers']['count'] += 1
            contractor_categories['outliers']['contractors'].append(contractor)
    
    return {
        'basic_stats': {
            'total_contractors': total_contractors,
            'mean': mean_projects,
            'median': median_projects,
            'standard_deviation': std_deviation,
            'min': min_projects,
            'max': max_projects,
            'range': max_projects - min_projects
        },
        'standard_deviation_bars': std_bars,
        'distribution_stats': contractor_categories
    }

def generate_chart_data(analysis):
    """Generate chart data for visualization"""
    print("📊 Generating visualization data...")
    
    if not analysis:
        return {}
    
    std_bars = analysis['standard_deviation_bars']
    distribution = analysis['distribution_stats']
    
    # Create chart datasets
    chart_data = {
        'labels': [
            '1 Standard Deviation',
            '1.5 Standard Deviations', 
            '2 Standard Deviations',
            '2.5 Standard Deviations',
            '3 Standard Deviations',
            'Outliers'
        ],
        'datasets': [
            {
                'label': 'Number of Contractors',
                'data': [
                    distribution['within_1sd']['count'],
                    distribution['within_1_5sd']['count'],
                    distribution['within_2sd']['count'],
                    distribution['within_2_5sd']['count'],
                    distribution['within_3sd']['count'],
                    distribution['outliers']['count']
                ],
                'backgroundColor': [
                    std_bars['1sd']['color'],
                    std_bars['1_5sd']['color'],
                    std_bars['2sd']['color'],
                    std_bars['2_5sd']['color'],
                    std_bars['3sd']['color'],
                    '#e83e8c'  # Pink for outliers
                ],
                'borderColor': [
                    '#1e7e34', '#d39e00', '#dc6903', '#c82333', '#5a2d91', '#c2185b'
                ],
                'borderWidth': 2
            }
        ]
    }
    
    return chart_data

async def main():
    """Main function to run the analysis"""
    print("📊 Starting SEC Contractor Project Distribution Standard Deviation Analysis...")
    
    # Get contractor project counts
    contractor_counts = await get_sec_contractor_project_counts()
    
    if not contractor_counts:
        print("❌ No contractor data found")
        return
    
    # Calculate standard deviation analysis
    analysis = calculate_standard_deviation_analysis(contractor_counts)
    
    if not analysis:
        print("❌ Failed to calculate analysis")
        return
    
    # Generate chart data
    chart_data = generate_chart_data(analysis)
    
    # Create output data structure
    output_data = {
        'metadata': {
            'generated_at': datetime.now().isoformat(),
            'analysis_type': 'SEC Contractor Standard Deviation Analysis',
            'data_source': 'SEC database with cross-database project counts',
            'total_contractors_analyzed': analysis['basic_stats']['total_contractors']
        },
        'analysis': analysis,
        'chart_data': chart_data
    }
    
    # Save to JSON file
    output_file = Path("static/data/sec_contractor_standard_deviation.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Analysis complete! Results saved to {output_file}")
    
    # Print summary
    basic_stats = analysis['basic_stats']
    distribution = analysis['distribution_stats']
    
    print(f"\n📊 Summary Statistics:")
    print(f"   Total Contractors: {basic_stats['total_contractors']}")
    print(f"   Mean Projects: {basic_stats['mean']:.2f}")
    print(f"   Median Projects: {basic_stats['median']:.2f}")
    print(f"   Standard Deviation: {basic_stats['standard_deviation']:.2f}")
    print(f"   Range: {basic_stats['min']} - {basic_stats['max']}")
    
    print(f"\n📏 Standard Deviation Bars:")
    for key, bar in analysis['standard_deviation_bars'].items():
        print(f"   {bar['label']}: {bar['lower']:.1f} - {bar['upper']:.1f} ({bar['percentage']:.1f}% of contractors fall within this range)")
    
    print(f"\n📈 Distribution:")
    print(f"   Within 1SD: {distribution['within_1sd']['count']} contractors ({distribution['within_1sd']['count']/basic_stats['total_contractors']*100:.1f}%)")
    print(f"   Within 1.5SD: {distribution['within_1_5sd']['count']} contractors ({distribution['within_1_5sd']['count']/basic_stats['total_contractors']*100:.1f}%)")
    print(f"   Within 2SD: {distribution['within_2sd']['count']} contractors ({distribution['within_2sd']['count']/basic_stats['total_contractors']*100:.1f}%)")
    print(f"   Within 2.5SD: {distribution['within_2_5sd']['count']} contractors ({distribution['within_2_5sd']['count']/basic_stats['total_contractors']*100:.1f}%)")
    print(f"   Within 3SD: {distribution['within_3sd']['count']} contractors ({distribution['within_3sd']['count']/basic_stats['total_contractors']*100:.1f}%)")
    print(f"   Outliers: {distribution['outliers']['count']} contractors ({distribution['outliers']['count']/basic_stats['total_contractors']*100:.1f}%)")

if __name__ == "__main__":
    asyncio.run(main())
