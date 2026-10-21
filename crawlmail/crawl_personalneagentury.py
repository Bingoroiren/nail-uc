# -*- coding: utf-8 -*-
"""
HỆ THỐNG CÀO DỮ LIỆU PERSONÁLNE AGENTÚRY SLOVAKIA (personalneagentury.sk)
-------------------------------------------------------------------------
Mục tiêu:
1. Cào toàn diện danh bạ các công ty tuyển dụng / cho thuê lao động tại Slovakia từ personalneagentury.sk.
2. Hỗ trợ cào trang chỉ định (ví dụ: strana/2) hoặc tự động cào toàn bộ các trang (strana/1 đến hết).
3. Chạy chế độ trực quan (headless=False) với Google Chrome, tự động vượt Cloudflare Turnstile kèm chuông báo \a.
4. Bóc tách chi tiết: Tên công ty, SĐT (chuẩn nháy đơn '), Email B2B, Website, Địa chỉ, Thành phố.
5. Xuất chuẩn 17 ký tự:
   - SK_AGCY_PERS_0RAW.csv (Dữ liệu thô đầy đủ thuộc tính)
   - SK_AGCY_PERS_2COL.csv (Chuẩn Cold Mail 20 cột, đẩy có email lên đầu)
"""

import sys
import os
import re
import csv
import json
import asyncio
import urllib.parse
from pathlib import Path
import pandas as pd
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT_DIR = Path("D:/glc/nail uc") if os.name == 'nt' else Path(".")
USER_DATA_DIR = ROOT_DIR / "chrome_user_data" / "personalne_chrome_profile"
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

OUT_RAW = ROOT_DIR / "SK_AGCY_PERS_0RAW.csv"
OUT_2COL = ROOT_DIR / "SK_AGCY_PERS_2COL.csv"
CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_personalneagentury.json"

HEADERS_20COL = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

HEADERS_RAW = [
    'No.', 'Name', 'Phone', 'Email', 'Web', 'Address', 'City', 'Detail_URL', 'Category', 'Source'
]

def clean_phone(raw):
    if not raw:
        return ""
    p = str(raw).strip()
    p = re.sub(r'^tel:\s*', '', p, flags=re.I)
    digits = re.sub(r'[^\d+]', '', p)
    if not digits:
        return ""
    clean_d = re.sub(r'[^\d]', '', digits)
    if len(clean_d) < 8 or len(clean_d) > 13:
        return ""
    if clean_d.startswith('421') and len(clean_d) == 12:
        res = f"+421 {clean_d[3:6]} {clean_d[6:9]} {clean_d[9:12]}"
    elif clean_d.startswith('0') and len(clean_d) == 10:
        res = f"+421 {clean_d[1:4]} {clean_d[4:7]} {clean_d[7:10]}"
    else:
        res = f"+{clean_d}" if not digits.startswith('+') else digits
    return f"'{res}" if not res.startswith("'") else res

def clean_email(raw):
    if not raw:
        return ""
    em = re.sub(r'^mailto:\s*', '', str(raw), flags=re.I).strip().lower().rstrip('.,;:')
    if any(k in em for k in ['wix', 'sentry', 'example', 'domain', 'support@', 'no-reply', 'asset', 'image']):
        return ""
    return em

