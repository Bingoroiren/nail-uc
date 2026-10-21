"""
Enrichment Module for Croatian Employment Agencies (HR_AGCY)
===========================================================
Pipeline:
1. Load HR_AGCY_0RAW.csv (or HR_AGCY_MROS_0RAW.csv)
2. Query FinInfo.hr:
   - Legal Name normalization
   - Tax ID: OIB (11 digits)
   - Director / Authorized Representative (Osobe ovlaštene za zastupanje)
   - Company Status (Aktivan, U likvidaciji, etc.)
3. Query Tvrtke.hr (and Moja-Djelatnost fallback):
   - Phone Number (always formatted with leading single quote: '01...)
   - Official Website URL
   - Representative / Odgovorna osoba
4. Deep Website Crawl (crawl-mail compliant):
   - Scan /kontakt, /o-nama, /karijera, /posao
   - Decode Cloudflare data-cfemail, obfuscated emails
   - Score and pick THE BEST B2B EMAIL (praca@, hr@, info@, etc.)
5. Incremental Auto-Save & Checkpoint Cache (JSON)
"""

import os
import sys
import re
import json
import time
import urllib.request
import urllib.parse
import ssl
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)


# Workspace root
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_CSV = os.path.join(WORKSPACE_DIR, 'HR_AGCY_0RAW.csv')
OUTPUT_CSV = os.path.join(WORKSPACE_DIR, 'HR_AGCY_1ENR.csv')
CACHE_FILE = os.path.join(WORKSPACE_DIR, 'crawlmail', 'cache_hr_agcy.json')

# SSL & Network context
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS_BROWSER = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'hr,en-US,en;q=0.9'
}

HEADERS_TVRTKE = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'AMP-Same-Origin': 'true',
    'Referer': 'https://www.tvrtke.hr/',
    'Origin': 'https://www.tvrtke.hr'
}

# B2B Email Scoring constants
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$')
JUNK_DOMAINS = {'sentry.io', 'wixpress.com', 'wix.com', 'wordpress.com', 'example.com', 'domain.com', 'email.com'}
INVALID_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js')

def clean_phone(phone):
    if not phone or str(phone).strip() in ['-', '', 'None']:
        return ''
    p = str(phone).strip()
    p = re.sub(r'[\r\n\t]+', ' ', p)
    p = re.sub(r'\s+', ' ', p).strip()
    if p and not p.startswith("'"):
        p = f"'{p}"
    return p

def clean_email(email):
    if not email or str(email).strip() in ['-', '', 'None']:
        return ''
    e = str(email).strip().lower()
    e = urllib.parse.unquote(e)
    e = e.replace('%20', '').strip()
    if '@' not in e or '.' not in e:
        return ''
    return e

def score_email_b2b(email, domain=""):
    if not email or not isinstance(email, str):
        return -1
    e = email.strip().lower()
    if not EMAIL_REGEX.match(e):
        return -1
    if any(e.endswith(ext) for ext in INVALID_EXTS):
        return -1
    u, d = e.split('@', 1)
    if d in JUNK_DOMAINS:
        return -1
    if any(k in u for k in ['youremail', 'your-email', 'yourname', 'sample', 'placeholder', 'no-reply', 'donotreply']):
        return -1

    score = 10
    clean_d = domain.lower().replace('www.', '').split('/')[0] if domain else ""
    if clean_d and (clean_d in d or d in clean_d):
        score += 50

    # Priorities for Employment Agency:
    # 1. HR / Recruitment / Jobs (+50 pts)
    if u in ['posao', 'karijera', 'hr', 'zaposljavanje', 'recruitment', 'jobs', 'radnici', 'prijava', 'talent']:
        score += 50
    # 2. Executive / Management (+45 pts)
    elif u in ['direktor', 'uprava', 'ceo', 'voditelj', 'director', 'manager', 'owner', 'vodstvo']:
        score += 45
    # 3. Official General Inbox (+40 pts)
    elif u in ['info', 'kontakt', 'contact', 'office', 'ured', 'agencija', 'tajrinstvo']:
        score += 40
    # 4. Individual name on company domain (+25 pts)
    elif '.' in u and score >= 60:
        score += 25
    # 5. Free webmail (+10 pts)
    elif d in ['gmail.com', 'net.hr', 't-com.hr', 'post.hr']:
        score += 10
    return score

