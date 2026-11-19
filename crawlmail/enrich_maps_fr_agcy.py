# -*- coding: utf-8 -*-
"""
BỘ LÀM GIÀU DỮ LIỆU DOANH NGHIỆP PHÁP BẰNG GOOGLE MAPS (ENRICH-MAPS) - BẢN KHẮC PHỤC TRIỆT ĐỂ LỖI CRASH
========================================================================================================
Kỹ năng: .agents/skills/enrich-maps/SKILL.md & data-standards
Input:  FR_AGCY_PJAU_0RAW.csv (560 công ty tuyển dụng & interim Paris từ PagesJaunes)
Output: 
- FR_AGCY_PJAU_1ENR.csv (Làm giàu SĐT, Website, Rating, Maps URL & Email B2B)
- FR_AGCY_PJAU_2COL.csv (Chuẩn Cold Mail, 100% dòng có Email đẩy lên đầu)
- FR_AGCY_PJAU_ONLY_EMAILS_READY.csv (Chỉ các công ty có Email)
"""

import os
import sys
import re
import csv
import json
import time
import asyncio
import urllib.parse
import unicodedata
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent

INPUT_CSV = ROOT_DIR / "FR_AGCY_PJAU_0RAW.csv"
OUT_1ENR = ROOT_DIR / "FR_AGCY_PJAU_1ENR.csv"
OUT_2COL = ROOT_DIR / "FR_AGCY_PJAU_2COL.csv"
OUT_READY = ROOT_DIR / "FR_AGCY_PJAU_ONLY_EMAILS_READY.csv"

CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_enrich_maps_fr_agcy.json"
USER_DATA_DIR = ROOT_DIR / "chrome_user_data" / "fr_maps_enrich_profile"

# Rule 12: Permanent Blacklist
PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

FRENCH_LEGAL_FORMS = [
    r'\bsas\b', r'\bsarl\b', r'\bsa\b', r'\beurl\b', r'\bsasu\b',
    r'\bsnc\b', r'\bselarl\b', r'\bgie\b', r'\bsci\b', r'\bscp\b'
]

DUMMY_EMAIL_PATTERNS = [
    r'example\.com', r'domain\.com', r'yourdomain\.com', r'yoursite\.com',
    r'sentry\.io', r'wixpress\.com', r'wordpress\.org', r'wix\.com',
    r'no-reply', r'donotreply', r'privacy@', r'gdpr@', r'contact@email\.com',
    r'name@email\.com', r'user@', r'someone@', r'john\.doe@',
    r'may4bewith\.you', r'email\.com', r'company\.com', r'vite\.com',
    r'mon\.email', r'^john@', r'johndoe@', r'luke\.skywalker',
    r'delegueprotectiondcp@', r'donnees@', r'rgpd@', r'dpo@', r'u003edpo',
    r'tech@maetva\.com', r'support@pharmao\.fr'
]

IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.bmp', '.pdf', '.js', '.css')

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

