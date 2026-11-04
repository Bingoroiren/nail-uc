# -*- coding: utf-8 -*-
"""
GOOGLE MAPS & WEB EMAIL ENRICHMENT - BELGIUM CONSTRUCTION ENTERPRISES (KBO)
==========================================================================
Kế thừa & Tuân thủ đầy đủ 100% các Skill:
- enrich-maps (.agents/skills/enrich-maps/SKILL.md)
- scrape-maps (.agents/skills/scrape-maps/SKILL.md)
- crawl-mail (.agents/skills/crawl-mail/SKILL.md)
- data-standards (.agents/skills/data-standards/SKILL.md)

Các quy chuẩn cốt lõi:
1. Lọc trùng lặp thông minh theo Tên công ty & Mã số KBO trước khi làm giàu Maps:
   - Gom các cơ sở chi nhánh (VE), phân xưởng trùng tên về 1 doanh nghiệp độc nhất.
   - Ưu tiên giữ lại bản ghi Trụ sở chính (ENT RP, ENT NP) và địa chỉ chi tiết nhất.
2. Geolocation Bỉ chuẩn xác (Brussels: 50.8503, 4.3517, locale 'nl-BE') tránh lệch vị trí.
3. Bộ Selectors chuẩn Google Maps kèm nhận diện đóng cửa 'Permanently closed'.
4. Smart & Strict Name Matching: Khử legal forms Bỉ (NV, BV, BVBA, SRL, SPRL, SA, BLDC...), NFKD accents, delimiter.
5. Bóc tách SĐT có nháy đơn '+32... (Rule 2).
6. 3 TẦNG BÓC TÁCH EMAIL B2B:
   - Tầng 1: Kế thừa Email & Web chính thức đã có từ KBO Detail.
   - Tầng 2: Quét trực tiếp Email B2B từ Website KBO.
   - Tầng 3: Tìm kiếm Google Maps để bóc tách thêm Website, Category, Reviews cho doanh nghiệp chưa có liên hệ.
7. Chấm điểm B2B Manpower Agency (score_email_b2b): Ưu tiên hr@, jobs@, praca@, info@, konatel@, loại bỏ mail rác.
8. Checkpoint JSON & Incremental Save mỗi 5 dòng hỗ trợ Resume 100%.
9. Rule 12 Hard Blacklist: Scandi Standard, Biliarta, Daigre.
10. Định dạng đầu ra Cold Mail 20 cột (Rule 10: BE_CNST_GMAP_2COL.csv), đẩy 100% email lên đầu.
"""

import os
import sys
import re
import ssl
import json
import time
import asyncio
import argparse
import urllib.parse
import urllib.request
import unicodedata
from pathlib import Path
import pandas as pd
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

DEFAULT_INPUT_CSV = ROOT_DIR / "BE_CNST_KBO0_0RAW.csv"
OUTPUT_1ENR_CSV = ROOT_DIR / "BE_CNST_GMAP_1ENR.csv"
OUTPUT_2COL_CSV = ROOT_DIR / "BE_CNST_GMAP_2COL.csv"
CACHE_PATH = ROOT_DIR / "crawlmail" / "cache_enrich_maps_be_cnst.json"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'nl-BE,nl;q=0.9,fr-BE;q=0.8,fr;q=0.7,en-US;q=0.6,en;q=0.5',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}

BLACKLIST_DOMAINS = [
    'facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'twitter.com',
    'google.com', 'maps.google.com', 'waze.com', 'apple.com',
    'yellowpages', 'goudengids.be', 'pagesdor.be', 'trendstop.knack.be',
    'infobel.com', 'companyweb.be', 'staatsbladmonitor.be', 'bizbook.be',
    'localservices.be'
]

PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

COL_20_HEADERS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng',
    'Hạn tuyển', 'Check gửi', 'Last Subject', 'Last Body HTML',
    'Trạng thái Reply', 'Lần Follow-up', 'Ngày Follow-up gần nhất',
    'Mailbox đã dùng', 'Category'
]

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

def clean_company_name(name):
    if not name:
        return ""
    n = re.sub(r'\s*\([^)]*\)', '', str(name))
    n = re.sub(r'\s*\[[^\]]*\]', '', n)
    n = re.sub(r'(?i)\b(NV|BV|BVBA|SRL|SPRL|SA|SNC|VOF|CVBA|SCRL|SDIR|BLDC|GmbH)\b', '', n)
    n = unicodedata.normalize('NFKD', n)
    n = ''.join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r'[\/\\:*\?\"<>\|,;.-]', ' ', n)
    return ' '.join(n.split()).strip().lower()

