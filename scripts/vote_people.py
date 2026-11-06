"""Reviewed office supplements and one-name-per-row presentation for Vote 2028."""
import hashlib
import json
import re
import unicodedata
from collections import defaultdict


def name_key(value):
    text = unicodedata.normalize('NFKD', str(value or '')).upper()
    return re.sub(r'[^A-Z0-9]', '', ''.join(c for c in text if not unicodedata.combining(c)))


def power_rank(office):
    """Rank elected offices; distinguish the President from the Vice President."""
    position = re.sub(r'[^A-Z0-9]+', ' ', str(office.get('position', '')).upper()).strip()
    group = office.get('officeGroup', '')
    if group == 'President / Vice President':
        return 1 if position.startswith('VICE PRESIDENT') else 0
    return {'Senator': 2, 'Congress / party-list representative': 3, 'Governor': 4,
            'Vice Governor': 5, 'Mayor': 6, 'Vice Mayor': 7, 'Provincial board member': 8,
            'Councilor': 9, 'Barangay captain': 10}.get(group, 11)


def apply_reviewed_sources(records, house_records, family, documented_families, path):
    data = json.loads(path.read_text())
    sources = data['sources']
    added = replaced = enriched = 0
    for person in data['people']:
        aliases = {name_key(x) for x in [person['name'], *person.get('aliases', [])]}
        provinces = {name_key(x) for x in [person['province'], *person.get('provinceAliases', [])]}
        unlocated_house_aliases = {name_key(x) for x in person.get('unlocatedHouseAliases', [])}
        key = 'cited-person:' + person['id']
        matched = []
        for record in records:
            name = name_key(record['name'])
            rule_match = any(name == name_key(rule['name']) and record['officeGroup'] == rule['officeGroup']
                             for rule in person.get('legacyIdentityRules', []))
            if name not in aliases and not rule_match:
                continue
            # Place restrictions apply even to an exact full-name match. An
            # elected national office may have no local province in the export.
            if record['officeGroup'] not in {'President / Vice President', 'Senator'}:
                approved_unlocated_house = (record['officeGroup'] == 'Congress / party-list representative'
                                             and not record.get('province') and name in unlocated_house_aliases)
                if name_key(record.get('province')) not in provinces and not approved_unlocated_house:
                    continue
            matched.append(record)
        remove_ids = set()
        retained_terms = set()
        for record in matched:
            family.union(key, record['personKey'])
            record.update(personKey=key, name=person['name'], familyKey=person['familyKey'],
                          familyBasis='Cited public family relationship',
                          reviewedAt=data['reviewedAt'])
            record['aliasEvidence'] = [{'name': alias, 'sourceUrl': sources[person['identitySource']]['url'],
                                       'source': 'Reviewed full-name variant / public name'}
                                      for alias in person.get('aliases', [])]
            # Keep current House seat objects because the builder also uses
            # these for its complete-roster coverage summary.
            if str(record.get('sourceId', '')).startswith('20th-house-'):
                matching = [r for r in person['roles'] if r['electionYear'] == record['electionYear']
                            and r['officeGroup'] == record['officeGroup']]
                if matching:
                    urls = [sources[s]['url'] for role in matching for s in role['sourceIds']]
                    record['roleSourceUrls'] = sorted(set([record.get('roleSourceUrl', ''), *urls]) - {''})
                    retained_terms.add((record['officeGroup'], record['electionYear']))
                enriched += 1
            elif record['electionYear'] >= person.get('replaceFromYear', 2004):
                # The reviewed role history replaces conflicting archive labels
                # for this named official, rather than counting both as offices.
                remove_ids.add(id(record))
        replaced += len(remove_ids)
        records = [record for record in records if id(record) not in remove_ids]
        for role in person['roles']:
            if (role['officeGroup'], role['electionYear']) in retained_terms:
                continue
            urls = [sources[source]['url'] for source in role['sourceIds']]
            start = role.get('officeStartYear', role['electionYear'])
            records.append({
                **role, 'personKey': key, 'familyKey': person['familyKey'], 'name': person['name'],
                'province': person['province'], 'region': '', 'party': role.get('party', ''),
                'officeStartYear': start, 'termYears': role['termThroughYear'] - start,
                'sourceId': f"reviewed-{person['id']}-{role['electionYear']}-{name_key(role['position'])}",
                'familyBasis': 'Cited public family relationship', 'roleSourceUrl': urls[0],
                'roleSourceUrls': urls, 'reviewedAt': data['reviewedAt'],
                'roleNote': 'Office and modeled term checked against cited public records.',
                'aliasEvidence': [{'name': alias, 'sourceUrl': sources[person['identitySource']]['url'],
                                   'source': 'Reviewed full-name variant / public name'}
                                  for alias in person.get('aliases', [])],
            })
            added += 1
    for item in data['families']:
        existing = next((entry for entry in documented_families if entry['key'] == item['key']), None)
        if existing is None:
            documented_families.append(item)
            continue
        for field in ('members', 'sources', 'relationships'):
            target = existing.setdefault(field, [])
            target.extend(value for value in item.get(field, []) if value not in target)
        if item['basis'] not in existing['basis']:
            existing['basis'] += ' ' + item['basis']
    return records, {'reviewedPeople': len(data['people']), 'reviewedOfficeTerms': sum(len(p['roles']) for p in data['people']),
                     'reviewedFamilyGroups': len(data['families']),
                     'explicitRelationshipEdges': sum(len(item.get('relationships', [])) for item in data['families']),
                     'addedOfficeRows': added, 'replacedArchiveRows': replaced,
                     'enrichedHouseSeats': enriched, 'reviewedAt': data['reviewedAt']}, list(sources.values())