def normalize_text(text):
    if not text:
        return ""
    n = unicodedata.normalize('NFKD', str(text)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    for lf in FRENCH_LEGAL_FORMS:
        n_clean = re.sub(lf, '', n_clean, flags=re.I)
    n_clean = re.sub(r'["\'„“”«»]', '', n_clean)
    n_clean = re.sub(r'[\(\[\{\)\}\]]', ' ', n_clean)
    n_clean = re.sub(r'[^\w\s-]', ' ', n_clean)
    return re.sub(r'\s+', ' ', n_clean).strip()

def is_valid_name_match_fr(query_name, candidate_name):
    if not query_name or not candidate_name:
        return False, "EMPTY"
        
    q_norm = normalize_text(query_name)
    c_norm = normalize_text(candidate_name)
    
    if not q_norm or not c_norm:
        return False, "EMPTY_NORM"
        
    if q_norm == c_norm:
        return True, "EXACT"
        
    if q_norm in c_norm or c_norm in q_norm:
        min_len = min(len(q_norm), len(c_norm))
        if min_len >= 5:
            return True, "SUBSTRING"
            
    parts = [p.strip() for p in re.split(r'[-–—|/:,]', c_norm) if p.strip()]
    if any(p == q_norm or q_norm in p for p in parts if len(p) >= 4):
        return True, "DELIMITER"
        
    return False, "NO_MATCH"

def format_french_phone(phone_raw):
    if not phone_raw:
        return ""
    clean = re.sub(r"[^\d+]", "", str(phone_raw).strip())
    if clean.startswith("0") and len(clean) == 10:
        clean = "+33" + clean[1:]
    elif clean.startswith("0033"):
        clean = "+33" + clean[4:]
    elif clean.startswith("33") and len(clean) == 11:
        clean = "+" + clean
    return f"'{clean}" if clean and not clean.startswith("'") else clean

def clean_email(email_str):
    if not email_str:
        return ""
    em = str(email_str).strip()
    em = urllib.parse.unquote(em)
    em = em.replace('\u00a0', '').replace('\xa0', '').replace('&nbsp;', '')
    em = em.replace('%20', '').replace('\u200b', '').replace('\ufeff', '')
    em = re.sub(r'^(?:20)+', '', em)
    em = re.sub(r'^(?:mailto:|u003e)', '', em, flags=re.I).strip()
    em = re.sub(r'\s+', '', em)
    em = em.strip('.,;:/\'"()[]{}')
    if '@' not in em:
        return ""
    em_low = em.lower()
    if any(em_low.endswith(ext) for ext in IMAGE_EXTENSIONS):
        return ""
    parts = em_low.split('@')
    if len(parts) != 2:
        return ""
    user, domain = parts[0], parts[1]
    if re.match(r'^\d+(\.\d+)+$', domain):
        return ""
    d_parts = domain.split('.')
    if len(d_parts) < 2 or not re.match(r'^[a-z]{2,12}$', d_parts[-1]):
        return ""
    if any(re.search(pat, em_low, re.I) for pat in DUMMY_EMAIL_PATTERNS):
        return ""
    if not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', em_low):
        return ""
    return em_low

def score_email_b2b(email, website_domain=""):
    if not email:
        return 0
    score = 0
    em_lower = email.lower()
    user_part = em_lower.split('@')[0] if '@' in em_lower else ''
    mail_domain = em_lower.split('@')[1] if '@' in em_lower else ''
    
    if website_domain and website_domain in mail_domain:
        score += 50
    elif any(f in mail_domain for f in ['gmail.com', 'orange.fr', 'wanadoo.fr', 'free.fr', 'yahoo.fr', 'outlook.fr']):
        score += 10
        
    if any(k in user_part for k in ['recrutement', 'rh', 'recrut', 'emploi', 'candidature', 'jobs', 'careers', 'hr']):
        score += 50
    elif any(k in user_part for k in ['direction', 'dir', 'directeur', 'ceo', 'fondateur', 'gerant', 'responsable', 'commercial']):
        score += 45
    elif any(k in user_part for k in ['contact', 'info', 'accueil', 'agence', 'paris', 'bureau', 'secretariat']):
        score += 40
    elif '.' in user_part:
        score += 25
    else:
        score += 15
        
    return score

def select_best_email(email_list, website_domain=""):
    valid_scored = []
    for em in email_list:
        c = clean_email(em)
        if c:
            s = score_email_b2b(c, website_domain)
            valid_scored.append((s, c))
    if not valid_scored:
        return ""
    valid_scored.sort(key=lambda x: x[0], reverse=True)
    return valid_scored[0][1]

def extract_domain(url):
    if not url:
        return ""
    try:
        p = urllib.parse.urlparse(url)
        netloc = p.netloc or p.path
        netloc = re.sub(r'^www\.', '', netloc).split(':')[0].strip().lower()
        return netloc
    except Exception:
        return ""

def clean_website(url):
    if not url:
        return ""
    u = url.strip()
    bad_domains = [
        "google.com", "gstatic.com", "facebook.com", "instagram.com", 
        "linkedin.com", "twitter.com", "x.com", "pagesjaunes.fr", 
        "yellowpages", "solocal.com", "societe.com", "infogreffe.fr", "verif.com"
    ]
    if any(b in u.lower() for b in bad_domains):
        return ""
    return u

async def handle_google_consent(page):
    try:
        consent_selectors = [
            "button:has-text('Tout accepter')",
            "button:has-text('Accept all')",
            "button:has-text('Alle akzeptieren')",
            "button:has-text('Priнять все')",
            "form[action*='consent'] button"
        ]
        for sel in consent_selectors:
            btn = page.locator(sel)
            if await btn.count() > 0 and await btn.first.is_visible():
                await btn.first.click()
                await asyncio.sleep(1.5)
                return True
    except Exception:
        pass
    return False

async def safe_close_page(p):
    if p:
        try:
            if not p.is_closed():
                await p.close()
        except Exception:
            pass

async def crawl_website_emails(context, base_url):
    if not base_url or not base_url.startswith("http"):
        return ""
    domain = extract_domain(base_url)
    found_emails = set()
    
    page = None
    try:
        page = await context.new_page()
    except Exception:
        return ""

    try:
        resp = await page.goto(base_url, timeout=10000, wait_until="domcontentloaded")
        if not resp or resp.status >= 400:
            await safe_close_page(page)
            return ""
            
        content = await page.content()
        # mailto links
        mailtos = await page.eval_on_selector_all("a[href^='mailto:']", "els => els.map(e => e.getAttribute('href'))")
        for m in mailtos:
            m_clean = re.sub(r'^mailto:', '', m, flags=re.I).split('?')[0].strip()
            c = clean_email(m_clean)
            if c:
                found_emails.add(c)
                
        for em in re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', content):
            c = clean_email(em)
            if c:
                found_emails.add(c)
                
        sub_urls = []
        links = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))")
        for l in links:
            l_lower = l.lower()
            if any(k in l_lower for k in ["contact", "recrut", "rh", "agence", "propos", "mentions"]):
                full = urllib.parse.urljoin(base_url, l)
                if extract_domain(full) == domain and full not in sub_urls and full != base_url:
                    sub_urls.append(full)
                    
        for s_url in sub_urls[:4]:
            try:
                await page.goto(s_url, timeout=8000, wait_until="domcontentloaded")
                s_content = await page.content()
                s_mailtos = await page.eval_on_selector_all("a[href^='mailto:']", "els => els.map(e => e.getAttribute('href'))")
                for m in s_mailtos:
                    m_clean = re.sub(r'^mailto:', '', m, flags=re.I).split('?')[0].strip()
                    c = clean_email(m_clean)
                    if c:
                        found_emails.add(c)
                for em in re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', s_content):
                    c = clean_email(em)
                    if c:
                        found_emails.add(c)
            except Exception:
                continue
    except Exception:
        pass
    finally:
        await safe_close_page(page)
        
    return select_best_email(list(found_emails), domain)

