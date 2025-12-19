import json
import os
import time
import asyncio
from playwright.async_api import async_playwright

INPUT_JSON = "repeated_targets.json"
SCREENSHOTS_DIR = "screenshots"
MAX_PROJECTS = 100

async def scroll_to_bottom(page):
    """Scroll down to ensure all images are loaded."""
    # User requested specific scroll logic: Scroll down to see all images
    # We'll use a series of PgDn and then End to mimic the AHK logic
    for _ in range(5):
        await page.keyboard.press("PageDown")
        await asyncio.sleep(0.5)
    await page.keyboard.press("End")
    await asyncio.sleep(1.0) # Wait for lazy loading

async def capture_screenshots():
    if not os.path.exists(INPUT_JSON):
        print(f"❌ {INPUT_JSON} not found.")
        return

    with open(INPUT_JSON, 'r', encoding='utf-8') as f:
        all_targets = json.load(f)

    targets = all_targets[:MAX_PROJECTS]
    print(f"📸 Starting screenshot capture for {len(targets)} projects...")

    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

    async with async_playwright() as p:
        # Launch browser (headless by default in automation, but can be set to False to watch)
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        page = await context.new_page()

        total_processed = 0
        
        for project in targets:
            links = project.get('transparency_links', [])
            for link in links:
                cid = link['id']
                portal_path = f"{SCREENSHOTS_DIR}/{cid}_portal.png"
                gallery_path = f"{SCREENSHOTS_DIR}/{cid}_gallery.png"

                if os.path.exists(portal_path) and os.path.exists(gallery_path):
                    print(f"⏩ Skipping {cid} (already exists)")
                    continue

                url = f"https://transparency.dpwh.gov.ph/?project={cid}"
                print(f"Processing {cid} -> {url}")

                try:
                    await page.goto(url, timeout=30000)
                    await page.wait_for_load_state('networkidle')
                    # Extra sleep to ensure rendering
                    await asyncio.sleep(2)

                    # 1. Portal Screenshot (Top of page)
                    if not os.path.exists(portal_path):
                        await page.keyboard.press("Home")
                        await asyncio.sleep(0.5)
                        await page.screenshot(path=portal_path)
                        print(f"   ✅ Portal saved")

                    # 2. Gallery Screenshot
                    if not os.path.exists(gallery_path):
                        # Switch to Gallery Tab
                        # The tabs are usually just anchor links. We can click by text or selector.
                        # Assuming there is a "Gallery" tab/link.
                        # Using exact logic: click the element with text "Gallery" or similar
                        gallery_tab = page.get_by_text("Gallery", exact=True)
                        if await gallery_tab.is_visible():
                            await gallery_tab.click()
                        else:
                            # Fallback: try finding it by class or href if text fails
                            # Or just click coordinates like the AHK script? No, Playwright is better.
                            # Try 'a[href="#gallery"]' or similar if known.
                            # For now, let's look for "Gallery" or "Photos"
                            await page.get_by_role("link", name="Gallery").click()
                        
                        await asyncio.sleep(2) # Wait for tab switch

                        # Scroll down logic
                        await scroll_to_bottom(page)
                        
                        await page.screenshot(path=gallery_path)
                        print(f"   ✅ Gallery saved")
                        
                    total_processed += 1
                    
                except Exception as e:
                    print(f"⚠️ Failed to capture {cid}: {e}")

        await browser.close()
        print("Done.")

if __name__ == "__main__":
    asyncio.run(capture_screenshots())
