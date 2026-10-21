import asyncio
from playwright.async_api import async_playwright
import urllib.parse
import urllib.request
import ssl
import re
import sys
import pandas as pd
import json
import os
import time

sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

CSV_PATH = 'HR_AGCY_1ENR.csv'
CACHE_PATH = os.path.join('crawlmail', 'cache_croatia_emails.json')

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$')
INVALID_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js')

def decode_cf(cf_hex):
    try:
        r = int(cf_hex[:2], 16)
        return ''.join([chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
    except:
        return ""

def score_email_b2b(email, domain=""):
    if not email or not isinstance(email, str):
        return -1
    e = email.strip().lower()
    if not EMAIL_REGEX.match(e) or any(e.endswith(ext) for ext in INVALID_EXTS):
        return -1
    u, d = e.split('@', 1)
    if d in ['sentry.io', 'wixpress.com', 'wix.com', 'example.com', 'domain.com', 'email.com', 'address.com']:
        return -1
    if any(k in u for k in ['youremail', 'your-email', 'yourname', 'sample', 'no-reply', 'donotreply']):
        return -1
    if u in ['mail', 'email'] and d in ['address.com', 'email.com', 'domain.com']:
        return -1

    score = 10
    clean_d = domain.lower().replace('www.', '').split('/')[0] if domain else ""
    if clean_d and (clean_d in d or d in clean_d):
        score += 50
    elif d.endswith('.hr'):
        score += 25

    if 'croatia' in u or 'hrvatska' in u or u.endswith('.hr') or u.startswith('hr.'):
        score += 35

    if u in ['posao', 'karijera', 'hr', 'zaposljavanje', 'recruitment', 'jobs', 'talent', 'radnici', 'prijava']:
        score += 50
    elif u in ['direktor', 'uprava', 'ceo', 'director', 'manager', 'voditelj']:
        score += 45
    elif u in ['info', 'kontakt', 'contact', 'office', 'ured', 'agencija', 'tajnistvo', 'infocroatia', 'info.hr']:
        score += 40
    elif '.' in u and score >= 60:
        score += 25
    return score

def select_best_email(emails, domain=""):
    valid = [e for e in set(emails) if score_email_b2b(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b(e, domain))

def crawl_site_for_emails(web_url):
    if not web_url or not web_url.startswith('http'):
        return ""
    parsed = urllib.parse.urlparse(web_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    pages = [web_url, f"{root}/kontakt", f"{root}/o-nama", f"{root}/posao"]
    found = set()
    for p in pages:
        try:
            req = urllib.request.Request(p, headers=HEADERS)
            with urllib.request.urlopen(req, context=ctx, timeout=4) as r:
                html = r.read().decode('utf-8', errors='ignore')
                for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', html):
                    dec = decode_cf(cf)
                    if '@' in dec:
                        found.add(dec.lower().strip())
                for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', html):
                    found.add(m.lower().strip())
                for em in re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', html):
                    cl = em.lower().strip()
                    if not any(cl.endswith(ext) for ext in INVALID_EXTS):
                        found.add(cl)
            if found:
                break
        except:
            continue
    return select_best_email(found, root)

def save_and_reorder(df, output_path):
    has_em = df[df['Email'].notna() & (df['Email'].astype(str).str.strip() != '') & (df['Email'].astype(str).str.strip() != 'nan')].copy()
    no_em = df[df['Email'].isna() | (df['Email'].astype(str).str.strip() == '') | (df['Email'].astype(str).str.strip() == 'nan')].copy()
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)
    df_sorted.to_csv(output_path, index=False, encoding='utf-8-sig')
    return len(has_em)

async def main():
    print("============================================================")
    print(" PRIORITY CROATIA AGENCY EMAIL HARVESTER (SOCS BYPASS)")
    print("============================================================")

    df = pd.read_csv(CSV_PATH, encoding='utf-8-sig', dtype=str)
    for col in ['Web', 'Email', 'SĐT', 'OIB']:
        if col not in df.columns:
            df[col] = ''
        df[col] = df[col].fillna('').astype(str)

    cache = {}
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            # Remove empty email entries from cache so we re-scan them with the working SOCS bypass
            cache = {k: v for k, v in cache.items() if v.get('Email')}
        except:
            pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US"
        )
        # SOCS cookie bypasses Google Consent completely
        await context.add_cookies([
            {'name': 'SOCS', 'value': 'CAESEwgDEgk2OTQ0NTgyODQaAmVuIAEaBgiA_LyaBg', 'domain': '.google.com', 'path': '/'}
        ])
        page = await context.new_page()

        total = len(df)
        processed = 0

        for idx, row in df.iterrows():
            brand = str(row['Tên thương hiệu']).strip()
            city = str(row['Thành phố']).strip() if pd.notna(row['Thành phố']) else ""
            cache_key = f"{brand}::{city}".lower()

            current_email = str(df.at[idx, 'Email']).strip()
            if current_email and current_email != 'nan':
                continue

            if cache_key in cache:
                c = cache[cache_key]
                if c.get('Email'):
                    df.at[idx, 'Email'] = c['Email']
                if c.get('Web') and not df.at[idx, 'Web']:
                    df.at[idx, 'Web'] = c['Web']
                if c.get('SĐT') and not df.at[idx, 'SĐT']:
                    df.at[idx, 'SĐT'] = c['SĐT']
                continue

            q = f"{brand} {city}".strip()
            url = f"https://www.google.com/maps/search/{q.replace(' ', '+')}"
            web_url = None
            phone_val = None

            try:
                await page.goto(url, timeout=15000)
                await page.wait_for_timeout(2500)

                items = await page.query_selector_all('a[href*="/maps/place/"]')
                if items:
                    await items[0].click()
                    await page.wait_for_timeout(2500)

                web_btn = await page.query_selector('a[data-item-id="authority"]')
                if web_btn:
                    web_url = await web_btn.get_attribute('href')

                phone_btn = await page.query_selector('button[data-item-id^="phone:"]')
                if phone_btn:
                    p_attr = await phone_btn.get_attribute('data-item-id')
                    if p_attr and p_attr.startswith('phone:tel:'):
                        phone_val = p_attr.replace('phone:tel:', '')
            except Exception as e:
                pass

            email = ""
            if web_url:
                email = crawl_site_for_emails(web_url)

            if web_url and not df.at[idx, 'Web']:
                df.at[idx, 'Web'] = web_url
            if email:
                df.at[idx, 'Email'] = email
            if phone_val and not df.at[idx, 'SĐT']:
                df.at[idx, 'SĐT'] = f"'{phone_val}"

            cache[cache_key] = {
                'Web': web_url or '',
                'Email': email or '',
                'SĐT': f"'{phone_val}" if phone_val else ''
            }
            processed += 1

            status = f"EMAIL: {email}" if email else "No email"
            web_disp = web_url[:35] if web_url else "No web"
            print(f"[{processed}/{total}] {brand[:25]:<25} ({city}) | {web_disp:<35} | {status}")

            if processed % 5 == 0:
                with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
                em_cnt = save_and_reorder(df, CSV_PATH)
                print(f"  --> [SAVED] {em_cnt} agencies with EMAIL pushed to top of {CSV_PATH}!")

        await browser.close()

    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    em_cnt = save_and_reorder(df, CSV_PATH)
    print(f"\nCOMPLETED! Total with Email: {em_cnt}/{total}")

if __name__ == '__main__':
    asyncio.run(main())