async def search_google_maps_for_company(page, company_name, address):
    try:
        addr_short = re.sub(r'Voir le plan.*', '', address).strip()
        query = f"{company_name} {addr_short} France" if addr_short else f"{company_name} Paris France"
        url = f"https://www.google.com/maps/search/{urllib.parse.quote(query)}?hl=fr"
        
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(2.0)
        await handle_google_consent(page)
        
        # Kiểm tra H1 địa điểm trực tiếp
        h1 = ""
        try:
            h1_el = page.locator("h1.DUwDvf").first
            if await h1_el.count() > 0:
                h1 = (await h1_el.inner_text(timeout=2000)).strip()
        except Exception:
            pass
            
        matched = False
        if h1:
            is_match, match_type = is_valid_name_match_fr(company_name, h1)
            if is_match:
                matched = True
                
        if not matched:
            # Kiểm tra danh sách thẻ kết quả
            try:
                cards = page.locator("a[href*='/maps/place/']")
                count = await cards.count()
                if count > 0:
                    for i in range(min(count, 3)):
                        card = cards.nth(i)
                        label = (await card.get_attribute("aria-label", timeout=2000) or "").strip()
                        is_match, match_type = is_valid_name_match_fr(company_name, label)
                        if is_match:
                            try:
                                await card.click(timeout=3000)
                                await asyncio.sleep(2.0)
                                matched = True
                                break
                            except Exception:
                                pass
            except Exception:
                pass
                
        if not matched:
            return None
            
        category = ""
        try:
            cat_el = page.locator("button.DkEaL").first
            if await cat_el.count() > 0:
                category = (await cat_el.inner_text(timeout=1500)).strip()
        except Exception:
            pass
            
        website = ""
        try:
            web_el = page.locator("a[data-item-id='authority']").first
            if await web_el.count() > 0:
                web_raw = (await web_el.get_attribute("href", timeout=1500) or "").strip()
                website = clean_website(web_raw)
        except Exception:
            pass
            
        phone = ""
        try:
            phone_el = page.locator("button[data-item-id*='phone:tel:'] div.fontBodyMedium").first
            if await phone_el.count() > 0:
                phone_raw = (await phone_el.inner_text(timeout=1500)).strip()
                phone = format_french_phone(phone_raw)
        except Exception:
            pass
            
        rating = ""
        reviews = ""
        try:
            r_el = page.locator("div.F7nice span[aria-hidden='true']").first
            if await r_el.count() > 0:
                rating = (await r_el.inner_text(timeout=1000)).strip().replace(',', '.')
            rev_el = page.locator("div.F7nice span:has-text('(')").first
            if await rev_el.count() > 0:
                rev_text = (await rev_el.inner_text(timeout=1000)).strip()
                rev_m = re.search(r'[\d\s]+', rev_text)
                if rev_m:
                    reviews = rev_m.group(0).replace(' ', '')
        except Exception:
            pass
            
        return {
            "Maps_Name": h1,
            "Maps_Category": category,
            "Maps_Phone": phone,
            "Maps_Website": website,
            "Rating": rating,
            "Reviews": reviews,
            "Google_Maps_URL": page.url
        }
    except Exception as e:
        return None

