#!/usr/bin/env python3
"""Build the Vote 2028 officeholder review from the archived ODV dynasty dump."""
import gzip
import hashlib
import json
import re
import unicodedata
import csv
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'database/dynasty_dump.sql.gz'
OUT = ROOT / 'static/nep-preview/vote-2028-data.json'
HOUSE_ROSTER = ROOT / 'static/data/20th_congress_representatives.json'
HOUSE_ROSTER_URL = 'https://www.congress.gov.ph/house-members'
FAMILY_LINK_DIR = ROOT / 'family_analysis/family_parser'
ODV_OFFICIALS = ROOT.parent / 'nep/data_sources/odv_dynasty/source_officials.csv.gz'
ASOG_DATASET = ROOT / 'database/ASoG-POLITICAL-DYNASTIES-DATASET-V2016.xlsx'
ODV_CONGRESSMEN = ROOT / 'static/data/congressmen_consolidated.json'


def norm(value):
    value = unicodedata.normalize('NFKD', str(value or ''))
    value = ''.join(c for c in value if not unicodedata.combining(c))
    return re.sub(r'[^A-Z0-9]+', ' ', value.upper()).strip()


def compact_norm(value):
    """Normalize punctuation and spacing for within-family duplicate identities."""
    return norm(value).replace(' ', '')


def first_last_key(value):
    """A conservative alias key; callers must verify it is unique."""
    parts = norm(value).split()
    if len(parts) < 2:
        return ''
    return compact_norm(parts[0] + ' ' + parts[-1])


def surname_key(value):
    """Return the final name token, excluding common generational suffixes."""
    parts = norm(value).split()
    while parts and parts[-1] in {'JR', 'SR', 'II', 'III', 'IV', 'V'}:
        parts.pop()
    return compact_norm(parts[-1]) if parts else ''


def clean_nickname(value):
    """Reject ODV nickname-field values that are actually dates or agencies."""
    value = re.sub(r'\s+', ' ', str(value or '').strip().strip('"'))
    if not value or value == r'\N' or len(value) > 48:
        return ''
    if re.search(r'\b(born|died|aged|age|circa)\b|\bc\.?\s*\d{3,4}\b', value, re.I):
        return ''
    if re.search(r'\b\d{3,4}\b', value):
        return ''
    if compact_norm(value) in {'PCSO', 'DILG', 'COMELEC'}:
        return ''
    if not re.search(r'[A-Za-z]', value):
        return ''
    return value


CURATED_PUBLIC_ALIASES = {
    compact_norm('RODRIGO ROA DUTERTE'): [{
        'name': 'Digong', 'sourceUrl': 'https://web.nlp.gov.ph/wp-content/uploads/2023/12/NLP-Special-Bibliography-on-PRRD-Part-II-compressed.pdf'}],
    compact_norm('SARA Z. DUTERTE-CARPIO'): [{
        'name': 'Inday Sara', 'sourceUrl': 'https://nnc.gov.ph/mindanao-region/women-of-davao-for-nutrition-mayor-inday-sara-duterte/'}],
    compact_norm('PAOLO Z. DUTERTE'): [{
        'name': 'Pulong', 'sourceUrl': 'https://www.gmanetwork.com/news/showbiz/chikaminute/598530/duterte-says-he-s-using-media-coverage-to-send-message-to-lover-boy-baste/story/'}],
    compact_norm('SEBASTIAN Z. DUTERTE'): [{
        'name': 'Baste', 'sourceUrl': 'https://www.gmanetwork.com/news/showbiz/chikaminute/598530/duterte-says-he-s-using-media-coverage-to-send-message-to-lover-boy-baste/story/'}],
    compact_norm('RODRIGO RIGO S DUTERTE II'): [{
        'name': 'Rigo', 'sourceUrl': 'https://mindanews.com/comelec-proclaims-5-dutertes-as-election-winners/'}],
}


def collect_alias_evidence(name, source_aliases=()):
    out, seen = [], set()
    for item in list(source_aliases) + CURATED_PUBLIC_ALIASES.get(compact_norm(name), []):
        alias = clean_nickname(item.get('name'))
        key = compact_norm(alias)
        if alias and key and key != compact_norm(name) and key not in seen:
            out.append({**item, 'name': alias})
            seen.add(key)
    return out


def office_group(position):
    p = norm(position)
    if p == 'PRESIDENT' or p.startswith('VICE PRESIDENT'):
        return 'President / Vice President'
    if p.startswith('SENATOR'):
        return 'Senator'
    if ('HOUSE OF REPRESENTATIVES' in p or 'CONGRESSMAN' in p or
            'PARTY LIST REPRESENTATIVE' in p or 'PARTY LIST' in p and 'REPRESENTATIVE' in p):
        return 'Congress / party-list representative'
    if 'VICE GOVERNOR' in p:
        return 'Vice Governor'
    if 'GOVERNOR' in p:
        return 'Governor'
    if 'VICE MAYOR' in p:
        return 'Vice Mayor'
    if 'MAYOR' in p:
        return 'Mayor'
    if 'PUNONG BARANGAY' in p or 'BARANGAY CAPTAIN' in p or 'CAPTAIN OF BARANGAY' in p or 'CAPTAIN OF BRGY' in p or p == 'BARANGAY CHAIRMAN':
        return 'Barangay captain'
    if 'PROVINCIAL BOARD' in p or 'SANGGUNIAN PANLALAWIGAN' in p:
        return 'Provincial board member'
    if 'COUNCILOR' in p or 'SANGGUNIAN' in p:
        return 'Councilor'
    return None


def office_level(group):
    if group in {'President / Vice President', 'Senator', 'Congress / party-list representative'}:
        return 'national'
    return 'local'


def office_identity(record):
    """Return the dedup identity for a person holding one office in one election.

    National offices were copied across many localities in the ODV export.
    For local offices, stable ODV person IDs remain the primary identity, with
    an exact-name + full-municipality fallback for duplicate IDs on the same
    local seat. Barangay offices are excluded from that fallback because the
    dump does not retain a reliable barangay field.
    """
    if office_level(record['officeGroup']) == 'national':
        identity = 'national-name:' + compact_norm(record['name'])
        if record['officeGroup'] == 'Congress / party-list representative':
            identity += '|' + compact_norm(record.get('district')) + '|' + compact_norm(record.get('party'))
        return identity
    return record['personKey']


def parse_copy(source, target):
    """Yield tab-delimited PostgreSQL COPY fields for one table."""
    active = False
    with gzip.open(source, 'rt', encoding='utf-8', errors='replace') as stream:
        for line in stream:
            if line.startswith(f'COPY public.{target} '):
                active = True
                continue
            if active and line.startswith('\\.'):
                return
            if active:
                yield line.rstrip('\n').split('\t')


def read_asog_election_rows(path):
    """Read the inventoried Ateneo/ODV historical election sheet (2004–2016)."""
    if not path.exists():
        return
    ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
          'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
          'p': 'http://schemas.openxmlformats.org/package/2006/relationships'}
    with zipfile.ZipFile(path) as archive:
        shared = ET.fromstring(archive.read('xl/sharedStrings.xml'))
        strings = [''.join(node.text or '' for node in item.findall('.//m:t', ns))
                   for item in shared.findall('m:si', ns)]
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        rels = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        targets = {item.attrib['Id']: item.attrib['Target'] for item in rels.findall('p:Relationship', ns)}
        data_sheet = next((sheet for sheet in workbook.findall('.//m:sheets/m:sheet', ns)
                           if sheet.attrib.get('name') == 'Data'), None)
        if data_sheet is None:
            return
        target = targets.get(data_sheet.attrib.get('{' + ns['r'] + '}id'), '')
        sheet_path = target if target.startswith('xl/') else 'xl/' + target
        sheet = ET.fromstring(archive.read(sheet_path))
        for row in sheet.findall('.//m:sheetData/m:row', ns):
            cells = {}
            for cell in row.findall('m:c', ns):
                ref = re.match(r'([A-Z]+)', cell.attrib.get('r', ''))
                value = cell.find('m:v', ns)
                if not ref or value is None:
                    continue
                raw = value.text or ''
                if cell.attrib.get('t') == 's' and raw:
                    raw = strings[int(raw)]
                cells[ref.group(1)] = raw
            if cells.get('A') == 'First Name':
                continue
            first = re.sub(r'\s+', ' ', cells.get('A', '')).strip()
            last = re.sub(r'\s+', ' ', cells.get('B', '')).strip()
            if not first or not last:
                continue
            # Quoted strings in the first-name field are nickname annotations,
            # not part of the official name used for identity matching.
            nickname_values = re.findall(r'["“]([^"”]+)["”]', first)
            name = re.sub(r'["“][^"”]*["”]', ' ', first)
            name = re.sub(r'\s+', ' ', f'{name} {last}').strip()
            try:
                year = int(cells.get('H', ''))
            except ValueError:
                continue
            group = office_group(cells.get('G', ''))
            if not group or year < 2004:
                continue
            yield {
                'name': name, 'officeGroup': group, 'position': cells.get('G', '').strip(),
                'province': cells.get('E', '').strip(), 'municipality': cells.get('F', '').strip(),
                'region': cells.get('D', '').strip(), 'party': cells.get('C', '').strip(),
                'electionYear': year, 'termYears': 6 if group in {'President / Vice President', 'Senator'} else 3,
                'termThroughYear': year + (6 if group in {'President / Vice President', 'Senator'} else 3),
                'dynastyScreen': cells.get('I', '').strip() == '1',
                'aliasEvidence': [{'name': alias.strip(),
                                   'source': 'Ateneo Policy Center historical election dataset nickname field'}
                                  for alias in nickname_values if alias.strip()],
            }


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            low, high = sorted((a, b))
            self.parent[high] = low


