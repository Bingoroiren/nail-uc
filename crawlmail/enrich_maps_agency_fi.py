# -*- coding: utf-8 -*-
"""
Hệ thống Làm giàu dữ liệu Agency Tuyển dụng & Cho thuê Nhân sự Phần Lan (ĐÃ TỐI ƯU HÓA TỐC ĐỘ & ĐỘ CHÍNH XÁC):
1. Tra cứu Google Maps (hl=fi, headless=False) với bộ lọc tên nghiêm ngặt cho Phần Lan.
2. Fallback sang Bing / DuckDuckGo nếu Maps không có kết quả hoặc không có website (có nhận diện Captcha).
3. Cào Website để tìm Email, SĐT và link Facebook (xử lý triệt để mã %20 và mailto).
4. Nếu Website không có Email, cào tiếp Fanpage Facebook để tìm Email.
5. Tối ưu:
   - Domain Cache & FB Cache: tránh cào lại cùng 1 trang web/fanpage nhiều lần (cho các agency nhiều chi nhánh như Barona, Eezy, SOL...).
   - Nhận diện trang liên hệ chuẩn Phần Lan (/yhteystiedot/, /ota-yhteytta/...) loại trừ các link báo cáo tài chính/informaatio.
   - Ưu tiên cào Web trước nếu đã có sẵn website từ Finder.fi giúp tăng tốc gấp 5 lần.
   - Lưu động 100%, bảo toàn dữ liệu khi bấm Ctrl+C, chống lỗi PermissionError khi mở Excel.
"""

import asyncio
import csv
import json
import os
import re
import sys
import urllib.parse
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession
from playwright.async_api import async_playwright
import openpyxl

# Set Windows Proactor Event Loop Policy
if sys.platform == 'win32':
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_CSV = os.path.join(BASE_DIR, "agency phần lan (đã lọc trùng).csv")
OUTPUT_CSV = os.path.join(BASE_DIR, "agency phần lan (đã lọc trùng).csv")
OUTPUT_XLSX = os.path.join(BASE_DIR, "agency phần lan.xlsx")
CACHE_FILE = os.path.join(BASE_DIR, "crawlmail", "cache_maps_enrich_agency_fi.json")

LEGAL_FORMS_FI = [
    'oy', 'ab', 'oyj', 'ky', 'ay', 'tmi', 'osk', 'ry', 'ltd'
]

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,7}\b')
INVALID_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf', '.css', '.js', '.ico', '.woff', '.woff2', '.mp4', '.mp3', '.ttf')
IGNORE_DOMAINS = {
    'sentry.io', 'wixpress.com', 'example.com', 'domain.com', 'schema.org', 
    'wordpress.org', 'cloudflare.com', 'google.com', 'facebook.com', 'w3.org', 
    'jsdelivr.net', 'bootstrapcdn.com', 'website.com', 'yourdomain.com', 'fb.com', 'email.fi'
}
DUMMY_EMAILS = {'user@website.com', 'name@domain.com', 'email@domain.com', 'info@domain.com', 'contact@domain.com', 'esimerkki@email.fi', 'etunimi.sukunimi@eezy.fi'}

EXCLUDED_SEARCH_DOMAINS_FI = {
    'finder.fi', 'kauppalehti.fi', 'asiakastieto.fi', 'yritystele.fi', 'proff.fi', 
    'fonecta.fi', 'suomi.fi', 'duunitori.fi', 'oikotie.fi', 'monster.fi', 'jobly.fi', 
    'tori.fi', 'yritysopas.fi', 'yrityshaku.fi', 'wikipedia.org', 'facebook.com', 
    'linkedin.com', 'instagram.com', 'youtube.com', 'google.com', 'google.fi', 
    'eniro.fi', 'tivi.fi', 'talouselama.fi', 'leadfeeder.com', 'is.fi', 'hs.fi', 'yle.fi'
}
DIRECTORY_KEYWORDS_FI = {'directory', 'yellowpages', 'yrityshaku', 'rekry', 'tyopaikat', 'duunit', 'katalog', 'listing', 'yritykset'}

