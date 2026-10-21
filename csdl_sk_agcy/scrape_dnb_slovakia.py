# -*- coding: utf-8 -*-
"""
D&B Slovakia Employment Services Scraper:
Cào toàn bộ danh sách 1,327 công ty môi giới / dịch vụ việc làm Slovakia từ Dun & Bradstreet:
https://www.dnb.com/business-directory/sk/employment_services/companies

Lưu ý: URL chuẩn KHÔNG CÓ đuôi .html (có .html sẽ bị lỗi 404).
Cơ chế: Chạy Google Chrome thực tế (headless=False), hỗ trợ vượt Captcha Cloudflare trực quan,
tự động cào và lật trang từ 1 đến 27, lưu tăng dần vào csdl_sk_agcy/dnb_slovakia_agcy_database.csv
"""

import sys
import os
import re
import csv
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

# Đảm bảo UTF-8 cho Windows Console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

OUTPUT_DIR = Path("D:/glc/nail uc/csdl_sk_agcy")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CSV_FILE = OUTPUT_DIR / "dnb_slovakia_agcy_database.csv"
PROFILE_DIR = Path("D:/glc/nail uc/chrome_user_data/dnb_profile")
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

FIELDNAMES = ['No.', 'Company', 'Location', 'City', 'Region', 'Country', 'Detail_URL', 'Page', 'Source']

# URL CHUẨN CỦA D&B (KHÔNG CÓ .html)
BASE_URL = "https://www.dnb.com/business-directory/sk/employment_services/companies"

def extract_companies_js(page, current_page):
    """
    Sử dụng JavaScript trực tiếp trên DOM để bóc tách toàn bộ danh sách công ty trên trang.
    """
    js_code = """
    () => {
        const results = [];
        const seen = new Set();
        
        // 1. Quét theo các hàng tr hoặc row trong bảng
        const rows = document.querySelectorAll('tr, [role="row"], div[class*="row"]');
        for (const r of rows) {
            const text = r.innerText || '';
            if (!text || (text.includes('COMPANY') && text.includes('LOCATION'))) continue;
            
            // Tìm thẻ <a> trong hàng
            const a = r.querySelector('a');
            if (a) {
                const name = a.innerText.trim();
                const href = a.href || '';
                
                if (name && name.length >= 3 && !seen.has(name.toLowerCase())) {
                    // Bỏ các từ điều hướng
                    const lower = name.toLowerCase();
                    if (lower.includes('business directory') || lower === 'small business' || lower === 'enterprise') continue;
                    
                    const lines = text.split('\\n').map(s => s.trim()).filter(Boolean);
                    let location = '';
                    for (const l of lines) {
                        if (l !== name && (l.includes('Slovakia') || l.includes('Kraj') || l.includes('Bratislava') || l.includes(','))) {
                            location = l;
                            break;
                        }
                    }
                    if (!location && lines.length > 1) {
                        location = lines[1];
                    }
                    
                    results.push({ name, href, location });
                    seen.add(name.toLowerCase());
                }
            }
        }
        
        // 2. Nếu không tìm thấy qua hàng, quét trực tiếp tất cả link công ty
        if (results.length === 0) {
            const allLinks = document.querySelectorAll('a[href*="/company-information/"], a[href*="/company-profiles/"], a[href*="/business-directory/company"]');
            for (const a of allLinks) {
                const name = a.innerText.trim();
                const href = a.href || '';
                if (name && name.length >= 3 && !seen.has(name.toLowerCase())) {
                    const parent = a.closest('tr') || a.parentElement?.parentElement || a.parentElement;
                    const text = parent ? (parent.innerText || '') : '';
                    const lines = text.split('\\n').map(s => s.trim()).filter(Boolean);
                    let location = lines.find(l => l !== name && (l.includes('Slovakia') || l.includes(','))) || '';
                    results.push({ name, href, location });
                    seen.add(name.toLowerCase());
                }
            }
        }
        
        return results;
    }
    """
    raw_data = page.evaluate(js_code)
    formatted = []
    
    for item in raw_data:
        name = item.get('name', '').strip()
        location = item.get('location', '').strip()
        href = item.get('href', '').strip()
        
        city = ""
        region = ""
        country = "Slovakia"
        if location:
            parts = [p.strip() for p in location.split(',') if p.strip()]
            if len(parts) >= 1:
                city = parts[0]
            if len(parts) >= 2:
                region = parts[1]
            if len(parts) >= 3:
                country = parts[2]
                
        formatted.append({
            'Company': name,
            'Location': location,
            'City': city,
            'Region': region,
            'Country': country,
            'Detail_URL': href,
            'Page': current_page,
            'Source': 'dnb.com'
        })
        
    return formatted