def save_csv_outputs(enriched_records):
    """Hàm phụ trợ lưu trọn gói 1ENR, 2COL và ONLY_EMAILS_READY an toàn"""
    fieldnames_1enr = [
        "Name", "Activity", "Address", "Postal_Code", "City", "Country",
        "Phone", "Website", "Email", "Rating", "Review_Count", "Google_Maps_URL", "PagesJaunes_URL", "Category_Source"
    ]
    
    fieldnames_20col = [
        "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ", "Email",
        "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển", "Check gửi",
        "Last Subject", "Last Body HTML", "Trạng thái Reply", "Lần Follow-up",
        "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
    ]

    try:
        with open(OUT_1ENR, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fieldnames_1enr)
            w.writeheader()
            w.writerows(enriched_records)
            
        with_email = [r for r in enriched_records if r.get("Email")]
        without_email = [r for r in enriched_records if not r.get("Email")]
        sorted_all = with_email + without_email
        
        col20_rows = []
        for i, r in enumerate(sorted_all, 1):
            row_20 = {
                "No.": str(i),
                "Công ty": r.get("Name", ""),
                "Chức danh": "Directeur / Responsable Recrutement",
                "Người liên hệ": "",
                "SĐT": r.get("Phone", ""),
                "Liên Hệ": r.get("Website", ""),
                "Email": r.get("Email", ""),
                "Liên Hệ mail": f"mailto:{r.get('Email', '')}" if r.get("Email") else "",
                "Địa chỉ": r.get("Address", ""),
                "Lương": "",
                "Ngày đăng": "",
                "Hạn tuyển": "",
                "Check gửi": "Chưa gửi" if r.get("Email") else "",
                "Last Subject": "",
                "Last Body HTML": "",
                "Trạng thái Reply": "",
                "Lần Follow-up": "",
                "Ngày Follow-up gần nhất": "",
                "Mailbox đã dùng": "",
                "Category": r.get("Activity", "") or r.get("Category_Source", "Recrutement & Interim")
            }
            col20_rows.append(row_20)
            
        with open(OUT_2COL, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fieldnames_20col)
            w.writeheader()
            w.writerows(col20_rows)
            
        ready_rows = [r for r in col20_rows if r.get("Email")]
        with open(OUT_READY, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fieldnames_20col)
            w.writeheader()
            w.writerows(ready_rows)
    except Exception as e:
        print(f"[!] Warning save CSV: {e}")

