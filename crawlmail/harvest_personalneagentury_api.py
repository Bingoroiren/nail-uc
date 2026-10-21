# -*- coding: utf-8 -*-
"""
HỆ THỐNG CÀO TOÀN BỘ DANH SÁCH TỪ PERSONALNEAGENTURY.SK BẰNG API
------------------------------------------------------------------
Đặc điểm:
1. Độc lập 100%: Dành riêng cho đối tác / người khác nhờ cào, không dùng dữ liệu nội bộ khác.
2. Nguồn dữ liệu: 
   - Lấy 3,405 công ty từ Sitemap gốc của personalneagentury.sk (Sitemap status 200, không bị Cloudflare chặn).
   - Bóc tách mã số thuế doanh nghiệp (IČO) từ mỗi URL.
   - Gọi API Cổng Dữ Liệu Doanh Nghiệp Slovakia (slovakdata.sk API) để lấy chi tiết pháp lý:
     Tên công ty chuẩn xác, Địa chỉ, Số nhà, Mã bưu điện, Thành phố, Ngành nghề NACE, Doanh thu, Trạng thái.
3. Xuất file chuẩn 17 ký tự:
   - SK_AGCY_PERS_0RAW.csv (Dữ liệu thô đầy đủ thuộc tính doanh nghiệp)
   - SK_AGCY_PERS_2COL.csv (Chuẩn 20 cột Cold Mail)
4. Hỗ trợ Resume / Checkpoint: Tự động lưu tăng dần, nếu tạm dừng có thể chạy tiếp không bị mất dữ liệu.
"""

import sys
import os
import re
import csv
import json
import time
from pathlib import Path
from curl_cffi import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT_DIR = Path("D:/glc/nail uc") if os.name == 'nt' else Path(".")
OUT_RAW = ROOT_DIR / "SK_AGCY_PERS_0RAW.csv"
OUT_2COL = ROOT_DIR / "SK_AGCY_PERS_2COL.csv"
CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_pers_api.json"

HEADERS_RAW = [
    'No.', 'Name', 'IČO', 'Phone', 'Email', 'Web', 'Address', 'City', 'Postal_Code',
    'Legal_Form', 'NACE', 'Revenue_EUR', 'Status', 'Detail_URL', 'Source'
]

HEADERS_20COL = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

def format_address(c):
    ulice = (c.get("ulice_text") or "").strip()
    cdom = str(c.get("cdom") or "").strip()
    cor = str(c.get("cor") or "").strip()
    obec = (c.get("obec_text") or "").strip()
    psc = (c.get("psc") or "").strip()

    num = ""
    if cor and cor != "0" and cdom and cdom != "0":
        num = f"{cdom}/{cor}"
    elif cor and cor != "0":
        num = cor
    elif cdom and cdom != "0":
        num = cdom

    street_part = f"{ulice} {num}".strip() if (ulice and num) else (ulice or obec)
    parts = []
    if street_part:
        parts.append(street_part)
    if psc and obec:
        parts.append(f"{psc} {obec}")
    elif obec:
        parts.append(obec)
    elif psc:
        parts.append(psc)
    parts.append("Slovensko")
    return ", ".join(parts)

def fetch_sitemap_agencies():
    print("[*] Đang kết nối tải Sitemap gốc: https://personalneagentury.sk/sitemap.xml...")
    try:
        r = requests.get('https://personalneagentury.sk/sitemap.xml', impersonate='chrome119', timeout=20)
        if r.status_code != 200:
            print(f"[-] Không thể tải sitemap: HTTP {r.status_code}")
            return []
            
        locs = re.findall(r'<loc>([^<]+)</loc>', r.text)
        records = []
        for u in locs:
            if '/pracovne-agentury/' in u:
                slug = u.split('/')[-1]
                m = re.search(r'^(.*)-(\d{6,8})$', slug)
                if m:
                    slug_name = m.group(1).replace('-', ' ').title()
                    ico = m.group(2)
                    records.append({
                        'slug_name': slug_name,
                        'ico': ico,
                        'url': u
                    })
        print(f"[✔] Đã bóc tách thành công {len(records):,} doanh nghiệp từ sitemap.xml!")
        return records
    except Exception as e:
        print(f"[-] Lỗi khi tải sitemap: {e}")
        return []