# Caches in-memory to prevent re-scraping identical parent domains/Facebook pages
DOMAIN_CACHE = {}
FB_CACHE = {}

def clean_company_name_fi(name):
    if not name:
        return ""
    n = re.sub(r'["\'„“”«»]', '', name).strip().lower()
    tokens = n.split()
    tokens = [t for t in tokens if t not in LEGAL_FORMS_FI]
    return ' '.join(tokens).strip()

def is_valid_name_match_fi(query_name, candidate_name):
    q = clean_company_name_fi(query_name)
    c = re.sub(r'["\'„“”«»]', '', candidate_name).strip().lower()
    c_clean = clean_company_name_fi(candidate_name)
    
    if not q or not c_clean:
        return False, "EMPTY"

    if q == c_clean:
        return True, "EXACT"
        
    c_without_brackets = re.sub(r'\(.*?\)|\[.*?\]', '', c).strip()
    c_without_brackets_clean = clean_company_name_fi(c_without_brackets)
    if q == c_without_brackets_clean:
        return True, "BRACKET_MATCH"
        
    parts = re.split(r'[-–—,.:|/]', c)
    parts_clean = [clean_company_name_fi(p) for p in parts if p.strip()]
    if any(p == q for p in parts_clean):
        return True, "SEPARATOR_MATCH"
        
    return False, "NO_MATCH"

def decode_cloudflare_email(hex_str):
    try:
        hex_data = bytes.fromhex(hex_str)
        key = hex_data[0]
        return ''.join(chr(b ^ key) for b in hex_data[1:])
    except Exception:
        return ""

def clean_email(email_str):
    if not email_str:
        return ""
    em = urllib.parse.unquote(email_str).replace('%20', '').strip().lower().rstrip('.,;:')
    if any(em.endswith(ext) for ext in INVALID_EXTENSIONS):
        return ""
    if em in DUMMY_EMAILS:
        return ""
    domain = em.split('@')[-1]
    if domain in IGNORE_DOMAINS or domain.endswith('.invalid'):
        return ""
    if len(em) < 6 or '@' not in em:
        return ""
    return em

def extract_emails_from_html(html):
    if not html:
        return set()
    found = set()
    
    # 1. Cloudflare emails
    for cf in re.findall(r'data-cfemail="([0-9a-fA-F]+)"', html):
        dec = decode_cloudflare_email(cf)
        em = clean_email(dec)
        if em:
            found.add(em)
            
    # 2. mailto: links (xử lý cả %20)
    for mailto in re.findall(r'mailto:([^\s"\'<>]+)', html, re.IGNORECASE):
        cleaned_m = mailto.split('?')[0]
        for sub_em in re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}', urllib.parse.unquote(cleaned_m)):
            em = clean_email(sub_em)
            if em:
                found.add(em)
                
    # 3. Plain text regex
    for match in EMAIL_REGEX.findall(html):
        em = clean_email(match)
        if em:
            found.add(em)
            
    return found

def extract_facebook_url(html):
    if not html:
        return ""
    for match in re.findall(r'https?://(?:www\.)?facebook\.com/(?:[a-zA-Z0-9.\-_]+)', html, re.IGNORECASE):
        m_lower = match.lower()
        if not any(x in m_lower for x in ['/sharer', '/share.php', '/tr', '/dialog', '/plugins', '/hashtag', '/pages']):
            m_clean = urllib.parse.unquote(match).split('?')[0].rstrip('/')
            if len(m_clean.split('/')[-1]) > 2:
                return m_clean
    return ""

def score_email(email, domain):
    score = 0
    clean_domain = domain.lower().replace('www.', '')
    if clean_domain and clean_domain in email:
        score += 50
    pfx = email.split('@')[0].lower()
    if pfx in ['info', 'rekry', 'rekrytointi', 'asiakaspalvelu', 'toimisto', 'myynti', 'hakemukset', 'contact']:
        score += 30
    elif any(pfx.startswith(x) for x in ['info', 'rekry', 'sales', 'contact', 'ura']):
        score += 20
    return score

