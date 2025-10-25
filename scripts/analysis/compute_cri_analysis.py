#!/usr/bin/env python3
"""
Compute EOGO CRI Analysis Offline
Generates cached JSON files for Political HHI, CRI Analysis, and Poverty Correlation
"""

import json
import os
import asyncio
import asyncpg
from datetime import datetime
import requests

class CRIAnalyzer:
    def __init__(self):
        self.db_config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'bettergov',
            'user': 'bettergov',
            'password': 'bettergov'
        }
        
    async def load_dynasty_data(self):
        """Load dynasty surnames data from cache"""
        cache_file = "static/data/dynasty_surnames_cache.json"
        if not os.path.exists(cache_file):
            print(f"❌ Dynasty cache not found: {cache_file}")
            return []
            
        with open(cache_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('surnames', [])
    
    async def load_philgeps_data(self):
        """Load PhilGEPS contractor data"""
        try:
            # Try to get data from API
            response = requests.get('http://172.30.147.217:8001/api/philgeps/top?limit=1000')
            if response.status_code == 200:
                data = response.json()
                contractors = data.get('contractors', [])
                print(f"📊 PhilGEPS API data structure: {list(contractors[0].keys()) if contractors else 'No data'}")
                return contractors
        except Exception as e:
            print(f"⚠️ API error: {e}")
        
        # Fallback: load from database
        try:
            conn = await asyncpg.connect(**self.db_config)
            query = """
                SELECT contractor_name, area_of_delivery, COUNT(*) as project_count
                FROM philgeps_contracts 
                WHERE area_of_delivery IS NOT NULL
                GROUP BY contractor_name, area_of_delivery
                ORDER BY project_count DESC
                LIMIT 1000
            """
            rows = await conn.fetch(query)
            await conn.close()
            
            contractors = [dict(row) for row in rows]
            print(f"📊 PhilGEPS DB data structure: {list(contractors[0].keys()) if contractors else 'No data'}")
            return contractors
        except Exception as e:
            print(f"❌ Error loading PhilGEPS data: {e}")
            return []
    
    async def load_poverty_data(self):
        """Load poverty data from JSON file"""
        poverty_file = "database/poverty.json"
        if not os.path.exists(poverty_file):
            print(f"❌ Poverty data not found: {poverty_file}")
            return []
            
        with open(poverty_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def calculate_political_hhi(self, dynasty_data):
        """Calculate Political HHI for each province"""
        province_stats = {}
        
        for surname in dynasty_data:
            province = surname['province']
            if province not in province_stats:
                province_stats[province] = {
                    'total': 0,
                    'surnames': {}
                }
            province_stats[province]['total'] += surname['total_count']
            province_stats[province]['surnames'][surname['surname']] = surname['total_count']
        
        # Calculate HHI for each province
        hhi_results = []
        for province, stats in province_stats.items():
            hhi = 0
            for count in stats['surnames'].values():
                share = count / stats['total']
                hhi += share * share
            
            dynasty_size = max(stats['surnames'].values()) if stats['surnames'] else 0
            
            hhi_results.append({
                'province': province,
                'hhi': round(hhi * 100, 1),
                'total_politicians': stats['total'],
                'unique_surnames': len(stats['surnames']),
                'dynasty_size': dynasty_size
            })
        
        return sorted(hhi_results, key=lambda x: x['hhi'], reverse=True)
    
    def calculate_contractor_hhi(self, philgeps_data):
        """Calculate Contractor HHI - simplified since no geographic data available"""
        # Since PhilGEPS data doesn't have geographic information,
        # we'll create a simplified contractor concentration analysis
        total_projects = sum(contractor.get('count', 0) for contractor in philgeps_data)
        contractor_counts = {}
        
        for contractor in philgeps_data:
            contractor_name = contractor.get('contractor', 'Unknown')
            count = contractor.get('count', 0)
            contractor_counts[contractor_name] = count
        
        # Calculate overall contractor HHI
        hhi = 0
        for count in contractor_counts.values():
            share = count / total_projects if total_projects > 0 else 0
            hhi += share * share
        
        return [{
            'province': 'National',
            'hhi': round(hhi * 100, 1),
            'total_projects': total_projects,
            'unique_contractors': len(contractor_counts)
        }]
    
    def process_poverty_data(self, poverty_data):
        """Process poverty data for correlation analysis"""
        poverty_results = []
        
        for region in poverty_data:
            if 'provinces' in region:
                for province in region['provinces']:
                    poverty_results.append({
                        'province': province['province'],
                        'poverty_rate': province['poverty']
                    })
        
        return sorted(poverty_results, key=lambda x: x['poverty_rate'], reverse=True)
    
    def calculate_comprehensive_cri(self, dynasty_data, philgeps_data, poverty_data):
        """Calculate comprehensive CRI scores combining all factors"""
        # Process all data sources
        political_hhi = self.calculate_political_hhi(dynasty_data)
        contractor_hhi = self.calculate_contractor_hhi(philgeps_data)
        poverty_data_processed = self.process_poverty_data(poverty_data)
        
        # Create province mapping
        province_stats = {}
        
        # Add political data
        for item in political_hhi:
            province = item['province']
            province_stats[province] = {
                'political_hhi': item['hhi'],
                'dynasty_size': item['dynasty_size'],
                'total_politicians': item['total_politicians'],
                'contractor_hhi': 0,
                'total_projects': 0,
                'poverty_rate': 0
            }
        
        # Add contractor data (simplified - no geographic breakdown)
        national_contractor_hhi = contractor_hhi[0]['hhi'] if contractor_hhi else 0
        for province in province_stats:
            province_stats[province]['contractor_hhi'] = national_contractor_hhi
            province_stats[province]['total_projects'] = contractor_hhi[0]['total_projects'] if contractor_hhi else 0
        
        # Add poverty data
        for item in poverty_data_processed:
            province = item['province'].upper()
            if province in province_stats:
                province_stats[province]['poverty_rate'] = item['poverty_rate']
        
        # Calculate CRI scores (EOGO methodology)
        cri_results = []
        for province, stats in province_stats.items():
            # CRI Score = (Political HHI * 0.4) + (Dynasty Size * 0.3) + (Contractor HHI * 0.2) + (Poverty Rate * 0.1)
            cri_score = (stats['political_hhi'] * 0.4) + (stats['dynasty_size'] * 0.3) + (stats['contractor_hhi'] * 0.2) + (stats['poverty_rate'] * 0.1)
            
            cri_results.append({
                'province': province,
                'cri_score': round(cri_score, 1),
                'political_hhi': stats['political_hhi'],
                'dynasty_size': stats['dynasty_size'],
                'contractor_hhi': stats['contractor_hhi'],
                'poverty_rate': stats['poverty_rate'],
                'total_politicians': stats['total_politicians'],
                'total_projects': stats['total_projects']
            })
        
        return sorted(cri_results, key=lambda x: x['cri_score'], reverse=True)
    
    async def generate_cri_cache(self):
        """Generate all CRI analysis cache files"""
        print("🔄 Loading data sources...")
        
        # Load all data sources
        dynasty_data = await self.load_dynasty_data()
        philgeps_data = await self.load_philgeps_data()
        poverty_data = await self.load_poverty_data()
        
        print(f"✅ Loaded {len(dynasty_data)} dynasty records")
        print(f"✅ Loaded {len(philgeps_data)} PhilGEPS records")
        print(f"✅ Loaded {len(poverty_data)} poverty regions")
        
        # Calculate Political HHI
        print("🔄 Computing Political HHI...")
        political_hhi = self.calculate_political_hhi(dynasty_data)
        
        # Calculate Contractor HHI
        print("🔄 Computing Contractor HHI...")
        contractor_hhi = self.calculate_contractor_hhi(philgeps_data)
        
        # Process Poverty Data
        print("🔄 Processing Poverty Data...")
        poverty_processed = self.process_poverty_data(poverty_data)
        
        # Calculate Comprehensive CRI
        print("🔄 Computing Comprehensive CRI...")
        cri_analysis = self.calculate_comprehensive_cri(dynasty_data, philgeps_data, poverty_data)
        
        # Generate cache files
        timestamp = datetime.now().isoformat()
        
        # Political HHI Cache
        political_cache = {
            'success': True,
            'last_updated': timestamp,
            'total_provinces': len(political_hhi),
            'data': political_hhi,
            'statistics': {
                'average_hhi': round(sum(p['hhi'] for p in political_hhi) / len(political_hhi), 1),
                'highest_hhi': political_hhi[0]['hhi'] if political_hhi else 0,
                'high_risk_count': len([p for p in political_hhi if p['hhi'] > 50])
            }
        }
        
        # Contractor HHI Cache
        contractor_cache = {
            'success': True,
            'last_updated': timestamp,
            'total_provinces': len(contractor_hhi),
            'data': contractor_hhi,
            'statistics': {
                'average_hhi': round(sum(c['hhi'] for c in contractor_hhi) / len(contractor_hhi), 1),
                'highest_hhi': contractor_hhi[0]['hhi'] if contractor_hhi else 0,
                'high_risk_count': len([c for c in contractor_hhi if c['hhi'] > 30])
            }
        }
        
        # Poverty Correlation Cache
        poverty_cache = {
            'success': True,
            'last_updated': timestamp,
            'total_provinces': len(poverty_processed),
            'data': poverty_processed,
            'statistics': {
                'average_poverty': round(sum(p['poverty_rate'] for p in poverty_processed) / len(poverty_processed), 1),
                'highest_poverty': poverty_processed[0]['poverty_rate'] if poverty_processed else 0,
                'high_poverty_count': len([p for p in poverty_processed if p['poverty_rate'] > 20])
            }
        }
        
        # CRI Analysis Cache
        cri_cache = {
            'success': True,
            'last_updated': timestamp,
            'total_provinces': len(cri_analysis),
            'data': cri_analysis,
            'statistics': {
                'average_cri': round(sum(c['cri_score'] for c in cri_analysis) / len(cri_analysis), 1),
                'highest_cri': cri_analysis[0]['cri_score'] if cri_analysis else 0,
                'high_risk_count': len([c for c in cri_analysis if c['cri_score'] > 50])
            }
        }
        
        # Save cache files
        os.makedirs('static/data', exist_ok=True)
        
        with open('static/data/political_hhi_cache.json', 'w', encoding='utf-8') as f:
            json.dump(political_cache, f, indent=2, ensure_ascii=False)
        
        with open('static/data/contractor_hhi_cache.json', 'w', encoding='utf-8') as f:
            json.dump(contractor_cache, f, indent=2, ensure_ascii=False)
        
        with open('static/data/poverty_correlation_cache.json', 'w', encoding='utf-8') as f:
            json.dump(poverty_cache, f, indent=2, ensure_ascii=False)
        
        with open('static/data/cri_analysis_cache.json', 'w', encoding='utf-8') as f:
            json.dump(cri_cache, f, indent=2, ensure_ascii=False)
        
        print("✅ Generated cache files:")
        print(f"   📊 Political HHI: {len(political_hhi)} provinces")
        print(f"   🏢 Contractor HHI: {len(contractor_hhi)} provinces")
        print(f"   📈 Poverty Data: {len(poverty_processed)} provinces")
        print(f"   🎯 CRI Analysis: {len(cri_analysis)} provinces")
        
        return True

async def main():
    analyzer = CRIAnalyzer()
    await analyzer.generate_cri_cache()

if __name__ == "__main__":
    asyncio.run(main())