def scrape_dnb():
    print("=" * 70)
    print(" BẮT ĐẦU CÀO DUN & BRADSTREET (D&B) - EMPLOYMENT SERVICES SLOVAKIA")
    print(f"[*] URL đích: {BASE_URL}")
    print("=" * 70)

    # Đọc checkpoint đã có
    scraped_companies = set()
    total_saved = 0
    if CSV_FILE.exists():
        with open(CSV_FILE, 'r', encoding='utf-8-sig', errors='ignore') as f:
            reader = csv.DictReader(f)
            for r in reader:
                c = r.get('Company', '').strip().lower()
                if c:
                    scraped_companies.add(c)
                    total_saved += 1
        print(f"[*] Đã có {total_saved:,} doanh nghiệp trong checkpoint CSV. Tiếp tục cào...")
    else:
        with open(CSV_FILE, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=FIELDNAMES)
            w.writeheader()

    with sync_playwright() as p:
        print("[*] Đang khởi chạy Google Chrome thực tế (headless=False)...")
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            headless=False,
            viewport={'width': 1280, 'height': 800},
            args=['--disable-blink-features=AutomationControlled', '--start-maximized']
        )
        page = context.new_page()

        print(f"[*] Điều hướng tới: {BASE_URL}")
        page.goto(BASE_URL, timeout=60000)

        # Kiểm tra Cloudflare và chờ người dùng click nếu có
        passed_cf = False
        print("[*] Đang kiểm tra trang và xác thực Cloudflare...")
        for wait_sec in range(90):
            title = page.title()
            body_text = page.locator('body').inner_text() if page.locator('body').count() > 0 else ""
            
            # Đã vào trang danh bạ thực sự
            if 'Employment Services' in title or 'Showing 1-' in body_text or 'MAXIN' in body_text:
                passed_cf = True
                print(f"[+] Xác thực thành công! Đã vào trang danh bạ: '{title}'")
                break
            
            if '404' in title:
                print(f"[-] Bị lỗi 404, đang tải lại URL chuẩn...")
                page.goto(BASE_URL, timeout=30000)
                time.sleep(2)
                continue

            if wait_sec % 5 == 0:
                print(f"\a[!] Trang đang xác thực Cloudflare... Vui lòng bấm tick 'Verify you are human' trên màn hình Chrome nếu thấy! (Chờ: {wait_sec}s/90s)")
            time.sleep(1)

        if not passed_cf:
            print("[-] Quá thời gian chờ xác thực Cloudflare. Hãy thử lại.")
            context.close()
            return

        # Vòng lặp cào từng trang từ 1 đến 27
        max_pages = 27
        current_page = 1

        while current_page <= max_pages:
            print(f"\n" + "-" * 50)
            print(f"[*] Đang xử lý D&B Trang {current_page}/{max_pages}...")
            
            # Đợi bảng dữ liệu load hoàn tất
            time.sleep(3)
            
            # Bóc tách các dòng công ty
            rows = extract_companies_js(page, current_page)
            print(f"[+] Trang {current_page}: Tìm thấy {len(rows)} doanh nghiệp.")

            if not rows:
                print(f"[*] Trang {current_page} không bóc tách được dòng nào hoặc đã hết dữ liệu.")
                # Thử đợi thêm 2s
                time.sleep(2)
                rows = extract_companies_js(page, current_page)
                if not rows:
                    print(f"[*] Kết thúc cào tại trang {current_page}.")
                    break

            new_in_page = 0
            for r in rows:
                c_key = r['Company'].strip().lower()
                if c_key not in scraped_companies:
                    total_saved += 1
                    r['No.'] = total_saved
                    with open(CSV_FILE, 'a', encoding='utf-8-sig', newline='') as af:
                        w = csv.DictWriter(af, fieldnames=FIELDNAMES)
                        w.writerow(r)
                    scraped_companies.add(c_key)
                    new_in_page += 1
                    print(f"  [{total_saved:>4}] {r['Company']:<40} | {r['City']}")

            print(f"[*] Đã lưu thêm {new_in_page} công ty mới từ trang {current_page}. Tổng cộng hiện có: {total_saved}")

            if current_page >= max_pages:
                print("[*] Đã hoàn thành trang cuối cùng (27).")
                break

            # Chuyển sang trang tiếp theo
            next_page = current_page + 1
            print(f"[*] Đang chuyển sang trang {next_page}...")

            # Cách 1: Thử click nút Next trên giao diện để không reload lại toàn trang
            clicked_next = False
            try:
                next_btn = page.locator('button:has-text("Next"), a:has-text("Next"), [aria-label*="next" i], [aria-label*="Next" i], li.next a, button.next')
                if next_btn.count() > 0 and next_btn.first.is_visible():
                    next_btn.first.click()
                    clicked_next = True
                    print("[+] Đã click nút Next thành công.")
                    time.sleep(3)
            except Exception:
                clicked_next = False

            # Cách 2: Nếu click không được, điều hướng URL kèm tham số ?page=
            if not clicked_next:
                target_url = f"{BASE_URL}?page={next_page}"
                print(f"[*] Điều hướng URL: {target_url}")
                page.goto(target_url, timeout=30000)

            current_page = next_page
            time.sleep(2)

        context.close()

    print("\n" + "=" * 70)
    print(f"[✔] HOÀN TẤT CÀO DUN & BRADSTREET (D&B) SLOVAKIA!")
    print(f"[*] Tổng số doanh nghiệp thu thập: {total_saved:,}")
    print(f"[*] File kết quả lưu tại: {CSV_FILE}")
    print("=" * 70)

if __name__ == '__main__':
    scrape_dnb()
