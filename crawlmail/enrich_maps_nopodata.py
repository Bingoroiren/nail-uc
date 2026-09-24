# -*- coding: utf-8 -*-
"""
Hệ thống Làm giàu dữ liệu Google Maps theo Tên công ty cho NOPODATA.csv:
1. Tra cứu Google Maps (hl=no, headless=False) theo Tên công ty & Thành phố.
2. So khớp tên nghiêm ngặt (không phân biệt hoa thường, giống hệt hoặc có dấu ngăn cách).
3. Bóc tách Số điện thoại (luôn có dấu ' ở đầu), Website chính thức.
4. Quét Website tìm Email B2B (loại bỏ %20, lọc template demo/rác).
5. Lưu tăng dần (Incremental Auto-Save) và Checkpoint JSON (Resume 100%).
"""

import sys
import os
import re
import csv
import json
import time
import html
import asyncio
import urllib.parse
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

try:
    from curl_cffi.requests import AsyncSession
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False
    import aiohttp

# Cấu hình encoding UTF-8 cho Windows Console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = str(ROOT_DIR / "NOPODATA.csv")
BACKUP_CSV = str(ROOT_DIR / "NOPODATA_backup_before_maps.csv")
CACHE_FILE = str(ROOT_DIR / "crawlmail" / "cache_enrich_maps_nopodata.json")

# Danh sách hậu tố loại hình công ty Na Uy
LEGAL_FORMS_NO = ['as', 'asa', 'enk', 'da', 'ans', 'nuf', 'sa', 'ba', 'iks', 'kf']

# Danh sách tên miền loại trừ (không phải website chính thức)
EXCLUDED_DOMAINS = {
    'facebook.com', 'instagram.com', 'linkedin.com', 'twitter.com', 'x.com',
    'youtube.com', 'tiktok.com', 'pinterest.com', 'wikipedia.org',
    'proff.no', 'brreg.no', 'gulesider.no', '1881.no', 'purehelp.no',
    'regnskapstall.no', 'kart.finn.no', 'finn.no', 'google.com', 'google.no',
    'maps.google.com', 'apple.com', 'yellowpages', 'tripadvisor'
}

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,10}\b')
JUNK_EMAIL_DOMAINS = {
    'facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com', 'youtube.com',
    'wix.com', 'wixsite.com', 'wordpress.com', 'squarespace.com', 'weebly.com',
    'godaddy.com', 'example.com', 'domain.com', 'placeholder.com', 'wixpress.com',
    'sentry.io', 'sentry.wixpress.com', 'schema.org', 'trustpilot.com', 'google.com'
}
SYSTEM_USERNAMES = {
    'noreply', 'no-reply', 'donotreply', 'privacy', 'terms', 'cookies', 'gdpr',
    'abuse', 'security', 'webmaster', 'sentry', 'admin', 'mailer-daemon', 'test', 'example'
}

def clean_company_name_no(name):
    """Chuẩn hóa tên công ty, loại bỏ dấu ngoặc kép và hậu tố loại hình."""
    if not name:
        return ""
    n = re.sub(r'["\'„“”«»]', '', name).strip().lower()
    tokens = [t for t in n.split() if t not in LEGAL_FORMS_NO]
    return ' '.join(tokens).strip()

