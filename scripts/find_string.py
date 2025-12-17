import os

search_str = "naming conflict"
root_dir = "scripts/"

print(f"Searching for '{search_str}' in {root_dir}")

for root, dirs, files in os.walk(root_dir):
    for file in files:
        if file.endswith(".py"):
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if search_str in content:
                        print(f"FOUND in: {path}")
                        lines = content.splitlines()
                        for i, line in enumerate(lines):
                            if search_str in line:
                                print(f"  Line {i+1}: {line.strip()}")
            except Exception as e:
                print(f"Could not read {path}: {e}")
