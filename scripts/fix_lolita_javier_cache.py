#!/usr/bin/env python3
"""
Special script to clean Lolita Javier's cache by ensuring projects belong to
Leyte 2nd District municipalities only.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List

class LolitaJavierCacheFixer:
    def __init__(self) -> None:
        self.base_dir = Path(__file__).parent.parent
        self.cache_dir = self.base_dir / 'static' / 'data'
        self.config_path = self.cache_dir / 'dynasty-projects-config.json'
        self.districts_path = self.cache_dir / 'districts.json'
        self.target_name = 'Lolita Javier'
        self.slug = 'lolita-javier'

    def contains_word(self, text: str, word: str) -> bool:
        if not word:
            return False
        pattern = rf'(?<!\w){re.escape(word)}(?!\w)'
        return re.search(pattern, text) is not None

    def load_config(self) -> Dict:
        with self.config_path.open('r', encoding='utf-8') as fh:
            data = json.load(fh)
        for entry in data.get('target_congressmen', []):
            if entry.get('display_name') == self.target_name:
                return entry
        raise RuntimeError('Could not find configuration for Lolita Javier')

    def load_districts(self) -> Dict:
        with self.districts_path.open('r', encoding='utf-8') as fh:
            return json.load(fh)

    def get_municipality_maps(self, districts_data: Dict) -> Dict[str, str]:
        leyte = districts_data.get('districts', {}).get('Leyte', {})
        return {name.upper(): district for name, district in leyte.get('municipalities', {}).items()}

    def filter_projects(self, projects: List[Dict], municipalities_map: Dict[str, str]) -> List[Dict]:
        target_muns = {name for name, dist in municipalities_map.items() if dist == '2nd District'}
        other_muns = {name for name, dist in municipalities_map.items() if dist != '2nd District'}
        other_muns.discard('LEYTE')  # avoid false positives with province name
        keyword_globs = [
            'LEYTE 2ND', '2ND LD', 'SECOND LD', '2ND LEGISLATIVE DISTRICT',
            '2ND DISTRICT ENGINEERING', '2ND DEO', '2ND LEGISLATIVE DIST.',
            'SECOND LEGISLATIVE DISTRICT', 'LEYTE II', 'LEYTE 2 DEO'
        ]
        invalid_keywords = [
            'LEYTE 1ST', 'LEYTE 3RD', 'LEYTE 4TH', 'LEYTE 5TH', 'LEYTE 6TH',
            '1ST LD', '3RD LD', '4TH LD', '5TH LD', '6TH LD',
            'SOUTHERN LEYTE', 'NORTHERN SAMAR', 'EASTERN SAMAR',
            'WESTERN SAMAR', 'SAMAR PROVINCE', 'BILIRAN', 'ORMOC CITY',
            'ORMOC', 'TACLOBAN', 'TAC. CITY', 'TAC CITY', 'LEYTE I DEO',
            'LEYTE 1 DEO', 'LEYTE 3 DEO', 'LEYTE 4 DEO', 'LEYTE 5 DEO', 'LEYTE 6 DEO'
        ]

        filtered: List[Dict] = []
        for proj in projects:
            text_parts = [proj.get('project_name', ''), proj.get('location', ''), proj.get('description', '')]
            combined = ' '.join(filter(None, text_parts)).upper()

            mentioned_target = {mun for mun in target_muns if self.contains_word(combined, mun)}
            mentioned_other = {mun for mun in other_muns if self.contains_word(combined, mun)}

            invalid_hit = any(keyword in combined for keyword in invalid_keywords)
            if invalid_hit:
                continue

            keyword_hit = any(keyword in combined for keyword in keyword_globs) and 'LEYTE' in combined

            if (mentioned_target or keyword_hit) and not mentioned_other:
                filtered.append(proj)
                continue

            if not mentioned_target and not mentioned_other:
                if keyword_hit:
                    filtered.append(proj)
                # else drop
            # if other municipalities present, drop project
        return filtered

    def recalc_scores(self, projects: List[Dict]) -> Dict[str, float]:
        total_cost = 0.0
        district_cost = 0.0
        contractor_cost = 0.0
        district_projects = 0
        contractor_projects = 0
        source_counts = {
            'DIME': 0,
            'PhilGEPS': 0,
            'SSP': 0,
            'Infrawatch': 0,
            'Microsite': 0,
        }

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
        source_counts = aggregates['source_counts']
        cache_data['summary']['dime'] = source_counts['DIME']
        cache_data['summary']['philgeps'] = source_counts['PhilGEPS']
        cache_data['summary']['ssp'] = source_counts['SSP']
        cache_data['summary']['infrawatch'] = source_counts['Infrawatch']
        cache_data['summary']['microsite'] = source_counts['Microsite']
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
            summary_data['summary']['total'] = len(projects) if 'summary' in summary_data else len(projects)
            if 'summary' in summary_data:
                summary_data['summary']['total'] = len(projects)
                summary_data['summary']['district_projects'] = int(aggregates['district_projects'])
                summary_data['summary']['contractor_projects'] = int(aggregates['contractor_projects'])
                summary_data['summary']['dime'] = source_counts['DIME']
                summary_data['summary']['philgeps'] = source_counts['PhilGEPS']
                summary_data['summary']['ssp'] = source_counts['SSP']
                summary_data['summary']['infrawatch'] = source_counts['Infrawatch']
                summary_data['summary']['microsite'] = source_counts['Microsite']
            summary_path.write_text(json.dumps(summary_data, indent=2), encoding='utf-8')

    def run(self) -> None:
        config_entry = self.load_config()
        districts_data = self.load_districts()
        municipalities_map = self.get_municipality_maps(districts_data)

        cache_path = self.cache_dir / f'congressman-projects-{self.slug}' / 'all-projects-cache.json'
        if not cache_path.exists():
            raise RuntimeError(f'Cache file not found: {cache_path}')

        cache_data = json.loads(cache_path.read_text(encoding='utf-8'))
        projects = cache_data.get('projects', [])
        print(f"Original projects: {len(projects)}")

        filtered = self.filter_projects(projects, municipalities_map)
        print(f"Filtered projects: {len(filtered)}")
        print(f"Removed: {len(projects) - len(filtered)}")

        aggregates = self.recalc_scores(filtered)
        self.update_cache(filtered, aggregates)
        print('✅ Lolita Javier cache updated successfully')

if __name__ == '__main__':
    LolitaJavierCacheFixer().run()
