# -*- coding: utf-8 -*-
"""
Latvia Labour Agency & Personnel Selection Scraper & Multi-Stage Enrichment:
- Sources:
  1. 1188.lv Catalog: Personnel Selection (https://www.1188.lv/en/catalog/personnel-selection-1380)
  2. 1188.lv Catalog: Public Employment Service (https://www.1188.lv/en/catalog/public-employment-service-6282)
  3. Viss.lv Catalog: Personāla atlase (https://viss.lv/katalogs/personala_atlase/latvija/)
- Outputs:
  * LV_AGCY_WEBD_0RAW.csv: Raw deduplicated records from all 3 catalogs
  * LV_AGCY_WEBD_1ENR.csv: Enriched with deep website crawl & social contacts
  * LV_AGCY_WEBD_2COL.csv: Final Cold Mail ready (20 columns, Emails on top, single quote ' on phones)
"""

import sys
import os
import re
import csv
import json
import time
import urllib.parse
import unicodedata
from pathlib import Path
from bs4 import BeautifulSoup
from curl_cffi import requests

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_0RAW = str(ROOT_DIR / "LV_AGCY_WEBD_0RAW.csv")
OUTPUT_1ENR = str(ROOT_DIR / "LV_AGCY_WEBD_1ENR.csv")
OUTPUT_2COL = str(ROOT_DIR / "LV_AGCY_WEBD_2COL.csv")
CACHE_FILE = str(ROOT_DIR / "crawlmail" / "cache_lv_agcy_webd.json")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'lv,en-US;q=0.7,en;q=0.3'
}

PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre', 'daigrė'
]

COLUMNS_2COL = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ', 'Email',
    'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển', 'Check gửi',
    'Last Subject', 'Last Body HTML', 'Trạng thái Reply', 'Lần Follow-up',
    'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

LATVIAN_MENU_KEYWORDS = [
    'kontakti', 'kontakt', 'par-mums', 'parmums', 'par_mums', 'vakances',
    'karjera', 'pakalpojumi', 'kontakts', 'rakstiet-mums', 'atrast-mus',
    'contact', 'about', 'team', 'jobs', 'careers'
]

LATVIAN_SUBPATHS = [
    '/kontakti', '/kontakti.html', '/kontakti.php',
    '/par-mums', '/par-mums.html', '/parmums',
    '/vakances', '/karjera', '/contact', '/contact-us',
    '/about', '/about-us'
]

JUNK_DOMAINS = {
    '1188.lv', 'viss.lv', 'crediweb.lv', 'crefocert.lv', 'lursoft.lv', 'facebook.com',
    'instagram.com', 'linkedin.com', 'twitter.com', 'x.com', 'youtube.com',
    'tiktok.com', 'tet.lv', 'maptiler.com', 'openstreetmap.org', 'leafletjs.com',
    'sentry.io', 'wixpress.com', 'wix.com', 'wordpress.com', 'example.com',
    'domain.com', 'schema.org'
}

JUNK_EMAILS = {
    'info@1188.lv', 'viss@viss.lv', 'info@viss.lv', 'sentry@', 'wix@',
    'noreply@', 'no-reply@', 'privacy@', 'terms@', 'gdpr@', 'cookies@'
}

FREE_WEBMAILS = {
    'inbox.lv', 'gmail.com', 'apollo.lv', 'tvnet.lv', 'mail.ru',
    'yahoo.com', 'hotmail.com', 'outlook.com', 'yandex.ru'
}

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