def is_valid_name_match(raw_name, candidate_name):
    c_raw = clean_company_name(raw_name)
    c_cand = clean_company_name(candidate_name)
    if not c_raw or not c_cand:
        return False, "Empty"
    if c_raw == c_cand:
        return True, "Exact"
    if c_raw in c_cand or c_cand in c_raw:
        return True, "Substring"
    tokens_raw = set(c_raw.split())
    tokens_cand = set(c_cand.split())
    intersect = tokens_raw.intersection(tokens_cand)
    if len(tokens_raw) > 0 and len(intersect) / len(tokens_raw) >= 0.6:
        return True, "TokenOverlap"
    return False, "Mismatch"

def clean_phone(phone_str):
    if not phone_str or phone_str == '-':
        return ""
    p = str(phone_str).strip()
    p = re.sub(r'[\s\.\(\)\/\-_]', '', p)
    if p.startswith('0032'):
        p = '+32' + p[4:]
    elif p.startswith('0') and len(p) >= 9:
        p = '+32' + p[1:]
    elif not p.startswith('+') and p.startswith('32'):
        p = '+' + p
    elif not p.startswith('+') and len(p) >= 8:
        p = '+32' + p
    return f"'{p}" if p and not p.startswith("'") else p

def clean_email(email_str):
    if not email_str:
        return ""
    e = urllib.parse.unquote(str(email_str)).strip().lower()
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\ufeff', 'mailto:']:
        e = e.replace(bad, '')
    e = re.sub(r'^[0-9]{2}(?=[a-z])', '', e)
    return e.strip(' .,-_/\\')

def is_junk_email(email):
    if not email or '@' not in email:
        return True
    e = email.lower()
    junk_patterns = [
        'sentry', 'wix', 'wixpress', 'wordpress', 'no-reply', 'donotreply',
        'privacy', 'gdpr', 'example.com', 'domain.com', 'yourcompany.com',
        'someone@', 'john.doe', 'user@domain', 'youremail@', 'yourname@',
        'localservices.be', 'bizbook.be', 'pagesdor.be', 'goudengids.be'
    ]
    if any(p in e for p in junk_patterns):
        return True
    if any(e.endswith(f"@{d}") or f".{d}" in e for d in BLACKLIST_DOMAINS):
        return True
    return False

def score_email_b2b(email, website_domain=""):
    if not email or is_junk_email(email):
        return -100
    e = email.lower()
    score = 0
    clean_domain = ""
    if website_domain:
        clean_domain = re.sub(r'^https?:\/\/', '', website_domain.lower()).split('/')[0].replace('www.', '')

    if clean_domain and clean_domain in e:
        score += 50

    if any(k in e for k in ['praca@', 'kariera@', 'hr@', 'personalne@', 'jobs@', 'recruitment@', 'career@', 'work@']):
        score += 50
    elif any(k in e for k in ['vedenie@', 'riaditel@', 'konatel@', 'ceo@', 'director@', 'manager@', 'obchod@', 'sales@', 'directie@', 'zaakvoerder@']):
        score += 45
    elif any(k in e for k in ['info@', 'kontakt@', 'contact@', 'office@', 'biuro@', 'sekretariat@', 'recepcia@', 'kancelaria@', 'onthaal@', 'administratie@']):
        score += 40
    elif re.match(r'^[a-z]+(\.[a-z]+)?@', e) and ('@gmail' not in e and '@seznam' not in e and '@hotmail' not in e):
        score += 25
    elif any(f"@{w}" in e for w in ['gmail.com', 'telenet.be', 'skynet.be', 'proximus.be', 'outlook.com', 'hotmail.com']):
        score += 10
    elif any(k in e for k in ['support@', 'admin@', 'servis@', 'facturatie@', 'faktury@', 'boekhouding@']):
        score += 5

    return score

