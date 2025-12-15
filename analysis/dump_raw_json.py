def dump_raw():
    path = "static/data/districts.json"
    with open(path, "r") as f:
        lines = f.readlines()
        
    for i, line in enumerate(lines):
        if "Caloocan" in line or "Marikina" in line:
            print(f"Line {i}: {line.strip()}")
            # print next 10 lines
            for j in range(1, 15):
                if i + j < len(lines):
                    print(f"  {lines[i+j].strip()}")
            print("-" * 20)

if __name__ == "__main__":
    dump_raw()
