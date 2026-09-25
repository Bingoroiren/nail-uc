# -*- coding: utf-8 -*-
"""
Hệ Thống Cào & Làm Giàu Dữ Liệu Doanh Nghiệp Lithuania (Rekvizitai.lt):
- Toàn bộ danh mục: Labour exchange, employment (Cung ứng lao động / Tuyển dụng)
- Tổng quy mô: 1,289 công ty (86 trang)
- Bóc tách đa tầng:
  1. Thu thập toàn bộ 1,289 công ty từ 86 trang danh mục.
  2. Bóc tách chi tiết từng công ty trên Rekvizitai: Mã số DN, VAT, Giám đốc, SĐT, Địa chỉ, Số NV, Website.
  3. Bóc tách Website chính thức: Deep crawl trang chủ & trang liên hệ lấy Email B2B.
  4. Bóc tách Mạng xã hội: Trích xuất Facebook Fanpage & LinkedIn.
  5. Xuất dữ liệu:
     - data/raw/rekvizitai_labour_exchange_employment_full.csv
     - data/formatted/rekvizitai_labour_exchange_employment_formatted.csv (Chuẩn 20 cột Cold Mail)
- Tính năng: Tự động Resume 100%, ghi tăng dần (Incremental Auto-Save), hỗ trợ vượt Cloudflare Turnstile.
"""

import sys
import os
import re
import csv
import json
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote
from bs4 import BeautifulSoup
import requests
import urllib3
from playwright.sync_api import sync_playwright

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Đảm bảo UTF-8 an toàn trên Windows Console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
RAW_CSV = str(ROOT_DIR / "data" / "raw" / "rekvizitai_labour_exchange_employment_full.csv")
FORMATTED_CSV = str(ROOT_DIR / "data" / "formatted" / "rekvizitai_labour_exchange_employment_formatted.csv")
PROGRESS_DIR = ROOT_DIR / "data" / "progress"
URLS_CACHE_FILE = str(PROGRESS_DIR / "rekvizitai_labour_exchange_urls.json")
PROFILE_DIR = str(ROOT_DIR / "data" / "cache" / "rekvizitai_browser_profile")

os.makedirs(os.path.dirname(RAW_CSV), exist_ok=True)
os.makedirs(os.path.dirname(FORMATTED_CSV), exist_ok=True)
os.makedirs(PROGRESS_DIR, exist_ok=True)
os.makedirs(PROFILE_DIR, exist_ok=True)

COLD_MAIL_COLUMNS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ', 
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển', 
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply', 
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

RAW_COLUMNS = [
    'No', 'Company_Name', 'Registration_Code', 'VAT_Code', 'Manager', 
    'Phone', 'Website', 'Facebook_URL', 'LinkedIn_URL', 'Email', 
    'Email_Source', 'All_Website_Emails', 'Employees', 'Address', 'Rekvizitai_URL'
]

web_session = requests.Session()
web_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9,lt;q=0.8'
})

def format_phone(phone_str):
    if not phone_str:
        return ""
    p = str(phone_str).strip()
    return f"'{p}" if not p.startswith("'") else p

def clean_email(email_str):
    if not email_str:
        return ""
    decoded = unquote(str(email_str)).strip().lower().replace('%20', '').replace(' ', '')
    if any(re.search(pat, decoded) for pat in [r'@\d+\.', r'\.\.', r'react@', r'core-js', r'lenis@', r'polyfill', r'wixpress', r'sentry']):
        return ""
    for junk in ['example.com', 'domain.com', 'test.com', 'sentry.io', 'mysite.com']:
        if junk in decoded:
            return ""
    return decoded

def extract_valid_emails(text):
    if not text:
        return []
    raw = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)
    valid = []
    for em in set(raw):
        c = clean_email(em)
        if c and not any(c.endswith(x) for x in ['.png', '.jpg', '.jpeg', '.svg', '.webp', '.css', '.js']):
            if '.' in c.split('@')[-1]:
                valid.append(c)
    return list(dict.fromkeys(valid))

