import json


def update_consolidated_config():
    try:
        with open('unique_contractors.json', 'r', encoding='utf-8') as f:
            unique_contractors = json.load(f)
    except FileNotFoundError:
        print('❌ unique_contractors.json not found. Run scripts/extract_all_contractors.py first.')
        return

    try:
        with open('static/data/congressmen_consolidated.json', 'r', encoding='utf-8') as f:
            congressmen = json.load(f)
    except FileNotFoundError:
        print('❌ congressmen_consolidated.json not found.')
        return

    print(f'Loaded {len(unique_contractors)} unique contractors and {len(congressmen)} congressmen.')

    updated_count = 0

    for cm in congressmen:
        keywords = set()

        linked = cm.get('linked_contractors', [])
        for linked_name in linked:
            if linked_name and len(linked_name) > 3:
                keywords.add(linked_name)

        family = cm.get('family_connections', {})
        family_contractors = family.get('contractors', [])
        for family_name in family_contractors:
            if family_name and len(family_name) > 3:
                keywords.add(family_name)

        if cm.get('id') == 17:
            keywords.update({'SUNWEST', 'FS CO', 'HI-TONE'})

        if not keywords:
            cm.setdefault('contractors', [])
            continue

        exact_matches = set()
        for keyword in keywords:
            keyword_upper = keyword.upper().strip()
            for db_contractor in unique_contractors:
                if keyword_upper in db_contractor.upper():
                    exact_matches.add(db_contractor)

        existing_contractors = set(cm.get('contractors', []))
        existing_contractors.update(exact_matches)
        cm['contractors'] = sorted(existing_contractors)

        if exact_matches:
            updated_count += 1

    with open('static/data/congressmen_consolidated.json', 'w', encoding='utf-8') as f:
        json.dump(congressmen, f, indent=2, ensure_ascii=False)

    print(f'✅ Updated {updated_count} congressmen configurations.')


if __name__ == '__main__':
    update_consolidated_config()
