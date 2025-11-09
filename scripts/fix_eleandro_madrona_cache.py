#!/usr/bin/env python3
"""
Special script to clean Eleandro Jesus Madrona's cache so it only contains
projects located in Romblon's Lone District.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List

class EleandroMadronaCacheFixer:
    def __init__(self) -> None:
        self.base_dir = Path(__file__).parent.parent
        self.cache_dir = self.base_dir / 'static' / 'data'
        self.config_path = self.cache_dir / 'dynasty-projects-config.json'
        self.districts_path = self.cache_dir / 'districts.json'
        self.target_name = 'Eleandro Jesus Madrona'
        self.slug = 'eleandro-jesus-madrona'

    def contains_word(self, text: str, word: str) -> bool:
        if not word:
            return False
        pattern = rf'(?<!\w){re.escape(word)}(?!\w)'
        return re.search(pattern, text) is not None

    def load_config(self) -> Dict:
        config = json.loads(self.config_path.read_text(encoding='utf-8'))
        for entry in config.get('target_congressmen', []):
            if entry.get('display_name') == self.target_name:
                return entry
        raise RuntimeError('Configuration for Eleandro Jesus Madrona not found')

    def load_districts(self) -> Dict:
        return json.loads(self.districts_path.read_text(encoding='utf-8'))

    def build_filters(self, districts_data: Dict) -> Dict[str, List[str]]:
        romblon_info = districts_data.get('districts', {}).get('Romblon', {})
        municipalities = romblon_info.get('municipalities', {})
        target_municipalities = [name.upper() for name, dist in municipalities.items() if dist == 'Lone District']
        other_municipalities = [name.upper() for name, dist in municipalities.items() if dist != 'Lone District']

        keyword_info = romblon_info.get('keywords', {}).get('Lone District', {})
        positive_keywords = [kw.upper() for kw in keyword_info.get('positive', [])]
        negative_keywords = [kw.upper() for kw in keyword_info.get('negative', [])]

        if not positive_keywords:
            positive_keywords = [
                'ROMBLON LONE', 'LONE DISTRICT', 'ROMBLON DEO', 'ROMBLON ENGINEERING'
            ]
        if not negative_keywords:
            negative_keywords = [
                'AKLAN', 'ANTIQUE', 'CAPIZ', 'ILOILO', 'GUIMARAS', 'MINDORO', 'PALAWAN', 'MASBATE', 'BATANGAS'
            ]

        return {
            'target_municipalities': target_municipalities,
            'other_municipalities': other_municipalities,
            'positive_keywords': positive_keywords,
            'negative_keywords': negative_keywords,
        }

    def filter_projects(self, projects: List[Dict], filters: Dict[str, List[str]]) -> List[Dict]:
        targets = set(filters['target_municipalities'])
        others = set(filters['other_municipalities'])
        positives = filters['positive_keywords']
        negatives = filters['negative_keywords']

        filtered: List[Dict] = []
        for proj in projects:
            text_parts = [proj.get('project_name', ''), proj.get('location', ''), proj.get('description', '')]
            combined = ' '.join(filter(None, text_parts)).upper()

            if any(neg in combined for neg in negatives):
                continue

            mentioned_targets = {mun for mun in targets if self.contains_word(combined, mun)}
            mentioned_others = {mun for mun in others if self.contains_word(combined, mun)}

            if mentioned_targets and not mentioned_others:
                filtered.append(proj)
                continue

            if not mentioned_targets and not mentioned_others:
                if any(keyword in combined for keyword in positives) and 'ROMBLON' in combined:
                    filtered.append(proj)

        return filtered

    def recalc(self, projects: List[Dict]) -> Dict[str, float]:
        total_cost = 0.0
        district_cost = 0.0
        contractor_cost = 0.0
        district_projects = 0
        contractor_projects = 0
        source_counts = {'DIME': 0, 'PhilGEPS': 0, 'SSP': 0, 'Infrawatch': 0, 'Microsite': 0}

        for proj in projects:
            amount = proj.get('amount', 0)
            if isinstance(amount, str):
                cleaned = amount.replace('₱', '').replace(',', '').strip()
                try:
                    amount = float(cleaned)
                except ValueError:
                    amount = 0.0
            if not isinstance(amount, (int, float)):
                amount = 0.0

            total_cost += amount
            if proj.get('match_type') == 'contractor':
                contractor_projects += 1
                contractor_cost += amount
            else:
                district_projects += 1
                district_cost += amount

            for src in proj.get('sources_list', []):
                key = src.strip()
                if key in source_counts:
                    source_counts[key] += 1

        return {
            'total_cost': total_cost,
            'district_cost': district_cost,
            'contractor_cost': contractor_cost,
            'district_projects': district_projects,
            'contractor_projects': contractor_projects,
            'source_counts': source_counts,
        }

    def update_cache(self, projects: List[Dict], aggregates: Dict[str, float]) -> None:
        cache_path = self.cache_dir / f'congressman-projects-{self.slug}' / 'all-projects-cache.json'
        summary_path = self.cache_dir / f'congressman-projects-{self.slug}' / 'summary.json'

        if not cache_path.exists():
            raise RuntimeError(f'Cache file not found: {cache_path}')

        cache_data = json.loads(cache_path.read_text(encoding='utf-8'))
        cache_data['projects'] = projects
        cache_data['summary']['total'] = len(projects)
        cache_data['summary']['district_projects'] = int(aggregates['district_projects'])
        cache_data['summary']['contractor_projects'] = int(aggregates['contractor_projects'])
        cache_data['summary']['total_cost'] = aggregates['total_cost']
        src = aggregates['source_counts']
        cache_data['summary']['dime'] = src['DIME']
        cache_data['summary']['philgeps'] = src['PhilGEPS']
        cache_data['summary']['ssp'] = src['SSP']
        cache_data['summary']['infrawatch'] = src['Infrawatch']
        cache_data['summary']['microsite'] = src['Microsite']

        cache_data['dashboard_stats']['total_projects'] = len(projects)
        cache_data['dashboard_stats']['district_count'] = int(aggregates['district_projects'])
        cache_data['dashboard_stats']['contractor_count'] = int(aggregates['contractor_projects'])
        cache_data['dashboard_stats']['total_cost_all'] = aggregates['total_cost']
        cache_data['dashboard_stats']['district_cost'] = aggregates['district_cost']
        cache_data['dashboard_stats']['contractor_cost'] = aggregates['contractor_cost']
        cache_data['total_projects'] = len(projects)
        cache_data['total_cost'] = f"₱{aggregates['total_cost']:,.2f}"
        cache_data['district_cost'] = f"₱{aggregates['district_cost']:,.2f}"
        cache_data['contractor_cost'] = f"₱{aggregates['contractor_cost']:,.2f}"
        cache_data['generated_at'] = datetime.utcnow().isoformat()
        cache_path.write_text(json.dumps(cache_data, indent=2), encoding='utf-8')

        if summary_path.exists():
            summary_data = json.loads(summary_path.read_text(encoding='utf-8'))
            summary_data['total_projects'] = len(projects)
            summary_data['total_cost'] = f"₱{aggregates['total_cost']:,.2f}"
            summary_data['district_projects'] = int(aggregates['district_projects'])
            summary_data['contractor_projects'] = int(aggregates['contractor_projects'])
            summary_data['generated_at'] = datetime.utcnow().isoformat()
            summary_data['summary'] = cache_data['summary']
            summary_path.write_text(json.dumps(summary_data, indent=2), encoding='utf-8')

    def run(self) -> None:
        config_entry = self.load_config()
        districts_data = self.load_districts()
        filters = self.build_filters(districts_data)

        cache_path = self.cache_dir / f'congressman-projects-{self.slug}' / 'all-projects-cache.json'
        if not cache_path.exists():
            raise RuntimeError(f'Cache file not found: {cache_path}')

        cache_data = json.loads(cache_path.read_text(encoding='utf-8'))
        projects = cache_data.get('projects', [])
        print(f"Original projects: {len(projects)}")

        filtered = self.filter_projects(projects, filters)
        print(f"Filtered projects: {len(filtered)}")
        print(f"Removed: {len(projects) - len(filtered)}")

        aggregates = self.recalc(filtered)
        self.update_cache(filtered, aggregates)
        print('✅ Eleandro Jesus Madrona cache updated successfully')

if __name__ == '__main__':
    EleandroMadronaCacheFixer().run()
