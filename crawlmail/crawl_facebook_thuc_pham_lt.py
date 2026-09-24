import asyncio
import csv
import json
import os
import re
import sys
import urllib.parse
from playwright.async_api import async_playwright

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_CSV = os.path.join(BASE_DIR, "Thuc pham litva - Raw.csv")
PROGRESS_FILE = os.path.join(BASE_DIR, "data", "progress", "fb_emails_lt.json")

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b')
INVALID_EXTS = ('.png', '.jpg', '.jpeg', '.svg', '.webp', '.pdf', '.css', '.js', '.ico')

JUNK_KEYWORDS = {'sentry', 'facebook.com', 'fb.com', 'example.com', 'wix', 'wixpress', 'noreply', 'no-reply'}

def is_valid_email(em):
    em_lower = em.strip().lower()
    if any(em_lower.endswith(ext) for ext in INVALID_EXTS):
        return False
    if any(kw in em_lower for kw in JUNK_KEYWORDS):
        return False
    parts = em_lower.split('@')
    if len(parts) != 2:
        return False
    domain = parts[1]
    if '.' not in domain or len(domain.split('.')[-1]) < 2:
        return False
    return True

def extract_emails_from_text(text):
    if not text:
        return []
    matches = EMAIL_REGEX.findall(text)
    return [m.lower().strip() for m in matches if is_valid_email(m)]

async def scrape_fanpage(page, fb_url):
    fb_url = fb_url.strip()
    if not fb_url.startswith(('http://', 'https://')):
        fb_url = 'https://' + fb_url
        
    emails = []
    # Visit main page
    try:
        print(f"[*] Navigating FB: {fb_url}", flush=True)
        await page.goto(fb_url, timeout=12000, wait_until="commit")
        await asyncio.sleep(3.0)
        
        # Check mailto
        try:
            links = await page.locator('a[href^="mailto:"]').all()
            for l in links:
                h = await l.get_attribute('href')
                if h:
                    em = h.replace('mailto:', '').split('?')[0].strip()
                    if is_valid_email(em):
                        emails.append(em.lower())
        except Exception:
            pass
            
        content = await page.content()
        emails.extend(extract_emails_from_text(content))
    except Exception as e:
        print(f"[-] Main page load error ({fb_url}): {e}", flush=True)

    # If no email, visit /about
    if not emails:
        about_url = fb_url.rstrip('/') + '/about'
        try:
            print(f"[*] Navigating FB About: {about_url}", flush=True)
            await page.goto(about_url, timeout=12000, wait_until="commit")
            await asyncio.sleep(2.5)
            
            try:
                links = await page.locator('a[href^="mailto:"]').all()
                for l in links:
                    h = await l.get_attribute('href')
                    if h:
                        em = h.replace('mailto:', '').split('?')[0].strip()
                        if is_valid_email(em):
                            emails.append(em.lower())
            except Exception:
                pass
                
            content_about = await page.content()
            emails.extend(extract_emails_from_text(content_about))
        except Exception as e:
            print(f"[-] About page load error ({about_url}): {e}", flush=True)

    unique_emails = list(dict.fromkeys(emails))
    return unique_emails

async def main():
    if not os.path.exists(INPUT_CSV):
        print(f"[-] File {INPUT_CSV} not found.")
        return

    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    cache = {}
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
        except Exception:
            cache = {}

    with open(INPUT_CSV, 'r', encoding='utf-8-sig', errors='ignore') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    # Find tasks
    tasks_to_scrape = {}
    for r in rows:
        em = r.get('Email', '').strip()
        fb = r.get('Facebook_URL', '').strip()
        if fb and not em:
            path = urllib.parse.urlparse(fb).path.strip('/')
            if path and path not in ['pages', 'tr', 'people', 'profile.php', 'sharer.php', 'p', 'plugins', 'share.php']:
                fb_norm = fb.rstrip('/')
                if fb_norm not in tasks_to_scrape:
                    tasks_to_scrape[fb_norm] = []
                tasks_to_scrape[fb_norm].append(r['Name'])

    print(f"[+] Total distinct valid FB fanpages needing email: {len(tasks_to_scrape)}")
    uncached = [u for u in tasks_to_scrape if u not in cache]
    print(f"[+] Uncached fanpages to scrape: {len(uncached)}")

    if uncached:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                viewport={'width': 1280, 'height': 800}
            )
            page = await context.new_page()

            for idx, fb_url in enumerate(uncached, 1):
                company_names = tasks_to_scrape[fb_url]
                print(f"\n[{idx}/{len(uncached)}] Scraping {fb_url} ({', '.join(company_names[:2])})...", flush=True)
                
                try:
                    found = await scrape_fanpage(page, fb_url)
                    if found:
                        print(f"  ===> SUCCESS! Found email: {found}", flush=True)
                    else:
                        print(f"  ---> No email found.", flush=True)
                    cache[fb_url] = found
                except Exception as e:
                    print(f"  [-] Error: {e}", flush=True)
                    cache[fb_url] = []

                # Save progress periodically
                if idx % 5 == 0 or idx == len(uncached):
                    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
                        json.dump(cache, f, ensure_ascii=False, indent=2)

            await browser.close()

    # Now update rows in Thuc pham litva - Raw.csv
    updated_count = 0
    for r in rows:
        em = r.get('Email', '').strip()
        fb = r.get('Facebook_URL', '').strip().rstrip('/')
        if not em and fb in cache:
            emails_found = cache[fb]
            if emails_found:
                r['Email'] = emails_found[0]
                updated_count += 1
                print(f"[UPDATED] {r['Name']} -> Email: {r['Email']} (via {fb})")

    if updated_count > 0:
        print(f"\n[*] Updating {INPUT_CSV} with {updated_count} newly found Facebook emails...")
        with open(INPUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print("[SUCCESS] Thuc pham litva - Raw.csv updated successfully!")

        # Re-run formatters
        print("[*] Re-running formatters/format_thuc_pham_lt_emails.py...")
        import subprocess
        subprocess.run([sys.executable, os.path.join(BASE_DIR, "formatters", "format_thuc_pham_lt_emails.py")])
    else:
        print("[*] No new emails were extracted from Facebook.")

if __name__ == '__main__':
    asyncio.run(main())