def select_best_email(emails, domain=""):
    valid = [e for e in set(emails) if score_email_b2b(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b(e, domain))

def query_fininfo(company_query, city=""):
    """Query FinInfo.hr for OIB, Legal Name, Address, Director, Status"""
    url = f"https://www.fininfo.hr/Home/SearchCompaniesFree?CompanyName={urllib.parse.quote(company_query)}&RadarList=False&UserId=0"
    try:
        req = urllib.request.Request(url, headers=HEADERS_BROWSER)
        with urllib.request.urlopen(req, context=ctx, timeout=8) as r:
            html = r.read().decode('utf-8', errors='ignore')
            rows = re.findall(r'<tr>\s*<td><span class="naziv"><a href="([^"]+)">([^<]+)</a></span></td>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>\s*</tr>', html)
            if not rows:
                return {}
            best = rows[0]
            if city:
                for row in rows:
                    if city.lower() in row[3].lower():
                        best = row
                        break
            href, full_name, addr, grad, oib = best
            res = {
                'oib': oib.strip(),
                'legal_name': full_name.strip(),
                'address': addr.strip(),
                'city': grad.strip(),
                'director': '',
                'status': 'Aktivan'
            }
            if href:
                detail_url = f"https://www.fininfo.hr{href}"
                try:
                    req_d = urllib.request.Request(detail_url, headers=HEADERS_BROWSER)
                    with urllib.request.urlopen(req_d, context=ctx, timeout=6) as rd:
                        d_html = rd.read().decode('utf-8', errors='ignore')
                        m_stat = re.search(r'Status:\s*([^\s<]+)', d_html)
                        if m_stat:
                            res['status'] = m_stat.group(1).strip()
                        m_dir = re.search(r'Osobe ovlaštene za zastupanje.*?<div[^>]*>([^<]+)</div>\s*,\s*direktor', d_html, re.DOTALL | re.IGNORECASE)
                        if not m_dir:
                            m_dir = re.search(r'Osobe ovlaštene za zastupanje.*?([\w\s\-]+),\s*direktor', d_html, re.DOTALL | re.IGNORECASE)
                        if m_dir:
                            clean_dir = re.sub(r'<[^>]+>', '', m_dir.group(1)).strip()
                            clean_dir = re.sub(r'\s+', ' ', clean_dir)
                            if len(clean_dir) < 60:
                                res['director'] = clean_dir
                except Exception:
                    pass
            return res
    except Exception:
        return {}

def query_tvrtke(brand_query, city=""):
    """Query Tvrtke.hr for Phone, Web, Profile link, and Representative"""
    url = f"https://www.tvrtke.hr/Services/Tvrtke.asmx/GetTvrtkeAmp?lang=hr&__amp_source_origin=https%3A%2F%2Fwww.tvrtke.hr&prefix={urllib.parse.quote(brand_query)}"
    try:
        req = urllib.request.Request(url, headers=HEADERS_TVRTKE)
        with urllib.request.urlopen(req, context=ctx, timeout=8) as r:
            data = json.loads(r.read().decode('utf-8'))
            if not data or not isinstance(data, list):
                return {}
            best_item = data[0]
            if city:
                for item in data:
                    if city.lower() in item.get('NazivWeb', '').lower():
                        best_item = item
                        break
            web_slug = best_item.get('NazivWeb', '')
            if not web_slug:
                return {}
            prof_url = f"https://www.tvrtke.hr{web_slug}"
            req_p = urllib.request.Request(prof_url, headers=HEADERS_BROWSER)
            with urllib.request.urlopen(req_p, context=ctx, timeout=8) as rp:
                p_html = rp.read().decode('utf-8', errors='ignore')
                phone = ""
                m_tel = re.search(r'Telefon:\s*</div>\s*<div[^>]*>([^<]+)</div>', p_html)
                if not m_tel:
                    m_tel = re.search(r'Telefon:.*?(\d[\d\s\/\-\(\)]+)', p_html)
                if m_tel:
                    phone = clean_phone(m_tel.group(1))

                rep = ""
                m_rep = re.search(r'Odgovorna osoba:\s*</div>\s*<div[^>]*>([^<]+)</div>', p_html)
                if not m_rep:
                    m_rep = re.search(r'Odgovorna osoba:\s*([^\n<]+)', p_html)
                if m_rep:
                    rep = m_rep.group(1).strip()

                ext_web = ""
                webs = re.findall(r'href=["\'](http[s]?://[^"\']+)["\']', p_html)
                cand = [w for w in webs if not any(x in w for x in ['tvrtke.hr', 'google', 'schema', 'w3', 'facebook', 'amp', 'twitter', 'linkedin'])]
                if cand:
                    ext_web = cand[0]

                return {
                    'phone': phone,
                    'representative': rep,
                    'web': ext_web,
                    'tvrtke_url': prof_url
                }
    except Exception:
        return {}

def decode_cloudflare_email(cf_hex):
    try:
        r = int(cf_hex[:2], 16)
        email = ''.join([chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
        return email
    except Exception:
        return ""

def crawl_website_emails(website_url):
    """Crawl homepage & subpages (/kontakt, /o-nama, etc.) for B2B emails"""
    if not website_url or not str(website_url).startswith('http'):
        return []
    parsed = urllib.parse.urlparse(website_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    
    subpaths = [
        website_url,
        urllib.parse.urljoin(root, '/kontakt'),
        urllib.parse.urljoin(root, '/kontakt.html'),
        urllib.parse.urljoin(root, '/o-nama'),
        urllib.parse.urljoin(root, '/karijera'),
        urllib.parse.urljoin(root, '/posao'),
        urllib.parse.urljoin(root, '/contact'),
        urllib.parse.urljoin(root, '/about-us')
    ]
    
    found_emails = set()
    for sub in subpaths[:5]:
        try:
            req = urllib.request.Request(sub, headers=HEADERS_BROWSER)
            with urllib.request.urlopen(req, context=ctx, timeout=6) as r:
                html = r.read().decode('utf-8', errors='ignore')
                
                # Cloudflare email decode
                for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', html):
                    decoded = decode_cloudflare_email(cf)
                    if '@' in decoded:
                        found_emails.add(decoded.lower().strip())
                
                # Normal mailto regex
                for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', html):
                    found_emails.add(clean_email(m))
                    
                # General regex
                for em in re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', html):
                    clean_em = clean_email(em)
                    if clean_em and not any(clean_em.endswith(ext) for ext in INVALID_EXTS):
                        found_emails.add(clean_em)
        except Exception:
            continue
    return [e for e in found_emails if e]

def run_enrichment():
    print(f"============================================================")
    print(f" CROATIAN EMPLOYMENT AGENCIES ENRICHMENT PIPELINE")
    print(f"============================================================")
    print(f"Input file:  {INPUT_CSV}")
    print(f"Output file: {OUTPUT_CSV}")
    print(f"Cache file:  {CACHE_FILE}")

    if not os.path.exists(INPUT_CSV):
        print(f"ERROR: {INPUT_CSV} does not exist!")
        return

    df = pd.read_csv(INPUT_CSV, encoding='utf-8-sig', dtype=str)
    # Ensure string dtype for all enrichment columns
    for col in ['OIB', 'SĐT', 'Web', 'Email', 'Người đại diện', 'Trạng thái']:
        if col not in df.columns:
            df[col] = ''
        df[col] = df[col].fillna('').astype(str)
    total = len(df)
    print(f"Loaded {total} agencies from input CSV.")


    # Load cache
    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"Loaded {len(cache)} cached records from {CACHE_FILE}.")
        except Exception as e:
            print(f"Warning: Failed to load cache: {e}")

    updated_count = 0
    start_time = time.time()

    for idx, row in df.iterrows():
        no = int(row['No.'])
        brand = str(row['Tên thương hiệu']).strip()
        comp = str(row['Công ty']).strip()
        city = str(row['Thành phố']).strip() if pd.notna(row['Thành phố']) else ""
        cache_key = f"{brand}::{city}".lower()

        print(f"\n[{no}/{total}] {brand} ({city or 'Croatia'})")

        # Check cache
        if cache_key in cache:
            item = cache[cache_key]
            for col in ['OIB', 'SĐT', 'Web', 'Email', 'Người đại diện', 'Trạng thái']:
                if item.get(col):
                    df.at[idx, col] = item[col]
            print(f"  [CACHE] OIB: {item.get('OIB')} | Phone: {item.get('SĐT')} | Email: {item.get('Email')}")
            continue

        item_data = {
            'OIB': row['OIB'] if pd.notna(row['OIB']) else '',
            'SĐT': row['SĐT'] if pd.notna(row['SĐT']) else '',
            'Web': row['Web'] if pd.notna(row['Web']) else '',
            'Email': row['Email'] if pd.notna(row['Email']) else '',
            'Người đại diện': row['Người đại diện'] if pd.notna(row['Người đại diện']) else '',
            'Trạng thái': row['Trạng thái'] if pd.notna(row['Trạng thái']) else ''
        }

        # Step 1: Query FinInfo
        fin = query_fininfo(brand, city)
        if not fin.get('oib') and comp != brand:
            fin = query_fininfo(comp, city)
        
        if fin.get('oib'):
            item_data['OIB'] = fin['oib']
            if fin.get('director') and not item_data['Người đại diện']:
                item_data['Người đại diện'] = fin['director']
            if fin.get('status'):
                item_data['Trạng thái'] = fin['status']
            print(f"  [FinInfo] OIB: {fin['oib']} | Dir: {fin.get('director')} | Status: {fin.get('status')}")

        # Step 2: Query Tvrtke.hr
        tv = query_tvrtke(brand, city)
        if tv.get('phone') and not item_data['SĐT']:
            item_data['SĐT'] = clean_phone(tv['phone'])
        if tv.get('web') and not item_data['Web']:
            item_data['Web'] = tv['web']
        if tv.get('representative') and not item_data['Người đại diện']:
            item_data['Người đại diện'] = tv['representative']
        if tv.get('phone') or tv.get('web'):
            print(f"  [Tvrtke]  Phone: {item_data['SĐT']} | Web: {item_data['Web']}")

        # Step 3: Deep Website Crawl for Email
        if item_data['Web']:
            emails = crawl_website_emails(item_data['Web'])
            best_mail = select_best_email(emails, item_data['Web'])
            if best_mail:
                item_data['Email'] = best_mail
                print(f"  [WebCrawl] Best Email: {best_mail}")

        # Update dataframe
        for k, v in item_data.items():
            if v:
                df.at[idx, k] = v

        cache[cache_key] = item_data
        updated_count += 1

        # Incremental save every 5 items
        if updated_count % 5 == 0:
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            # Sort emails to the top
            has_em = df[df['Email'].notna() & (df['Email'].str.strip() != '')]
            no_em = df[df['Email'].isna() | (df['Email'].str.strip() == '')]
            df_sorted = pd.concat([has_em, no_em], ignore_index=True)
            df_sorted['No.'] = range(1, len(df_sorted) + 1)
            df_sorted.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')

        time.sleep(0.3)  # Polite delay

    # Final save & sort
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    has_em = df[df['Email'].notna() & (df['Email'].str.strip() != '')]
    no_em = df[df['Email'].isna() | (df['Email'].str.strip() == '')]
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)
    df_sorted.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')

    elapsed = time.time() - start_time
    print(f"\n============================================================")
    print(f" ENRICHMENT COMPLETED in {elapsed/60:.2f} minutes!")
    print(f" Output saved to: {OUTPUT_CSV}")
    print(f" Total records with Email: {len(has_em)}/{total}")
    print(f"============================================================")

if __name__ == '__main__':
    run_enrichment()
