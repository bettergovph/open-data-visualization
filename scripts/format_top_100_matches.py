
import json

INPUT_JSON = "top_100_mpb_targets.json"
OUTPUT_MD = "top_100_mpb_detailed_list.md"

def main():
    try:
        with open(INPUT_JSON, 'r', encoding='utf-8') as f:
            targets = json.load(f)
    except FileNotFoundError:
        print(f"Error: {INPUT_JSON} not found.")
        return

    print(f"Reading from {INPUT_JSON}, found {len(targets)} matched projects.")

    with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
        f.write("# Top 100 Repeated MPB - Transparency Matches\n\n")
        f.write(f"**Total Matched Projects:** {len(targets)}\n\n")
        
        # Sort by amount descending (it should already be, but ensuring)
        targets.sort(key=lambda x: x['amount'], reverse=True)

        for idx, project in enumerate(targets, 1):
            pid = project.get('project_id')
            pname = project.get('project_name')
            pamount = project.get('amount', 0)
            matches = project.get('matches', [])

            amt_fmt = f"P{pamount:,.2f}"
            
            f.write(f"## {idx}. {pname}\n")
            f.write(f"- **Budget ID:** `{pid}`\n")
            f.write(f"- **Amount:** {amt_fmt}\n")
            f.write(f"- **Transparency Matches ({len(matches)}):**\n")
            
            if matches:
                f.write("| Contract ID | Contract Name | Amount |\n")
                f.write("|:------------|:--------------|:-------|\n")
                for m in matches:
                    ced = m.get('contract_id')
                    cname = m.get('name')
                    camount = m.get('amount', 0)
                    camt_fmt = f"P{camount:,.2f}"
                    # Create link to portal
                    link = f"[{ced}](https://transparency.dpwh.gov.ph/?project={ced})"
                    f.write(f"| {link} | {cname} | {camt_fmt} |\n")
                
                f.write("\n")
                import os
                import glob
                
                # Artifacts path: C:\Users\joebe\.gemini\antigravity\brain\d401e83b-02e8-4dfe-bd2e-2bee2e0be88b
                # WSL Path
                ARTIFACTS_DIR = "/mnt/c/Users/joebe/.gemini/antigravity/brain/d401e83b-02e8-4dfe-bd2e-2bee2e0be88b"
                
                has_screenshots = False
                for m in matches:
                    ced = m.get('contract_id')
                    ced_lower = ced.lower()
                    
                    # Pattern match for files: ced_lower + "_portal" + "*" + ".png"
                    # We need to find the actual filename in the artifacts dir
                    
                    portal_img_path = None
                    gallery_img_path = None
                    
                    # Find Portal Image
                    # pattern: 20o00045_portal*.png
                    p_pattern = os.path.join(ARTIFACTS_DIR, f"{ced_lower}_portal*.png")
                    p_matches = glob.glob(p_pattern)
                    # Sort by modification time to get the latest? Or just take the first one.
                    if p_matches:
                        p_matches.sort(key=os.path.getmtime, reverse=True)
                        portal_img_path = p_matches[0]
                        
                    # Find Gallery Image
                    g_pattern = os.path.join(ARTIFACTS_DIR, f"{ced_lower}_gallery*.png")
                    g_matches = glob.glob(g_pattern)
                    if g_matches:
                        g_matches.sort(key=os.path.getmtime, reverse=True)
                        gallery_img_path = g_matches[0]
                    
                    if portal_img_path or gallery_img_path:
                        if not has_screenshots:
                            f.write("**Screenshots:**\n\n")
                            has_screenshots = True
                        
                        f.write(f"**{ced}**:\n")
                        if portal_img_path:
                            # Pandoc needs the path. If it's absolute WSL path, it should work.
                            f.write(f"![Portal View]({portal_img_path}){{ width=45% }} ")
                        if gallery_img_path:
                            f.write(f"![Gallery View]({gallery_img_path}){{ width=45% }}\n")
                        f.write("\n")
            else:
                f.write("  - No matches found.\n")
            
            f.write("\n---\n\n")

    print(f"Generated detailed list: {OUTPUT_MD}")

if __name__ == "__main__":
    main()
