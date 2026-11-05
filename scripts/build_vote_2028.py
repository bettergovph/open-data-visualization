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


def compact_norm(value):
    """Normalize punctuation and spacing for within-family duplicate identities."""
    return norm(value).replace(' ', '')


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
                                         ('Publicly documented family link' if record['personKey'] in documented_member_keys
                                          else 'ODV linked family group'))
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
            'personKey': record['personKey'], 'name': record['name'], 'offices': []
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

    records.sort(key=lambda r: (r['electionYear'], r['officeGroup'], norm(r['province']), norm(r['municipality']), norm(r['name'])))
    result = {
        'generatedAt': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
        'source': 'ODV database/dynasty_dump.sql.gz · political_dynasties and verified relationships tables, supplemented with cited current role records and family links for Duterte, Cayetano, Tulfo, and Villar officials',
        'sourceSha256': source_hash,
        'years': sorted({r['electionYear'] for r in records}),
        'scope': 'Deduplicated elected office records in archived ODV data for national and local offices from 2004–2025, supplemented with published current roles and documented family links for Duterte, Cayetano, Tulfo, and Villar officials where ODV is missing or mislabels records. This does not make the national ODV roster complete and is not a 2028 candidate list.',
        'recordsScope': 'The records array contains NO-marked officeholders only. The families object retains linked historical family-member office records for context.',
        'method': {
            'noVoteRule': 'NO means at least two distinct linked family members held office in the same modeled calendar year. A family with exactly one local and one national officeholder in that year is excluded. Links come from ODV-verified relationships, shared ODV dynasty_family_id, or specifically cited public family sources; shared surnames alone do not count.',
            'officeLevels': 'President/vice president, senators, and House/party-list representatives are classified as national. Governors, vice governors, mayors, vice mayors, provincial board members, and councilors are classified as local.',
            'terms': 'President/vice president and senators are modeled as six-year terms; other included elected positions as three-year terms, based on the election year in ODV. Partial final calendar years are included in overlap checks.',
            'familyLinks': 'Uses ODV relationship records marked verified=true (family relationship types 1–20), source dynasty_family_id values, and separately cited public family links for Duterte, Cayetano, Tulfo, and Villar officials. Duplicate person IDs are consolidated only with an exact full name inside a linked family group or on the same fully identified local seat. Repeated copies of one national office or House seat in the same election year are collapsed; distinct House districts remain separate. Conflicting copied location labels are omitted. Surname-only matching is not used.',
            'limitations': 'The archived ODV records are incomplete and vary by election year and office. Online additions repair selected current roles and documented family links, not the full national or local roster; the wider 2019 winner-marked roster remains incomplete, and 2022/2025 local-office coverage is sparse. Some source rows or relationships may still be omitted or misclassified. NO years use inclusive modeled calendar-year windows; check the linked evidence and official records before relying on a marker. No NO means this incomplete screen found no qualifying overlap, not that no political family link exists.',
        },
        'summary': {
            'officialRows': len(records),
            'noVoteRows': sum(r['doNotVote'] for r in records),
            'familyGroupsWithQualifyingTerms': len({r['familyKey'] for r in records if r['doNotVote']}),
            'duplicatePersonIdsConsolidatedWithinFamilies': identity_dedup_count,
            'duplicateOfficeRowsRemoved': duplicate_office_rows_removed,
            'senateSnapshotRowsCorrectedTo2022Term': senate_snapshot_rows_corrected,
            'senateNameVariantsNormalized': senate_name_variants_normalized,
            'misclassifiedSenateRowsRemoved': misclassified_senate_rows_removed,
            'byYear': {str(y): {'rows': sum(r['electionYear'] == y for r in records), 'noVoteRows': sum(r['electionYear'] == y and r['doNotVote'] for r in records)} for y in sorted({r['electionYear'] for r in records})},
            'byOffice': {g: {'rows': sum(r['officeGroup'] == g for r in records), 'noVoteRows': sum(r['officeGroup'] == g and r['doNotVote'] for r in records)} for g in sorted({r['officeGroup'] for r in records})},
        },
        'documentedFamilyLinks': documented_families,
        'documentedRoleOutcomes': [{
            'name': online_people['rodrigo'][0], 'electionYear': 2025,
            'outcome': 'Elected mayor but did not take the oath and did not assume office; not counted as an officeholder for the NO rule.',
            'sourceUrl': 'https://www.gmanetwork.com/news/topstories/regions/973931/baste-duterte-takes-oath-as-davao-city-mayor/story/'
        }],
        'families': family_history,
        'records': [record for record in records if record['doNotVote']],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n')
    return result['summary']


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False, indent=2))