async def main():
    if not INPUT_CSV.exists():
        print(f"[!] Không tìm thấy tệp đầu vào: {INPUT_CSV}")
        return
        
    print("=" * 80)
    print("🚀  LÀM GIÀU DỮ LIỆU GOOGLE MAPS & EMAIL B2B CHO DOANH NGHIỆP PHÁP")
    print(f"    - Tệp đầu vào: {INPUT_CSV.name}")
    print(f"    - Tệp đầu ra 1ENR: {OUT_1ENR.name}")
    print(f"    - Tệp đầu ra 2COL: {OUT_2COL.name}")
    print("=" * 80)
    
    rows = []
    with open(INPUT_CSV, 'r', encoding='utf-8-sig', errors='replace') as f:
        reader = csv.DictReader(f)
        for r in reader:
            if not is_blacklisted_company(r.get("Name", "")):
                rows.append(r)
                
    print(f"[*] Tổng số doanh nghiệp cần làm giàu: {len(rows)}")
    
    cache = {}
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"[*] Nạp Cache đã xử lý từ trước: {len(cache)} doanh nghiệp.")
        except Exception:
            cache = {}
            
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    enriched_records = []
    
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            channel="chrome",
            viewport={"width": 1280, "height": 850},
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = context.pages[0] if context.pages else await context.new_page()
        
        try:
            await page.goto("https://www.google.com/maps?hl=fr", timeout=30000)
            await asyncio.sleep(2)
            await handle_google_consent(page)
        except Exception:
            pass
            
        for idx, row in enumerate(rows, 1):
            name = row.get("Name", "").strip()
            addr = row.get("Address", "").strip()
            pj_phone = row.get("Phone", "").strip()
            pj_web = row.get("Website", "").strip()
            
            cache_key = f"{name}|{addr}"
            cached_data = cache.get(cache_key)
            
            if cached_data:
                enriched_records.append(cached_data)
                continue
                
            try:
                # Kiểm tra kết nối page còn sống không
                if page.is_closed():
                    page = await context.new_page()
                    
                print(f"\n[{idx:03d}/{len(rows):03d}] 🔍 Đang tìm Google Maps: {name[:35]:<35} ...", end=" ", flush=True)
                maps_res = await search_google_maps_for_company(page, name, addr)
                
                final_phone = pj_phone
                final_web = pj_web
                maps_url = ""
                rating = ""
                reviews = ""
                
                if maps_res:
                    print("-> [KHỚP GOOGLE MAPS!]", end=" ")
                    if maps_res.get("Maps_Phone") and not final_phone:
                        final_phone = maps_res["Maps_Phone"]
                    if maps_res.get("Maps_Website") and not final_web:
                        final_web = maps_res["Maps_Website"]
                    maps_url = maps_res.get("Google_Maps_URL", "")
                    rating = maps_res.get("Rating", "")
                    reviews = maps_res.get("Reviews", "")
                else:
                    print("-> [Không khớp Maps, giữ nguyên PJ]", end=" ")
                    
                # Quét Email B2B từ Website
                email = ""
                if final_web:
                    print(f"| Quét Web: {final_web[:30]} ...", end=" ", flush=True)
                    try:
                        email = await crawl_website_emails(context, final_web)
                        print(f"-> Email: {email if email else 'Không có'}", end=" ")
                    except Exception as e_web:
                        print(f"-> Lỗi web: {e_web}", end=" ")
                else:
                    print("| Không có Website", end=" ")
                    
                rec_1enr = {
                    "Name": name,
                    "Activity": row.get("Activity", ""),
                    "Address": addr,
                    "Postal_Code": row.get("Postal_Code", ""),
                    "City": "Paris",
                    "Country": "France",
                    "Phone": format_french_phone(final_phone),
                    "Website": final_web,
                    "Email": email,
                    "Rating": rating,
                    "Review_Count": reviews,
                    "Google_Maps_URL": maps_url,
                    "PagesJaunes_URL": row.get("PagesJaunes_URL", ""),
                    "Category_Source": row.get("Category_Source", "")
                }
                
                cache[cache_key] = rec_1enr
                enriched_records.append(rec_1enr)
                
                # Lưu checkpoint cache sau mỗi dòng
                with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
                    
                # Lưu tăng dần sau mỗi 3 dòng
                if idx % 3 == 0:
                    save_csv_outputs(enriched_records)
                    
            except Exception as e_row:
                print(f"\n[!] Lỗi nhẹ dòng {idx} ({name}): {e_row}. Đang tự động bỏ qua sang dòng tiếp theo...")
                try:
                    if page.is_closed():
                        page = await context.new_page()
                except Exception:
                    pass
                continue
                
        await context.close()
        
    save_csv_outputs(enriched_records)
    
    with_email = [r for r in enriched_records if r.get("Email")]
    print("\n" + "=" * 80)
    print(f"🎉 HOÀN THÀNH LÀM GIÀU DỮ LIỆU GOOGLE MAPS!")
    print(f"    - Tổng số công ty đã xử lý : {len(enriched_records)}")
    print(f"    - Tìm thấy Website chính thức: {sum(1 for r in enriched_records if r.get('Website'))}")
    print(f"    - Bóc tách được Email B2B  : {len(with_email)} ({len(with_email)*100/len(enriched_records) if enriched_records else 0:.1f}%)")
    print(f"    - File 1ENR: {OUT_1ENR.name}")
    print(f"    - File Cold Mail 20 cột: {OUT_2COL.name} (100% có email nằm ở hàng đầu)")
    print(f"    - File Ready to Send: {OUT_READY.name}")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