def prioritize_emails(emails_set, domain=""):
    if not emails_set:
        return ""
    sorted_emails = sorted(list(emails_set), key=lambda e: score_email(e, domain), reverse=True)
    return "; ".join(sorted_emails)

async def check_for_captcha(page, platform_name="Google"):
    url = page.url.lower()
    content = ""
    try:
        content = await page.content()
        content_lower = content.lower()
    except Exception:
        content_lower = ""
        
    is_blocked = False
    if "sorry/index" in url or "google.com/sorry" in url:
        is_blocked = True
    elif "unusual traffic" in content_lower or "recaptcha" in content_lower and "g-recaptcha" in content_lower:
        is_blocked = True
    elif "detected unusual traffic" in content_lower:
        is_blocked = True

    if is_blocked:
        print("\n" + "!" * 75, flush=True)
        print(f" [CẢNH BÁO BOT] {platform_name} phát hiện hoạt động bất thường / Yêu cầu Captcha!", flush=True)
        print(" Trình duyệt Chrome đang mở sẵn (headless=False) trên màn hình của bạn.", flush=True)
        print(" Vui lòng thao tác giải Captcha trên cửa sổ trình duyệt.", flush=True)
        print(" Sau khi hoàn tất, quay lại đây nhấn phím [ENTER] để tiếp tục cào...", flush=True)
        print("!" * 75 + "\n", flush=True)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, input, ">> Nhấn [ENTER] khi bạn đã giải quyết Captcha: ")
        await asyncio.sleep(2)
        return True
    return False

async def search_google_maps_fi(page, company_name):
    """
    Tra cứu Google Maps với ngôn ngữ Phần Lan (hl=fi)
    """
    q_clean = clean_company_name_fi(company_name)
    query = f"{q_clean} Suomi"
    url = f"https://www.google.com/maps/search/{urllib.parse.quote(query)}?hl=fi"
    
    res = {
        "tag_maps": "",
        "phone": "",
        "website": "",
        "address": "",
        "maps_title": "",
        "matched": False,
        "match_reason": ""
    }
    
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=18000)
        # Chờ ngắn xem có kết quả hoặc cookie banner
        await asyncio.sleep(2)
        await check_for_captcha(page, "Google Maps")
        
        # Handle Cookie consent Phần Lan
        try:
            btn = page.locator('button[aria-label*="Hyväksy"], button[aria-label*="Hylkää"], button[aria-label*="Accept"], form[action*="consent"] button')
            if await btn.count() > 0:
                await btn.first.click()
                await asyncio.sleep(1)
        except Exception:
            pass
            
        # Case A: Direct Detail View
        title_elem = page.locator('h1.DUwDvf, h1[class*="fontHeadlineLarge"]')
        if await title_elem.count() > 0:
            title = await title_elem.first.text_content()
            matched, reason = is_valid_name_match_fi(q_clean, title or "")
            if matched:
                res["matched"] = True
                res["match_reason"] = reason
                res["maps_title"] = title.strip()
                
                cat_elem = page.locator('button.DkEaL, button[jsaction*="category"], span.DkEaL')
                if await cat_elem.count() > 0:
                    res["tag_maps"] = (await cat_elem.first.text_content()).strip()
                    
                phone_elem = page.locator('button[data-item-id*="phone"]')
                if await phone_elem.count() > 0:
                    raw_ph = await phone_elem.first.text_content()
                    clean_p = re.sub(r'[\ue000-\uf8ff]', '', raw_ph)
                    res["phone"] = re.sub(r'[^\d+ ]', '', clean_p).strip()
                    
                web_elem = page.locator('a[data-item-id="authority"]')
                if await web_elem.count() > 0:
                    res["website"] = (await web_elem.first.get_attribute("href") or "").strip()
                    
                addr_elem = page.locator('button[data-item-id="address"]')
                if await addr_elem.count() > 0:
                    raw_addr = await addr_elem.first.text_content()
                    clean_a = re.sub(r'[\ue000-\uf8ff]', '', raw_addr)
                    res["address"] = clean_a.strip()
                return res

        # Case B: List of Results
        cards = page.locator('a.hfpxzc')
        card_count = await cards.count()
        if card_count > 0:
            for i in range(min(card_count, 3)):
                card_title = await cards.nth(i).get_attribute('aria-label')
                matched, reason = is_valid_name_match_fi(q_clean, card_title or "")
                if matched:
                    res["matched"] = True
                    res["match_reason"] = reason
                    res["maps_title"] = card_title.strip()
                    
                    await cards.nth(i).click()
                    await asyncio.sleep(2)
                    
                    cat_elem = page.locator('button.DkEaL, button[jsaction*="category"], span.DkEaL')
                    if await cat_elem.count() > 0:
                        res["tag_maps"] = (await cat_elem.first.text_content()).strip()
                        
                    phone_elem = page.locator('button[data-item-id*="phone"]')
                    if await phone_elem.count() > 0:
                        raw_ph = await phone_elem.first.text_content()
                        clean_p = re.sub(r'[\ue000-\uf8ff]', '', raw_ph)
                        res["phone"] = re.sub(r'[^\d+ ]', '', clean_p).strip()
                        
                    web_elem = page.locator('a[data-item-id="authority"]')
                    if await web_elem.count() > 0:
                        res["website"] = (await web_elem.first.get_attribute("href") or "").strip()
                        
                    addr_elem = page.locator('button[data-item-id="address"]')
                    if await addr_elem.count() > 0:
                        raw_addr = await addr_elem.first.text_content()
                        clean_a = re.sub(r'[\ue000-\uf8ff]', '', raw_addr)
                        res["address"] = clean_a.strip()
                    return res
    except Exception:
        pass
        
    return res