async def wait_for_cloudflare(page):
    """Kiểm tra và tự động vượt bảo mật Cloudflare Turnstile."""
    notified = False
    
    while True:
        try:
            if page.is_closed():
                return False
                
            title = await page.title()
            content = await page.content()
            
            is_cf = (
                "Just a moment" in title 
                or "Bezpečnostná kontrola" in title 
                or "nie ste robot" in content
                or "cf-turnstile" in content
                or "challenges.cloudflare.com" in content
                or "chrome-error" in page.url
            )
            
            has_content = (
                "personálne agentúry" in content.lower() 
                or "personalne-agentury" in content.lower()
                or "company-info" in content.lower()
                or "gap-3" in content.lower()
            ) and not is_cf
            
            if has_content:
                return True
                
            if not notified:
                print("\a\n" + "!" * 75)
                print("[!] PHÁT HIỆN BẢO MẬT CLOUDFLARE TURNSTILE TRÊN MÀN HÌNH CHROME!")
                print("    Vui lòng click vào ô xác nhận 'Nie som robot' nếu hiển thị...")
                print("    Hệ thống cũng đang tự động click tìm ô xác nhận...")
                print("!" * 75 + "\n")
                notified = True
                
            # Thử click vào các frame Turnstile
            for f in page.frames:
                try:
                    if any(k in f.url for k in ["cloudflare", "challenge", "turnstile"]):
                        chk = await f.query_selector("input[type='checkbox'], .cb-lb, #challenge-stage, .ctp-checkbox-label")
                        if chk:
                            await chk.click()
                except Exception:
                    pass
                    
            await asyncio.sleep(2.0)
        except Exception:
            await asyncio.sleep(1.5)

async def parse_cards_from_page(html, base_url):
    """Bóc tách toàn bộ danh sách thẻ doanh nghiệp trên trang."""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("div.flex.flex-1.flex-col.gap-3")
    
    results = []
    for c in cards:
        h = c.find(["h2", "h3"])
        name = h.get_text(strip=True) if h else ""
        if not name:
            continue
            
        address = ""
        city = ""
        web = ""
        email = ""
        phone = ""
        detail_url = ""
        
        for a in c.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if "google.com/maps" in href:
                address = text
                parts = [p.strip() for p in address.split(',') if p.strip()]
                if len(parts) >= 2:
                    city = parts[-1]
            elif href.startswith("mailto:"):
                email = clean_email(href)
            elif href.startswith("tel:"):
                phone = clean_phone(href)
            elif href.startswith("http") and not any(k in href for k in ["google", "maps", "personalneagentury"]):
                web = href.rstrip('/')
            elif href.startswith("/personalne-agentury/"):
                detail_url = urllib.parse.urljoin(base_url, href)
                
        if not web:
            for text_node in c.stripped_strings:
                if text_node.startswith("http://") or text_node.startswith("https://"):
                    if "google" not in text_node and "personalneagentury" not in text_node:
                        web = text_node.rstrip('/')
                        break
                        
        results.append({
            "Name": name,
            "Address": address,
            "City": city,
            "Phone": phone,
            "Email": email,
            "Web": web,
            "Detail_URL": detail_url,
            "Category": "Personálne agentúry a ľudské zdroje",
            "Source": "personalneagentury.sk"
        })
    return results

def save_outputs(records):
    """Lưu và đồng bộ tự động ra cả 2 file: 0RAW và 2COL (100% email lên đầu)."""
    if not records:
        return
        
    # 1. Lưu file SK_AGCY_PERS_0RAW.csv
    with open(OUT_RAW, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS_RAW)
        writer.writeheader()
        for idx, r in enumerate(records, 1):
            row = dict(r)
            row["No."] = idx
            writer.writerow(row)
            
    # 2. Lưu file SK_AGCY_PERS_2COL.csv (chuẩn Cold Mail 20 cột, đẩy có email lên đầu)
    rows_2col = []
    for r in records:
        email = r.get("Email", "").strip()
        mail_link = f"mailto:{email}" if email else ""
        c_name = r.get("Name", "").strip()
        phone = r.get("Phone", "").strip()
        web = r.get("Web", "").strip()
        addr = r.get("Address", "").strip()
        cat = r.get("Category", "Personálne agentúry")
        
        row_2col = {
            'No.': 0,
            'Công ty': c_name,
            'Chức danh': '',
            'Người liên hệ': '',
            'SĐT': phone,
            'Liên Hệ': web,
            'Email': email,
            'Liên Hệ mail': mail_link,
            'Địa chỉ': addr,
            'Lương': '',
            'Ngày đăng': '',
            'Hạn tuyển': '',
            'Check gửi': 'Chưa gửi' if email else '',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': 0,
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': f"{cat} [Nguồn: personalneagentury.sk]"
        }
        rows_2col.append(row_2col)
        
    # Phân loại có email lên đầu
    has_em = [r for r in rows_2col if r['Email']]
    no_em = [r for r in rows_2col if not r['Email']]
    sorted_2col = has_em + no_em
    for idx, r in enumerate(sorted_2col, 1):
        r['No.'] = idx
        
    with open(OUT_2COL, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS_20COL)
        writer.writeheader()
        writer.writerows(sorted_2col)