def build():
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    odv_aliases_by_id = defaultdict(list)
    if ODV_OFFICIALS.exists():
        try:
            with gzip.open(ODV_OFFICIALS, 'rt', encoding='utf-8', errors='replace', newline='') as stream:
                for row in csv.DictReader(stream):
                    alias = clean_nickname(row.get('nickname'))
                    if alias:
                        item = {'name': alias, 'source': 'ODV source_officials nickname field'}
                        if item not in odv_aliases_by_id[row.get('id', '')]:
                            odv_aliases_by_id[row.get('id', '')].append(item)
        except (OSError, UnicodeError, csv.Error):
            pass
    raw_house_roster = json.loads(HOUSE_ROSTER.read_text(encoding='utf-8'))
    congressman_profiles = json.loads(ODV_CONGRESSMEN.read_text(encoding='utf-8')) if ODV_CONGRESSMEN.exists() else []
    profile_display_to_full = defaultdict(set)
    profile_full_to_display = defaultdict(set)
    for profile in congressman_profiles:
        display_name = str(profile.get('display_name') or '').strip()
        full_name = str(profile.get('full_name') or '').strip()
        if display_name and full_name and compact_norm(display_name) != compact_norm(full_name):
            profile_display_to_full[compact_norm(display_name)].add(full_name)
            profile_full_to_display[compact_norm(full_name)].add(display_name)
    congressman_name_aliases = {}
    for display_key, full_names in profile_display_to_full.items():
        if len(full_names) == 1:
            full_name = next(iter(full_names))
            if len(profile_full_to_display[compact_norm(full_name)]) == 1:
                congressman_name_aliases[display_key] = full_name
                congressman_name_aliases[compact_norm(full_name)] = next(iter(profile_full_to_display[compact_norm(full_name)]))
    congressman_unique_name_variant_pairs = len({tuple(sorted((display_key, compact_norm(next(iter(full_names))))))
                                                  for display_key, full_names in profile_display_to_full.items()
                                                  if len(full_names) == 1 and
                                                  len(profile_full_to_display[compact_norm(next(iter(full_names)))]) == 1})
    house_roster = []
    for item in raw_house_roster:
        constituency = re.sub(r'\[[^\]]+\]', '', str(item.get('district') or '')).strip()
        province = re.sub(r'\[[^\]]+\]', '', str(item.get('province') or '')).strip()
        member = re.sub(r'\[[^\]]+\]', '', str(item.get('representative') or '')).strip()
        party = re.sub(r'\[[^\]]+\]', '', str(item.get('party') or '')).strip()
        if not member:
            continue
        if re.fullmatch(r'(?:Lone|\d+(?:st|nd|rd|th))', constituency, re.I) and province:
            house_roster.append({'name': member, 'province': province, 'district': constituency,
                                 'party': party, 'seatType': 'district'})
        elif not constituency and party.isdigit() and province and member:
            # The local 20th-Congress roster stores party-list rows as
            # province=member name, representative=party-list organization,
            # party=seat number.
            house_roster.append({'name': province, 'province': '', 'district': member,
                                 'party': member, 'seatType': 'party-list'})
    family = UnionFind()
    edges = []
    # Verified relationship records are explicit family links; the source dump
    # also carries family IDs assigned by ODV's dynasty database.
    for row in parse_copy(SOURCE, 'relationships'):
        if len(row) >= 12 and row[8] == 't' and row[1].isdigit() and row[2].isdigit() and row[1] != row[2]:
            try:
                relationship_type = int(row[3])
            except ValueError:
                continue
            if relationship_type <= 20:
                left, right = 'id:' + row[1], 'id:' + row[2]
                family.union(left, right)
                edges.append({'a': left, 'b': right, 'type': relationship_type,
                              'detail': row[4] if row[4] != r'\N' else '', 'basis': 'verified ODV relationship'})

    records = []
    house_name_keys = {compact_norm(item['name']) for item in house_roster}
    odv_house_identity_rows = defaultdict(list)
    odv_dynasty_family_surnames = defaultdict(set)
    for row in parse_copy(SOURCE, 'political_dynasties'):
        if len(row) < 30:
            continue
        # The old ODV family page groups dynasty-screened officials by
        # surname and province. Keep this broader screen separate from
        # person-to-person kinship evidence and never use it for the NO rule.
        if row[9] == '1' and row[2] != r'\N' and row[5] != r'\N':
            family_surname = compact_norm(row[2])
            family_province = compact_norm(row[5])
            family_name = compact_norm(row[22] if row[22] != r'\N' else ' '.join(x for x in (row[1], row[2]) if x and x != r'\N'))
            if family_surname and family_province and family_name:
                odv_dynasty_family_surnames[(family_province, family_surname)].add(family_name)
        # Capture all historical office rows for exact House-roster names, not
        # only their congressional rows: ODV may store the member's explicit
        # family ID or relationship anchor on an earlier local office record.
        raw_name = row[22] if row[22] != r'\N' else ' '.join(x for x in (row[1], row[19], row[2], row[20]) if x and x != r'\N')
        candidate_names = {raw_name, ' '.join(x for x in (row[1], row[19], row[2], row[20]) if x and x != r'\N'),
                           ' '.join(x for x in (row[21], row[2], row[20]) if x and x != r'\N')}
        alias_field = '' if row[24] == r'\N' else row[24]
        candidate_names.update(re.split(r'[,;|]', alias_field))
        for candidate_name in candidate_names:
            candidate_key = compact_norm(candidate_name)
            if candidate_key in house_name_keys:
                odv_house_identity_rows[candidate_key].append({
                    'id': row[0], 'unifiedId': '' if row[23] == r'\N' else row[23],
                    'familyId': '' if row[25] == r'\N' else row[25],
                    'fat': row[9] == '1', 'position': row[7], 'district': '' if row[29] == r'\N' else row[29],
                    'province': '' if row[5] == r'\N' else row[5], 'municipality': '' if row[6] == r'\N' else row[6],
                    'year': '' if row[8] == r'\N' else row[8]})
        if row[11] != 't' or row[15].lower() != 'elected' or row[8] == r'\N':
            continue
        group = office_group(row[7])
        if not group:
            continue
        organization = '' if row[18] == r'\N' else norm(row[18])
        department = '' if row[17] == r'\N' else norm(row[17])
        display_position = row[7]
        if group == 'President / Vice President':
            affiliation = department + ' ' + organization
            if 'OFFICE OF THE VICE PRESIDENT' in affiliation:
                display_position = 'VICE PRESIDENT'
            elif 'OFFICE OF THE PRESIDENT' not in affiliation:
                continue
        try:
            election_year = int(row[8])
        except ValueError:
            continue
        if election_year < 2004:
            continue
        first, last = row[1], row[2]
        # The dump's actual order is middle_name (19), suffix (20),
        # canonical_first_name (21), canonical_name (22). Prefer ODV's
        # normalized full name; the raw first/last/suffix fields are fallback.
        suffix = '' if row[20] == r'\N' else row[20]
        canonical = '' if row[22] == r'\N' else row[22]
        name = canonical or ' '.join(x for x in (first, last, suffix) if x and x != r'\N').strip()
        province = '' if row[5] == r'\N' else row[5]
        municipality = '' if row[6] == r'\N' else row[6]
        unified = '' if row[23] == r'\N' else row[23]
        birth = '' if row[26] == r'\N' else row[26]
        # Stable entity key ties repeated election records for the same person,
        # while retaining place and birth data to avoid surname-only matching.
        person_key = ('person:' + unified) if unified else 'name:' + '|'.join(
            (norm(canonical or name), norm(province), norm(municipality), birth))
        node = 'id:' + row[0]
        family.union(node, person_key)
        family_id = '' if row[25] == r'\N' else row[25]
        if family_id:
            family.union(person_key, 'family:' + family_id)
        role_years = 6 if group in {'President / Vice President', 'Senator'} else 3
        district = '' if row[29] == r'\N' else row[29]
        party = '' if row[3] == r'\N' else row[3]
        records.append({
            'personKey': person_key, 'familyKey': None,
            'name': name, 'position': display_position, 'odvPosition': row[7], 'officeGroup': group,
            'aliasEvidence': collect_alias_evidence(name, odv_aliases_by_id.get(row[0], [])),
            'province': province, 'municipality': municipality, 'district': district,
            'region': '' if row[4] == r'\N' else row[4], 'party': party,
            'electionYear': election_year, 'termYears': role_years,
            'termThroughYear': election_year + role_years,
            'sourceId': row[0], 'familyBasis': 'ODV verified relationship' if any(e['a'] == node or e['b'] == node for e in edges) else ('ODV dynasty family ID' if family_id else ''),
        })

    current_house_odv_family_page_group_matches = sum(
        seat['seatType'] == 'district' and
        len(odv_dynasty_family_surnames.get((compact_norm(seat['province']), surname_key(seat['name'])), set())) >= 2
        for seat in house_roster
    )

    # Use only the congressman profile's uniquely paired display/full-name
    # variants as aliases. Its contractor fields are not family evidence.
    for record in records:
        alternate = congressman_name_aliases.get(compact_norm(record['name']))
        if alternate:
            record['aliasEvidence'] = collect_alias_evidence(record['name'], record.get('aliasEvidence', []) + [{
                'name': alternate, 'source': 'ODV congressman profile · unique display/full-name pair'}])

    # Add the separate Ateneo/ODV historical election dataset. It identifies
    # elected names, offices, places, years, and a dynasty-screen flag, but it
    # has no person-to-person kinship edges. An ASOG flag is never treated as
    # proof of a family link or as sufficient for a NO marker.
    asog_rows_loaded = 0
    asog_dynasty_flag_rows = 0
    asog_exact_identity_matches_to_odv = 0
    asog_election_rows_added = 0
    asog_unmatched_or_ambiguous_identity_rows = 0
    exact_odv_rows = defaultdict(set)
    exact_odv_records = defaultdict(list)
    exact_odv_people = defaultdict(set)
    for record in records:
        key = (compact_norm(record['name']), record['officeGroup'], record['electionYear'],
               compact_norm(record.get('province')), compact_norm(record.get('municipality')))
        exact_odv_rows[key].add(record['personKey'])
        exact_odv_records[key].append(record)
        exact_odv_people[(key[0], key[1], key[3], key[4])].add(record['personKey'])
    for row_number, item in enumerate(read_asog_election_rows(ASOG_DATASET), start=2):
        asog_rows_loaded += 1
        asog_dynasty_flag_rows += bool(item['dynastyScreen'])
        exact_key = (compact_norm(item['name']), item['officeGroup'], item['electionYear'],
                     compact_norm(item['province']), compact_norm(item['municipality']))
        matches = exact_odv_rows.get(exact_key, set())
        identity_matches = exact_odv_people.get((exact_key[0], exact_key[1], exact_key[3], exact_key[4]), set())
        if len(matches) == 1:
            person_key = next(iter(matches))
            asog_exact_identity_matches_to_odv += 1
        elif len(identity_matches) == 1:
            person_key = next(iter(identity_matches))
            asog_exact_identity_matches_to_odv += 1
        else:
            # Keep an ambiguous or unmatched election row source-local instead
            # of guessing that equal/similar names identify one person.
            digest = hashlib.sha1((compact_norm(item['name']) + '|' + item['officeGroup'] + '|' +
                                   str(item['electionYear']) + '|' + compact_norm(item['province']) + '|' +
                                   compact_norm(item['municipality'])).encode()).hexdigest()[:16]
            person_key = 'asog-election:' + digest
        if len(matches) != 1:
            records.append({
                'personKey': person_key, 'familyKey': None, 'name': item['name'],
                'position': item['position'], 'odvPosition': item['position'],
                'officeGroup': item['officeGroup'], 'province': item['province'],
                'municipality': item['municipality'], 'district': '', 'region': item['region'],
                'party': item['party'], 'electionYear': item['electionYear'],
                'termYears': item['termYears'], 'termThroughYear': item['termThroughYear'],
                'sourceId': f'asog-{item["electionYear"]}-{row_number}',
                'familyBasis': '', 'aliasEvidence': collect_alias_evidence(item['name'], item['aliasEvidence']), 'odvDynastyFlag': False,
                'asogDynastyFlag': bool(item['dynastyScreen']),
                'roleNote': 'Ateneo Policy Center / ODV historical election record; its dynasty flag is a screening marker, not a verified family link.',
                'sourceDataset': 'Ateneo Policy Center Political Dynasties Dataset · historical election row',
                'asogOnly': len(identity_matches) != 1,
            })
            exact_odv_records[exact_key].append(records[-1])
            asog_election_rows_added += 1
            if len(identity_matches) != 1:
                asog_unmatched_or_ambiguous_identity_rows += 1
            exact_odv_rows[exact_key].add(person_key)
            exact_odv_people[(exact_key[0], exact_key[1], exact_key[3], exact_key[4])].add(person_key)
        # Preserve ASOG's screening result and provenance on an exact matched
        # ODV role as well as on ASOG-only roles.
        if len(matches) == 1:
            for record in exact_odv_records.get(exact_key, []):
                if record['personKey'] != person_key:
                    continue
                record['asogDynastyFlag'] = bool(record.get('asogDynastyFlag') or item['dynastyScreen'])
                record['aliasEvidence'] = collect_alias_evidence(
                    record['name'], record.get('aliasEvidence', []) + item['aliasEvidence'])
                record.setdefault('sourceDataset', 'ODV political_dynasties + Ateneo Policy Center historical election dataset')
                if item['dynastyScreen']:
                    note = 'Ateneo/ODV historical dataset marks this election row dynasty-flagged; this screening marker does not establish a specific family link.'
                    if note not in record.get('roleNote', ''):
                        record['roleNote'] = (record.get('roleNote', '') + ' ' + note).strip()

    # The archived ODV dump has elected Duterte office records but no verified
    # family edge or dynasty_family_id for Rodrigo Duterte, Sara Duterte, and
    # Paolo Duterte. Its sole Duterte-related edge is explicitly unverified
    # and does not connect those records. Add only the direct, publicly
    # documented parent-child links below; do not infer relationships from the
    # Duterte surname alone (which would incorrectly merge unrelated people).
    # ODV has incomplete/mislabelled Duterte rows and stops before the 2025
    # election winners. Replace those members' ODV office rows with a compact,
    # source-linked role history. Other people named Duterte are left alone.
    documented_families = [{
        'key': 'source-family:duterte',
        'members': ['RODRIGO ROA DUTERTE', 'SARA Z. DUTERTE-CARPIO', 'PAOLO Z. DUTERTE',
                    'SEBASTIAN Z. DUTERTE', 'OMAR VINCENT S. DUTERTE',
                    'RODRIGO "RIGO" S. DUTERTE II', 'HAROLD JAMES TAPANGAN DUTERTE'],
        'basis': 'Publicly documented Duterte family relationships; no shared-surname matching.',
        'sources': [
            'https://votepilipinas.com/candidate/duterte-sara.html',
            'https://pco.gov.ph/photo12-063016/',
            'https://www.pulongduterte.com/the-congressman',
            'https://www.sunstar.com.ph/davao/local-news/pulong-sons-take-oath',
            'https://pcij.org/2026/05/25/7-reasons-why-the-party-list-system-serves-dynasties-not-democracy/',
        ],
    }, {
        'key': 'source-family:villar',
        'members': ['MARK VILLAR', 'CAMILLE VILLAR'],
        'basis': 'Publicly documented siblings; both held Senate seats concurrently from 2025.',
        'sources': [
            'https://www.abs-cbn.com/news/nation/2025/5/17/camille-villar-proclaimed-senator-elect-to-join-brother-at-senate-1608',
            'https://www.gmanetwork.com/news/topstories/nation/964033/saln-senators/story/',
        ],
    }, {
        'key': 'source-family:tulfo',
        'members': ['RAFFY TULFO', 'ERWIN TULFO', 'RALPH WENDEL TULFO', 'JOCELYN P TULFO'],
        'basis': 'Publicly documented siblings, spouses, and parent–child links among current officeholders.',
        'sources': [
            'https://qa.philstar.com/headlines/2024/10/07/2390588/while-aiming-join-brother-senate-erwin-tulfo-backs-political-dynasty-ban',
            'https://legacy.senate.gov.ph/senators/sen_bio/tulfo_raffy_bio.asp',
            'https://verafiles.org/articles/fact-sheet-what-happens-when-fat-dynasties-become-obese',
            'https://www.congress.gov.ph/house-members',
        ],
    }, {
        'key': 'source-family:cayetano',
        'members': ['ALAN PETER CAYETANO', 'PIA CAYETANO', 'MARIA CAYETANO'],
        'basis': 'Publicly documented siblings and spouses; Alan and Pia are siblings, and Alan is married to Lani (Maria) Cayetano.',
        'sources': [
            'https://legacy.senate.gov.ph/senators/sen_bio/cayetano_alanpeter_bio.asp',
            'https://senate.gov.ph/media/news-release/power-couple-alan-and-lani-cayetano-a-story-of-love-and-success-2',
            'https://mb.com.ph/2025/05/14/sweet-sweep-victory-lani-cayetano-grateful-for-big-win-in-taguig',
        ],
    }, {
        'key': 'source-family:sotto',
        'members': ['TITO SOTTO', 'GIAN CARLO SOTTO', 'VICO SOTTO'],
        'basis': 'Publicly documented father–son and uncle–nephew relationships among current officeholders.',
        'sources': [
            'https://mb.com.ph/2022/2/6/sotto-denies-family-an-emerging-dynasty-in-ph-politics',
            'https://legacy.senate.gov.ph/press_release/2022/0120_prib1.asp',
            'https://quezoncity.gov.ph/proclamation-of-quezon-city-local-candidates/',
            'https://mb.com.ph/2025/05/13/domagoso-reelected-in-manila-10-incumbent-mayors-win-fresh-mandates',
        ],
    }]
    duterte_aliases = {
        'RODRIGO DUTERTE', 'RODRIGO ROA DUTERTE',
        'SARA DUTERTE', 'SARA DUTERTE CARPIO', 'SARA Z DUTERTE CARPIO',
        'SARA ZIMMERMAN DUTERTE CARPIO', 'SARA Z DUTERTE-CARPIO',
        'PAOLO DUTERTE', 'PAOLO Z DUTERTE', 'PAOLO ZIMMERMAN DUTERTE',
        'SEBASTIAN DUTERTE', 'SEBASTIAN Z DUTERTE', 'SEBASTIAN ZIMMERMAN DUTERTE',
        'OMAR DUTERTE', 'OMAR VINCENT S DUTERTE', 'OMAR VINCENT S DUTERTE',
        'RODRIGO DUTERTE II', 'RODRIGO S DUTERTE II', 'RODRIGO RIGO S DUTERTE II',
        'HAROLD JAMES TAPANGAN DUTERTE', 'HAROLD TAPANGAN DUTERTE',
    }
    records = [r for r in records if norm(r['name']) not in duterte_aliases]

    # The 2025 ODV rows include a current-Senate snapshot, not only 2025
    # election winners. Restore the official 2022 term cohort, normalize
    # known public-name variants, and drop two incorrectly marked winners.
    senate_2022_names = {compact_norm(name) for name in (
        'ALAN PETER CAYETANO', 'VICTOR EJERCITO', 'FRANCIS ESCUDERO',
        'JINGGOY EJERCITO ESTRADA', 'SHERWIN GATCHALIAN', 'RISA HONTIVEROS',
        'LOREN LEGARDA', 'ROBINHOOD PADILLA', 'RAFFY TULFO',
        'JOEL VILLANUEVA', 'MARK VILLAR', 'JUAN MIGUEL ZUBIRI',
    )}
    senate_name_aliases = {
        'MANUEL LAPID': 'LITO LAPID',
        'RONALD DELA ROSA': 'BATO DELA ROSA',
        'CHRISTOPHER GO': 'BONG GO',
    }
    senate_2022_source = 'https://legacy.senate.gov.ph/publications/STSRO/STSRO%20Primer%202022_Printed%20in%20July%202022.pdf'
    senate_snapshot_rows_corrected = 0
    senate_name_variants_normalized = 0
    misclassified_senate_rows_removed = 0
    corrected_records = []
    for record in records:
        if (record['electionYear'] == 2025 and record['position'].upper() == 'SENATOR' and
                compact_norm(record['name']) == 'RAULLAMBINO'):
            misclassified_senate_rows_removed += 1
            continue
        if (record['electionYear'] == 2025 and record['position'].upper() == 'PRESIDENT' and
                compact_norm(record['name']) == 'PANFILOLACSON'):
            misclassified_senate_rows_removed += 1
            continue
        canonical_name = senate_name_aliases.get(compact_norm(record['name']), record['name'])
        if canonical_name != record['name']:
            senate_name_variants_normalized += 1
            record['name'] = canonical_name
        if record['position'].upper() == 'SENATOR' and compact_norm(record['name']) in senate_2022_names:
            if record['electionYear'] == 2025:
                senate_snapshot_rows_corrected += 1
            record['electionYear'] = 2022
            record['officeStartYear'] = 2022
            record['termYears'] = 6
            record['termThroughYear'] = 2028
            record['roleSourceUrl'] = senate_2022_source
            record['roleNote'] = (record.get('roleNote', '') +
                                  ' ODV lists this current Senate seat in its 2025 snapshot; the official Senate directory places this term in the 2022–2028 cohort.').strip()
        corrected_records.append(record)
    records = corrected_records

    role_sources = {
        'rodrigo_history': 'https://www.icc-cpi.int/sites/default/files/CourtRecords/0902ebd180af4f78.pdf',
        'sara_history': 'https://votepilipinas.com/candidate/duterte-sara.html',
        'paolo_barangay': 'https://pcij.org/2016/05/06/wealth-check-rodrigo-duterte-pdp-laban/',
        'paolo_resignation': 'https://www.pna.gov.ph/articles/1019809',
        '2025_winners': 'https://mindanews.com/comelec-proclaims-5-dutertes-as-election-winners/',
        'davao_2019_2022': 'https://davaocity.gov.ph/wp-content/uploads/2019/07/Directory-of-Davao-City-Department-Heads-.pdf',
        'sebastian_2022': 'https://www.sunstar.com.ph/davao/local-news/sebastian-duterte-is-mayormelchor-quitain-jr-is-vm',
        'davao_succession': 'https://www.gmanetwork.com/news/topstories/regions/973931/baste-duterte-takes-oath-as-davao-city-mayor/story/',
        'davao_council': 'https://davaocity.gov.ph/local-government/21st-city-council-commences-committee-leaders-elected/',
        'harold_comelec': 'https://www.comelec.gov.ph/php-tpls-attachments/2025NLE/COC_2025NLE/COC_Partylist162/2.%20PPP.pdf',
        'harold_house': 'https://congress.gov.ph/index.php/house-members/view/L033',
        'alan_senate': 'https://legacy.senate.gov.ph/senators/sen_bio/cayetano_alanpeter_bio.asp',
        'lani_mayor_2025': 'https://mb.com.ph/2025/05/14/sweet-sweep-victory-lani-cayetano-grateful-for-big-win-in-taguig',
        'senate_2025_winners': 'https://www.philstar.com/headlines/2025/05/18/2443908/comelec-proclaims-winning-senators',
        'senate_2022_cohort': 'https://legacy.senate.gov.ph/publications/STSRO/STSRO%20Primer%202022_Printed%20in%20July%202022.pdf',
        'gian_vice_mayor_2025': 'https://quezoncity.gov.ph/proclamation-of-quezon-city-local-candidates/',
        'vico_mayor_2025': 'https://mb.com.ph/2025/05/13/domagoso-reelected-in-manila-10-incumbent-mayors-win-fresh-mandates',
        'ralph_house_2025': 'https://congress.gov.ph/house-members/view/K089',
        'jocelyn_house_2025': 'https://www.congress.gov.ph/house-members/view/K102',
    }
    online_people = {
        'rodrigo': ('RODRIGO ROA DUTERTE', 'Davao del Sur', 'Davao City'),
        'sara': ('SARA Z. DUTERTE-CARPIO', 'Davao del Sur', 'Davao City'),
        'paolo': ('PAOLO Z. DUTERTE', 'Davao del Sur', 'Davao City'),
        'sebastian': ('SEBASTIAN Z. DUTERTE', 'Davao del Sur', 'Davao City'),
        'omar': ('OMAR VINCENT S. DUTERTE', 'Davao del Sur', 'Davao City'),
        'rigo': ('RODRIGO "RIGO" S. DUTERTE II', 'Davao del Sur', 'Davao City'),
        'harold': ('HAROLD JAMES TAPANGAN DUTERTE', '', 'Party-list'),
        'alan_cayetano': ('ALAN PETER CAYETANO', 'Metro Manila', 'Taguig'),
        'lani_cayetano': ('MARIA CAYETANO', 'Metro Manila', 'Taguig'),
        'joel_villanueva': ('JOEL VILLANUEVA', 'Metro Manila', 'Quezon City'),
        'migz_zubiri': ('JUAN MIGUEL ZUBIRI', 'Bukidnon', 'Malaybalay'),
        'tito_sotto': ('TITO SOTTO', 'Metro Manila', 'Quezon City'),
        'ping_lacson': ('PANFILO LACSON', 'Cavite', 'Imus'),
        'gian_sotto': ('GIAN CARLO SOTTO', 'Metro Manila', 'Quezon City'),
        'vico_sotto': ('VICO SOTTO', 'Metro Manila', 'Pasig City'),
        'ralph_tulfo': ('RALPH WENDEL TULFO', 'Metro Manila', 'Quezon City'),
        'jocelyn_tulfo': ('JOCELYN P TULFO', 'National', 'Party-list'),
    }
    online_records = []

    def add_online(slug, election_year, position, office_group, through, source_key,
                   district='', party='', note='', office_start=None,
                   family_key='source-family:duterte', family_basis='Publicly documented Duterte family link'):
        name, province, municipality = online_people[slug]
        person_key = 'online-person:' + slug
        alias_evidence = collect_alias_evidence(name)
        online_records.append({
            'personKey': person_key, 'familyKey': family_key,
            'name': name, 'position': position, 'odvPosition': position.upper(),
            'officeGroup': office_group, 'province': province, 'municipality': municipality,
            'district': district, 'region': 'Davao Region' if province else 'National',
            'party': party, 'electionYear': election_year,
            'officeStartYear': office_start if office_start is not None else election_year,
            'termYears': through - (office_start if office_start is not None else election_year),
            'termThroughYear': through,
            'sourceId': 'online-duterte-' + slug + '-' + str(election_year) + '-' + re.sub(r'\W+', '-', position.lower()).strip('-'),
            'familyBasis': family_basis,
            'aliasEvidence': alias_evidence,
            'roleSourceUrl': role_sources[source_key], 'roleNote': note,
        })

    # Davao executive offices and the Duterte family’s local/national terms.
    add_online('rodrigo', 2004, 'Mayor', 'Mayor', 2007, 'rodrigo_history')
    add_online('rodrigo', 2007, 'Mayor', 'Mayor', 2010, 'rodrigo_history')
    add_online('rodrigo', 2010, 'Vice Mayor', 'Vice Mayor', 2013, 'rodrigo_history')
    add_online('rodrigo', 2013, 'Mayor', 'Mayor', 2016, 'rodrigo_history')
    add_online('rodrigo', 2016, 'President', 'President / Vice President', 2022, 'rodrigo_history')
    # Rodrigo Duterte won the 2025 mayoral election but failed to take the
    # oath; the seat became vacant before he assumed office, so this outcome
    # is recorded as provenance below, not counted as an office held.

    add_online('sara', 2007, 'Vice Mayor', 'Vice Mayor', 2010, 'sara_history')
    add_online('sara', 2010, 'Mayor', 'Mayor', 2013, 'sara_history')
    add_online('sara', 2016, 'Mayor', 'Mayor', 2019, 'sara_history')
    add_online('sara', 2019, 'Mayor', 'Mayor', 2022, 'sara_history')
    add_online('sara', 2022, 'Vice President', 'President / Vice President', 2028, 'sara_history')

    add_online('paolo', 2007, 'Barangay Captain', 'Barangay captain', 2010, 'paolo_barangay',
               district='Catalunan Grande, Davao City')
    add_online('paolo', 2010, 'Barangay Captain', 'Barangay captain', 2013, 'paolo_barangay',
               district='Catalunan Grande, Davao City')
    add_online('paolo', 2013, 'Vice Mayor', 'Vice Mayor', 2016, 'paolo_resignation')
    add_online('paolo', 2016, 'Vice Mayor', 'Vice Mayor', 2017, 'paolo_resignation',
               note='Resigned on 25 December 2017.')
    add_online('paolo', 2019, 'House Representative · 1st District', 'Congress / party-list representative', 2022, '2025_winners', district='Davao City · 1st District')
    add_online('paolo', 2022, 'House Representative · 1st District', 'Congress / party-list representative', 2025, '2025_winners', district='Davao City · 1st District')
    add_online('paolo', 2025, 'House Representative · 1st District', 'Congress / party-list representative', 2028, '2025_winners', district='Davao City · 1st District')

    add_online('sebastian', 2019, 'Vice Mayor', 'Vice Mayor', 2022, 'davao_2019_2022')
    add_online('sebastian', 2022, 'Mayor', 'Mayor', 2025, 'sebastian_2022')
    add_online('sebastian', 2025, 'Acting Mayor', 'Mayor', 2026, 'davao_succession',
               note='Elected Vice Mayor in 2025; directed to act as Mayor from June 2025, then sworn in as Mayor on 23 January 2026.')
    add_online('sebastian', 2025, 'Mayor · by succession', 'Mayor', 2028, 'davao_succession',
               note='Sworn in as Mayor on 23 January 2026 after Rodrigo Duterte failed to take the oath.', office_start=2026)

    # The 2025 COMELEC results added two grandsons and a nephew to office.
    add_online('omar', 2025, 'House Representative · 2nd District', 'Congress / party-list representative', 2028, '2025_winners', district='Davao City · 2nd District')
    add_online('rigo', 2025, 'Councilor · 1st District', 'Councilor', 2028, '2025_winners', district='Davao City · 1st District')
    add_online('rigo', 2025, 'Acting Vice Mayor', 'Vice Mayor', 2026, 'davao_council',
               note='Became Acting Vice Mayor in July 2025; sworn in as Vice Mayor on 23 January 2026.')
    add_online('rigo', 2025, 'Vice Mayor · by succession', 'Vice Mayor', 2028, 'davao_council',
               note='Sworn in as Vice Mayor on 23 January 2026 after Sebastian Duterte succeeded to Mayor.', office_start=2026)
    add_online('harold', 2025, 'Party-list Representative · PPP', 'Congress / party-list representative', 2028, 'harold_house',
               party='Puwersa ng Pilipinong Pandagat (PPP)', district='Party-list')
    # Fill current national/local offices missing from ODV's winner-marked
    # archive so linked current Cayetano family terms are represented.
    add_online('alan_cayetano', 2022, 'Senator', 'Senator', 2028, 'alan_senate',
               family_key='source-family:cayetano',
               family_basis='Publicly documented Cayetano family link')
    add_online('lani_cayetano', 2025, 'Mayor', 'Mayor', 2028, 'lani_mayor_2025',
               family_key='source-family:cayetano',
               family_basis='Publicly documented Cayetano family link')
    # Complete the current Senate roster where ODV's 2025 snapshot omitted
    # 2022 cohort members, and correct missing 2025 winners/current local roles.
    add_online('joel_villanueva', 2022, 'Senator', 'Senator', 2028, 'senate_2022_cohort',
               family_key='source-family:senate-2022', family_basis='Official Senate 2022–2028 term roster')
    add_online('migz_zubiri', 2022, 'Senator', 'Senator', 2028, 'senate_2022_cohort',
               family_key='source-family:senate-2022', family_basis='Official Senate 2022–2028 term roster')
    add_online('tito_sotto', 2025, 'Senator', 'Senator', 2031, 'senate_2025_winners',
               family_key='source-family:sotto', family_basis='Publicly documented Sotto family link')
    add_online('ping_lacson', 2025, 'Senator', 'Senator', 2031, 'senate_2025_winners',
               family_key='source-family:senate-2025', family_basis='Officially proclaimed 2025 Senator')
    add_online('gian_sotto', 2025, 'Vice Mayor', 'Vice Mayor', 2028, 'gian_vice_mayor_2025',
               family_key='source-family:sotto', family_basis='Publicly documented Sotto family link')
    add_online('vico_sotto', 2025, 'Mayor', 'Mayor', 2028, 'vico_mayor_2025',
               family_key='source-family:sotto', family_basis='Publicly documented Sotto family link')
    add_online('ralph_tulfo', 2025, 'House Representative · 2nd District', 'Congress / party-list representative', 2028,
               'ralph_house_2025', district='Quezon City · 2nd District',
               family_key='source-family:tulfo', family_basis='Publicly documented Tulfo family link')
    add_online('jocelyn_tulfo', 2025, 'Party-list Representative · ACT-CIS', 'Congress / party-list representative', 2028,
               'jocelyn_house_2025', party='ACT-CIS', district='Party-list',
               family_key='source-family:tulfo', family_basis='Publicly documented Tulfo family link')
    records.extend(online_records)

    # Use the locally captured 20th Congress roster as the current House
    # officeholder source. The ODV 2025 election snapshot has incomplete and
    # duplicated winner rows, so replace its 2025 House rows with this roster.
    records = [r for r in records if not (r['electionYear'] == 2025 and
                                          r['officeGroup'] == 'Congress / party-list representative')]
    records = [r for r in records if not (r.get('sourceId', '').startswith('online-duterte-') and
                                          r['electionYear'] == 2025 and
                                          r['officeGroup'] == 'Congress / party-list representative')]
    house_family_people = {
        compact_norm('PAOLO DUTERTE'): ('PAOLO Z. DUTERTE', 'online-person:paolo', 'source-family:duterte', '2025_winners'),
        compact_norm('OMAR DUTERTE'): ('OMAR VINCENT S. DUTERTE', 'online-person:omar', 'source-family:duterte', '2025_winners'),
        compact_norm('HAROLD DUTERTE'): ('HAROLD JAMES TAPANGAN DUTERTE', 'online-person:harold', 'source-family:duterte', 'harold_house'),
        compact_norm('RALPH TULFO'): ('RALPH WENDEL TULFO', 'online-person:ralph_tulfo', 'source-family:tulfo', 'ralph_house_2025'),
        compact_norm('JOCELYN TULFO'): ('JOCELYN P TULFO', 'online-person:jocelyn_tulfo', 'source-family:tulfo', 'jocelyn_house_2025'),
    }
    family_source_by_key = {x['key']: x for x in documented_families}
    resignation_events = {}
    for item in raw_house_roster:
        if 'resigned' not in str(item.get('party') or '').casefold():
            continue
        name = compact_norm(re.sub(r'\[[^\]]+\]', '', str(item.get('province') or '')))
        date = re.sub(r'\[[^\]]+\]', '', str(item.get('representative') or '')).strip()
        if name:
            resignation_events[name] = date
    current_house_odv_match_count = 0
    current_house_fat_flag_count = 0
    current_house_verified_link_count = 0
    odv_flagged_full_names = set()
    if ODV_OFFICIALS.exists():
        try:
            with gzip.open(ODV_OFFICIALS, 'rt', encoding='utf-8', errors='replace', newline='') as stream:
                for row in csv.DictReader(stream):
                    if row.get('fat') != '1':
                        continue
                    name = ' '.join(row.get(field, '') for field in
                                    ('first_name', 'middle_name', 'last_name', 'suffix')).strip()
                    if compact_norm(name):
                        odv_flagged_full_names.add(compact_norm(name))
        except (OSError, UnicodeError, csv.Error):
            pass
    house_roster_records = []
    for seat in house_roster:
        roster_name = seat['name']
        family_person = house_family_people.get(compact_norm(roster_name))
        display_name = family_person[0] if family_person else roster_name.upper()
        if family_person:
            person_key = family_person[1]
            family_key = family_person[2]
            family_basis = 'Publicly documented family link'
            role_source = role_sources[family_person[3]]
        else:
            seat_identity = '|'.join((compact_norm(display_name), compact_norm(seat['province']),
                                      compact_norm(seat['district']), compact_norm(seat['party'])))
            person_key = 'current-house:' + hashlib.sha1(seat_identity.encode()).hexdigest()[:16]
            family_key = None
            family_basis = ''
            role_source = HOUSE_ROSTER_URL
        profile_alias = congressman_name_aliases.get(compact_norm(roster_name), '')
        odv_hits = list({hit['id']: hit for name in (roster_name, profile_alias)
                         for hit in odv_house_identity_rows.get(compact_norm(name), [])}.values())
        if odv_hits:
            current_house_odv_match_count += 1
            district_number = re.search(r'\d+', seat['district'])
            matching_house_hits = [hit for hit in odv_hits
                                   if office_group(hit['position']) == 'Congress / party-list representative'
                                   and (not district_number or not re.search(r'\d+', hit['district']) or
                                        district_number.group(0) == re.search(r'\d+', hit['district']).group(0))]
            identity_ids = {hit['unifiedId'] for hit in matching_house_hits if hit['unifiedId']}
            if len(identity_ids) == 1:
                unified_id = next(iter(identity_ids))
                family.union(person_key, 'person:' + unified_id)
                for hit in matching_house_hits:
                    if hit['unifiedId'] == unified_id:
                        family.union('id:' + hit['id'], 'person:' + unified_id)
            elif matching_house_hits:
                # Without a unified ODV ID, only attach source rows whose
                # normalized district matches this House seat. Exact name plus
                # seat identity is required; a surname match is never used.
                seat_number = district_number.group(0) if district_number else None
                selected = [hit for hit in matching_house_hits
                            if seat_number and re.search(r'\d+', hit['district']) and
                            re.search(r'\d+', hit['district']).group(0) == seat_number]
                for hit in selected:
                    family.union(person_key, 'id:' + hit['id'])
                    if hit['unifiedId']:
                        family.union('id:' + hit['id'], 'person:' + hit['unifiedId'])
            family_ids = {hit['familyId'] for hit in odv_hits if hit['familyId']}
            if len(family_ids) == 1:
                family.union(person_key, 'family:' + next(iter(family_ids)))
            if any(family.find(person_key) == family.find('id:' + hit['id']) for hit in odv_hits if hit['id']):
                current_house_verified_link_count += 1
        position = ('Party-list Representative · ' + seat['district'] if seat['seatType'] == 'party-list'
                    else 'House Representative · ' + seat['district'])
        source_id = '20th-house-' + hashlib.sha1((compact_norm(roster_name) + '|' + compact_norm(seat['district'])).encode()).hexdigest()[:16]
        resignation_date = resignation_events.get(compact_norm(roster_name))
        name_key = compact_norm(roster_name)
        # The ODV flag comes from any source row for that exact full name.
        # Do not carry it across first+last aliases because namesakes can be
        # different officials and the flag is only a screening indicator.
        dynasty_flag = any(compact_norm(name) in odv_flagged_full_names
                           for name in (roster_name, profile_alias) if name)
        current_house_fat_flag_count += bool(dynasty_flag)
        house_alias_evidence = collect_alias_evidence(
            display_name,
            ([{'name': profile_alias, 'source': 'ODV congressman profile · unique display/full-name pair'}]
             if profile_alias else []) +
            [item for hit in odv_hits for item in odv_aliases_by_id.get(hit['id'], [])])
        house_roster_records.append({
            'personKey': person_key, 'familyKey': family_key, 'name': display_name,
            'aliasEvidence': house_alias_evidence,
            'position': position, 'odvPosition': 'PARTY-LIST REPRESENTATIVE' if seat['seatType'] == 'party-list' else 'MEMBER, HOUSE OF REPRESENTATIVES',
            'officeGroup': 'Congress / party-list representative',
            'province': seat['province'], 'municipality': '', 'district': seat['district'],
            'region': 'National' if seat['seatType'] == 'party-list' else '',
            'party': seat['district'] if seat['seatType'] == 'party-list' else seat['party'],
            'electionYear': 2025, 'officeStartYear': 2025, 'termYears': 3,
            'termThroughYear': 2025 if resignation_date else 2028,
            'sourceId': source_id, 'familyBasis': family_basis, 'roleSourceUrl': role_source,
            'roleNote': ('20th Congress House roster; ' + ('party-list seat.' if seat['seatType'] == 'party-list' else 'district seat.') +
                         (f' Roster records resignation on {resignation_date}; term is not extended beyond 2025.' if resignation_date else '')),
            'odvDynastyFlag': bool(dynasty_flag),
        })
    records.extend(house_roster_records)

    # Add source-linked family-parser relationships to ODV officeholder
    # identities. This repository contains reviewed research extracts from
    # Wikipedia, Rappler, and other public reporting. Require an explicit
    # kinship type, confidence >= 8/10, and a source URL. Political allies,
    # succession, same-person, and vague dynasty labels are not kinship edges.
    kinship_terms = {
        'father/son', 'father/daughter', 'son/father', 'daughter/father',
        'mother/son', 'mother/daughter', 'son/mother', 'daughter/mother',
        'husband/wife', 'wife/husband', 'brother/brother', 'brother/sister',
        'sister/brother', 'sister/sister', 'brother', 'sister', 'cousin',
        'father-in-law/son-in-law', 'father-in-law/daughter-in-law',
        'sister/brother-in-law', 'brother-in-law/sister-in-law',
        'sister-in-law', 'brother-in-law', 'grandfather/grandson',
        'grandson/grandfather', 'grandson/grandmother', 'nephew/aunt',
        'niece/uncle', 'nephew/uncle', 'uncle/nephew', 'son', 'sisters',
        'father', 'mother', 'daughter', 'husband', 'wife', 'spouse', 'parent', 'child',
        'uncle', 'aunt', 'nephew', 'niece', 'grandfather', 'grandmother',
        'grandson', 'granddaughter', 'granduncle', 'grandaunt', 'father-in-law',
        'mother-in-law', 'son-in-law', 'daughter-in-law', 'grandchild',
    }
    house_person_keys = {r['personKey'] for r in house_roster_records}
    # Full names are primary. A first+last alias is admitted only where it
    # identifies exactly one person in the relevant roster or office records.
    house_aliases = defaultdict(set)
    office_aliases = defaultdict(set)
    for record in house_roster_records:
        house_aliases[compact_norm(record['name'])].add(record['personKey'])
        for alias in record.get('aliasEvidence', []):
            house_aliases[compact_norm(alias.get('name'))].add(record['personKey'])
        alias = first_last_key(record['name'])
        if alias:
            house_aliases[alias].add(record['personKey'])
    for record in records:
        if record.get('asogOnly'):
            continue
        office_aliases[compact_norm(record['name'])].add(record['personKey'])
        for alias in record.get('aliasEvidence', []):
            office_aliases[compact_norm(alias.get('name'))].add(record['personKey'])
        alias = first_last_key(record['name'])
        if alias:
            office_aliases[alias].add(record['personKey'])
    cited_family_edges = []
    seen_cited_edges = set()
    relationship_paths = sorted(FAMILY_LINK_DIR.glob('llm_relationships_*.csv'))
    relationship_paths.extend(sorted((ROOT / 'database').rglob('*.csv')))
    specific_relationship_file = FAMILY_LINK_DIR / 'all_names_relationships_csvs/llm_specific_names_relationships.csv'
    if specific_relationship_file.exists():
        relationship_paths.append(specific_relationship_file)
    for path in relationship_paths:
        try:
            with path.open(encoding='utf-8-sig', newline='') as stream:
                for relation in csv.DictReader(stream):
                    relation_type = (relation.get('relationship_type') or '').strip().casefold()
                    source_url = (relation.get('source_url') or '').strip()
                    if not re.match(r'^https?://', source_url, re.I):
                        continue
                    try:
                        confidence = int(relation.get('confidence_level') or 0)
                    except ValueError:
                        continue
                    left_name = (relation.get('person1_name') or '').strip()
                    right_name = (relation.get('person2_name') or '').strip()
                    if (relation_type not in kinship_terms or confidence < 8 or not source_url
                            or not left_name or not right_name):
                        continue

                    def resolve_person(name, aliases, exact_only=False):
                        candidates = aliases.get(compact_norm(name), set())
                        if not candidates and not exact_only:
                            alias = first_last_key(name)
                            candidates = aliases.get(alias, set()) if alias else set()
                        return next(iter(candidates)) if len(candidates) == 1 else None

                    left_house = resolve_person(left_name, house_aliases)
                    right_house = resolve_person(right_name, house_aliases)
                    # At least one side must be a current House member. Resolve
                    # the other side against the complete elected-office set.
                    if left_house:
                        left_key = left_house
                        right_key = resolve_person(right_name, office_aliases)
                    elif right_house:
                        left_key = resolve_person(left_name, office_aliases)
                        right_key = right_house
                    else:
                        continue
                    if not left_key or not right_key or left_key == right_key:
                        continue
                    identity = tuple(sorted((left_key, right_key))) + (relation_type, source_url)
                    if identity in seen_cited_edges:
                        continue
                    seen_cited_edges.add(identity)
                    family.union(left_key, right_key)
                    edge = {'a': left_key, 'b': right_key, 'type': relation_type,
                            'detail': (relation.get('relationship_description') or '').strip(),
                            'basis': 'cited family-parser relationship', 'sourceUrl': source_url,
                            'confidence': confidence}
                    edges.append(edge)
                    cited_family_edges.append(edge)
        except (OSError, UnicodeError, csv.Error):
            continue
    cited_house_link_count = len({key for edge in cited_family_edges
                                  for key in (edge['a'], edge['b']) if key in house_person_keys})

    # Succession changes are one continuous office tenure for the same
    # Duterte official; do not count the acting title and the sworn-in title
    # as duplicate officeholders during their transition year.
    for source_id, person_key, combined_position, note in (
        ('online-duterte-sebastian-2025-acting-mayor', 'online-person:sebastian',
         'Mayor · acting then by succession',
         'Began acting as Mayor in June 2025 and was sworn in after succession on 23 January 2026; modeled once as one continuous mayoral tenure.'),
        ('online-duterte-rigo-2025-acting-vice-mayor', 'online-person:rigo',
         'Vice Mayor · acting then by succession',
         'Became Acting Vice Mayor in July 2025 and was sworn in after succession on 23 January 2026; modeled once as one continuous vice-mayoral tenure.'),
    ):
        transition = next((r for r in records if r.get('sourceId') == source_id), None)
        if not transition:
            continue
        person = dict(transition)
        person.update({'position': combined_position, 'odvPosition': combined_position.upper(),
                       'officeStartYear': 2025, 'termYears': 3, 'termThroughYear': 2028,
                       'roleNote': note})
        records = [r for r in records if r.get('personKey') != person_key or
                   not (r['electionYear'] == 2025 and r['officeGroup'] in {'Mayor','Vice Mayor'} and
                        ('acting' in r['position'].casefold() or 'by succession' in r['position'].casefold()))]
        records.append(person)
    # Rigo left his elected councilor seat when he became vice mayor. Retain
    # the councilor year as a completed, separate office and avoid carrying
    # that seat forward alongside the succession tenure.
    for record in records:
        if record.get('personKey') == 'online-person:rigo' and record['position'] == 'Councilor · 1st District':
            record['termThroughYear'] = 2025
            record['termYears'] = 0
            record['roleNote'] = 'Held the elected councilor seat before becoming Acting Vice Mayor in July 2025.'

    documented_member_keys = set()
    documented_family_basis = {}
    for documented in documented_families:
        aliases = {compact_norm(name) for name in documented['members']}
        member_keys = {record['personKey'] for record in records
                       if compact_norm(record['name']) in aliases}
        for record in records:
            if compact_norm(record['name']) in aliases:
                record['documentedFamilyKey'] = documented['key']
                record['documentedFamilyBasis'] = documented['basis']
        for member_key in member_keys:
            family.union(member_key, documented['key'])
            documented_member_keys.add(member_key)
            documented_family_basis[member_key] = documented['basis']

    # ODV has multiple person/unified-person IDs for a few officials who are
    # already connected inside the same explicit family. Collapse these
    # duplicate identities so their separate office rows become one family
    # member with a complete history. The exact full name and shared verified
    # family component are both required; surname-only matching is not used.
    identity_groups = defaultdict(list)
    for record in records:
        root = family.find(record['personKey'])
        identity_groups[(root, compact_norm(record['name']))].append(record)
    identity_dedup_count = 0
    for (root, identity), matches in identity_groups.items():
        old_keys = {record['personKey'] for record in matches}
        if len(old_keys) < 2 or not identity:
            continue
        canonical_key = 'family-person:' + hashlib.sha1((root + '|' + identity).encode()).hexdigest()[:16]
        family.union(canonical_key, root)
        for record in matches:
            record['personKey'] = canonical_key
            record['identityDedupBasis'] = 'Exact full name within the same linked family group; ODV person IDs consolidated'
        identity_dedup_count += len(old_keys) - 1

    # ODV repeats some winners once for every municipality in a province (and
    # senators once for many municipalities). Those rows describe one seat,
    # not separate offices. Collapse to one person + election + position.
    # For national positions, exact full name + position + year also catches
    # duplicate ODV entity IDs. For local positions, keep the stable person
    # key so same-name candidates in separate places remain distinct.
    office_groups = defaultdict(list)
    for record in records:
        key = (office_identity(record), record['electionYear'], compact_norm(record['position']),
               record['officeGroup'], record.get('officeStartYear', record['electionYear']),
               record['termThroughYear'])
        office_groups[key].append(record)

    # Merge family components linked through duplicate national-office IDs,
    # then repeat the exact-name identity pass. This catches one ODV person
    # whose historical rows use a location-based key while later rows use a
    # unified ID, where the connecting family edge appears on another record.
    for matches in office_groups.values():
        for duplicate in matches[1:]:
            family.union(matches[0]['personKey'], duplicate['personKey'])

    # Some local winners have duplicate ODV IDs despite identical full names
    # and the same municipality, office, and election. Collapse only this
    # exact seat collision; same-name officials in different places stay
    # separate. Barangay captain rows lack a barangay identifier and are not
    # inferred to be duplicates from municipality alone.
    # Explicitly reconcile the ODV Ginatilan entries "Karyn Duterte" and
    # "Karyn James Duterte" using public reports identifying Karyn James
    # Duterte as the Ginatilan councilor. Do not generalize this to other
    # same-surname officials or to other first/last-name variants.
    karyn_aliases = {compact_norm('Karyn Duterte'), compact_norm('Karyn James Duterte'),
                     compact_norm('Karyn James Berongan Duterte')}
    karyn_records = [r for r in records if compact_norm(r['name']) in karyn_aliases
                     and compact_norm(r.get('province')) == compact_norm('Cebu')
                     and compact_norm(r.get('municipality')) == compact_norm('Ginatilan')
                     and r['officeGroup'] == 'Councilor']
    karyn_person_keys = {r['personKey'] for r in karyn_records}
    karyn_duterte_name_variants_deduplicated = int(len(karyn_person_keys) > 1)
    if karyn_duterte_name_variants_deduplicated:
        canonical = 'documented-person:karyn-james-berongan-duterte'
        for person_key in karyn_person_keys:
            family.union(canonical, person_key)
        for record in records:
            if record['personKey'] in karyn_person_keys:
                record['personKey'] = canonical
    local_seat_groups = defaultdict(list)
    for record in records:
        province = compact_norm(record.get('province'))
        municipality = compact_norm(record.get('municipality'))
        if (record['officeGroup'] == 'Barangay captain' or not province or not municipality):
            continue
        key = ('local-seat-name:' + compact_norm(record['name']), province, municipality,
               compact_norm(record.get('district')), record['electionYear'],
               compact_norm(record['position']), record.get('officeStartYear', record['electionYear']),
               record['termThroughYear'])
        local_seat_groups[key].append(record)
    for matches in local_seat_groups.values():
        for duplicate in matches[1:]:
            family.union(matches[0]['personKey'], duplicate['personKey'])
    identity_groups = defaultdict(list)
    for record in records:
        identity_groups[(family.find(record['personKey']), compact_norm(record['name']))].append(record)
    for (root, identity), matches in identity_groups.items():
        old_keys = {record['personKey'] for record in matches}
        if len(old_keys) < 2 or not identity:
            continue
        canonical_key = 'family-person:' + hashlib.sha1((root + '|' + identity).encode()).hexdigest()[:16]
        family.union(canonical_key, root)
        for record in matches:
            record['personKey'] = canonical_key
        identity_dedup_count += len(old_keys) - 1

    office_groups = defaultdict(list)
    for record in records:
        key = (office_identity(record), record['electionYear'], compact_norm(record['position']),
               record['officeGroup'], record.get('officeStartYear', record['electionYear']),
               record['termThroughYear'])
        office_groups[key].append(record)

    deduped_records = []
    duplicate_office_rows_removed = 0
    for matches in office_groups.values():
        # Deterministically retain a source row with the most complete fields.
        matches.sort(key=lambda r: (-sum(bool(r.get(k)) for k in ('region', 'province', 'municipality', 'district', 'party')),
                                    str(r.get('sourceId', ''))))
        record = matches[0]
        duplicate_office_rows_removed += len(matches) - 1
        for field in ('region', 'province', 'municipality', 'district'):
            values = {r.get(field, '') for r in matches if r.get(field, '')}
            if office_level(record['officeGroup']) == 'national' and field in {'province', 'municipality', 'district'}:
                record[field] = ''
            elif len(values) == 1:
                record[field] = next(iter(values))
            elif len(values) > 1:
                record[field] = ''
        if office_level(record['officeGroup']) == 'national':
            record['region'] = 'National'
        record['aliasEvidence'] = collect_alias_evidence(
            record['name'], [item for match in matches for item in match.get('aliasEvidence', [])])
        if len(matches) > 1:
            record['sourceRowIds'] = sorted({r['sourceId'] for r in matches if r.get('sourceId')})
            record['duplicateRowsCollapsed'] = len(matches) - 1
            localities = sorted({', '.join(x for x in (r.get('municipality'), r.get('province')) if x)
                                 for r in matches if r.get('municipality') or r.get('province')})
            if len(localities) > 1:
                note = f"ODV repeated this same person and office across {len(localities)} location labels; duplicate rows were consolidated and conflicting place labels were omitted."
                record['roleNote'] = (record.get('roleNote', '') + ' ' + note).strip()
        deduped_records.append(record)
    records = deduped_records

    aliases_by_person = defaultdict(list)
    for record in records:
        aliases_by_person[record['personKey']].extend(record.get('aliasEvidence', []))
    for record in records:
        record['aliasEvidence'] = collect_alias_evidence(record['name'], aliases_by_person[record['personKey']])
        record['aliases'] = [item['name'] for item in record['aliasEvidence']]

    # Build overlapping family officeholder windows. NO applies when two or
    # more distinct family members hold office in the same calendar year,
    # except a family represented by exactly one local and one national
    # officeholder in that year.
    offices_by_family = defaultdict(list)
    for record in records:
        root = family.find(record['personKey'])
        linked = (any(family.find(e['a']) == root or family.find(e['b']) == root for e in edges)
                  or root.startswith('family:') or record.get('documentedFamilyKey')
                  or record['personKey'] in documented_member_keys)
        record['familyKey'] = (record.get('documentedFamilyKey') or root) if linked else None
        if record['familyKey']:
            if not record['familyBasis']:
                record['familyBasis'] = (record.get('documentedFamilyBasis') or
                                         ('Cited family relationship' if any(
                                             family.find(edge['a']) == root or family.find(edge['b']) == root
                                             for edge in cited_family_edges) else
                                          ('Publicly documented family link' if record['personKey'] in documented_member_keys
                                           else 'ODV linked family group')))
            offices_by_family[record['familyKey']].append(record)
    no_vote_decisions = {}
    for family_key, members in offices_by_family.items():
        # Compress duplicate rows for the same person/office/election year.
        dedup = {}
        for member in members:
            dedup[(member['personKey'], member['officeGroup'], member['electionYear'],
                   member.get('officeStartYear', member['electionYear']), member['termThroughYear'],
                   member['position'])] = member
        members = list(dedup.values())
        for member in members:
            concurrent_by_person = defaultdict(list)
            no_vote_years = set()
            for other in members:
                if other['personKey'] == member['personKey']:
                    continue
                start = max(member.get('officeStartYear', member['electionYear']),
                            other.get('officeStartYear', other['electionYear']))
                end = min(member['termThroughYear'], other['termThroughYear'])
                if start > end:
                    continue
                years = list(range(start, end + 1))
                concurrent_by_person[other['personKey']].append({
                    'name': other['name'], 'position': other['position'],
                    'officeGroup': other['officeGroup'], 'province': other['province'],
                    'municipality': other['municipality'], 'electionYear': other['electionYear'],
                    'overlapYears': years,
                })
            concurrent = []
            for office_records in concurrent_by_person.values():
                positions = sorted({office['position'] for office in office_records})
                years = sorted({year for office in office_records for year in office['overlapYears']})
                representative = min(office_records, key=lambda office: (office['electionYear'], office['position']))
                concurrent.append({
                    'name': representative['name'], 'position': '; '.join(positions),
                    'aliases': representative.get('aliases', []),
                    'officeGroup': representative['officeGroup'], 'province': representative['province'],
                    'municipality': representative['municipality'], 'electionYear': representative['electionYear'],
                    'overlapYears': years,
                })
            for year in range(member.get('officeStartYear', member['electionYear']), member['termThroughYear'] + 1):
                active = [other for other in members
                          if other.get('officeStartYear', other['electionYear']) <= year <= other['termThroughYear']]
                levels_by_person = defaultdict(set)
                for official in active:
                    levels_by_person[official['personKey']].add(office_level(official['officeGroup']))
                if len(levels_by_person) < 2:
                    continue
                # Exclude precisely the single-local + single-national case.
                if (len(levels_by_person) == 2 and
                    sorted(tuple(sorted(levels)) for levels in levels_by_person.values()) == [('local',), ('national',)]):
                    continue
                no_vote_years.add(year)
            member['doNotVote'] = bool(no_vote_years)
            member['noVoteYears'] = sorted(no_vote_years)
            member['concurrentFamilyOfficeholders'] = sorted(concurrent, key=lambda x: (x['electionYear'], x['name'], x['position']))
            no_vote_decisions[(family_key, member['personKey'], member['officeGroup'], member['electionYear'],
                               member.get('officeStartYear', member['electionYear']), member['termThroughYear'],
                               member['position'])] = member
    for record in records:
        decision = no_vote_decisions.get((record['familyKey'], record['personKey'], record['officeGroup'], record['electionYear'],
                                          record.get('officeStartYear', record['electionYear']), record['termThroughYear'],
                                          record['position'])) if record['familyKey'] else None
        record['doNotVote'] = bool(decision and decision['doNotVote'])
        record['noVoteYears'] = decision['noVoteYears'] if decision else []
        record.setdefault('concurrentFamilyOfficeholders', decision['concurrentFamilyOfficeholders'] if decision else [])
        record.setdefault('concurrentFamilyOfficeholders', [])

    # Keep a complete linked-family history separately from each row. The page
    # can open this on demand without duplicating a large family list on every
    # officeholder record in the JSON.
    family_history = defaultdict(dict)
    for record in records:
        if not record['familyKey']:
            continue
        person = family_history[record['familyKey']].setdefault(record['personKey'], {
            'personKey': record['personKey'], 'name': record['name'], 'offices': [],
            'aliases': record.get('aliases', []), 'aliasEvidence': record.get('aliasEvidence', [])
        })
        office = {
            'position': record['position'], 'officeGroup': record['officeGroup'],
            'province': record['province'], 'municipality': record['municipality'],
            'district': record['district'], 'party': record['party'],
            'electionYear': record['electionYear'], 'officeStartYear': record.get('officeStartYear', record['electionYear']),
            'termThroughYear': record['termThroughYear'], 'roleNote': record.get('roleNote', ''),
            'roleSourceUrl': record.get('roleSourceUrl', '')
        }
        if office not in person['offices']:
            person['offices'].append(office)
    family_history = {
        key: sorted((dict(member, offices=sorted(member['offices'], key=lambda x: (x['electionYear'], x['position'], x['province'], x['municipality'])))
                    for member in members.values()), key=lambda x: (norm(x['name']), x['name']))
        for key, members in family_history.items()
    }

    cited_evidence_by_root = defaultdict(list)
    for edge in cited_family_edges:
        root = family.find(edge['a'])
        item = {'relationship': edge['detail'] or edge['type'], 'sourceUrl': edge['sourceUrl'],
                'confidence': edge['confidence']}
        if item not in cited_evidence_by_root[root]:
            cited_evidence_by_root[root].append(item)
    family_link_evidence = {}
    for record in records:
        if not record.get('familyKey'):
            continue
        items = cited_evidence_by_root.get(family.find(record['personKey']), [])
        documented = next((item for item in documented_families
                           if item['key'] == record['familyKey']), None)
        if documented:
            items = items + [{'relationship': documented['basis'], 'sourceUrl': url,
                              'confidence': None} for url in documented['sources']]
        if items:
            target = family_link_evidence.setdefault(record['familyKey'], [])
            target.extend(item for item in items if item not in target)
    current_house_family_linked_rows = sum(bool(r.get('familyKey')) for r in house_roster_records)
    current_house_no_vote_rows = sum(bool(r.get('doNotVote')) for r in house_roster_records)

    records.sort(key=lambda r: (r['electionYear'], r['officeGroup'], norm(r['province']), norm(r['municipality']), norm(r['name'])))
    result = {
        'generatedAt': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
        'source': 'Historical elected-office records; Ateneo Policy Center historical election data (2004–2016); official 20th Congress roster; and cited public family-relationship sources',
        'years': sorted({r['electionYear'] for r in records}),
        'scope': 'Deduplicated elected office records in archived ODV data for national and local offices from 2004–2025, supplemented with the local 20th Congress district and party-list roster and cited current roles/family links. This is not a complete national/local officeholder roster and is not a 2028 candidate list.',
        'recordsScope': 'The records array contains officeholders whose linked-family records meet the displayed one-at-a-time criterion in one or more modeled years. The families object retains linked historical family-member office records for context.',
        'method': {
            'noVoteRule': 'A red marker means at least two distinct linked family members held office in the same modeled calendar year. A family with exactly one local and one national officeholder in that year is excluded. Links come from ODV-verified relationships, shared ODV dynasty_family_id, or specifically cited public family sources; shared surnames alone do not count.',
            'aliases': 'Official names remain the primary display and identity fields. Usable ODV nickname-field values and separately cited public aliases are preserved as aliases for search, display, details, and export. Date-like values and a short list of known agency abbreviations are excluded. Nicknames never determine family links or identity merges.',
            'officeLevels': 'President/vice president, senators, and House/party-list representatives are classified as national. Governors, vice governors, mayors, vice mayors, provincial board members, and councilors are classified as local.',
            'terms': 'President/vice president and senators are modeled as six-year terms; other included elected positions as three-year terms, based on the election year in ODV. Partial final calendar years are included in overlap checks.',
            'familyLinks': 'Uses ODV relationship records marked verified=true (family relationship types 1–20), source dynasty_family_id values, cited public family links, and source-linked family-parser edges with explicit kinship types and confidence >= 8/10. Family-parser edges connect to the 20th House roster only on exact full-name matches or unique first+last aliases, and connect to another elected officeholder only when that name resolves uniquely. Political allies, succession claims, same-person labels, vague dynasty labels, and surname-only matching are excluded. Duplicate person IDs are consolidated only with an exact full name inside a linked family group or on the same fully identified local seat. Repeated copies of one national office or House seat in the same election year are collapsed; distinct House districts remain separate.',
            'odvFamilyPageScreen': 'A separate broad coverage count matches current district representatives to the archived ODV family-page grouping by exact province and surname where at least two distinct officials in the historical 2004–2016 records carry the ODV dynasty-screen flag. The match does not establish that the current representative is related to those officials or that they held office concurrently. It is not proof of kinship and never creates a family edge or NO mark.',
            'localNameDeduplication': 'The documented Ginatilan entries Karyn Duterte and Karyn James Duterte are consolidated as one person using public reporting. This is a specific source-backed alias reconciliation, not a general first+last or shared-surname merge.',
            'historicalElectionData': 'The Ateneo Policy Center historical election dataset adds 2004–2016 elected-office records and a separate dynasty-screen flag. Its flag is not a person-to-person relationship and never establishes a person-to-person family link or creates a red marker. ODV congressman display/full-name variants are used only as unique name aliases; congressman family_connections fields list contractor entities, so they are excluded from family-link evidence. Party-list membership rows are an identity/seat source, not kinship evidence.',
            'limitations': 'The archived ODV records remain incomplete and vary by election year and office. All 311 current district and party-list House seats are represented from the locally captured 20th Congress roster; exact ODV and cited-kinship match counts are reported in the summary. The historical election dataset adds records where ODV rows were absent, but historical 2019 coverage and 2022/2025 local-office coverage remain sparse. ODV fat=1 and the Ateneo dynasty flag are screening markers only; neither is proof of a specific kinship link and neither independently creates a family group or NO vote. Some source rows or relationships may still be omitted or misclassified. NO years use inclusive modeled calendar-year windows; check linked evidence and official records before relying on a marker. No NO means this incomplete screen found no qualifying overlap, not that an official has no family ties.',
        },
        'summary': {
            'officialRows': len(records),
            'noVoteRows': sum(r['doNotVote'] for r in records),
            'noVoteRowsWithKnownAliases': sum(bool(r.get('aliases')) for r in records if r['doNotVote']),
            'familyGroupsWithQualifyingTerms': len({r['familyKey'] for r in records if r['doNotVote']}),
            'duplicatePersonIdsConsolidatedWithinFamilies': identity_dedup_count,
            'duplicateOfficeRowsRemoved': duplicate_office_rows_removed,
            'asogHistoricalElectionRowsRead': asog_rows_loaded,
            'asogDynastyScreenFlaggedElectionRows': asog_dynasty_flag_rows,
            'asogRowsMatchedToODVPersonIdentity': asog_exact_identity_matches_to_odv,
            'asogAdditionalHistoricalOfficeRows': asog_election_rows_added,
            'asogUnmatchedOrAmbiguousIdentityRows': asog_unmatched_or_ambiguous_identity_rows,
            'odvCongressmanProfilesRead': len(congressman_profiles),
            'odvCongressmanUniqueNameVariantPairs': congressman_unique_name_variant_pairs,
            'DuterteNameVariantsDeduplicated': karyn_duterte_name_variants_deduplicated,
            'senateSnapshotRowsCorrectedTo2022Term': senate_snapshot_rows_corrected,
            'senateNameVariantsNormalized': senate_name_variants_normalized,
            'misclassifiedSenateRowsRemoved': misclassified_senate_rows_removed,
            'currentHouseRosterRows': len(house_roster),
            'currentHouseODVExactNameMatches': current_house_odv_match_count,
            'currentHouseODVDynastyFlagMatches': current_house_fat_flag_count,
            'currentHouseODVIdentityLinkedRows': current_house_verified_link_count,
            'currentHouseCitedKinshipLinkMatches': cited_house_link_count,
            'currentHouseFamilyLinkedRows': current_house_family_linked_rows,
            'currentHouseODVFamilyPageGroupMatches': current_house_odv_family_page_group_matches,
            'currentHouseNoVoteRows': current_house_no_vote_rows,
            'citedKinshipEdgesUsed': len(cited_family_edges),
            'currentHouseRosterSource': HOUSE_ROSTER_URL,
            'byYear': {str(y): {'rows': sum(r['electionYear'] == y for r in records), 'noVoteRows': sum(r['electionYear'] == y and r['doNotVote'] for r in records)} for y in sorted({r['electionYear'] for r in records})},
            'byOffice': {g: {'rows': sum(r['officeGroup'] == g for r in records), 'noVoteRows': sum(r['officeGroup'] == g and r['doNotVote'] for r in records)} for g in sorted({r['officeGroup'] for r in records})},
        },
        'documentedFamilyLinks': documented_families,
        'documentedNameVariantLinks': [{
            'names': ['Karyn Duterte', 'Karyn James Duterte'],
            'scope': 'Ginatilan, Cebu councilor records',
            'sources': ['https://www.philstar.com/cebu-news/2005/06/25/283619/town-mayor-defends-speedy-budget-okay',
                        'https://www.comelec.gov.ph/php-tpls-attachments/2019NLE/ElectionResults/2019NLE_LIst_of_Elected_CityMun_Candidates.pdf']
        }],
        'documentedRoleOutcomes': [{
            'name': online_people['rodrigo'][0], 'electionYear': 2025,
            'outcome': 'Elected mayor but did not take the oath and did not assume office; not counted as an officeholder for this screen.',
            'sourceUrl': 'https://www.gmanetwork.com/news/topstories/regions/973931/baste-duterte-takes-oath-as-davao-city-mayor/story/'
        }],
        'families': family_history,
        'familyLinkEvidence': family_link_evidence,
        'records': [record for record in records if record['doNotVote']],
    }
    def public_copy(value):
        if isinstance(value, dict):
            clean = {}
            for key, item in value.items():
                if key == 'sourceSha256':
                    continue
                public_key = key.replace('ODV', 'Historical').replace('odv', 'archive')
                clean[public_key] = public_copy(item)
            return clean
        if isinstance(value, list):
            return [public_copy(item) for item in value]
        if isinstance(value, str):
            return re.sub(r'(?i)odv', 'historical archive', value)
        return value

    result = public_copy(result)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n')
    return result['summary']


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False, indent=2))
