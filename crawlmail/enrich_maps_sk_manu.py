import asyncio
import os
import sys
import re
import ssl
import json
import argparse
import urllib.parse
import urllib.request
import pandas as pd
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

CSV_PATH = 'SK_MANU_SLVD_1ENR.csv'
CACHE_PATH = os.path.join('crawlmail', 'cache_enrich_maps_sk_manu.json')

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
# Strict Email Regex: TLD must be purely alphabetical 2-10 chars (rejects @1.10.0 version artifacts)
EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')
INVALID_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.pdf', '.woff', '.woff2', '.ico', '.mp4')

BLACKLIST_DOMAINS = [
    'facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'twitter.com', 'x.com',
    'google.com', 'maps.google.com', 'yellowpages', 'proff.no', 'brreg.no', 'zlatestranky.sk',
    'azet.sk', 'finstat.sk', 'orsr.sk', 'zrsr.sk', 'wikipedia.org', 'portal.sk',
    'profesia.sk', 'kariera.zoznam.sk', 'praca.sme.sk', 'worki.sk', 'sentry.io', 'wixpress.com'
]

def decode_cf(cf_hex):
    try:
        r = int(cf_hex[:2], 16)
        return ''.join([chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
    except:
        return ""

def is_valid_name_match(query_name, candidate_name):
    """Strict Name Matching per skill enrich-maps: exact, brackets, or delimiters"""
    if not query_name or not candidate_name:
        return False, "EMPTY"
    
    q = re.sub(r'["\'„“”«»]', '', str(query_name)).strip().lower()
    c = re.sub(r'["\'„“”«»]', '', str(candidate_name)).strip().lower()
    
    for lf in ['spol. s r.o.', 'spol. s r. o.', 's.r.o.', 's. r. o.', 'a.s.', 'a. s.', 'k.s.', 'v.o.s.', 'druzstvo', 'gmbh']:
        q = q.replace(lf, '').strip()
        c = c.replace(lf, '').strip()
        
    if not q or not c:
        return False, "EMPTY_AFTER_CLEAN"
        
    if q == c:
        return True, "EXACT"
        
    c_nobrackets = re.sub(r'\(.*?\)|\[.*?\]', '', c).strip()
    if q == c_nobrackets:
        return True, "BRACKET_MATCH"
        
    parts = [p.strip() for p in re.split(r'[-–—|/:,]', c) if p.strip()]
    if any(p == q for p in parts):
        return True, "DELIMITER_MATCH"
        
    if len(q) >= 6 and (q in c or c in q):
        return True, "SUBSTRING_MATCH"
        
    return False, "NO_MATCH"

def score_email_b2b(email, domain=""):
    if not email or not isinstance(email, str):
        return -1
    e = email.strip().lower()
    if not EMAIL_REGEX.match(e) or any(e.endswith(ext) for ext in INVALID_EXTS):
        return -1
    u, d = e.split('@', 1)
    
    # Reject version artifacts and js bundles (e.g. es-module-shims@1.10.0, 1@yu.wk)
    if re.search(r'\d+\.\d+', d) or len(u) <= 1 or len(d) <= 3:
        return -1
    if any(bad in d for bad in ['sentry', 'wixpress', 'wix.com', 'example.com', 'domain.com', 'email.com', 'address.com', 'mail.sk']):
        return -1
    if any(bad in u for bad in ['sentry', 'youremail', 'your-email', 'yourname', 'sample', 'no-reply', 'donotreply', 'es-module']):
        return -1
    if u in ['mail', 'email'] and (d in ['mail.sk', 'email.com', 'address.com'] or u == d.split('.')[0]):
        return -1

    score = 10
    clean_d = domain.lower().replace('www.', '').split('/')[0] if domain else ""
    if clean_d and (clean_d in d or d in clean_d):
        score += 50
    elif d.endswith('.sk'):
        score += 25

    if u in ['praca', 'kariera', 'hr', 'personalne', 'jobs', 'recruitment', 'nabor', 'career']:
        score += 50
    elif u in ['vedenie', 'riaditel', 'konatel', 'ceo', 'director', 'manager', 'obchod', 'sales']:
        score += 45
    elif u in ['info', 'kontakt', 'contact', 'office', 'sekretariat', 'recepcia', 'kancelaria']:
        score += 40
    elif '.' in u and score >= 60:
        score += 25
    return score

def select_best_email(emails, domain=""):
    valid = [e for e in set(emails) if score_email_b2b(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b(e, domain))

def fetch_html_stealth(url):
    """Fetch HTML with curl_cffi chrome120 or fallback urllib"""
    try:
        from curl_cffi import requests as c_requests
        r = c_requests.get(url, impersonate='chrome120', timeout=6, verify=False)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=4) as r:
            return r.read().decode('utf-8', errors='ignore')
    except Exception:
        pass
    return ""

def crawl_site_for_emails(web_url):
    """DOM-First Multi-Tier Email Extractor per Skill crawl-mail"""
    if not web_url or not web_url.startswith('http'):
        return ""
    if any(bad in web_url.lower() for bad in BLACKLIST_DOMAINS):
        return ""
        
    parsed = urllib.parse.urlparse(web_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    found = set()
    
    # 1. Fetch Homepage
    home_html = fetch_html_stealth(web_url)
    if not home_html and web_url != root:
        home_html = fetch_html_stealth(root)
        
    if home_html:
        # Priority 1: Check mailto on homepage
        for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', home_html, re.I):
            clean_m = m.split('?')[0].strip().lower()
            if '@' in clean_m:
                found.add(clean_m)
        # Check cloudflare on homepage
        for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', home_html):
            dec = decode_cf(cf)
            if '@' in dec:
                found.add(dec.strip().lower())
        # Check direct regex on homepage
        for em in EMAIL_REGEX.findall(home_html):
            if score_email_b2b(em, root) > 0:
                found.add(em.strip().lower())
                
        # If found good domain email on homepage, return immediately
        best_home = select_best_email(found, root)
        if best_home and score_email_b2b(best_home, root) >= 50:
            return best_home

        # Priority 2: Extract real DOM contact links from homepage (<a href="...">)
        from bs4 import BeautifulSoup
        try:
            soup = BeautifulSoup(home_html, 'html.parser')
            dom_contact_links = []
            for a in soup.find_all('a', href=True):
                h = a['href'].lower()
                txt = a.get_text().lower()
                if any(k in h or k in txt for k in ['kontakt', 'kontakty', 'contact', 'o-nas', 'kariera', 'praca', 'impressum', 'career']):
                    full = urllib.parse.urljoin(web_url, a['href'])
                    if full not in dom_contact_links and '#' not in a['href'] and not any(full.lower().endswith(ext) for ext in INVALID_EXTS):
                        dom_contact_links.append(full)
                        
            for cl in dom_contact_links[:4]:
                chtml = fetch_html_stealth(cl)
                if not chtml:
                    continue
                for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', chtml, re.I):
                    clean_m = m.split('?')[0].strip().lower()
                    if '@' in clean_m:
                        found.add(clean_m)
                for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', chtml):
                    dec = decode_cf(cf)
                    if '@' in dec:
                        found.add(dec.strip().lower())
                for em in EMAIL_REGEX.findall(chtml):
                    if score_email_b2b(em, root) > 0:
                        found.add(em.strip().lower())
                if found:
                    break
        except Exception:
            pass

    # Priority 3: Fallback Guess Paths if still nothing found
    if not found:
        guess_paths = [
            f"{root}/kontakt", f"{root}/sk/kontakt", f"{root}/kontakt.html",
            f"{root}/o-nas", f"{root}/kariera", f"{root}/contact"
        ]
        for gp in guess_paths:
            ghtml = fetch_html_stealth(gp)
            if not ghtml:
                continue
            for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', ghtml, re.I):
                clean_m = m.split('?')[0].strip().lower()
                if '@' in clean_m:
                    found.add(clean_m)
            for em in EMAIL_REGEX.findall(ghtml):
                if score_email_b2b(em, root) > 0:
                    found.add(em.strip().lower())
            if found:
                break

    return select_best_email(found, root)

def save_and_reorder(df, output_path):
    has_em = df[df['Email'].notna() & (df['Email'].astype(str).str.strip() != '') & (df['Email'].astype(str).str.strip() != 'nan')].copy()
    no_em = df[df['Email'].isna() | (df['Email'].astype(str).str.strip() == '') | (df['Email'].astype(str).str.strip() == 'nan')].copy()
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)
    df_sorted.to_csv(output_path, index=False, encoding='utf-8-sig')
    return len(has_em)

async def run_enrichment(headless=False):
    print("================================================================================")
    print(" GOOGLE MAPS DATA ENRICHMENT - SLOVAK MANUFACTURING (STRICT MATCH)")
    print("================================================================================")
    print(f" Target File : {CSV_PATH}")
    print(f" Cache File  : {CACHE_PATH}")
    print(f" View Mode   : {'HEADLESS (Background)' if headless else 'VISUAL (Headless=False)'}")
    print("================================================================================\n")

    if not os.path.exists(CSV_PATH):
        print(f"[ERROR] Target file '{CSV_PATH}' not found!")
        return

    df = pd.read_csv(CSV_PATH, encoding='utf-8-sig', dtype=str)
    for col in ['Web', 'Email', 'SĐT']:
        if col not in df.columns:
            df[col] = ''
        df[col] = df[col].fillna('').astype(str)

    cache = {}
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
        except Exception as e:
            print(f"[WARN] Could not load cache: {e}")

    # Build memory cache from existing items with clean emails
    for idx, row in df.iterrows():
        comp = str(row['Công ty']).strip()
        ico = str(row.get('IČO', '')).strip()
        em = str(row['Email']).strip()
        if em and em != 'nan':
            cache[ico or comp] = {
                'Web': str(row['Web']).strip(),
                'Email': em,
                'SĐT': str(row['SĐT']).strip()
            }

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-sandbox",
                "--js-flags=--max-old-space-size=512"
            ]
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="sk-SK"
        )
        await context.add_cookies([
            {'name': 'SOCS', 'value': 'CAESEwgDEgk2OTQ0NTgyODQaAmVuIAEaBgiA_LyaBg', 'domain': '.google.com', 'path': '/'}
        ])
        page = await context.new_page()

        total = len(df)
        processed = 0

        for idx, row in df.iterrows():
            comp = str(row['Công ty']).strip()
            city = str(row['Thành phố']).strip() if pd.notna(row['Thành phố']) else ""
            ico = str(row.get('IČO', '')).strip()
            cache_key = ico if ico else f"{comp}::{city}".lower()

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

            # Query Google Maps
            q = f"{comp} {city}".strip()
            url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(q)}"
            web_url = None
            phone_val = None
            matched = False

            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=12000)
                await page.wait_for_timeout(2000)

                if "consent.google.com" in page.url or await page.query_selector("iframe[src*='recaptcha']"):
                    print("\n\a[WARNING] Google Captcha detected! Please solve it on browser window...\n")
                    await page.wait_for_timeout(10000)

                items = await page.query_selector_all('a[href*="/maps/place/"]')
                if items:
                    for item in items[:3]:
                        aria_label = await item.get_attribute('aria-label') or ""
                        is_ok, _ = is_valid_name_match(comp, aria_label)
                        if is_ok:
                            await item.click()
                            await page.wait_for_timeout(2000)
                            matched = True
                            break
                else:
                    title_elem = await page.query_selector('h1.DUwDvf')
                    if title_elem:
                        t_text = await title_elem.inner_text()
                        is_ok, _ = is_valid_name_match(comp, t_text)
                        matched = is_ok

                if matched:
                    web_btn = await page.query_selector('a[data-item-id="authority"]')
                    if web_btn:
                        cand_web = await web_btn.get_attribute('href')
                        if cand_web and not any(bad in cand_web.lower() for bad in BLACKLIST_DOMAINS):
                            web_url = cand_web

                    phone_btn = await page.query_selector('button[data-item-id^="phone:"]')
                    if phone_btn:
                        p_attr = await phone_btn.get_attribute('data-item-id')
                        if p_attr and p_attr.startswith('phone:tel:'):
                            phone_val = p_attr.replace('phone:tel:', '').strip()
            except Exception:
                pass

            email = ""
            if web_url and matched:
                email = crawl_site_for_emails(web_url)

            if web_url and matched and not df.at[idx, 'Web']:
                df.at[idx, 'Web'] = web_url
            if email:
                df.at[idx, 'Email'] = email
            if phone_val and matched and not df.at[idx, 'SĐT']:
                df.at[idx, 'SĐT'] = f"'{phone_val}" if not str(phone_val).startswith("'") else phone_val

            cache[cache_key] = {
                'Web': (web_url if matched else '') or df.at[idx, 'Web'] or '',
                'Email': email or '',
                'SĐT': df.at[idx, 'SĐT'] or ''
            }
            processed += 1

            status = f"[EMAIL] {email}" if email else ("No match" if not matched else "No email")
            web_disp = web_url[:35] if (web_url and matched) else "No web"
            print(f"[{processed:04d}/{total}] {comp[:30]:<30} ({city:<10}) | {web_disp:<35} | {status}")

            if processed % 5 == 0:
                with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
                em_cnt = save_and_reorder(df, CSV_PATH)
                print(f"  --> [CHECKPOINT] {em_cnt} factories with EMAIL sorted to top of {CSV_PATH}!")

            # Periodic Page Recycling: release accumulated Chromium memory leaks every 25 queries
            if processed % 25 == 0:
                try:
                    await page.close()
                    page = await context.new_page()
                except Exception:
                    pass

        await browser.close()

    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    em_cnt = save_and_reorder(df, CSV_PATH)
    print(f"\n================================================================================")
    print(f" COMPLETED! Total verified clean emails on top: {em_cnt}/{total}")
    print(f" Output File: {CSV_PATH}")
    print(f"================================================================================")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Enrich Slovak Manufacturing data via Google Maps (Strict)")
    parser.add_argument('--headless', action='store_true', help="Run browser in headless mode without UI")
    args = parser.parse_args()
    asyncio.run(run_enrichment(headless=args.headless))
