
import json
import shutil
from pathlib import Path

# Paths
ROOT = Path(__file__).parent.parent
DISTRICTS_PATH = ROOT / "static/data/districts.json"
CONFIG_PATH = ROOT / "static/data/dynasty-projects-config.json"

def patch_districts():
    print(f"Patching {DISTRICTS_PATH}...")
    with open(DISTRICTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Backup original Maguindanao reps
    mag = data["districts"].get("Maguindanao", {})
    reps = mag.get("representatives", {})
    rep1 = reps.get("1st District", "")
    rep2 = reps.get("2nd District", "")

    # Define New Provinces
    del_norte = {
        "all_districts": ["Lone District"],
        "municipalities": {
            "Barira": "Lone District", "Buldon": "Lone District", "Datu Blah T. Sinsuat": "Lone District",
            "Datu Odin Sinsuat": "Lone District", "Kabuntalan": "Lone District", "Matanog": "Lone District",
            "Northern Kabuntalan": "Lone District", "Parang": "Lone District", "North Upi": "Lone District",
            "Sultan Kudarat": "Lone District", "Sultan Mastura": "Lone District", "Talitay": "Lone District",
            "Upi": "Lone District", "Cotabato City": "Lone District"
        },
        "representatives": {
            "Lone District": rep1 or "Sittie Shahara Mastura (2022-present)"
        }
    }

    del_sur = {
        "all_districts": ["Lone District"],
        "municipalities": {
            "Ampatuan": "Lone District", "Buluan": "Lone District", "Datu Abdullah Sangki": "Lone District",
            "Datu Anggal Midtimbang": "Lone District", "Datu Hoffer Ampatuan": "Lone District", "Datu Montawal": "Lone District",
            "Datu Paglas": "Lone District", "Datu Piang": "Lone District", "Datu Salibo": "Lone District",
            "Datu Saudi Ampatuan": "Lone District", "Datu Unsay": "Lone District", "General Salipada K. Pendatun": "Lone District",
            "Guindulungan": "Lone District", "Mamasapano": "Lone District", "Mangudadatu": "Lone District",
            "Pagalungan": "Lone District", "Paglat": "Lone District", "Pandag": "Lone District", "Rajah Buayan": "Lone District",
            "Shariff Aguak": "Lone District", "Shariff Saydona Mustapha": "Lone District", "South Upi": "Lone District",
            "Sultan sa Barongis": "Lone District", "Talayan": "Lone District"
        },
        "representatives": {
            "Lone District": rep2 or "Mohamad Paglas (2022-present)"
        }
    }

    # Apply Updates
    data["districts"]["Maguindanao del Norte"] = del_norte
    data["districts"]["Maguindanao del Sur"] = del_sur
    
    # Optional: Keep "Maguindanao" legacy to prevent crashes if something looks it up, 
    # but maybe mark it or leave as is. For now, we prepend/overwrite.

    with open(DISTRICTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("Districts patched.")

def patch_config():
    print(f"Patching {CONFIG_PATH}...")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    changed = 0
    for entry in data.get("target_congressmen", []):
        name = entry.get("display_name", "")
        # Patch Sittie Shahara Mastura
        if "Mastura" in name and entry.get("province") == "Maguindanao":
            entry["province"] = "Maguindanao del Norte"
            entry["district_number"] = "Lone District"
            changed += 1
            print(f"Updated {name}")

        # Patch Mohamad Paglas
        if "Paglas" in name and entry.get("province") == "Maguindanao":
            entry["province"] = "Maguindanao del Sur"
            entry["district_number"] = "Lone District"
            changed += 1
            print(f"Updated {name}")

    if changed > 0:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Config patched ({changed} entries).")
    else:
        print("No config entries needed patching.")

if __name__ == "__main__":
    patch_districts()
    patch_config()