def is_valid_company_domain_fi(domain, query_clean):
    d = domain.lower()
    if any(ex in d for ex in EXCLUDED_SEARCH_DOMAINS_FI):
        return False
    if any(kw in d for kw in DIRECTORY_KEYWORDS_FI):
        return False
    tokens = [t for t in query_clean.split() if len(t) > 3]
    if tokens:
        if any(t in d for t in tokens):
            return True
        clean_q_nospace = query_clean.replace(' ', '')
        if clean_q_nospace in d:
            return True
    return False

async def fallback_search_website_fi(http_session, company_name):
    """
    Fallback tìm kiếm website qua Bing / DuckDuckGo nếu Maps không có website
    """
    q_clean = clean_company_name_fi(company_name)
    query = f'"{q_clean}" Suomi yhteystiedot'
    
    # 1. Bing Search
    try:
        b_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
        res = await http_session.get(b_url, timeout=7)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            for li in soup.find_all('li', class_='b_algo'):
                cite = li.find('cite')
                h2 = li.find('h2')
                if cite:
                    cite_text = cite.get_text(strip=True)
                    match = re.search(r'https?://[^\s›/]+', cite_text)
                    if match:
                        found_url = match.group(0)
                        domain = urllib.parse.urlparse(found_url).netloc.lower().replace('www.', '')
                        if is_valid_company_domain_fi(domain, q_clean):
                            return f"https://{domain}"
                        t_text = h2.get_text(strip=True) if h2 else ""
                        matched, _ = is_valid_name_match_fi(q_clean, t_text)
                        if matched and not any(kw in domain for kw in DIRECTORY_KEYWORDS_FI):
                            return f"https://{domain}"
    except Exception:
        pass

    # 2. DuckDuckGo HTML
    try:
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        res = await http_session.get(url, timeout=7)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            for a in soup.find_all('a', class_='result__url'):
                href = a.get('href', '')
                text = a.get_text(strip=True).lower()
                parsed = urllib.parse.urlparse(href if href.startswith('http') else 'https://' + text)
                domain = parsed.netloc.lower().replace('www.', '')
                if is_valid_company_domain_fi(domain, q_clean):
                    return f"https://{domain}"
    except Exception:
        pass

    return ""

