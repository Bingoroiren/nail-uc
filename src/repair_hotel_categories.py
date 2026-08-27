import asyncio
import csv
import os
import random
import sys
import re
from playwright.async_api import async_playwright

# Force UTF-8 encoding for stdout
if sys.platform.startswith('win'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

csv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hotel_portugal.csv")
backup_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hotel_portugal_before_repair.csv")

# Robust category selector
CATEGORY_SELECTOR = 'span.mgr77e, button.DkEaCc, button.DkEaL, div.F7nice ~ span, div.F7nice ~ button'

async def bypass_consent_screen(page):
    try:
        consent_buttons = page.locator('button:has-text("Accept all"), button:has-text("Agree"), button:has-text("I agree"), button:has-text("Accept"), button:has-text("Aceitar tudo"), button:has-text("Concordo")')
        if await consent_buttons.count() > 0:
            print("[*] Google Consent Screen detected. Bypassing...")
            await consent_buttons.first.click()
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(1000)
    except Exception:
        pass

async def main():
    print("=============================================================")
    print("      PORTUGAL HOTEL CATEGORY REPAIR SCRIPT                 ")
    print("=============================================================")
    
    if not os.path.exists(csv_path):
        print(f"[ERROR] File {csv_path} not found.")
        return

    # Backup original CSV
    if not os.path.exists(backup_path):
        print(f"[*] Creating backup of original CSV to: {backup_path}")
        import shutil
        shutil.copy2(csv_path, backup_path)

    # Read all rows
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    # Identify rows to repair
    to_repair = []
    for idx, r in enumerate(rows):
        if not r.get('Category', '').strip() and r.get('URL', '').strip():
            to_repair.append((idx, r))

    print(f"[*] Found {len(rows)} total rows in CSV.")
    print(f"[*] Rows needing Category repair: {len(to_repair)}")

    if not to_repair:
        print("[SUCCESS] No rows need category repair!")
        return

    print("[*] Launching browser to repair categories...")
    
    async with async_playwright() as p:
        browser = None
        for channel in ["chrome", "msedge", None]:
            try:
                chan_str = f"channel '{channel}'" if channel else "default Chromium"
                print(f"[*] Attempting to launch browser with {chan_str}...")
                browser = await p.chromium.launch(
                    headless=False,  # Headful to see progress and bypass CAPTCHA easily
                    channel=channel if channel else None,
                    args=["--disable-blink-features=AutomationControlled", "--lang=pt-PT,pt"]
                )
                print(f"[+] Successfully launched browser using {chan_str}!")
                break
            except Exception as e:
                print(f"[-] Failed to launch with channel '{channel}': {e}")
                
        if not browser:
            print("[!] Could not launch any browser. Exiting.")
            return
            
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            locale="pt-PT"
        )
        page = await context.new_page()
        
        # Load Google Maps once to bypass consent
        await page.goto("https://www.google.com/maps?hl=pt", timeout=30000)
        await page.wait_for_timeout(2000)
        await bypass_consent_screen(page)
        
        save_counter = 0
        success_count = 0
        
        try:
            for count, (idx, r) in enumerate(to_repair, 1):
                name = r.get('Name')
                url = r.get('URL')
                print(f"\n[{count}/{len(to_repair)}] Repairing: '{name}'")
                
                try:
                    await page.goto(url, timeout=30000, wait_until="commit")
                    await page.wait_for_timeout(1000)
                    await bypass_consent_screen(page)
                    
                    # Extract Category with a wait loop
                    category = ""
                    category_loc = page.locator(CATEGORY_SELECTOR)
                    for _ in range(15):
                        count = await category_loc.count()
                        if count > 0:
                            for i in range(count):
                                txt = await category_loc.nth(i).inner_text()
                                txt_clean = txt.strip().replace("·", "").strip()
                                if txt_clean and txt_clean not in ["", "·"]:
                                    category = txt_clean
                                    break
                            if category:
                                break
                        await page.wait_for_timeout(200)
                        
                    if category:
                        rows[idx]['Category'] = category
                        success_count += 1
                        save_counter += 1
                        print(f"    [+] Category found: {category}")
                    else:
                        print("    [-] Category not found.")
                        
                    # Save progress every 10 updates
                    if save_counter >= 10:
                        print("[*] Saving intermediate progress to CSV...")
                        with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f_out:
                            writer = csv.DictWriter(f_out, fieldnames=fieldnames)
                            writer.writeheader()
                            writer.writerows(rows)
                        save_counter = 0
                        
                except Exception as e:
                    print(f"    [!] Error loading details: {e}")
                    
                # Delay to look human
                await page.wait_for_timeout(random.uniform(1000, 2000))
                
        except KeyboardInterrupt:
            print("\n[-] Interrupted by user. Saving current progress...")
        finally:
            # Write final output
            print("[*] Writing final data to CSV...")
            with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f_out:
                writer = csv.DictWriter(f_out, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            
            print(f"\n=============================================================")
            print(f"  REPAIR COMPLETE: Successfully repaired {success_count} rows.")
            print(f"  Data saved to: {csv_path}")
            print(f"=============================================================")
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
