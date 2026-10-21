# -*- coding: utf-8 -*-
"""
D&B Slovakia - Bóc tách chi tiết từng trang công ty (Detail Scraper):
Truy cập từng Detail_URL của 1,002 công ty thu thập được từ D&B để cào:
1. Địa chỉ chi tiết (Address: số nhà, tên đường, mã bưu điện)
2. Website chính thức của công ty
3. Người đại diện / Lãnh đạo (Key Principal)
4. Quy mô nhân sự (Employees)
5. Mô tả hoạt động (Description)

Lưu tăng dần (Incremental Auto-Save) vào csdl_sk_agcy/dnb_slovakia_agcy_detailed.csv
Hỗ trợ Resume 100% nếu tạm dừng.
"""

import sys
import os
import re
import csv
import time
from pathlib import Path
import pandas as pd
from playwright.sync_api import sync_playwright

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

OUTPUT_DIR = Path("D:/glc/nail uc/csdl_sk_agcy")
INPUT_CSV = OUTPUT_DIR / "dnb_slovakia_agcy_database.csv"
OUTPUT_CSV = OUTPUT_DIR / "dnb_slovakia_agcy_detailed.csv"
PROFILE_DIR = Path("D:/glc/nail uc/chrome_user_data/dnb_profile")

FIELDNAMES = [
    'No.', 'Company', 'Address', 'City', 'Region', 'Country', 'Website', 
    'Key_Principal', 'Employees', 'Description', 'Detail_URL', 'Source'
]

def enrich_dnb_details():
    print("=" * 70)
    print(" BẮT ĐẦU CÀO CHI TIẾT TỪNG TRANG CÔNG TY D&B SLOVAKIA")
    print("=" * 70)

    if not INPUT_CSV.exists():
        print(f"[-] Không tìm thấy file danh sách gốc: {INPUT_CSV}")
        return

    df_in = pd.read_csv(INPUT_CSV, dtype=str).fillna('')
    total_input = len(df_in)
    print(f"[*] Tổng số doanh nghiệp trong danh sách: {total_input:,}")

    # Đọc checkpoint đã có
    scraped_urls = set()
    total_saved = 0
    if OUTPUT_CSV.exists():
        with open(OUTPUT_CSV, 'r', encoding='utf-8-sig', errors='ignore') as f:
            reader = csv.DictReader(f)
            for r in reader:
                u = r.get('Detail_URL', '').strip()
                if u:
                    scraped_urls.add(u)
                    total_saved += 1
        print(f"[*] Đã cào chi tiết {total_saved:,} công ty trước đó. Sẽ cào tiếp các công ty còn lại...")
    else:
        with open(OUTPUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=FIELDNAMES)
            w.writeheader()

    remaining_items = []
    for idx, r in df_in.iterrows():
        durl = r.get('Detail_URL', '').strip()
        if durl and durl not in scraped_urls:
            remaining_items.append(r)

    print(f"[*] Số lượng công ty cần bóc tách chi tiết: {len(remaining_items):,}")
    if not remaining_items:
        print("[✓] Toàn bộ công ty đã được cào chi tiết hoàn tất!")
        return

    with sync_playwright() as p:
        print("[*] Đang khởi chạy Google Chrome thực tế (headless=False)...")
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            headless=False,
            viewport={'width': 1280, 'height': 800},
            args=['--disable-blink-features=AutomationControlled']
        )
        page = context.new_page()

        for idx, item in enumerate(remaining_items, 1):
            cname = item.get('Company', '').strip()
            durl = item.get('Detail_URL', '').strip()
            city = item.get('City', '').strip()
            region = item.get('Region', '').strip()
            country = item.get('Country', 'Slovakia').strip()

            address = ""
            website = ""
            key_principal = ""
            employees = ""
            description = ""

            try:
                page.goto(durl, timeout=25000)
                time.sleep(2.5)

                # Kiểm tra nếu bị Cloudflare chặn
                title = page.title()
                if 'Just a moment' in title:
                    print(f"\a[!] Phát hiện Cloudflare tại: {cname}. Đang đợi 5s...")
                    time.sleep(5)

                body_text = page.locator('body').inner_text()
                
                # Bóc tách bằng regex tối ưu
                addr_m = re.search(r'Address:\s*([^\n\r]+)', body_text)
                if addr_m:
                    address = addr_m.group(1).strip()

                web_m = re.search(r'Website:\s*([^\n\r]+)', body_text)
                if web_m:
                    website = web_m.group(1).strip()

                princ_m = re.search(r'Key Principal:\s*([^\n\r]+)', body_text)
                if princ_m:
                    key_principal = princ_m.group(1).strip()

                emp_m = re.search(r'Employees\s*\([^)]*\):\s*([^\n\r]+)', body_text)
                if emp_m:
                    employees = emp_m.group(1).strip()

                desc_m = re.search(r'Description:\s*([^\n\r]+)', body_text)
                if desc_m:
                    description = desc_m.group(1).strip()

            except Exception as e:
                print(f"[-] Lỗi tải {cname}: {e}")

            total_saved += 1
            rec = {
                'No.': total_saved,
                'Company': cname,
                'Address': address if address else item.get('Location', ''),
                'City': city,
                'Region': region,
                'Country': country,
                'Website': website,
                'Key_Principal': key_principal,
                'Employees': employees,
                'Description': description,
                'Detail_URL': durl,
                'Source': 'dnb.com'
            }

            # Ghi ngay vào CSV (Incremental Auto-Save)
            with open(OUTPUT_CSV, 'a', encoding='utf-8-sig', newline='') as af:
                w = csv.DictWriter(af, fieldnames=FIELDNAMES)
                w.writerow(rec)

            print(f"[{total_saved:>4}/{total_input}] {cname:<35} | Web: {website:<25} | Người đại diện: {key_principal}")
            time.sleep(1)

        context.close()

    print("\n" + "=" * 70)
    print(f"[✔] HOÀN TẤT BÓC TÁCH CHI TIẾT D&B SLOVAKIA!")
    print(f"[*] Tổng số công ty đã cào chi tiết: {total_saved:,}")
    print(f"[*] File lưu tại: {OUTPUT_CSV}")
    print("=" * 70)

if __name__ == '__main__':
    enrich_dnb_details()