async def scrape_website_details_fi(http_session, raw_url):
    """
    Quét trang web tối ưu: Có Domain Cache, phát hiện chuẩn trang liên hệ Phần Lan, xử lý %20
    """
    url = urllib.parse.unquote(raw_url.strip())
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
        
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower().replace('www.', '')
    
    # 1. Kiểm tra Domain Cache trước
    if domain in DOMAIN_CACHE:
        return DOMAIN_CACHE[domain]
        
    collected_emails = set()
    collected_phones = []
    fb_url = ""
    phone_regex = re.compile(r'(?:\+358\s?|0)[1-9]\d{1,2}[\s-]?\d{3,4}[\s-]?\d{2,4}')
    
    # 2. Quét trang chủ
    homepage_html = ""
    try:
        res = await http_session.get(url, timeout=7, allow_redirects=True)
        if res.status_code == 200:
            homepage_html = res.text
            collected_emails.update(extract_emails_from_html(homepage_html))
            fb_url = extract_facebook_url(homepage_html)
            for ph in phone_regex.findall(homepage_html):
                if len(re.sub(r'\D', '', ph)) >= 8:
                    collected_phones.append(ph.strip())
    except Exception:
        if url.startswith('https://'):
            try:
                res = await http_session.get('http://' + url[8:], timeout=7, allow_redirects=True)
                if res.status_code == 200:
                    homepage_html = res.text
                    collected_emails.update(extract_emails_from_html(homepage_html))
                    fb_url = extract_facebook_url(homepage_html)
                    for ph in phone_regex.findall(homepage_html):
                        if len(re.sub(r'\D', '', ph)) >= 8:
                            collected_phones.append(ph.strip())
            except Exception:
                pass

    # 3. Tìm các trang liên hệ chuẩn
    contact_urls = []
    
    # A. Danh sách các đường dẫn ưu tiên cao của website Phần Lan
    priority_slugs = ['/yhteystiedot/', '/yhteystiedot', '/yhteys/', '/yhteys', '/ota-yhteytta/', '/ota-yhteytta', '/contact/', '/contact']
    for slug in priority_slugs[:4]:
        contact_urls.append(urllib.parse.urljoin(url, slug))
        
    # B. Quét thẻ <a> trên trang chủ tìm trang liên hệ
    if homepage_html:
        soup = BeautifulSoup(homepage_html, 'html.parser')
        keywords_text = ['ota yhteyt', 'yhteystiedot', 'yhteys', 'asiakaspalvelu', 'rekrytoijat', 'tiimi', 'contact']
        keywords_href = ['/yhteystiedot', '/yhteys', '/ota-yhteytta', '/contact', '/tiimi']
        
        for a in soup.find_all('a', href=True):
            href = urllib.parse.unquote(a['href'].strip())
            txt = a.get_text(strip=True).lower()
            href_l = href.lower()
            
            # Loại bỏ anchor hoặc các file tải về
            if href.startswith('#') or any(href_l.endswith(ext) for ext in ['.pdf', '.jpg', '.png', '.zip']):
                continue
            # Loại bỏ các trang báo cáo tài chính/informaatio/blog
            if any(bad in href_l for bad in ['informaatio', 'sijoittaj', 'raport', 'taloustiet', 'blog/']):
                continue
                
            is_match = any(k in txt for k in keywords_text) or any(k in href_l for k in keywords_href)
            if is_match:
                full_u = urllib.parse.urljoin(url, href)
                if full_u not in contact_urls and full_u != url:
                    contact_urls.append(full_u)
                    if len(contact_urls) >= 5:
                        break

    # 4. Quét tối đa 3 trang liên hệ tốt nhất
    for cu in contact_urls[:3]:
        try:
            c_res = await http_session.get(cu, timeout=6, allow_redirects=True)
            if c_res.status_code == 200:
                collected_emails.update(extract_emails_from_html(c_res.text))
                for ph in phone_regex.findall(c_res.text):
                    if len(re.sub(r'\D', '', ph)) >= 8:
                        collected_phones.append(ph.strip())
                if not fb_url:
                    fb_url = extract_facebook_url(c_res.text)
        except Exception:
            continue

    emails_str = prioritize_emails(collected_emails, domain)
    phone_str = collected_phones[0] if collected_phones else ""
    DOMAIN_CACHE[domain] = (emails_str, phone_str, fb_url)
    return emails_str, phone_str, fb_url

