import os
import sys
import re
import csv
import json
import time
import shutil
import asyncio
from playwright.async_api import async_playwright

# Ensure UTF-8 output on Windows console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Paths
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET_CSV = os.path.join(WORKSPACE_DIR, "(11_9) SIRI Certified companies Denmark - Trang tính1.csv")
BACKUP_CSV = os.path.join(WORKSPACE_DIR, "(11_9) SIRI Certified companies Denmark - Trang tính1.backup.csv")
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache_siri_cvr_enrich.json")
USER_DATA_DIR = os.path.join(WORKSPACE_DIR, "chrome_user_data")

def clean_phone_dk(phone_str):
    """
    Cleans Danish phone number:
    - Normalizes to international Danish format (+45)
    - Always prepends a single quote "'" for Google Sheets text formatting
    """
    if not phone_str:
        return ""
    s = str(phone_str).strip().lstrip("'").strip()
    digits = re.sub(r'[^0-9]', '', s)
    if not digits:
        return ""
    if digits.startswith("0045"):
        clean = f"+{digits[2:]}"
    elif digits.startswith("45") and len(digits) == 10:
        clean = f"+{digits}"
    elif len(digits) == 8:
        clean = f"+45{digits}"
    else:
        clean = f"+{digits}"
    return f"'{clean}"