def scan_website_deep(website):
    if not website or not website.startswith('http'):
        return {'emails': [], 'fb_links': []}
    
    found_emails = []
    found_fb_links = []
    
    try:
        r = web_session.get(website, timeout=7, verify=False)
        if r.status_code == 200:
            found_emails.extend(extract_valid_emails(r.text))
            
            soup = BeautifulSoup(r.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = a['href']
                if any(x in href.lower() for x in ['facebook.com', 'fb.com', 'fb.me']):
                    if not any(x in href.lower() for x in ['sharer', 'share.php', 'plugins']):
                        found_fb_links.append(href)
            
            contact_links = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                text = (a.get_text() or '').lower()
                href_lower = href.lower()
                if any(k in href_lower or k in text for k in ['contact', 'kontaktai', 'apie', 'about', 'career', 'karjera']):
                    full_u = urljoin(website, href)
                    if urlparse(full_u).netloc == urlparse(website).netloc:
                        contact_links.append(full_u)
            
            for c_url in list(dict.fromkeys(contact_links))[:3]:
                try:
                    r_c = web_session.get(c_url, timeout=5, verify=False)
                    if r_c.status_code == 200:
                        found_emails.extend(extract_valid_emails(r_c.text))
                        c_soup = BeautifulSoup(r_c.text, 'html.parser')
                        for a in c_soup.find_all('a', href=True):
                            href = a['href']
                            if any(x in href.lower() for x in ['facebook.com', 'fb.com']):
                                if not any(x in href.lower() for x in ['sharer', 'share.php']):
                                    found_fb_links.append(href)
                except Exception:
                    pass
    except Exception:
        pass
        
    return {
        'emails': list(dict.fromkeys(found_emails)),
        'fb_links': list(dict.fromkeys(found_fb_links))
    }

PAGES_PROGRESS_FILE = str(PROGRESS_DIR / "rekvizitai_pages_progress.json")

def load_pages_progress():
    if os.path.exists(PAGES_PROGRESS_FILE):
        try:
            with open(PAGES_PROGRESS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_pages_progress(prog):
    try:
        with open(PAGES_PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(prog, f, indent=2)
    except Exception:
        pass

def handle_cloudflare(page):
    """Kiểm tra và chờ giải quyết Cloudflare Turnstile nếu gặp phải"""
    for _ in range(3):
        title = page.title()
        if "just a moment" in title.lower() or "security verification" in title.lower():
            print("\a" * 2)
            print("\n" + "=" * 70)
            print("  🛑 PHÁT HIỆN BẢO VỆ CLOUDFLARE TURNSTILE!")
            print("  👉 Vui lòng tick vào ô 'Verify you are human' trên màn hình Chrome...")
            print("=" * 70 + "\n")
            
            for sec in range(90):
                time.sleep(1)
                t = page.title()
                if "just a moment" not in t.lower() and "security verification" not in t.lower():
                    print(f"[+] Vượt qua Cloudflare thành công! (sau {sec}s)")
                    time.sleep(2)
                    return True
            print("[!] Hết thời gian chờ 90s xác minh Cloudflare.")
            return False
        time.sleep(0.5)
    return True

def collect_all_company_urls(page, max_pages=86):
    """Giai đoạn 1: Thu thập toàn bộ URL của 1,289 công ty từ 86 trang (Hỗ trợ Resume & Chống bỏ sót trang)"""
    all_companies = []
    seen_urls = set()

    # Tải danh sách URLs đã có từ cache
    if os.path.exists(URLS_CACHE_FILE):
        try:
            with open(URLS_CACHE_FILE, 'r', encoding='utf-8') as f:
                all_companies = json.load(f)
                seen_urls = set(x['url'] for x in all_companies)
                print(f"[*] Đã tải {len(all_companies)} công ty từ cache: {URLS_CACHE_FILE}")
        except Exception:
            pass

    pages_prog = load_pages_progress()

    if len(all_companies) >= 1285:
        print(f"[+] Đã có đầy đủ {len(all_companies)} công ty trong cache. Bỏ qua thu thập danh mục.")
        return all_companies

    print(f"\n[*] Tiếp tục thu thập danh sách 1,289 công ty từ các trang còn thiếu (Tổng 86 trang)...")

    for p in range(1, max_pages + 1):
        # Bỏ qua các trang đã cào đủ (ít nhất 10 công ty trên trang)
        if str(p) in pages_prog and pages_prog[str(p)] >= 10:
            continue

        url = f"https://rekvizitai.vz.lt/en/companies/labour_exchange_employment/{p}/"
        page_success = False

        for attempt in range(1, 6):
            try:
                page.goto(url, timeout=45000)
                handle_cloudflare(page)
                
                # Đợi load thẻ công ty
                try:
                    page.wait_for_selector('div.company-info', timeout=7000)
                except Exception:
                    pass
                    
                soup = BeautifulSoup(page.content(), 'html.parser')
                cards = soup.find_all('div', class_='company-info')
                
                # NẾU TRANG RỖNG HOẶC BỊ CAPTCHA CHẶN -> TUYỆT ĐỐI KHÔNG BỎ QUA!
                if not cards:
                    print("\a" * 2)
                    print(f"  🛑 [CẢNH BÁO] Trang {p} đang bị dính Captcha hoặc trống (Lần thử {attempt}/5)!")
                    print("  👉 Vui lòng nhìn màn hình Chrome: tick vào ô xác thực hoặc giải Captcha...")
                    for _ in range(15):
                        time.sleep(1)
                        if "just a moment" not in page.title().lower():
                            break
                    time.sleep(2)
                    continue

                page_added = 0
                for c in cards:
                    a_tag = c.find('a', class_=re.compile(r'company-title|title'))
                    if not a_tag or not a_tag.get('href'):
                        continue
                    c_url = urljoin("https://rekvizitai.vz.lt", a_tag['href'])
                    c_name = a_tag.get_text(strip=True) or a_tag.get('title', '')
                    
                    addr_div = c.find('div', class_='address')
                    addr = addr_div.get_text(strip=True) if addr_div else ""
                    
                    if c_url not in seen_urls:
                        seen_urls.add(c_url)
                        all_companies.append({
                            'name': c_name,
                            'url': c_url,
                            'address_preview': addr
                        })
                        page_added += 1

                pages_prog[str(p)] = len(cards)
                save_pages_progress(pages_prog)

                print(f"  Trang {p:>2}/{max_pages}: +{page_added:>2} công ty mới ({len(cards)} trên trang) | Tổng tích lũy: {len(all_companies)} công ty")
                page_success = True

                # Lưu cập nhật cache sau mỗi trang
                with open(URLS_CACHE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(all_companies, f, ensure_ascii=False, indent=2)

                time.sleep(1.2)
                break # Thành công trang này -> sang trang tiếp theo

            except Exception as e:
                print(f"  [!] Lỗi khi cào trang {p} (lần {attempt}): {e}")
                time.sleep(3)

        if not page_success:
            print(f"  ⚠️ CẢNH BÁO: Trang {p} không thể nạp sau 5 lần thử. Script sẽ tạm dừng để bạn xử lý trên trình duyệt.")
            time.sleep(5)

    with open(URLS_CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_companies, f, ensure_ascii=False, indent=2)
    print(f"[+] Hoàn thành thu thập toàn bộ {len(all_companies)} công ty vào {URLS_CACHE_FILE}\n")
    return all_companies

def get_already_scraped_urls():
    """Đọc các URL đã hoàn thành trong file RAW để phục vụ tính năng Resume 100%"""
    done = set()
    if os.path.exists(RAW_CSV):
        try:
            with open(RAW_CSV, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for r in reader:
                    u = r.get('Rekvizitai_URL', '').strip()
                    if u:
                        done.add(u)
        except Exception:
            pass
    return done

def init_output_files():
    """Khởi tạo header cho file RAW và Formatted nếu chưa có"""
    if not os.path.exists(RAW_CSV) or os.path.getsize(RAW_CSV) == 0:
        with open(RAW_CSV, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=RAW_COLUMNS)
            writer.writeheader()
            
    if not os.path.exists(FORMATTED_CSV) or os.path.getsize(FORMATTED_CSV) == 0:
        with open(FORMATTED_CSV, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=COLD_MAIL_COLUMNS)
            writer.writeheader()

def main():
    print("=" * 80)
    print("  HỆ THỐNG CÀO TOÀN BỘ 1,289 CÔNG TY REKVIZITAI LITHUANIA (EMPLOYMENT)")
    print("  - Danh mục: https://rekvizitai.vz.lt/en/companies/labour_exchange_employment/")
    print("  - Quy mô: 86 trang | 1,289 doanh nghiệp cung ứng lao động")
    print("  - Bóc tách: Thư bạ + Website chính thức + Facebook Fanpage + Email B2B")
    print("=" * 80)

    init_output_files()
    done_urls = get_already_scraped_urls()
    print(f"[*] Dữ liệu đã cào trước đó trong file: {len(done_urls)} công ty (sẽ tự động bỏ qua).")

    with sync_playwright() as p:
        print("[*] Khởi động trình duyệt Google Chrome (có giao diện trực quan)...")
        context = p.chromium.launch_persistent_context(
            PROFILE_DIR,
            channel="chrome",
            headless=False,
            viewport={'width': 1280, 'height': 800},
            args=['--disable-blink-features=AutomationControlled']
        )
        page = context.pages[0] if context.pages else context.new_page()

        # Giai đoạn 1: Thu thập đầy đủ URLs
        company_list = collect_all_company_urls(page, max_pages=86)
        total_comps = len(company_list)
        print(f"[*] Bắt đầu bóc tách chi tiết & làm giàu cho {total_comps} công ty...")

        current_idx = len(done_urls)

        # Giai đoạn 2: Bóc tách chi tiết từng công ty & Deep crawl website
        for i, comp in enumerate(company_list, 1):
            c_name = comp['name']
            c_url = comp['url']

            if c_url in done_urls:
                continue

            current_idx += 1
            print(f"\n[{current_idx}/{total_comps}] 🏢 {c_name}")
            print(f"    - URL: {c_url}")

            reg_code = ""
            vat_code = ""
            manager = ""
            address = comp.get('address_preview', '')
            phone = ""
            website = ""
            facebook_url = ""
            linkedin_url = ""
            employees = ""

            try:
                page.goto(c_url, timeout=35000)
                handle_cloudflare(page)
                
                soup = BeautifulSoup(page.content(), 'html.parser')
                h1 = soup.find('h1')
                if h1:
                    c_name = h1.get_text(strip=True)

                for tr in soup.find_all('tr'):
                    tds = [td.get_text(strip=True) for td in tr.find_all(['th', 'td']) if td.get_text(strip=True)]
                    if len(tds) >= 2:
                        label = tds[0].lower()
                        val = tds[1]
                        if any(k in label for k in ['registration code', 'company code', 'įmonės kodas']):
                            reg_code = val
                        elif 'vat' in label or 'pvm' in label:
                            vat_code = val
                        elif any(k in label for k in ['manager', 'director', 'vadovas']):
                            manager = val.split('More')[0].strip()
                        elif 'address' in label or 'adresas' in label:
                            address = val
                        elif 'phone' in label or 'mobile' in label or 'telefonas' in label:
                            if not phone:
                                phone = val
                        elif 'website' in label or 'tinklalapis' in label:
                            a_web = tr.find('a', href=True)
                            website = a_web['href'] if a_web else val.replace('Uždaryti', '').replace('Close', '').strip()
                        elif 'facebook' in label:
                            a_fb = tr.find('a', href=True)
                            facebook_url = a_fb['href'] if a_fb else val
                        elif 'linkedin' in label:
                            a_li = tr.find('a', href=True)
                            linkedin_url = a_li['href'] if a_li else val
                        elif 'employees' in label or 'darbuotojai' in label:
                            employees = val.split('insured')[0].strip()

                if not manager:
                    m_match = re.search(r'(?:Manager|Director|Vadovas)[:\s]+([^\n\r,]+)', page.content(), re.IGNORECASE)
                    if m_match:
                        manager = m_match.group(1).strip()
            except Exception as e:
                print(f"    [!] Lỗi tải trang Rekvizitai: {e}")

            if website and not website.startswith('http'):
                website = f"http://{website}"

            print(f"    - Mã số: {reg_code} | VAT: {vat_code} | Quản lý: {manager}")
            print(f"    - SĐT: {phone} | Địa chỉ: {address}")
            print(f"    - Website: {website} | Nhân viên: {employees}")

            # Deep crawl website công ty
            scan_res = scan_website_deep(website)
            web_emails = scan_res['emails']
            web_fb_links = scan_res['fb_links']

            if not facebook_url and web_fb_links:
                facebook_url = web_fb_links[0]

            best_email = web_emails[0] if web_emails else ""
            email_source = "Website" if best_email else ""

            print(f"    - ✉️ Email: {best_email or 'Chưa tìm thấy'} (Nguồn: {email_source or 'N/A'})")
            print(f"    - 🌐 Facebook Fanpage: {facebook_url or 'Không có'}")

            # Lưu tăng dần vào file RAW
            raw_record = {
                'No': current_idx,
                'Company_Name': c_name,
                'Registration_Code': reg_code,
                'VAT_Code': vat_code,
                'Manager': manager,
                'Phone': format_phone(phone),
                'Website': website,
                'Facebook_URL': facebook_url,
                'LinkedIn_URL': linkedin_url,
                'Email': best_email,
                'Email_Source': email_source,
                'All_Website_Emails': "; ".join(web_emails),
                'Employees': employees,
                'Address': address,
                'Rekvizitai_URL': c_url
            }

            with open(RAW_CSV, 'a', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=RAW_COLUMNS)
                writer.writerow(raw_record)
                f.flush()

            # Lưu tăng dần vào file Formatted Cold Mail
            cold_record = {
                'No.': current_idx,
                'Công ty': c_name,
                'Chức danh': 'Vadovas / Manager' if manager else '',
                'Người liên hệ': manager,
                'SĐT': format_phone(phone),
                'Liên Hệ': website,
                'Email': best_email,
                'Liên Hệ mail': facebook_url,
                'Địa chỉ': address,
                'Lương': '',
                'Ngày đăng': '',
                'Hạn tuyển': '',
                'Check gửi': '',
                'Last Subject': '',
                'Last Body HTML': '',
                'Trạng thái Reply': '',
                'Lần Follow-up': '0',
                'Ngày Follow-up gần nhất': '',
                'Mailbox đã dùng': '',
                'Category': 'Cung ứng lao động / Tuyển dụng (Lithuania)'
            }

            with open(FORMATTED_CSV, 'a', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=COLD_MAIL_COLUMNS)
                writer.writerow(cold_record)
                f.flush()

            done_urls.add(c_url)
            time.sleep(1.0)

        context.close()

    print("\n" + "=" * 80)
    print(f"  HOÀN TẤT CÀO & LÀM GIÀU TOÀN BỘ DANH MỤC REKVIZITAI LITHUANIA!")
    print(f"  - Tệp RAW chi tiết: {RAW_CSV}")
    print(f"  - Tệp Formatted Cold Mail: {FORMATTED_CSV}")
    print("=" * 80)

if __name__ == '__main__':
    main()
