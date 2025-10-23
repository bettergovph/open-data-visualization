#!/usr/bin/env python3
"""
Contractor Project Distribution Standard Deviation Analysis

This script analyzes contractor project counts and generates standard deviation
analysis with bars for 1SD, 1.5SD, 2SD, 2.5SD, and 3SD.

Usage:
    python3 utils/contractor_standard_deviation_analysis.py
"""

import json
import math
import statistics
from pathlib import Path
from datetime import datetime
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def get_contractor_project_counts():
    """Get contractor project counts from the database"""
    try:
        # Connect to the database
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_SEC', 'sec')
        )
        
        # Get contractor project counts
        contractors = await conn.fetch("""
            SELECT contractor_name, project_count
            FROM contractors 
            WHERE project_count IS NOT NULL AND project_count > 0
            ORDER BY project_count DESC
        """)
        
        await conn.close()
        
        return [(row['contractor_name'], row['project_count']) for row in contractors]
        
    except Exception as e:
        print(f"Error fetching contractor data: {e}")
        return []

def calculate_standard_deviation_analysis(contractor_data):
    """Calculate standard deviation analysis for contractor project counts"""
    if not contractor_data:
        return None
    
    # Extract project counts
    project_counts = [count for _, count in contractor_data]
    
    # Calculate basic statistics
    mean = statistics.mean(project_counts)
    std_dev = statistics.stdev(project_counts) if len(project_counts) > 1 else 0
    median = statistics.median(project_counts)
    mode = statistics.mode(project_counts) if project_counts else 0
    
    # Calculate standard deviation bars
    std_bars = {
        '1SD': {
            'lower': mean - std_dev,
            'upper': mean + std_dev,
            'label': '1 Standard Deviation',
            'color': '#28a745',  # Green
            'description': '68% of contractors fall within this range'
        },
        '1.5SD': {
            'lower': mean - (1.5 * std_dev),
            'upper': mean + (1.5 * std_dev),
            'label': '1.5 Standard Deviations',
            'color': '#ffc107',  # Yellow
            'description': '87% of contractors fall within this range'
        },
        '2SD': {
            'lower': mean - (2 * std_dev),
            'upper': mean + (2 * std_dev),
            'label': '2 Standard Deviations',
            'color': '#fd7e14',  # Orange
            'description': '95% of contractors fall within this range'
        },
        '2.5SD': {
            'lower': mean - (2.5 * std_dev),
            'upper': mean + (2.5 * std_dev),
            'label': '2.5 Standard Deviations',
            'color': '#dc3545',  # Red
            'description': '99% of contractors fall within this range'
        },
        '3SD': {
            'lower': mean - (3 * std_dev),
            'upper': mean + (3 * std_dev),
            'label': '3 Standard Deviations',
            'color': '#6f42c1',  # Purple
            'description': '99.7% of contractors fall within this range'
        }
    }
    
    # Categorize contractors by standard deviation ranges
    contractor_categories = {
        'within_1sd': [],
        'within_1_5sd': [],
        'within_2sd': [],
        'within_2_5sd': [],
        'within_3sd': [],
        'outliers': []
    }
    
    for contractor_name, count in contractor_data:
        if count >= std_bars['1SD']['lower'] and count <= std_bars['1SD']['upper']:
            contractor_categories['within_1sd'].append((contractor_name, count))
        elif count >= std_bars['1.5SD']['lower'] and count <= std_bars['1.5SD']['upper']:
            contractor_categories['within_1_5sd'].append((contractor_name, count))
        elif count >= std_bars['2SD']['lower'] and count <= std_bars['2SD']['upper']:
            contractor_categories['within_2sd'].append((contractor_name, count))
        elif count >= std_bars['2.5SD']['lower'] and count <= std_bars['2.5SD']['upper']:
            contractor_categories['within_2_5sd'].append((contractor_name, count))
        elif count >= std_bars['3SD']['lower'] and count <= std_bars['3SD']['upper']:
            contractor_categories['within_3sd'].append((contractor_name, count))
        else:
            contractor_categories['outliers'].append((contractor_name, count))
    
    # Calculate distribution statistics
    total_contractors = len(contractor_data)
    distribution_stats = {
        'within_1sd': {
            'count': len(contractor_categories['within_1sd']),
            'percentage': (len(contractor_categories['within_1sd']) / total_contractors) * 100
        },
        'within_1_5sd': {
            'count': len(contractor_categories['within_1_5sd']),
            'percentage': (len(contractor_categories['within_1_5sd']) / total_contractors) * 100
        },
        'within_2sd': {
            'count': len(contractor_categories['within_2sd']),
            'percentage': (len(contractor_categories['within_2sd']) / total_contractors) * 100
        },
        'within_2_5sd': {
            'count': len(contractor_categories['within_2_5sd']),
            'percentage': (len(contractor_categories['within_2_5sd']) / total_contractors) * 100
        },
        'within_3sd': {
            'count': len(contractor_categories['within_3sd']),
            'percentage': (len(contractor_categories['within_3sd']) / total_contractors) * 100
        },
        'outliers': {
            'count': len(contractor_categories['outliers']),
            'percentage': (len(contractor_categories['outliers']) / total_contractors) * 100
        }
    }
    
    return {
        'basic_stats': {
            'total_contractors': total_contractors,
            'mean': round(mean, 2),
            'median': round(median, 2),
            'mode': mode,
            'standard_deviation': round(std_dev, 2),
            'min_projects': min(project_counts),
            'max_projects': max(project_counts),
            'range': max(project_counts) - min(project_counts)
        },
        'standard_deviation_bars': std_bars,
        'contractor_categories': contractor_categories,
        'distribution_stats': distribution_stats,
        'generated_at': datetime.now().isoformat(),
        'analysis_version': '1.0'
    }