def clean_cvr(raw_cvr):
    if not raw_cvr:
        return ""
    return re.sub(r'[^0-9]', '', str(raw_cvr))

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def save_csv(rows, fieldnames):
    try:
        with open(TARGET_CSV, mode="w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    except Exception as e:
        print(f"[-] Loi ghi CSV: {e}", flush=True)

async def enrich_cvr_data():
    print("=" * 70, flush=True)
    print(" [*] LAM GIAU DU LIEU CTY DAN MACH TREN VIRK.DK (DATACVR)", flush=True)
    print(" [*] Che do: TRINH DUYET HIEN THI TRUC QUAN (headless=False)", flush=True)
    print("=" * 70, flush=True)

    if not os.path.exists(TARGET_CSV):
        print(f"[ERROR] Khong tim thay file: {TARGET_CSV}", flush=True)
        return

    # Backup original CSV
    if not os.path.exists(BACKUP_CSV):
        print(f"[*] Tao ban sao luu: {BACKUP_CSV} ...", flush=True)
        shutil.copy2(TARGET_CSV, BACKUP_CSV)
        print("[+] Sao luu hoan tat.", flush=True)

    # Read rows
    with open(TARGET_CSV, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    print(f"[*] Tong so dong doc duoc: {len(rows)}", flush=True)

    cache = load_cache()
    print(f"[*] Da load {len(cache)} CVR tu cache.", flush=True)

    # Launch Playwright with real Chrome & persistent user data
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            channel="chrome",
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--start-maximized',
                '--no-sandbox'
            ],
            no_viewport=True
        )
        page = context.pages[0] if context.pages else await context.new_page()

        total = len(rows)
        cookie_accepted = False

        for idx, r in enumerate(rows, 1):
            raw_cvr = r.get("CVR no.", "").strip()
            cvr = clean_cvr(raw_cvr)
            company_name = r.get("Cong ty", "").strip()

            if not cvr:
                continue

            # Check cache
            if cvr in cache:
                cached = cache[cvr]
                if cached.get("email"):
                    r["Email"] = cached["email"]
                    r["Check gui"] = "OK"
                if cached.get("phone"):
                    r["SDT"] = cached["phone"]
                if cached.get("address"):
                    r["Dia chi"] = cached["address"]
                if cached.get("cvr_url"):
                    r["Lien He"] = cached["cvr_url"]
                continue

            cvr_url = f"https://datacvr.virk.dk/enhed/virksomhed/{cvr}"
            print(f"\n[{idx}/{total}] CVR: {cvr} | {company_name}", flush=True)

            try:
                await page.goto(cvr_url, timeout=30000, wait_until="networkidle")
                await page.wait_for_timeout(1000)

                # Check for Cloudflare challenge
                title = await page.title()
                if "Just a moment" in title or "Cloudflare" in title:
                    print("  [!] Phat hien Cloudflare, cho xac thuc tu dong...", flush=True)
                    for _ in range(12):
                        await page.wait_for_timeout(1000)
                        t = await page.title()
                        if "Just a moment" not in t and "Cloudflare" not in t:
                            break

                # Accept cookies once
                if not cookie_accepted:
                    try:
                        cookie_btn = page.locator('button:has-text("Accepter"), button:has-text("Tillad alle")')
                        if await cookie_btn.count() > 0 and await cookie_btn.first.is_visible():
                            await cookie_btn.first.click()
                            cookie_accepted = True
                            await page.wait_for_timeout(800)
                    except Exception:
                        pass

                # Click accordion button for extended details
                acc_btn = page.locator('#accordion-udvidede-virksomhedsoplysninger-button, [data-cy="accordion-udvidede-virksomhedsoplysninger"]')
                if await acc_btn.count() > 0:
                    try:
                        await acc_btn.first.scroll_into_view_if_needed()
                        await acc_btn.first.click()
                        await page.wait_for_timeout(1000)
                    except Exception:
                        pass

                # Extract text
                body_text = await page.locator('body').inner_text()
                lines = [l.strip() for l in body_text.splitlines() if l.strip()]

                email = ""
                phone = ""
                street = ""
                city = ""
                branche = ""

                for i, l in enumerate(lines):
                    l_lower = l.lower()
                    if l_lower == 'mail' and i + 1 < len(lines):
                        cand = lines[i+1].strip()
                        if '@' in cand and '.' in cand:
                            email = cand
                    elif l_lower == 'telefon' and i + 1 < len(lines):
                        cand = lines[i+1].strip()
                        if any(c.isdigit() for c in cand):
                            phone = cand
                    elif l_lower == 'adresse' and i + 1 < len(lines):
                        street = lines[i+1].strip()
                    elif l_lower == 'postnummer og by' and i + 1 < len(lines):
                        city = lines[i+1].strip()
                    elif l_lower == 'branchekode' and i + 1 < len(lines):
                        branche = lines[i+1].strip()

                addr_parts = [p for p in [street, city, 'Danmark'] if p]
                full_address = ', '.join(addr_parts)
                clean_phone_val = clean_phone_dk(phone)

                # Save to row
                if email:
                    r["Email"] = email
                    r["Check gui"] = "OK"
                if clean_phone_val:
                    r["SDT"] = clean_phone_val
                if full_address:
                    r["Dia chi"] = full_address
                r["Lien He"] = cvr_url

                # Log result
                print(f"  -> Email: {email if email else '(khong co)'}", flush=True)
                print(f"  -> SDT: {clean_phone_val if clean_phone_val else '(khong co)'}", flush=True)
                print(f"  -> Dia chi: {full_address}", flush=True)

                # Save to cache
                cache[cvr] = {
                    "email": email,
                    "phone": clean_phone_val,
                    "address": full_address,
                    "cvr_url": cvr_url,
                    "branche": branche
                }
                save_cache(cache)

            except Exception as e:
                print(f"  [-] Loi khi cao CVR {cvr}: {e}", flush=True)
                cache[cvr] = {
                    "email": "",
                    "phone": "",
                    "address": "",
                    "cvr_url": cvr_url,
                    "branche": ""
                }
                save_cache(cache)

            # Update CSV every 10 items
            if idx % 10 == 0 or idx == total:
                save_csv(rows, fieldnames)

        await context.close()

    # Final sort and save: rows with email on top
    print("\n[*] Hoan tat quet CVR. Dang sap xep dong co mail len tren dau...", flush=True)
    rows_with_email = [r for r in rows if r.get("Email", "").strip()]
    rows_without_email = [r for r in rows if not r.get("Email", "").strip()]
    sorted_rows = rows_with_email + rows_without_email

    for i, r in enumerate(sorted_rows, 1):
        r["No."] = str(i)

    save_csv(sorted_rows, fieldnames)

    print("=" * 70, flush=True)
    print(" [HOAN TAT LAM GIAU DU LIEU CVR DAN MACH]", flush=True)
    print(f"  - Tong so dong: {len(sorted_rows)}", flush=True)
    print(f"  - So cong ty co Email (Check gui = OK): {len(rows_with_email)}", flush=True)
    print(f"  - So cong ty khong co Email tren Virk: {len(rows_without_email)}", flush=True)
    print(f"  - File da luu: {TARGET_CSV}", flush=True)
    print("=" * 70, flush=True)

def main():
    asyncio.run(enrich_cvr_data())

if __name__ == "__main__":
    main()