def unique_people(records):
    """Group exact full names for display, retaining separate source identities."""
    eligible_keys = {record['personKey'] for record in records if record.get('doNotVote')}
    grouped = defaultdict(list)
    for record in records:
        if record['personKey'] in eligible_keys:
            grouped[name_key(record['name'])].append(record)
    people = []
    for key, matches in grouped.items():
        matched_offices = {}
        for record in matches:
            signature = (name_key(record['position']), record['officeGroup'], record['electionYear'],
                         record.get('officeStartYear', record['electionYear']), record['termThroughYear'],
                         name_key(record.get('province')), name_key(record.get('municipality')),
                         name_key(record.get('district')))
            office = matched_offices.setdefault(signature, dict(record, sourcePersonKeys=[], sourceFamilyKeys=[]))
            for field, value in [('sourcePersonKeys', record['personKey']), ('sourceFamilyKeys', record.get('familyKey'))]:
                if value and value not in office[field]:
                    office[field].append(value)
            urls = set(office.get('roleSourceUrls', [])) | set(record.get('roleSourceUrls', []))
            urls.update(filter(None, [office.get('roleSourceUrl'), record.get('roleSourceUrl')]))
            office['roleSourceUrls'] = sorted(urls)
            office['doNotVote'] = bool(office.get('doNotVote') or record.get('doNotVote'))
            office['noVoteYears'] = sorted(set(office.get('noVoteYears', [])) | set(record.get('noVoteYears', [])))
        offices = sorted(matched_offices.values(), key=lambda r: (
            -r.get('officeStartYear', r['electionYear']), -r['electionYear'], power_rank(r),
            -r['termThroughYear'], r['position'], r.get('province', '')))
        aliases, alias_evidence = [], []
        for record in matches:
            for alias in record.get('aliases', []):
                if name_key(alias) != key and alias not in aliases:
                    aliases.append(alias)
            for evidence in record.get('aliasEvidence', []):
                if evidence not in alias_evidence:
                    alias_evidence.append(evidence)
        past = {}
        for office in offices[1:]:
            identity = tuple(name_key(office.get(k)) for k in ('position', 'province', 'municipality', 'district'))
            item = past.setdefault(identity, {k: office.get(k, '') for k in ('position', 'officeGroup', 'province', 'municipality', 'district')})
            item.setdefault('terms', []).append({'electionYear': office['electionYear'],
                'officeStartYear': office.get('officeStartYear', office['electionYear']),
                'termThroughYear': office['termThroughYear']})
            item['sourceUrls'] = sorted(set(item.get('sourceUrls', [])) | set(office.get('roleSourceUrls', [])))
        people.append({
            'id': 'name:' + hashlib.sha1(key.encode()).hexdigest()[:16], 'name': offices[0]['name'],
            'personKeys': sorted({r['personKey'] for r in matches}),
            'familyKeys': sorted({r['familyKey'] for r in matches if r.get('familyKey')}),
            'aliases': aliases, 'aliasEvidence': alias_evidence, 'offices': offices,
            'latestOffice': offices[0], 'pastPositions': list(past.values()),
            'powerRank': min(power_rank(office) for office in offices),
            'electionYears': sorted({r['electionYear'] for r in matches}),
            'officeGroups': sorted({r['officeGroup'] for r in matches}),
            'noVoteYears': sorted({year for r in matches for year in r.get('noVoteYears', [])}),
            'familyBasis': '; '.join(sorted({r.get('familyBasis') for r in matches if r.get('familyBasis')})),
        })
    return sorted(people, key=lambda p: (p['powerRank'], name_key(p['name'])))