def decode_cloudflare_email(cf_hex):
    try:
        r = int(cf_hex[:2], 16)
        email = ''.join([chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
        return email
    except Exception:
        return ""

def crawl_website_emails(website_url):
    if not website_url or any(bad in website_url for bad in BLACKLIST_DOMAINS):
        return []
    base_url = website_url if website_url.startswith('http') else f"https://{website_url}"
    base_url = base_url.rstrip('/')
    parsed_base = urllib.parse.urlparse(base_url)
    domain = parsed_base.netloc.replace('www.', '')

    subpaths = [
        "", "/contact", "/contact-us", "/kontakt", "/contacteer-ons",
        "/over-ons", "/about", "/about-us", "/a-propos", "/qui-sommes-nous",
        "/jobs", "/werken-bij", "/vacatures", "/carriere", "/team",
        "/impressum", "/mentions-legales"
    ]

    all_emails = set()
    for sp in subpaths:
        target_url = base_url + sp
        try:
            req = urllib.request.Request(target_url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=7, context=ctx) as resp:
                raw_html = resp.read().decode('utf-8', errors='ignore')

            for cf in re.findall(r'data-cfemail=["\']([a-f0-9]+)["\']', raw_html, re.I):
                dec = decode_cloudflare_email(cf)
                if dec and '@' in dec:
                    all_emails.add(clean_email(dec))

            soup = BeautifulSoup(raw_html, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = a['href'].strip()
                if href.lower().startswith('mailto:'):
                    m_mail = href[7:].split('?')[0].strip()
                    if m_mail and '@' in m_mail:
                        all_emails.add(clean_email(m_mail))

            for m in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', raw_html):
                all_emails.add(clean_email(m))

            if any(k in e for e in all_emails for k in ['hr@', 'jobs@', 'info@', 'contact@']):
                break

        except Exception:
            continue

    valid_emails = [e for e in all_emails if not is_junk_email(e)]
    valid_emails.sort(key=lambda x: score_email_b2b(x, domain), reverse=True)
    return valid_emails

def deduplicate_companies(raw_records):
    print(f"[*] Đang khử trùng lặp thông minh cho {len(raw_records):,} bản ghi cào thô KBO...")
    groups = {}
    for r in raw_records:
        name = r.get('Company_Name', '').strip()
        postcode = r.get('Postcode', '').strip()
        kbo_num = r.get('KBO_Number', '').strip()

        clean_kbo = re.sub(r'[^0-9]', '', kbo_num)
        if len(clean_kbo) == 10:
            key = f"kbo_{clean_kbo}"
        else:
            c_name = clean_company_name(name)
            key = f"name_{c_name}_{postcode}"

        if key not in groups:
            groups[key] = []
        groups[key].append(r)

    deduped = []
    for key, items in groups.items():
        def priority_score(item):
            score = 0
            ent_type = str(item.get('Type', '')).upper()
            if 'ENT RP' in ent_type or 'ENT NP' in ent_type:
                score += 50
            if item.get('VE_Number') and item.get('VE_Number') != '-':
                score += 10
            if item.get('Email'):
                score += 30
            if item.get('Website'):
                score += 20
            if item.get('Phone'):
                score += 10
            score += len(str(item.get('Address', '')))
            return score

        best_item = max(items, key=priority_score)
        deduped.append(best_item)

    print(f"[+] Khử trùng hoàn tất: {len(raw_records):,} bản ghi thô -> {len(deduped):,} doanh nghiệp độc nhất!")
    return deduped

async def enrich_maps_be_cnst(input_csv, limit=None, headless=False):
    print("=" * 80)
    print("🇧🇪  BẮT ĐẦU LÀM GIÀU DỮ LIỆU GOOGLE MAPS & EMAIL B2B - XÂY DỰNG BỈ (KBO)")
    print(f"    - Nguồn dữ liệu      : {input_csv.name}")
    print(f"    - Chế độ trình duyệt : {'Ẩn danh (headless=True)' if headless else 'Trực quan (headless=False)'}")
    print(f"    - Checkpoint Cache   : {CACHE_PATH.name}")
    print(f"    - Đầu ra Cold Mail   : {OUTPUT_2COL_CSV.name} (Rule 10: 17 ký tự)")
    print("=" * 80)

    if not input_csv.exists():
        print(f"[!] Không tìm thấy tệp {input_csv.name}!")
        return

    df_raw = pd.read_csv(input_csv, dtype=str).fillna('')
    raw_records = df_raw.to_dict('records')

    unique_companies = deduplicate_companies(raw_records)
    if limit:
        unique_companies = unique_companies[:limit]

    cache = {}
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Đã nạp checkpoint: {len(cache):,} doanh nghiệp đã xử lý trước đó.")
        except Exception:
            cache = {}

    enriched_rows = []
    records_to_process = [c for c in unique_companies if not is_blacklisted_company(c.get('Company_Name'))]
    print(f"[*] Tổng số doanh nghiệp xây dựng cần làm giàu Maps: {len(records_to_process):,}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
        )
        context_kwargs = {
            'locale': 'nl-BE',
            'geolocation': {'latitude': 50.8503, 'longitude': 4.3517},
            'permissions': ['geolocation'],
            'user_agent': HEADERS['User-Agent']
        }
        if not headless:
            context_kwargs['no_viewport'] = True
        else:
            context_kwargs['viewport'] = {'width': 1280, 'height': 800}

        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()

        count = 0
        for item in records_to_process:
            count += 1
            name = item.get('Company_Name', '').strip()
            address = item.get('Address', '').strip()
            postcode = item.get('Postcode', '').strip()
            kbo_num = item.get('KBO_Number', '').strip()

            clean_kbo = re.sub(r'[^0-9]', '', kbo_num)
            unique_key = f"kbo_{clean_kbo}" if len(clean_kbo) == 10 else f"{name}_{postcode}"

            if unique_key in cache:
                cached_item = cache[unique_key]
                enriched_rows.append(cached_item)
                continue

            query = f"{clean_company_name(name)} {address} Belgium"
            search_url = f"https://www.google.com/maps/search/{urllib.parse.quote(query)}"

            found_name = ""
            found_phone = ""
            found_website = ""
            found_address = ""
            found_cat = ""
            is_closed = False

            try:
                await page.goto(search_url, wait_until='domcontentloaded', timeout=15000)
                await asyncio.sleep(1.0)

                try:
                    consent_btn = await page.query_selector('button[aria-label*="Alle akkoord"], button[aria-label*="Tout accepter"], form[action*="consent"] button')
                    if consent_btn:
                        await consent_btn.click()
                        await asyncio.sleep(0.5)
                except Exception:
                    pass

                title_el = await page.query_selector('h1.DUwDvf')
                if title_el:
                    cand_name = (await title_el.inner_text()).strip()
                    matched, match_type = is_valid_name_match(name, cand_name)
                    if matched:
                        found_name = cand_name
                        phone_el = await page.query_selector('button[data-item-id^="phone:tel:"]')
                        if phone_el:
                            found_phone = (await phone_el.inner_text()).strip()
                        web_el = await page.query_selector('a[data-item-id="authority"]')
                        if web_el:
                            found_website = await web_el.get_attribute('href')
                        addr_el = await page.query_selector('button[data-item-id^="address"]')
                        if addr_el:
                            found_address = (await addr_el.inner_text()).strip()
                        cat_el = await page.query_selector('button.DkEaL')
                        if cat_el:
                            found_cat = (await cat_el.inner_text()).strip()

                        body_txt = await page.inner_text('body')
                        if any(c in body_txt for c in ['Definitief gesloten', 'Fermé définitivement', 'Permanently closed']):
                            is_closed = True

                if not found_name:
                    listings = await page.query_selector_all('a.hfpxzc')
                    for l in listings[:3]:
                        l_name = await l.get_attribute('aria-label')
                        if l_name:
                            matched, match_type = is_valid_name_match(name, l_name)
                            if matched:
                                await l.click()
                                await asyncio.sleep(1.5)
                                t_el = await page.query_selector('h1.DUwDvf')
                                if t_el:
                                    found_name = (await t_el.inner_text()).strip()
                                p_el = await page.query_selector('button[data-item-id^="phone:tel:"]')
                                if p_el:
                                    found_phone = (await p_el.inner_text()).strip()
                                w_el = await page.query_selector('a[data-item-id="authority"]')
                                if w_el:
                                    found_website = await w_el.get_attribute('href')
                                a_el = await page.query_selector('button[data-item-id^="address"]')
                                if a_el:
                                    found_address = (await a_el.inner_text()).strip()
                                c_el = await page.query_selector('button.DkEaL')
                                if c_el:
                                    found_cat = (await c_el.inner_text()).strip()
                                break

            except Exception:
                pass

            kbo_web = item.get('Website', '').strip()
            kbo_mail = item.get('Email', '').strip()
            kbo_phone = item.get('Phone', '').strip()

            clean_web = ""
            if found_website:
                m = re.search(r'q=([^&]+)', found_website)
                if m:
                    clean_web = urllib.parse.unquote(m.group(1))
                else:
                    clean_web = found_website.split('?')[0].rstrip('/')

            # Kế thừa website từ KBO nếu Google Maps không tìm thấy
            if not clean_web and kbo_web:
                clean_web = kbo_web if kbo_web.startswith('http') else f"https://{kbo_web}"

            # Quét và tuyển chọn 1 email B2B giá trị nhất từ Website & KBO
            candidate_emails = []
            if kbo_mail and not is_junk_email(kbo_mail):
                candidate_emails.append(kbo_mail)

            if clean_web and not any(bad in clean_web for bad in BLACKLIST_DOMAINS):
                crawled = crawl_website_emails(clean_web)
                for em in crawled:
                    if em not in candidate_emails:
                        candidate_emails.append(em)

            best_email = ""
            if candidate_emails:
                scored = sorted(candidate_emails, key=lambda e: score_email_b2b(e, clean_web), reverse=True)
                best_email = clean_email(scored[0])

            final_phone = clean_phone(found_phone) or clean_phone(kbo_phone)
            final_address = found_address if found_address else address

            enriched_row = dict(item)
            enriched_row['Maps_Name'] = found_name
            enriched_row['Phone'] = final_phone
            enriched_row['Website'] = clean_web
            enriched_row['Email'] = best_email
            enriched_row['Maps_Address'] = final_address
            enriched_row['Maps_Category'] = found_cat
            enriched_row['Permanently_Closed'] = 'Yes' if is_closed else 'No'

            cache[unique_key] = enriched_row
            enriched_rows.append(enriched_row)

            status_str = f"SĐT: {final_phone or '-'} | Mail: {best_email or '-'}"
            print(f"  [{count:04d}/{len(records_to_process):04d}] {name[:25]} -> {status_str}", flush=True)

            if count % 5 == 0 or count == len(records_to_process):
                CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
                with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, ensure_ascii=False)
                pd.DataFrame(enriched_rows).to_csv(OUTPUT_1ENR_CSV, index=False, encoding='utf-8-sig')

            await asyncio.sleep(0.5)

        await browser.close()

    df_enr = pd.DataFrame(enriched_rows)
    df_enr.to_csv(OUTPUT_1ENR_CSV, index=False, encoding='utf-8-sig')
    print(f"\n[+] Đã lưu {len(df_enr):,} doanh nghiệp vào {OUTPUT_1ENR_CSV.name}")

    df_active = df_enr[df_enr['Permanently_Closed'] != 'Yes'].copy()
    
    rows_2col = []
    idx = 1
    for _, r in df_active.iterrows():
        c_name = r.get('Company_Name', '').strip()
        phone = clean_phone(r.get('Phone', ''))
        email = clean_email(r.get('Email', ''))
        addr = r.get('Maps_Address') or r.get('Address') or ''
        cat = r.get('Maps_Category') or r.get('Activity') or 'Construction'

        rows_2col.append({
            'No.': idx,
            'Công ty': c_name,
            'Chức danh': '',
            'Người liên hệ': '',
            'SĐT': phone,
            'Liên Hệ': '',
            'Email': email,
            'Liên Hệ mail': '',
            'Địa chỉ': addr,
            'Lương': '',
            'Ngày đăng': '',
            'Hạn tuyển': '',
            'Check gửi': '',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': cat
        })
        idx += 1

    with_email = [r for r in rows_2col if r['Email']]
    without_email = [r for r in rows_2col if not r['Email']]
    sorted_2col = with_email + without_email

    for i, r in enumerate(sorted_2col, 1):
        r['No.'] = i

    df_2col = pd.DataFrame(sorted_2col, columns=COL_20_HEADERS)
    df_2col.to_csv(OUTPUT_2COL_CSV, index=False, encoding='utf-8-sig')

    for extra_dir in [ROOT_DIR / "csdl_mlt", ROOT_DIR / "archive" / "be_belgium"]:
        extra_dir.mkdir(parents=True, exist_ok=True)
        try:
            import shutil
            shutil.copy2(OUTPUT_1ENR_CSV, extra_dir / OUTPUT_1ENR_CSV.name)
            shutil.copy2(OUTPUT_2COL_CSV, extra_dir / OUTPUT_2COL_CSV.name)
        except Exception:
            pass

    print("\n" + "=" * 80)
    print("🏆 HOÀN THÀNH LÀM GIÀU DỮ LIỆU XÂY DỰNG BỈ!")
    print(f"   - File làm giàu chi tiết : {OUTPUT_1ENR_CSV.name}")
    print(f"   - File chuẩn Cold Mail   : {OUTPUT_2COL_CSV.name} ({len(df_2col):,} dòng)")
    print(f"   - Doanh nghiệp có Email  : {len(with_email):,} ({len(with_email)*100/max(1, len(df_2col)):.1f}%)")
    print("=" * 80 + "\n")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Enrich Belgium Construction Enterprises via Google Maps & Web")
    parser.add_argument("--input", default=str(DEFAULT_INPUT_CSV), help="File CSV đầu vào (BE_CNST_KBO0_0RAW.csv)")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số doanh nghiệp")
    parser.add_argument("--headless", action="store_true", help="Chạy ẩn (mặc định hiện trình duyệt)")
    args = parser.parse_args()

    asyncio.run(enrich_maps_be_cnst(Path(args.input), limit=args.limit, headless=args.headless))
