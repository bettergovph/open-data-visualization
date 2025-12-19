import json
import os

TARGETS_FILE = "/home/joebert/open-data-visualization/screenshot_targets.json"
SCREENSHOTS_DIR = "/home/joebert/open-data-visualization/screenshots"
OUTPUT_FILE = "/home/joebert/open-data-visualization/pending_screenshots.json"

def main():
    if not os.path.exists(TARGETS_FILE):
        print(f"Error: {TARGETS_FILE} not found.")
        return

    if not os.path.exists(SCREENSHOTS_DIR):
        print(f"Creating {SCREENSHOTS_DIR}...")
        os.makedirs(SCREENSHOTS_DIR)

    with open(TARGETS_FILE, 'r') as f:
        targets = json.load(f)

    pending = []
    
    print(f"Total targets: {len(targets)}")
    
    existing_files = set(os.listdir(SCREENSHOTS_DIR))
    
    for t in targets:
        cid = t['contract_id']
        # Check for both portal and gallery
        portal_exists = f"{cid}_portal.png" in existing_files
        gallery_exists = f"{cid}_gallery.png" in existing_files
        
        if not (portal_exists and gallery_exists):
            pending.append(t)
            
    print(f"Pending targets: {len(pending)}")
    
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(pending, f, indent=2)
        
    print(f"Saved pending list to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