def clean_phone(phone_str):
    if not phone_str or str(phone_str) == 'nan':
        return ""
    p = str(phone_str).strip()
    p = re.sub(r'^(?:Tel|T\.|Tālr\.|Tālrunis)[:\s]*', '', p, flags=re.I).strip()
    p = re.sub(r'[\(\)\-\s]', '', p)
    if p.startswith('+371'):
        num = p[4:]
    elif p.startswith('00371'):
        num = p[5:]
    elif p.startswith('371') and len(p) == 11:
        num = p[3:]
    else:
        num = p
    
    # Standard Latvian phone is 8 digits
    if len(num) == 8 and num.isdigit():
        formatted = f"+371 {num}"
    elif p.startswith('+'):
        formatted = p
    elif p:
        formatted = f"+371 {num}" if len(num) == 8 else p
    else:
        formatted = ""
        
    if formatted and not formatted.startswith("'"):
        formatted = f"'{formatted}"
    return formatted

def clean_company_name(name):
    if not name:
        return ""
    c = str(name).strip()
    c = re.sub(r'^[\"\'„“\s]+|[\"\'”\s]+$', '', c)
    c = re.sub(r'\s*\d+\s*$', '', c)
    return c.strip()

def clean_email(email_str):
    if not email_str:
        return None
    e = email_str.lower().strip().replace('%20', '').strip('.,;:()[]"\'')
    e = re.sub(r'^(?:e-mail\.|email\.|mailto:)', '', e)
    e = e.rstrip('/')
    if '@' not in e or len(e) < 6:
        return None
    user, _, dom = e.partition('@')
    if not user or not dom or '.' not in dom:
        return None
    if any(e.startswith(je) or e == je for je in JUNK_EMAILS):
        return None
    if dom in JUNK_DOMAINS or any(dom.endswith('.' + jd) for jd in JUNK_DOMAINS):
        return None
    if any(e.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf', '.css', '.js']):
        return None
    return e

def score_email_b2b(email, website_domain=""):
    e = email.lower().strip()
    user, _, domain = e.partition('@')
    score = 0
    if website_domain and website_domain in domain:
        score += 50
    # Top Priority: Recruitment / HR / Jobs in Latvian & English
    if any(k in user for k in ['cv', 'vakances', 'darbs', 'hr', 'recruitment', 'jobs', 'karjera', 'personals', 'staff', 'talent']):
        score += 50
    # Executive / Management
    elif any(k in user for k in ['vadiba', 'direktors', 'ceo', 'manager', 'director', 'valde', 'owner', 'president']):
        score += 45
    # Official Contact Desk
    elif any(k in user for k in ['info', 'kontakti', 'contact', 'birojs', 'office', 'pasts', 'reception', 'mail']):
        score += 40
    elif '.' in user and website_domain in domain:
        score += 25
    elif any(w in domain for w in FREE_WEBMAILS):
        score += 10
    else:
        score += 5
    return score

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[!] Error saving cache: {e}", flush=True)

# -------------------------------------------------------------
# PHASE 1: Scrape 1188.lv
# -------------------------------------------------------------
def scrape_1188_category(session, start_url, category_name):
    print(f"\n[*] Scraping 1188.lv: {category_name} ({start_url})...", flush=True)
    results = []
    page_num = 1
    
    while True:
        url = f"{start_url}?page={page_num}"
        try:
            r = session.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.text, 'html.parser')
            cards = soup.select('.company')
            if not cards:
                break
                
            print(f"  Page {page_num}: Found {len(cards)} listings.", flush=True)
            for c in cards:
                name_a = c.find('a', class_='name')
                if not name_a:
                    continue
                name_raw = name_a.get_text(strip=True)
                comp_name = clean_company_name(name_raw)
                profile_url = name_a.get('href', '').strip()
                if not profile_url:
                    continue
                    
                phone = ""
                email = ""
                website = ""
                address = ""
                try:
                    time.sleep(0.3)
                    r_det = session.get(profile_url, headers=HEADERS, timeout=12)
                    if r_det.status_code == 200:
                        s_det = BeautifulSoup(r_det.text, 'html.parser')
                        
                        name_span = s_det.select_one('h1 span.name')
                        if name_span:
                            comp_name = clean_company_name(name_span.get_text(strip=True))
                            
                        # Phone
                        tel_a = s_det.find('a', href=lambda h: h and h.startswith('tel:'))
                        if tel_a:
                            phone = clean_phone(tel_a['href'].replace('tel:', '').strip())
                            
                        # Email
                        mail_a = s_det.find('a', href=lambda h: h and h.startswith('mailto:'))
                        if mail_a:
                            email = clean_email(mail_a['href'].replace('mailto:', '').split('?')[0].strip()) or ""
                            
                        # Website strictly inside company-info box
                        info_box = s_det.find(class_='company-info')
                        if info_box:
                            # 1. Check for utm_medium links
                            for a in info_box.find_all('a', href=True):
                                h = a['href'].strip()
                                if 'utm_medium=homepage' in h or 'utm_medium=screenshot' in h:
                                    p = urllib.parse.urlparse(h)
                                    website = f"{p.scheme}://{p.netloc}"
                                    break
                            # 2. Check direct domain links
                            if not website:
                                for a in info_box.find_all('a', href=True):
                                    h = a['href'].strip()
                                    if h.startswith('http') and not any(ign in h.lower() for ign in JUNK_DOMAINS):
                                        p = urllib.parse.urlparse(h)
                                        if p.netloc and '.' in p.netloc:
                                            website = f"{p.scheme}://{p.netloc}"
                                            break
                                
                        # Address
                        addr_div = s_det.find(class_=lambda cls: cls and 'address' in cls)
                        if addr_div:
                            address = addr_div.get_text(" ", strip=True)
                except Exception as e_det:
                    print(f"    [!] Error parsing profile {profile_url}: {e_det}", flush=True)

                if is_blacklisted_company(comp_name):
                    continue

                item = {
                    'Công ty': comp_name,
                    'Chức danh': category_name,
                    'Người liên hệ': '',
                    'SĐT': phone,
                    'Liên Hệ': website,
                    'Email': email,
                    'Liên Hệ mail': profile_url if email else '',
                    'Địa chỉ': address,
                    'Category': category_name,
                    'Source': '1188.lv',
                    'Profile_URL': profile_url
                }
                results.append(item)
                print(f"    + [{category_name}] {comp_name:<32} | Phone: {phone:<18} | Email: {email:<25} | Web: {website}", flush=True)

            next_a = soup.find('a', href=lambda h: h and f'page={page_num + 1}' in h)
            if not next_a:
                break
            page_num += 1
        except Exception as e:
            print(f"[!] Error on page {page_num}: {e}", flush=True)
            break
            
    return results