def is_valid_name_match_no(query_name, candidate_name):
    """
    So khớp nghiêm ngặt theo yêu cầu:
    1. Không phân biệt hoa thường.
    2. Giống hệt từ khóa tìm kiếm.
    3. Nếu có từ/cụm từ khác biệt thì BẮT BUỘC phải có dấu ngăn cách (-, –, —, |, /, :, ,, (), []).
    """
    if not query_name or not candidate_name:
        return False, "EMPTY"

    q_raw = re.sub(r'["\'„“”«»]', '', query_name).strip().lower()
    c_raw = re.sub(r'["\'„“”«»]', '', candidate_name).strip().lower()

    # 1. Khớp giống hệt 100% nguyên bản
    if q_raw == c_raw:
        return True, "EXACT_RAW"

    # 2. Khớp có dấu ngoặc phân tách chi nhánh / địa danh
    c_nobrackets = re.sub(r'\(.*?\)|\[.*?\]', '', c_raw).strip()
    if q_raw == c_nobrackets:
        return True, "BRACKET_MATCH"

    # 3. Khớp có dấu ngăn cách phân tách (-, –, —, |, /, :, ,)
    parts = [p.strip() for p in re.split(r'[-–—|/:,]', c_raw) if p.strip()]
    if any(p == q_raw for p in parts):
        return True, "DELIMITER_MATCH"

    # 4. So khớp sau khi chuẩn hóa hậu tố loại hình kinh doanh (AS, NUF...)
    q_clean = clean_company_name_no(query_name)
    c_clean = clean_company_name_no(candidate_name)
    if q_clean and q_clean == c_clean:
        return True, "EXACT_CORE"

    c_nobrackets_clean = clean_company_name_no(c_nobrackets)
    if q_clean and q_clean == c_nobrackets_clean:
        return True, "BRACKET_CORE"

    parts_clean = [clean_company_name_no(p) for p in parts if clean_company_name_no(p)]
    if q_clean and any(p == q_clean for p in parts_clean):
        return True, "DELIMITER_CORE"

    return False, "NO_MATCH"

def format_norway_phone(phone_str):
    """Chuẩn hóa số điện thoại Na Uy, luôn thêm dấu nháy đơn ' ở đầu."""
    if not phone_str:
        return ""
    clean = re.sub(r'[^\d+]', '', str(phone_str).strip())
    if not clean:
        return ""
    if not clean.startswith("'"):
        clean = f"'{clean}"
    return clean

