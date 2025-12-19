
import json
import os
from datetime import datetime

INPUT_JSON = "repeated_targets.json"
OUTPUT_MD = "repeated_projects_report.md"
MAX_PROJECTS = 100

def format_currency(amount):
    try:
        return f"₱{float(amount):,.2f}"
    except:
        return str(amount)

def main():
    if not os.path.exists(INPUT_JSON):
        print(f"Waiting for {INPUT_JSON}...")
        return

    with open(INPUT_JSON, 'r', encoding='utf-8') as f:
        all_targets = json.load(f)
    
    # Apply Top 100 limit
    targets = all_targets[:MAX_PROJECTS]
    print(f"Generating report for top {len(targets)} projects (out of {len(all_targets)})...")
    
    with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
        # Header
        f.write(f"# Most Expensive Multi-Purpose Buildings Report (2026 Integration)\n\n")
        f.write(f"**Generated At:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Total Projects:** {len(targets)}\n\n")
        
        f.write("---\n\n")
        
        for p in targets:
            pid = p['id']
            name = p['name']
            hist_match = p.get('historical_match', 'N/A')
            links = p.get('transparency_links', [])
            
            f.write(f"## {name}\n\n")
            f.write(f"- **Project ID:** `{pid}`\n")
            f.write(f"- **Historical Match Trigger:** {hist_match}\n\n")
            
            if links:
                f.write(f"### Matched Transparency Contracts ({len(links)})\n\n")
                
                for link in links:
                    cid = link['id']
                    cname = link['name']
                    camount = format_currency(link['amount'])
                    url = f"https://transparency.dpwh.gov.ph/?project={cid}"
                    
                    f.write(f"#### Contract: [{cid}]({url})\n")
                    f.write(f"- **Contract Name:** {cname}\n")
                    f.write(f"- **Amount:** {camount}\n\n")
                    
                    # Screenshots Placeholders
                    # Note: Images must be in the artifacts directory to be embedded properly.
                    # We will name them: screenshots/{cid}_portal.png and screenshots/{cid}_gallery.png
                    
                    f.write(f"**Portal View:**\n")
                    f.write(f"![Portal View {cid}](screenshots/{cid}_portal.png)\n\n")
                    
                    f.write(f"**Gallery View:**\n")
                    f.write(f"![Gallery View {cid}](screenshots/{cid}_gallery.png)\n\n")
                    
                f.write("---\n\n")
            else:
                f.write("> No confirmed transparency links found.\n\n")
                f.write("---\n\n")

    print(f"✅ Report generated at {OUTPUT_MD}")

if __name__ == "__main__":
    main()