# -------------------------------------------------------------
# PHASE 2: Scrape viss.lv
# -------------------------------------------------------------
def scrape_viss_category(session, start_url):
    print(f"\n[*] Scraping viss.lv: Personāla atlase ({start_url})...", flush=True)
    results = []
    try:
        r = session.get(start_url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            print(f"[-] Failed to fetch viss.lv: {r.status_code}", flush=True)
            return results
            
        soup = BeautifulSoup(r.text, 'html.parser')
        blist = soup.find('ul', id='business_list')
        if not blist:
            print("[-] Could not find ul#business_list on viss.lv", flush=True)
            return results
            
        items = blist.find_all('li', recursive=False)
        print(f"  Found {len(items)} listings on viss.lv.", flush=True)
        
        for li in items:
            title_a = li.find('a', href=lambda h: h and h.startswith('/?p='))
            if not title_a:
                continue
                
            raw_title = title_a.get('title', '')
            if not raw_title:
                t_div = title_a.find('div')
                raw_title = t_div.get_text(strip=True) if t_div else title_a.get_text(strip=True)
                
            comp_name = clean_company_name(raw_title)
            if is_blacklisted_company(comp_name):
                continue
                
            addr_tag = li.find('address')
            address = addr_tag.get_text(" ", strip=True) if addr_tag else ""
            
            tel_a = li.find('a', href=lambda h: h and h.startswith('tel:'))
            phone = clean_phone(tel_a.get_text(strip=True) if tel_a else "")
            
            mail_a = li.find('a', href=lambda h: h and h.startswith('mailto:'))
            raw_email = mail_a['href'].replace('mailto:', '').split('?')[0].strip() if mail_a else ""
            email = clean_email(raw_email) or ""
            
            detail_url = f"https://viss.lv{title_a['href']}"
            
            website = ""
            if email and '@' in email:
                dom = email.partition('@')[2]
                if dom not in FREE_WEBMAILS and dom not in JUNK_DOMAINS:
                    website = f"https://www.{dom}"
                    
            item = {
                'Công ty': comp_name,
                'Chức danh': 'Personāla atlase',
                'Người liên hệ': '',
                'SĐT': phone,
                'Liên Hệ': website,
                'Email': email,
                'Liên Hệ mail': detail_url if email else '',
                'Địa chỉ': address,
                'Category': 'Personāla atlase',
                'Source': 'viss.lv',
                'Profile_URL': detail_url
            }
            results.append(item)
            print(f"    + [viss.lv] {comp_name:<32} | Phone: {phone:<18} | Email: {email:<25} | Web: {website}", flush=True)
    except Exception as e:
        print(f"[!] Error scraping viss.lv: {e}", flush=True)
        
    return results

# -------------------------------------------------------------
# PHASE 3: Deduplicate and Merge Raw Data
# -------------------------------------------------------------
def deduplicate_raw_companies(all_records):
    print("\n[*] Deduplicating records across 1188.lv and viss.lv...", flush=True)
    unique_dict = {}
    
    def norm_key(name):
        n = unicodedata.normalize('NFKD', str(name)).lower()
        n = ''.join(c for c in n if not unicodedata.combining(c))
        n = re.sub(r'[^a-z0-9]', '', n)
        for lf in ['sia', 'as', 'ik', 'biedriba', 'latvija', 'personalaatlase']:
            n = n.replace(lf, '')
        return n.strip()
        
    for r in all_records:
        k = norm_key(r['Công ty'])
        if not k:
            continue
            
        if k not in unique_dict:
            unique_dict[k] = dict(r)
        else:
            exist = unique_dict[k]
            if not exist.get('SĐT') and r.get('SĐT'):
                exist['SĐT'] = r['SĐT']
            if not exist.get('Email') and r.get('Email'):
                exist['Email'] = r['Email']
                exist['Liên Hệ mail'] = r.get('Liên Hệ mail', '')
            if not exist.get('Liên Hệ') and r.get('Liên Hệ'):
                exist['Liên Hệ'] = r['Liên Hệ']
            if not exist.get('Địa chỉ') and r.get('Địa chỉ'):
                exist['Địa chỉ'] = r['Địa chỉ']
            exist['Source'] = f"{exist.get('Source', '')} + {r.get('Source', '')}"
            
    deduped = list(unique_dict.values())
    print(f"[+] Total raw records: {len(all_records)} -> Unique companies: {len(deduped)}", flush=True)
    return deduped

# -------------------------------------------------------------
# PHASE 4: Deep Website Email Crawl
# -------------------------------------------------------------
def crawl_website_for_b2b_email(session, base_url, comp_name=""):
    if not base_url or not base_url.startswith('http'):
        return None, None
        
    parsed = urllib.parse.urlparse(base_url)
    base_netloc = parsed.netloc.lower()
    clean_domain = base_netloc[4:] if base_netloc.startswith('www.') else base_netloc
    
    found_emails = set()
    source_url = base_url
    
    try:
        r = session.get(base_url, headers=HEADERS, timeout=8, verify=False)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            for a in soup.find_all('a', href=re.compile(r'^mailto:', re.I)):
                ce = clean_email(a['href'][7:].split('?')[0].strip())
                if ce: found_emails.add(ce)
            for m in re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', r.text):
                ce = clean_email(m)
                if ce: found_emails.add(ce)
                
            dom_links = []
            for a in soup.find_all('a', href=True):
                href = a['href'].strip()
                txt = a.get_text(strip=True).lower()
                if any(k in txt or k in href.lower() for k in LATVIAN_MENU_KEYWORDS):
                    full = urllib.parse.urljoin(base_url, href)
                    p_sub = urllib.parse.urlparse(full)
                    if p_sub.netloc.lower() == base_netloc and full != base_url:
                        dom_links.append(full)
                        
            targets = list(dict.fromkeys(dom_links))[:4]
            if len(targets) < 2:
                for fb in LATVIAN_SUBPATHS:
                    targets.append(urllib.parse.urljoin(base_url, fb))
                    
            for sub in list(dict.fromkeys(targets))[:4]:
                try:
                    r_sub = session.get(sub, headers=HEADERS, timeout=6, verify=False)
                    if r_sub.status_code == 200:
                        s_sub = BeautifulSoup(r_sub.text, 'html.parser')
                        for a in s_sub.find_all('a', href=re.compile(r'^mailto:', re.I)):
                            ce = clean_email(a['href'][7:].split('?')[0].strip())
                            if ce:
                                found_emails.add(ce)
                                source_url = sub
                        for m in re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', r_sub.text):
                            ce = clean_email(m)
                            if ce:
                                found_emails.add(ce)
                                source_url = sub
                except Exception:
                    pass
    except Exception:
        pass
        
    if not found_emails:
        return None, None
        
    scored = sorted(list(found_emails), key=lambda x: score_email_b2b(x, clean_domain), reverse=True)
    return scored[0], source_url

# -------------------------------------------------------------
# PHASE 5: Pipeline Orchestration & File Export
# -------------------------------------------------------------
def run_pipeline():
    print("=================================================================", flush=True)
    print("   LATVIA LABOUR AGENCY & RECRUITMENT DATA HARVESTING PIPELINE", flush=True)
    print(f"   Outputs: 0RAW -> 1ENR -> 2COL", flush=True)
    print("=================================================================\n", flush=True)
    
    session = requests.Session(impersonate="chrome124")
    
    # 1. Scrape 1188.lv
    results_1380 = scrape_1188_category(session, "https://www.1188.lv/en/catalog/personnel-selection-1380", "Personnel selection")
    results_6282 = scrape_1188_category(session, "https://www.1188.lv/en/catalog/public-employment-service-6282", "Public employment service")
    
    # 2. Scrape viss.lv
    results_viss = scrape_viss_category(session, "https://viss.lv/katalogs/personala_atlase/latvija/")
    
    all_raw = results_1380 + results_6282 + results_viss
    print(f"\n[+] Total listings harvested: {len(all_raw)}", flush=True)
    
    # 3. Deduplicate
    unique_companies = deduplicate_raw_companies(all_raw)
    
    # Export LV_AGCY_WEBD_0RAW.csv
    with open(OUTPUT_0RAW, 'w', encoding='utf-8-sig', newline='') as f:
        fieldnames = list(unique_companies[0].keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(unique_companies)
    print(f"[+] Saved RAW Dataset: {OUTPUT_0RAW} ({len(unique_companies)} companies)\n", flush=True)
    
    # 4. Deep Enrich Websites for Missing Emails
    print("=================================================================", flush=True)
    print("   DEEP ENRICHMENT VIA OFFICIAL WEBSITES & CACHE", flush=True)
    print("=================================================================", flush=True)
    cache = load_cache()
    enriched_companies = []
    
    for idx, comp in enumerate(unique_companies, start=1):
        c_name = comp['Công ty']
        current_email = comp.get('Email', '').strip()
        current_web = comp.get('Liên Hệ', '').strip()
        
        # Deduce website from email domain if website missing
        if not current_web and current_email and '@' in current_email:
            dom = current_email.partition('@')[2].lower()
            if dom not in FREE_WEBMAILS and dom not in JUNK_DOMAINS:
                current_web = f"https://www.{dom}"
                comp['Liên Hệ'] = current_web
                
        print(f"[{idx}/{len(unique_companies)}] {c_name}", flush=True)
        
        if current_email:
            print(f"  -> Existing Direct Email: {current_email} (Web: {current_web or 'None'})", flush=True)
            enriched_companies.append(comp)
            continue
            
        if not current_web:
            print(f"  [-] No website available to crawl.", flush=True)
            enriched_companies.append(comp)
            continue
            
        cached = cache.get(current_web)
        if cached:
            c_mail = cached.get('email')
            c_src = cached.get('source_url', '')
            print(f"  -> Cache Hit: {c_mail}", flush=True)
            if c_mail:
                comp['Email'] = c_mail
                comp['Liên Hệ mail'] = c_src
            enriched_companies.append(comp)
            continue
            
        print(f"  -> Deep crawling website: {current_web}...", flush=True)
        best_mail, mail_src = crawl_website_for_b2b_email(session, current_web, c_name)
        if best_mail:
            print(f"  ==> [SUCCESS] Found B2B Email: {best_mail} (from {mail_src})", flush=True)
            comp['Email'] = best_mail
            comp['Liên Hệ mail'] = mail_src
        else:
            print(f"  [-] No email found on website.", flush=True)
            
        cache[current_web] = {
            'email': best_mail or '',
            'source_url': mail_src or '',
            'timestamp': time.time()
        }
        save_cache(cache)
        enriched_companies.append(comp)
        
    # Export LV_AGCY_WEBD_1ENR.csv
    with open(OUTPUT_1ENR, 'w', encoding='utf-8-sig', newline='') as f:
        fieldnames = list(enriched_companies[0].keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(enriched_companies)
    print(f"\n[+] Saved 1ENR Dataset: {OUTPUT_1ENR} ({len(enriched_companies)} companies)", flush=True)
    
    # 5. Export Final LV_AGCY_WEBD_2COL.csv
    print("\n=================================================================", flush=True)
    print("   CONSOLIDATING FINAL 2COL COLD MAIL DATASET", flush=True)
    print("=================================================================", flush=True)
    
    formatted_rows = []
    for r in enriched_companies:
        row_2col = {col: '' for col in COLUMNS_2COL}
        row_2col['Công ty'] = r.get('Công ty', '')
        row_2col['Chức danh'] = r.get('Chức danh', 'Agency / Recruiter')
        row_2col['Người liên hệ'] = r.get('Người liên hệ', '')
        row_2col['SĐT'] = clean_phone(r.get('SĐT', ''))
        row_2col['Liên Hệ'] = r.get('Liên Hệ', '')
        row_2col['Email'] = r.get('Email', '')
        row_2col['Liên Hệ mail'] = r.get('Liên Hệ mail', '')
        row_2col['Địa chỉ'] = r.get('Địa chỉ', '')
        row_2col['Category'] = r.get('Category', 'Labour Agency')
        formatted_rows.append(row_2col)
        
    # Sort: Companies WITH EMAIL strictly on TOP
    with_email = [r for r in formatted_rows if r.get('Email', '').strip()]
    without_email = [r for r in formatted_rows if not r.get('Email', '').strip()]
    final_2col = with_email + without_email
    
    for idx, r in enumerate(final_2col, start=1):
        r['No.'] = str(idx)
        
    with open(OUTPUT_2COL, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS_2COL)
        writer.writeheader()
        writer.writerows(final_2col)
        
    print(f"[+] Saved Final Cold Mail Dataset: {OUTPUT_2COL}", flush=True)
    print(f"    - Total Companies: {len(final_2col)}", flush=True)
    print(f"    - WITH EMAIL (Ranked #1 - #{len(with_email)}): {len(with_email)}", flush=True)
    print(f"    - Without Email: {len(without_email)}", flush=True)
    print("=================================================================\n", flush=True)

if __name__ == '__main__':
    run_pipeline()