async def scrape_facebook_email_fi(page, fb_url):
    """
    Quét Fanpage Facebook với FB_CACHE và timeout nhanh
    """
    if not fb_url:
        return ""
    clean_fb = fb_url.rstrip('/').lower()
    if clean_fb in FB_CACHE:
        return FB_CACHE[clean_fb]
        
    email_found = ""
    try:
        about_url = fb_url.rstrip('/') + '/about'
        await page.goto(about_url, wait_until="domcontentloaded", timeout=10000)
        await asyncio.sleep(2)
        
        try:
            close_btn = page.locator('div[aria-label="Sulje"], div[aria-label="Close"], i[data-visualcompletion="css-img"]')
            if await close_btn.count() > 0:
                await close_btn.first.click()
                await asyncio.sleep(1)
        except Exception:
            pass
            
        content = await page.content()
        emails = extract_emails_from_html(content)
        valid = [e for e in emails if 'facebook' not in e and 'fb.com' not in e]
        if valid:
            email_found = valid[0]
            FB_CACHE[clean_fb] = email_found
            return email_found
            
        # Fallback trang chính
        await page.goto(fb_url, wait_until="domcontentloaded", timeout=8000)
        await asyncio.sleep(1.5)
        content2 = await page.content()
        emails2 = extract_emails_from_html(content2)
        valid2 = [e for e in emails2 if 'facebook' not in e and 'fb.com' not in e]
        if valid2:
            email_found = valid2[0]
    except Exception:
        pass
        
    FB_CACHE[clean_fb] = email_found
    return email_found

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def save_outputs(rows, fieldnames):
    new_cols = ['tag_doanh_nghiep_maps', 'facebook_url', 'dia_chi_maps', 'nguon_enrich']
    for c in new_cols:
        if c not in fieldnames:
            fieldnames.append(c)
            
    # Save CSV UTF-8-BOM với fallback backup nếu file đang mở trong Excel
    try:
        with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    except PermissionError:
        backup_csv = OUTPUT_CSV.replace('.csv', '_backup.csv')
        try:
            with open(backup_csv, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            print(f"  [!] File CSV đang mở, đã lưu động vào: {os.path.basename(backup_csv)}", flush=True)
        except Exception:
            pass
    except Exception as e:
        print(f"  [!] Lỗi lưu CSV: {e}", flush=True)
        
    # Save Excel: bảo toàn các sheet hiện có
    try:
        if os.path.exists(OUTPUT_XLSX):
            try:
                wb = openpyxl.load_workbook(OUTPUT_XLSX)
            except Exception:
                wb = openpyxl.Workbook()
        else:
            wb = openpyxl.Workbook()
            
        sheet_name = "Doanh nghiệp (Lọc trùng)"
        if sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            ws.delete_rows(1, ws.max_row + 1)
        else:
            ws = wb.create_sheet(title=sheet_name, index=0)
            
        ws.append(fieldnames)
        for r in rows:
            ws.append([r.get(f, '') for f in fieldnames])
        wb.save(OUTPUT_XLSX)
    except PermissionError:
        backup_xlsx = OUTPUT_XLSX.replace('.xlsx', '_backup.xlsx')
        try:
            wb.save(backup_xlsx)
            print(f"  [!] File Excel đang mở, đã lưu động vào: {os.path.basename(backup_xlsx)}", flush=True)
        except Exception:
            pass
    except Exception as e:
        print(f"  [!] Lỗi lưu Excel: {e}", flush=True)

async def main():
    print("=" * 75, flush=True)
    print(" HỆ THỐNG LÀM GIÀU DỮ LIỆU AGENCY PHẦN LAN (TỐI ƯU HÓA HIỆU NĂNG) ", flush=True)
    print(" Chế độ quan sát trực quan: HEADLESS = FALSE (Mở cửa sổ Chrome) ", flush=True)
    print("=" * 75, flush=True)
    
    if not os.path.exists(INPUT_CSV):
        print(f"[-] Không tìm thấy file: {INPUT_CSV}", flush=True)
        return
        
    rows = []
    fieldnames = []
    with open(INPUT_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)
        
    # Lọc danh sách cần làm giàu email
    target_rows = [r for r in rows if not r.get('email', '').strip()]
    print(f"[+] Tổng số agency duy nhất: {len(rows)} | Cần làm giàu email: {len(target_rows)} agency", flush=True)
    
    cache = load_cache()
    print(f"[+] Đã có trong Cache: {len(cache)} agency đã xử lý trước đó", flush=True)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, channel="chrome")
        context = await browser.new_context(
            locale="fi-FI",
            viewport={"width": 1280, "height": 850},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        async with AsyncSession(impersonate='chrome124', verify=False) as http_session:
            processed_count = 0
            try:
                for idx, r in enumerate(target_rows, 1):
                    c_name = r['name'].strip()
                    cache_key = c_name.lower()
                    
                    # 1. Kiểm tra cache
                    if cache_key in cache:
                        c_data = cache[cache_key]
                        if c_data.get('email'):
                            r['email'] = c_data['email']
                        if c_data.get('phone') and not r.get('phone'):
                            r['phone'] = c_data['phone']
                        if c_data.get('website') and not r.get('website'):
                            r['website'] = c_data['website']
                        if c_data.get('tag_maps'):
                            r['tag_doanh_nghiep_maps'] = c_data['tag_maps']
                        if c_data.get('facebook_url'):
                            r['facebook_url'] = c_data['facebook_url']
                        if c_data.get('address'):
                            r['dia_chi_maps'] = c_data['address']
                        continue
                        
                    processed_count += 1
                    print(f"\n[{processed_count}/{len(target_rows)}] Xử lý: {c_name}", flush=True)
                    
                    cur_phone = r.get('phone', '').strip()
                    cur_web = r.get('website', '').strip()
                    cur_email = r.get('email', '').strip()
                    tag_maps = ""
                    addr_maps = ""
                    fb_url = ""
                    source = []
                    
                    # 2. CHIẾN LƯỢC TỐI ƯU: NẾU ĐÃ CÓ WEBSITE TỪ TRƯỚC -> QUÉT WEBSITE NGAY
                    if cur_web:
                        print(f"  -> Quét nhanh Website sẵn có ({cur_web})...", flush=True)
                        web_email, found_phone, found_fb = await scrape_website_details_fi(http_session, cur_web)
                        if web_email:
                            cur_email = web_email
                            source.append("Website")
                            print(f"    [+] EMAIL TỪ WEB: {cur_email}", flush=True)
                        if found_phone and not cur_phone:
                            cur_phone = found_phone
                            print(f"    [+] SĐT TỪ WEB: {cur_phone}", flush=True)
                        if found_fb:
                            fb_url = found_fb
                            print(f"    [+] LINK FACEBOOK: {fb_url}", flush=True)
                            
                    # 3. NẾU CHƯA CÓ WEBSITE HOẶC CẦN TÌM THÊM THÔNG TIN LIÊN HỆ -> MỚI TRA MAPS
                    if not cur_web or not cur_phone or not cur_email:
                        print(f"  -> Tra cứu trên Google Maps (hl=fi)...", flush=True)
                        maps_info = await search_google_maps_fi(page, c_name)
                        if maps_info["matched"]:
                            source.append("GoogleMaps")
                            tag_maps = maps_info["tag_maps"]
                            addr_maps = maps_info["address"]
                            print(f"    [Maps Khớp ({maps_info['match_reason']})]: {maps_info['maps_title']}", flush=True)
                            if tag_maps:
                                print(f"      - Tag ngành (FI): {tag_maps}", flush=True)
                            if maps_info["phone"] and not cur_phone:
                                cur_phone = maps_info["phone"]
                                print(f"      - SĐT mới (Maps): {cur_phone}", flush=True)
                            if maps_info["website"] and not cur_web:
                                cur_web = maps_info["website"]
                                print(f"      - Website mới (Maps): {cur_web}", flush=True)
                                # Cào website mới phát hiện từ Maps
                                web_email, found_phone, found_fb = await scrape_website_details_fi(http_session, cur_web)
                                if web_email and not cur_email:
                                    cur_email = web_email
                                    source.append("Website(Maps)")
                                    print(f"      [+] EMAIL MỚI: {cur_email}", flush=True)
                                if found_phone and not cur_phone:
                                    cur_phone = found_phone
                                if found_fb and not fb_url:
                                    fb_url = found_fb
                        else:
                            print(f"    [Maps Không khớp/Không thấy]", flush=True)
                            
                    # 4. BƯỚC FALLBACK SEARCH BING / DUCKDUCKGO NẾU VẪN CHƯA CÓ WEBSITE
                    if not cur_web:
                        print(f"  -> Fallback Search (Bing/DDG) tìm website...", flush=True)
                        fb_web = await fallback_search_website_fi(http_session, c_name)
                        if fb_web:
                            cur_web = fb_web
                            source.append("SearchFallback")
                            print(f"    - Website tìm thấy: {cur_web}", flush=True)
                            web_email, found_phone, found_fb = await scrape_website_details_fi(http_session, cur_web)
                            if web_email and not cur_email:
                                cur_email = web_email
                                source.append("Website(Search)")
                                print(f"    [+] EMAIL WEBSITE: {cur_email}", flush=True)
                            if found_phone and not cur_phone:
                                cur_phone = found_phone
                            if found_fb and not fb_url:
                                fb_url = found_fb
                        else:
                            print(f"    - Không tìm thấy website trên search", flush=True)
                            
                    # 5. QUÉT FACEBOOK NẾU VẪN CHƯA CÓ EMAIL MÀ CÓ LINK FB
                    if not cur_email and fb_url:
                        print(f"  -> Quét Fanpage Facebook ({fb_url}) tìm email...", flush=True)
                        fb_email = await scrape_facebook_email_fi(page, fb_url)
                        if fb_email:
                            cur_email = fb_email
                            source.append("Facebook")
                            print(f"    [+] EMAIL FACEBOOK: {cur_email}", flush=True)
                        else:
                            print(f"    - Không thấy email trên Facebook", flush=True)
                            
                    # CẬP NHẬT DỮ LIỆU
                    r['email'] = cur_email
                    if cur_phone:
                        r['phone'] = cur_phone
                    if cur_web:
                        r['website'] = cur_web
                    if tag_maps:
                        r['tag_doanh_nghiep_maps'] = tag_maps
                    if addr_maps:
                        r['dia_chi_maps'] = addr_maps
                    if fb_url:
                        r['facebook_url'] = fb_url
                    r['nguon_enrich'] = ", ".join(source) if source else "None"
                    
                    # Lưu cache ngay lập tức sau mỗi công ty
                    cache[cache_key] = {
                        "email": cur_email,
                        "phone": cur_phone,
                        "website": cur_web,
                        "tag_maps": tag_maps,
                        "address": addr_maps,
                        "facebook_url": fb_url,
                        "source": r['nguon_enrich']
                    }
                    save_cache(cache)
                    
                    # Lưu CSV / Excel sau mỗi 3 công ty hoặc khi có email mới
                    if processed_count % 3 == 0 or cur_email:
                        save_outputs(rows, fieldnames)
                        
            except (KeyboardInterrupt, asyncio.CancelledError):
                print("\n[!] Đã nhận tín hiệu dừng (Ctrl+C). Đang lưu toàn bộ tiến trình...", flush=True)
            except Exception as e:
                print(f"\n[!] Lỗi trong quá trình chạy: {e}", flush=True)
            finally:
                save_cache(cache)
                save_outputs(rows, fieldnames)
                print("[+] Đã lưu file an toàn trước khi đóng trình duyệt!", flush=True)
                try:
                    await browser.close()
                except Exception:
                    pass
                    
    print("\n" + "=" * 75, flush=True)
    print("                 HOÀN TẤT LÀM GIÀU DỮ LIỆU AGENCY PHẦN LAN!", flush=True)
    print("=" * 75, flush=True)
    print(f"- File CSV kết quả: {OUTPUT_CSV}", flush=True)
    print(f"- File Excel kết quả: {OUTPUT_XLSX}", flush=True)
    print("=" * 75, flush=True)

if __name__ == '__main__':
    asyncio.run(main())
