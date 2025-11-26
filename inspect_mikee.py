import json

try:
    with open('static/data/dynasty-projects-config.json', 'r') as f:
        config = json.load(f)

    congressmen = config.get('target_congressmen', [])
    print(f"Loaded {len(congressmen)} congressmen")

    found = False
    for cm in congressmen:
        name = cm.get('display_name', cm.get('name', 'Unknown'))
        if 'Romero' in name or 'Mikee' in name:
            print("\nFOUND MIKEE ROMERO:")
            print(json.dumps(cm, indent=2))
            found = True
    
    if not found:
        print("Mikee Romero not found in config")

except Exception as e:
    print(f"Error: {e}")