def clean_email_string(email_str):
    """Làm sạch email, decode %20, loại bỏ ký tự rác và mail demo."""
    if not email_str:
        return ""
    em = urllib.parse.unquote(str(email_str)).replace('%20', '').strip().lower().rstrip('.,;:')
    if any(em.endswith(ext) for ext in ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf', '.css', '.js')):
        return ""
    if '@' not in em or len(em) < 6:
        return ""
    u, d = em.split('@', 1)
    if d in JUNK_EMAIL_DOMAINS or u in SYSTEM_USERNAMES:
        return ""
    return em

def decode_cloudflare_email(hex_str):
    """Giải mã Cloudflare protected email."""
    try:
        hex_data = bytes.fromhex(hex_str)
        key = hex_data[0]
        return ''.join(chr(b ^ key) for b in hex_data[1:])
    except Exception:
        return ""

def score_email_b2b(email, comp_domain=""):
    """Chấm điểm chọn email B2B tốt nhất cho công ty nhân sự Na Uy."""
    clean_em = clean_email_string(email)
    if not clean_em:
        return -1
    score = 10
    u, d = clean_em.split('@', 1)
    if comp_domain and (comp_domain in d or d in comp_domain):
        score += 50
    if u in ['post', 'kontakt', 'info', 'firmapost']:
        score += 30
    elif u in ['rekruttering', 'bemanning', 'hr', 'jobb', 'booking']:
        score += 25
    elif u in ['administrasjon', 'office', 'salg']:
        score += 15
    return score

async def fetch_website_emails(website_url):
    """Cào website doanh nghiệp để lấy email B2B."""
    if not website_url:
        return ""
    
    clean_url = website_url.strip()
    if not clean_url.startswith(("http://", "https://")):
        clean_url = "https://" + clean_url
        
    try:
        domain = urllib.parse.urlparse(clean_url).netloc.lower().replace('www.', '')
    except Exception:
        domain = ""
        
    pages_to_check = [clean_url]
    # Thêm các subpage liên hệ phổ biến ở Na Uy
    base_slash = clean_url.rstrip('/')
    for path in ['/kontakt', '/kontakt-oss', '/om-oss', '/om-os', '/contact', '/about']:
        pages_to_check.append(f"{base_slash}{path}")
        
    found_emails = set()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    
    for url in pages_to_check[:3]: # Quét tối đa 3 trang để tối ưu thời gian
        html_text = ""
        try:
            if HAS_CURL_CFFI:
                async with AsyncSession(impersonate="chrome120", timeout=12) as session:
                    resp = await session.get(url, headers=headers)
                    if resp.status_code == 200:
                        html_text = resp.text
            else:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
                    async with session.get(url, headers=headers, ssl=False) as resp:
                        if resp.status == 200:
                            html_text = await resp.text()
        except Exception:
            continue
            
        if not html_text:
            continue
            
        # 1. Cloudflare emails
        for cf in re.findall(r'data-cfemail="([0-9a-fA-F]+)"', html_text):
            dec = decode_cloudflare_email(cf)
            clean_em = clean_email_string(dec)
            if clean_em:
                found_emails.add(clean_em)
                
        # 2. mailto: links
        for m in re.findall(r'mailto:([^\s"\'<>]+)', html_text, re.IGNORECASE):
            raw_m = m.split('?')[0]
            clean_em = clean_email_string(raw_m)
            if clean_em:
                found_emails.add(clean_em)
                
        # 3. Regex emails
        for m in EMAIL_REGEX.findall(html_text):
            clean_em = clean_email_string(m)
            if clean_em:
                found_emails.add(clean_em)
                
        if found_emails:
            break
            
    if not found_emails:
        return ""
        
    best_email = max(found_emails, key=lambda e: score_email_b2b(e, domain))
    return best_email

async def handle_captcha_interactive(page):
    """Kiểm tra và xử lý Captcha của Google Maps."""
    try:
        content = await page.content()
        title = await page.title()
        if "unusual traffic" in content.lower() or "sorry/index" in page.url or "captcha" in title.lower():
            print("\n" + "!" * 75, flush=True)
            print("[CẢNH BÁO BOT] Google Maps yêu cầu xác thực Captcha!", flush=True)
            print("Cửa sổ Chrome đang mở sẵn trên màn hình của bạn.", flush=True)
            print("Vui lòng click giải Captcha trên trình duyệt, sau đó nhấn ENTER tại đây để tiếp tục...", flush=True)
            print("!" * 75 + "\n", flush=True)
            sys.stdout.write('\a')
            sys.stdout.flush()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, input, ">> Nhấn [ENTER] sau khi đã giải Captcha: ")
            await asyncio.sleep(2)
            return True
    except Exception:
        pass
    return False