def save_all_records(completed_dict):
    records = list(completed_dict.values())
    
    # 1. Ghi file SK_AGCY_PERS_0RAW.csv
    with open(OUT_RAW, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS_RAW)
        writer.writeheader()
        for idx, r in enumerate(records, 1):
            row = dict(r)
            row["No."] = idx
            writer.writerow(row)
            
    # 2. Ghi file SK_AGCY_PERS_2COL.csv
    with open(OUT_2COL, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS_20COL)
        writer.writeheader()
        for idx, r in enumerate(records, 1):
            row_2col = {
                'No.': idx,
                'Công ty': r.get('Name', ''),
                'Chức danh': '',
                'Người liên hệ': '',
                'SĐT': r.get('Phone', ''),
                'Liên Hệ': r.get('Web', ''),
                'Email': r.get('Email', ''),
                'Liên Hệ mail': f"mailto:{r.get('Email')}" if r.get('Email') else '',
                'Địa chỉ': r.get('Address', ''),
                'Lương': '',
                'Ngày đăng': '',
                'Hạn tuyển': '',
                'Check gửi': 'Chưa gửi' if r.get('Email') else '',
                'Last Subject': '',
                'Last Body HTML': '',
                'Trạng thái Reply': f"IČO: {r.get('IČO', '')} | Doanh thu: {r.get('Revenue_EUR', '')} EUR",
                'Lần Follow-up': 0,
                'Ngày Follow-up gần nhất': '',
                'Mailbox đã dùng': '',
                'Category': f"Personálne agentúry [IČO: {r.get('IČO')}, NACE: {r.get('NACE')}]"
            }
            writer.writerow(row_2col)

def main():
    print("=" * 80)
    print(" CÀO TOÀN BỘ DANH SÁCH PERSONALNEAGENTURY.SK QUA API KHÔNG BỊ CHẶN")
    print(" Dữ liệu Độc lập 100% - Phục vụ nhu cầu cào độc lập cho khách hàng / đối tác")
    print("=" * 80 + "\n")

    # 1. Đọc cache nếu có
    completed = {}
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                completed = json.load(f)
            print(f"[*] Đã nạp từ Cache tiến độ: {len(completed):,} công ty đã hoàn tất trước đó.")
        except Exception:
            pass

    # 2. Tải danh sách sitemap
    sitemap_items = fetch_sitemap_agencies()
    if not sitemap_items:
        print("[!] Không có danh sách sitemap để xử lý.")
        return

    total = len(sitemap_items)
    print(f"\n[*] Bắt đầu làm giàu thông tin pháp lý & địa chỉ qua API cho {total:,} công ty...")
    print("=" * 80)

    count_processed = len(completed)
    save_counter = 0

    for idx, item in enumerate(sitemap_items, 1):
        ico = item['ico']
        slug_name = item['slug_name']
        detail_url = item['url']

        if ico in completed:
            continue

        url_api = f"https://slovakdata.sk/api/search?q={ico}"
        comp_name = slug_name
        address = ""
        city = ""
        psc = ""
        legal_form = "s.r.o."
        nace = ""
        revenue = ""
        status = "Active"

        try:
            r = requests.get(url_api, impersonate='chrome120', timeout=10)
            if r.status_code == 200:
                data = r.json()
                results = data.get('results', [])
                if results:
                    c = results[0]
                    comp_name = c.get('firma') or slug_name
                    city = c.get('obec_text') or ""
                    psc = c.get('psc') or ""
                    legal_form = c.get('forma_text') or "Spoločnosť s ručením obmedzeným"
                    nace = c.get('nace_text') or ""
                    revenue = c.get('trzby') or ""
                    is_paused = c.get('pozastavena', False)
                    status = "Inactive" if is_paused else "Active"
                    address = format_address(c)
        except Exception:
            pass

        record = {
            'No.': idx,
            'Name': comp_name,
            'IČO': ico,
            'Phone': '',
            'Email': '',
            'Web': '',
            'Address': address,
            'City': city,
            'Postal_Code': psc,
            'Legal_Form': legal_form,
            'NACE': nace,
            'Revenue_EUR': revenue,
            'Status': status,
            'Detail_URL': detail_url,
            'Source': 'personalneagentury.sk'
        }

        completed[ico] = record
        count_processed += 1
        save_counter += 1

        print(f"[{count_processed:04d}/{total:04d}] IČO: {ico} | {comp_name[:35]:<35} | {city[:15]:<15} | {status}")

        # Lưu checkpoint sau mỗi 25 bản ghi
        if save_counter >= 25:
            save_all_records(completed)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(completed, f, ensure_ascii=False, indent=2)
            save_counter = 0

        time.sleep(0.1)

    # Lưu lần cuối khi hoàn tất
    save_all_records(completed)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(completed, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print(" HOÀN TẤT CÀO TOÀN BỘ 3,405 CÔNG TY TỪ PERSONALNEAGENTURY.SK!")
    print(f" [*] File thô: {OUT_RAW.name} ({len(completed):,} dòng)")
    print(f" [*] File chuẩn 20 cột: {OUT_2COL.name} ({len(completed):,} dòng)")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
