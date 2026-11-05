#!/usr/bin/env python3
"""Build the Vote 2028 officeholder review from the archived ODV dynasty dump."""
import gzip
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'database/dynasty_dump.sql.gz'
OUT = ROOT / 'static/nep-preview/vote-2028-data.json'


def norm(value):
    value = unicodedata.normalize('NFKD', str(value or ''))
    value = ''.join(c for c in value if not unicodedata.combining(c))
    return re.sub(r'[^A-Z0-9]+', ' ', value.upper()).strip()


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
    for row in parse_copy(SOURCE, 'political_dynasties'):
        if len(row) < 30 or row[11] != 't' or row[15].lower() != 'elected' or row[8] == r'\N':
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
            'province': province, 'municipality': municipality, 'district': district,
            'region': '' if row[4] == r'\N' else row[4], 'party': party,
            'electionYear': election_year, 'termYears': role_years,
            'termThroughYear': election_year + role_years,
            'sourceId': row[0], 'familyBasis': 'ODV verified relationship' if any(e['a'] == node or e['b'] == node for e in edges) else ('ODV dynasty family ID' if family_id else ''),
        })

    # Build overlapping family officeholder windows. NO applies when two or
    # more distinct family members hold office in the same calendar year,
    # except a family represented by exactly one local and one national
    # officeholder in that year.
    offices_by_family = defaultdict(list)
    for record in records:
        root = family.find(record['personKey'])
        record['familyKey'] = root if any(family.find(e['a']) == root or family.find(e['b']) == root for e in edges) or root.startswith('family:') else None
        if record['familyKey']:
            if not record['familyBasis']:
                record['familyBasis'] = 'ODV linked family group'
            offices_by_family[record['familyKey']].append(record)
    no_vote_decisions = {}
    for family_key, members in offices_by_family.items():
        # Compress duplicate rows for the same person/office/election year.
        dedup = {}
        for member in members:
            dedup[(member['personKey'], member['officeGroup'], member['electionYear'])] = member
        members = list(dedup.values())
        for member in members:
            concurrent = []
            no_vote_years = set()
            for other in members:
                if other['personKey'] == member['personKey']:
                    continue
                start = max(member['electionYear'], other['electionYear'])
                end = min(member['termThroughYear'], other['termThroughYear'])
                if start > end:
                    continue
                years = list(range(start, end + 1))
                concurrent.append({
                    'name': other['name'], 'position': other['position'],
                    'officeGroup': other['officeGroup'], 'province': other['province'],
                    'municipality': other['municipality'], 'electionYear': other['electionYear'],
                    'overlapYears': years,
                })
            for year in range(member['electionYear'], member['termThroughYear'] + 1):
                active = [other for other in members
                          if other['electionYear'] <= year <= other['termThroughYear']]
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
            no_vote_decisions[(family_key, member['personKey'], member['officeGroup'], member['electionYear'])] = member
    for record in records:
        decision = no_vote_decisions.get((record['familyKey'], record['personKey'], record['officeGroup'], record['electionYear'])) if record['familyKey'] else None
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
            'personKey': record['personKey'], 'name': record['name'], 'offices': []
        })
        office = {
            'position': record['position'], 'officeGroup': record['officeGroup'],
            'province': record['province'], 'municipality': record['municipality'],
            'district': record['district'], 'party': record['party'],
            'electionYear': record['electionYear'], 'termThroughYear': record['termThroughYear']
        }
        if office not in person['offices']:
            person['offices'].append(office)
    family_history = {
        key: sorted((dict(member, offices=sorted(member['offices'], key=lambda x: (x['electionYear'], x['position'], x['province'], x['municipality'])))
                    for member in members.values()), key=lambda x: (norm(x['name']), x['name']))
        for key, members in family_history.items()
    }

    records.sort(key=lambda r: (r['electionYear'], r['officeGroup'], norm(r['province']), norm(r['municipality']), norm(r['name'])))
    result = {
        'generatedAt': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
        'source': 'ODV database/dynasty_dump.sql.gz · political_dynasties and verified relationships tables',
        'sourceSha256': source_hash,
        'years': sorted({r['electionYear'] for r in records}),
        'scope': 'Winner-marked elected office records present in the archived ODV source for president, vice president, senators, House and party-list representatives, governors, vice governors, mayors, vice mayors, provincial board members and councilors. The archived source has no identifiable barangay captain office rows, and its 2019 winner-marked office coverage is incomplete. Latest source election snapshot is 2025; this is not a 2028 candidate list.',
        'recordsScope': 'The records array contains NO-marked officeholders only. The families object retains linked historical family-member office records for context.',
        'method': {
            'noVoteRule': 'NO means at least two distinct ODV-linked family members held office in the same modeled calendar year. A family with exactly one local and one national officeholder in that year is excluded. This Dapat Isa Lang–inspired screen is applied only to verified ODV relationships or shared ODV dynasty_family_id; shared surnames alone do not count.',
            'officeLevels': 'President/vice president, senators, and House/party-list representatives are classified as national. Governors, vice governors, mayors, vice mayors, provincial board members, and councilors are classified as local.',
            'terms': 'President/vice president and senators are modeled as six-year terms; other included elected positions as three-year terms, based on the election year in ODV. Partial final calendar years are included in overlap checks.',
            'familyLinks': 'Uses only relationship records marked verified=true (family relationship types 1–20) and the source dynasty_family_id field. It does not infer a relationship from a shared surname.',
            'limitations': 'The archived ODV records are incomplete and vary by election year and office. No barangay captain office rows were identifiable in the dump; 2019 winner-marked office coverage is incomplete, and 2019 is consequently absent from the rendered election-year list. Some winning rows may have been omitted or misclassified; relationship verification and term windows may be incomplete. No NO means no qualifying overlap was found in these records, not that no political family link exists. Check the cited ODV record before relying on the marker.',
        },
        'summary': {
            'officialRows': len(records),
            'noVoteRows': sum(r['doNotVote'] for r in records),
            'familyGroupsWithQualifyingTerms': len({r['familyKey'] for r in records if r['doNotVote']}),
            'byYear': {str(y): {'rows': sum(r['electionYear'] == y for r in records), 'noVoteRows': sum(r['electionYear'] == y and r['doNotVote'] for r in records)} for y in sorted({r['electionYear'] for r in records})},
            'byOffice': {g: {'rows': sum(r['officeGroup'] == g for r in records), 'noVoteRows': sum(r['officeGroup'] == g and r['doNotVote'] for r in records)} for g in sorted({r['officeGroup'] for r in records})},
        },
        'families': family_history,
        'records': [record for record in records if record['doNotVote']],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n')
    return result['summary']


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False, indent=2))