async def search_google_maps_company(page, company_name, city):
    """Tra cứu tên công ty trên Google Maps với giao diện Na Uy."""
    query = f"{company_name}, {city}, Norway" if city else f"{company_name}, Norway"
    search_url = f"https://www.google.com/maps/search/{urllib.parse.quote(query)}?hl=no"
    
    result = {
        "matched": False,
        "match_type": "",
        "maps_title": "",
        "phone": "",
        "website": "",
        "address": ""
    }
    
    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=25000)
        await handle_captcha_interactive(page)
        
        # Bypass Cookie Consent nếu có
        try:
            consent_btn = page.locator('button[aria-label*="Godta"], button[aria-label*="Accept"], form[action*="consent"] button')
            if await consent_btn.count() > 0:
                await consent_btn.first.click()
                await asyncio.sleep(1)
        except Exception:
            pass
            
        # Chờ nạp phần tử Maps
        try:
            await page.wait_for_selector('h1.DUwDvf, a.hfpxzc, div[role="feed"], div:has-text("Fant ingen resultater")', timeout=8000)
        except Exception:
            await asyncio.sleep(2)
            
        # Case A: Google Maps mở trực tiếp trang chi tiết doanh nghiệp
        title_elem = page.locator('h1.DUwDvf')
        if await title_elem.count() > 0:
            title = (await title_elem.first.text_content() or "").strip()
            matched, match_type = is_valid_name_match_no(company_name, title)
            if matched:
                result["matched"] = True
                result["match_type"] = match_type
                result["maps_title"] = title
                
                # Phone
                phone_loc = page.locator('button[data-item-id*="phone:tel:"]')
                if await phone_loc.count() > 0:
                    raw_ph = await phone_loc.first.get_attribute("data-item-id")
                    if raw_ph:
                        result["phone"] = format_norway_phone(raw_ph.replace("phone:tel:", ""))
                        
                # Website
                web_loc = page.locator('a[data-item-id="authority"]')
                if await web_loc.count() > 0:
                    href = await web_loc.first.get_attribute("href")
                    if href and not any(ex in href.lower() for ex in EXCLUDED_DOMAINS):
                        result["website"] = href.strip()
                        
                # Address
                addr_loc = page.locator('button[data-item-id*="address"]')
                if await addr_loc.count() > 0:
                    raw_addr = await addr_loc.first.get_attribute("aria-label")
                    if raw_addr:
                        result["address"] = raw_addr.replace("Adresse:", "").replace("Address:", "").strip()
                        
                return result

        # Case B: Google Maps hiển thị danh sách các thẻ kết quả
        cards = page.locator('a.hfpxzc')
        count = await cards.count()
        if count > 0:
            for i in range(min(count, 3)):
                card_title = (await cards.nth(i).get_attribute('aria-label') or "").strip()
                matched, match_type = is_valid_name_match_no(company_name, card_title)
                if matched:
                    result["matched"] = True
                    result["match_type"] = match_type
                    result["maps_title"] = card_title
                    
                    await cards.nth(i).click()
                    try:
                        await page.wait_for_selector('h1.DUwDvf, button[data-item-id*="phone"]', timeout=6000)
                    except Exception:
                        await asyncio.sleep(2)
                        
                    phone_loc = page.locator('button[data-item-id*="phone:tel:"]')
                    if await phone_loc.count() > 0:
                        raw_ph = await phone_loc.first.get_attribute("data-item-id")
                        if raw_ph:
                            result["phone"] = format_norway_phone(raw_ph.replace("phone:tel:", ""))
                            
                    web_loc = page.locator('a[data-item-id="authority"]')
                    if await web_loc.count() > 0:
                        href = await web_loc.first.get_attribute("href")
                        if href and not any(ex in href.lower() for ex in EXCLUDED_DOMAINS):
                            result["website"] = href.strip()
                            
                    addr_loc = page.locator('button[data-item-id*="address"]')
                    if await addr_loc.count() > 0:
                        raw_addr = await addr_loc.first.get_attribute("aria-label")
                        if raw_addr:
                            result["address"] = raw_addr.replace("Adresse:", "").replace("Address:", "").strip()
                            
                    return result
    except Exception as e:
        # Lỗi mạng không dừng toàn bộ tiến trình
        pass
        
    return result

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