async def run_scraper(target_page=2, scrape_all=False):
    print("=" * 80)
    print(" BẮT ĐẦU CÀO DỮ LIỆU TỪ: personalneagentury.sk")
    print(f" Chế độ: {'Cào tất cả các trang' if scrape_all else f'Cào trang {target_page}'}")
    print(" Trình duyệt: Google Chrome trực quan (Headless=False) - Tự động xử lý Turnstile")
    print("=" * 80 + "\n")
    
    records = []
    seen_names = set()
    
    # Nạp cache cũ nếu có
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
                for r in cached:
                    records.append(r)
                    seen_names.add(r["Name"].strip().lower())
            print(f"[*] Đã nạp từ Cache: {len(records)} công ty từ trước.")
        except Exception:
            pass

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            channel="chrome",
            headless=False,
            viewport={"width": 1280, "height": 800},
            locale="sk-SK",
            ignore_default_args=["--enable-automation"],
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
            ]
        )
        await browser.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        page = browser.pages[0] if browser.pages else await browser.new_page()
        
        # Xác định danh sách các trang cần cào
        pages_to_crawl = []
        if scrape_all:
            pages_to_crawl = list(range(1, 15))
        else:
            pages_to_crawl = [target_page]
            
        for page_num in pages_to_crawl:
            if page_num == 1:
                url = "https://personalneagentury.sk/personalne-agentury"
            else:
                url = f"https://personalneagentury.sk/personalne-agentury/strana/{page_num}"
                
            print(f"\n[+] Đang mở trang {page_num}: {url}...")
            try:
                await page.goto(url, timeout=30000)
            except Exception as e:
                pass
                
            passed = await wait_for_cloudflare(page)
            if not passed:
                print(f"[-] Không thể vượt Cloudflare ở trang {page_num}. Bỏ qua...")
                continue
                
            await asyncio.sleep(1.0)
            html = await page.content()
            page_cards = await parse_cards_from_page(html, url)
            
            if not page_cards:
                print(f"[*] Không tìm thấy thêm công ty ở trang {page_num}. Kết thúc phân trang.")
                if scrape_all:
                    break
                    
            print(f"[✔] Trang {page_num}: Bóc tách thành công {len(page_cards)} doanh nghiệp:")
            new_count = 0
            for card in page_cards:
                nm = card["Name"].strip()
                if nm.lower() in seen_names:
                    continue
                seen_names.add(nm.lower())
                records.append(card)
                new_count += 1
                em_str = card["Email"] if card["Email"] else "(Chưa có email)"
                ph_str = card["Phone"] if card["Phone"] else "(Chưa có SĐT)"
                print(f"   -> {nm:<35} | {ph_str:<18} | {em_str}")
                
            # Lưu tăng dần sau mỗi trang
            save_outputs(records)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
                
            await asyncio.sleep(1.5)
            
        # Đóng trình duyệt
        await browser.close()
        
    print("\n" + "=" * 80)
    print(" HOÀN TẤT TIẾN TRÌNH CÀO PERSONALNEAGENTURY.SK!")
    print(f" [*] Tổng số công ty thu thập được: {len(records)}")
    print(f" [*] Đã xuất file thô: {OUT_RAW.name}")
    print(f" [*] Đã xuất file chuẩn Cold Mail 20 cột: {OUT_2COL.name}")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    target = 2
    scrape_all = False
    if len(sys.argv) > 1:
        if sys.argv[1].lower() in ["all", "--all", "-a"]:
            scrape_all = True
        else:
            try:
                target = int(sys.argv[1])
            except ValueError:
                target = 2
    asyncio.run(run_scraper(target_page=target, scrape_all=scrape_all))