def generate_visualization_data(analysis_data):
    """Generate data for visualization charts"""
    if not analysis_data:
        return None
    
    std_bars = analysis_data['standard_deviation_bars']
    basic_stats = analysis_data['basic_stats']
    
    # Create chart data for standard deviation bars
    chart_data = {
        'labels': ['Mean', '1SD', '1.5SD', '2SD', '2.5SD', '3SD'],
        'datasets': [
            {
                'label': 'Lower Bound',
                'data': [
                    basic_stats['mean'],
                    std_bars['1SD']['lower'],
                    std_bars['1.5SD']['lower'],
                    std_bars['2SD']['lower'],
                    std_bars['2.5SD']['lower'],
                    std_bars['3SD']['lower']
                ],
                'backgroundColor': [bar['color'] for bar in std_bars.values()],
                'borderColor': [bar['color'] for bar in std_bars.values()],
                'borderWidth': 2
            },
            {
                'label': 'Upper Bound',
                'data': [
                    basic_stats['mean'],
                    std_bars['1SD']['upper'],
                    std_bars['1.5SD']['upper'],
                    std_bars['2SD']['upper'],
                    std_bars['2.5SD']['upper'],
                    std_bars['3SD']['upper']
                ],
                'backgroundColor': [bar['color'] for bar in std_bars.values()],
                'borderColor': [bar['color'] for bar in std_bars.values()],
                'borderWidth': 2
            }
        ]
    }
    
    return chart_data

async def main():
    """Main function to run the analysis"""
    print("📊 Starting Contractor Project Distribution Standard Deviation Analysis...")
    
    # Get contractor data
    print("🔍 Fetching contractor project counts from database...")
    contractor_data = await get_contractor_project_counts()
    
    if not contractor_data:
        print("❌ No contractor data found")
        return
    
    print(f"✅ Found {len(contractor_data)} contractors with project data")
    
    # Calculate standard deviation analysis
    print("📈 Calculating standard deviation analysis...")
    analysis_data = calculate_standard_deviation_analysis(contractor_data)
    
    if not analysis_data:
        print("❌ Failed to calculate analysis")
        return
    
    # Generate visualization data
    print("📊 Generating visualization data...")
    chart_data = generate_visualization_data(analysis_data)
    
    # Save analysis results
    output_file = Path("static/data/contractor_standard_deviation.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    results = {
        'analysis': analysis_data,
        'chart_data': chart_data,
        'metadata': {
            'generated_at': datetime.now().isoformat(),
            'total_contractors': len(contractor_data),
            'analysis_version': '1.0',
            'description': 'Contractor project distribution standard deviation analysis'
        }
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Analysis complete! Results saved to {output_file}")
    
    # Print summary
    basic_stats = analysis_data['basic_stats']
    print(f"\n📊 Summary Statistics:")
    print(f"   Total Contractors: {basic_stats['total_contractors']}")
    print(f"   Mean Projects: {basic_stats['mean']}")
    print(f"   Median Projects: {basic_stats['median']}")
    print(f"   Standard Deviation: {basic_stats['standard_deviation']}")
    print(f"   Range: {basic_stats['min_projects']} - {basic_stats['max_projects']}")
    
    # Print standard deviation bars
    print(f"\n📏 Standard Deviation Bars:")
    for key, bar in analysis_data['standard_deviation_bars'].items():
        print(f"   {bar['label']}: {bar['lower']:.1f} - {bar['upper']:.1f} ({bar['description']})")
    
    # Print distribution
    print(f"\n📈 Distribution:")
    for category, stats in analysis_data['distribution_stats'].items():
        print(f"   {category.replace('_', ' ').title()}: {stats['count']} contractors ({stats['percentage']:.1f}%)")

if __name__ == "__main__":
    asyncio.run(main())