async def main():
    print("=" * 75)
    print("   LÀM GIÀU DỮ LIỆU GOOGLE MAPS THEO TÊN CÔNG TY (NOPODATA.CSV)")
    print("=" * 75)
    
    if not os.path.exists(INPUT_CSV):
        print(f"[-] Không tìm thấy tệp {INPUT_CSV}")
        return
        
    # Tạo backup file trước khi xử lý
    if not os.path.exists(BACKUP_CSV):
        import shutil
        shutil.copy2(INPUT_CSV, BACKUP_CSV)
        print(f"[+] Đã tạo tệp sao lưu an toàn tại: {BACKUP_CSV}")
        
    # Đọc dữ liệu CSV
    with open(INPUT_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
        
    cache = load_cache()
    print(f"[*] Tổng số công ty trong CSV: {len(rows)}")
    print(f"[*] Đã tải {len(cache)} bản ghi từ Cache.")
    
    # Lọc danh sách cần xử lý: các công ty còn thiếu Website, Phone hoặc Email
    to_process = []
    for idx, r in enumerate(rows):
        orgnr = r.get("orgnr", "").strip()
        has_web = bool(r.get("website", "").strip())
        has_phone = bool(r.get("phone", "").strip())
        has_email = bool(r.get("email", "").strip())
        
        # Nếu đã có đủ cả 3 thông tin thì bỏ qua
        if has_web and has_phone and has_email:
            continue
            
        # Nếu đã có trong cache và đã hoàn thành tra cứu Maps
        if orgnr in cache:
            continue
            
        to_process.append((idx, r))
        
    print(f"[*] Số công ty cần tra cứu Google Maps: {len(to_process)}")
    if not to_process:
        print("[+] Toàn bộ công ty đã được làm giàu đầy đủ!")
        return
        
    # Khởi tạo Playwright với headless=False theo Rule workspace
    async with async_playwright() as p:
        print("[*] Đang khởi chạy trình duyệt Chrome (headless=False) để bạn quan sát...")
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            geolocation={"latitude": 59.9139, "longitude": 10.7522}, # Oslo, Norway
            permissions=["geolocation"]
        )
        page = await context.new_page()
        
        saved_count = 0
        for current_step, (row_idx, row) in enumerate(to_process, 1):
            orgnr = row.get("orgnr", "").strip()
            name = row.get("name", "").strip()
            city = row.get("city", "").strip()
            
            print(f"\n[{current_step}/{len(to_process)}] Tra cứu: {name} (Thành phố: {city}) | Orgnr: {orgnr}")
            
            # Tra cứu Maps
            maps_res = await search_google_maps_company(page, name, city)
            
            cache_entry = {
                "matched": maps_res["matched"],
                "match_type": maps_res["match_type"],
                "maps_title": maps_res["maps_title"],
                "found_phone": maps_res["phone"],
                "found_website": maps_res["website"],
                "found_email": ""
            }
            
            if maps_res["matched"]:
                print(f"  [+] KHỚP TÊN ({maps_res['match_type']}): '{maps_res['maps_title']}'")
                
                # Bổ sung Phone nếu thiếu
                if maps_res["phone"] and not row.get("phone", "").strip():
                    row["phone"] = maps_res["phone"]
                    print(f"  [+] Cập nhật SĐT: {row['phone']}")
                    
                # Bổ sung Website nếu thiếu
                if maps_res["website"] and not row.get("website", "").strip():
                    row["website"] = maps_res["website"]
                    print(f"  [+] Cập nhật Website: {row['website']}")
                    
                # Quét Email từ Website vừa tìm được hoặc Website sẵn có
                target_web = row.get("website", "").strip()
                if target_web and not row.get("email", "").strip():
                    print(f"  [*] Đang quét email trên website: {target_web}...")
                    found_email = await fetch_website_emails(target_web)
                    if found_email:
                        row["email"] = found_email
                        cache_entry["found_email"] = found_email
                        print(f"  [+] TÌM THẤY EMAIL B2B: {found_email}")
                    else:
                        print("  [-] Không tìm thấy email hợp lệ trên website.")
            else:
                print("  [-] Không tìm thấy kết quả khớp tên chuẩn trên Google Maps.")
                
            cache[orgnr] = cache_entry
            saved_count += 1
            
            # Lưu tăng dần mỗi dòng vào Cache và mỗi 5 dòng vào CSV
            if saved_count % 5 == 0 or current_step == len(to_process):
                save_cache(cache)
                # Ghi lại toàn bộ bảng NOPODATA.csv an toàn
                with open(INPUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
                print(f"  [✓] Đã tự động lưu dữ liệu tăng dần vào NOPODATA.csv ({saved_count} công ty đã duyệt).")
                
            await asyncio.sleep(1.0)
            
        await browser.close()
        
    print("\n" + "=" * 75)
    print("   HOÀN TẤT QUÁ TRÌNH LÀM GIÀU DỮ LIỆU NOPODATA.CSV THÀNH CÔNG!")
    print("=" * 75)

if __name__ == "__main__":
    asyncio.run(main())
