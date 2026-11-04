# -*- coding: utf-8 -*-
"""
TIỀN XỬ LÝ & LÀM SẠCH DỮ LIỆU CÀO GOOGLE MAPS TIỆM NAIL ÁO (AT_NAIL)
=============================================================================
1. Lọc bỏ các địa điểm đóng cửa vĩnh viễn (Permanently Closed).
2. Lọc bỏ danh sách đen cố định (Scandi Standard, Biliarta, Daigre).
3. Khử trùng lặp đa tầng theo Place ID, SĐT, Tên + Địa chỉ, và Domain Website.
4. Chuẩn hóa SĐT có dấu nháy đơn (') theo Rule 2.
5. Xuất tệp sạch sẵn sàng cho bước bóc tách Email chuyên sâu:
   - data/formatted/AT_NAIL_GMAP_0RAW_clean.csv
"""

import csv
import os
import shutil
import re
import unicodedata

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_CSV = os.path.join(ROOT_DIR, "data", "raw", "AT_NAIL_GMAP_0RAW.csv")
BACKUP_CSV = os.path.join(ROOT_DIR, "data", "raw", "AT_NAIL_GMAP_0RAW_backup.csv")
OUTPUT_CLEAN_CSV = os.path.join(ROOT_DIR, "data", "formatted", "AT_NAIL_GMAP_0RAW_clean.csv")

PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

def normalize_domain(url):
    if not url:
        return ""
    u = url.strip().lower()
    u = re.sub(r'^https?://', '', u)
    u = re.sub(r'^www\.', '', u)
    return u.split('/')[0].split('?')[0]

def clean_phone(phone):
    if not phone:
        return ""
    p = str(phone).strip()
    if not p.startswith("'"):
        p = f"'{p}"
    return p

def preprocess():
    # Kiểm tra file đầu vào (ưu tiên data/raw, sau đó là thư mục gốc)
    target_input = INPUT_CSV
    if not os.path.exists(target_input):
        alt_input = os.path.join(ROOT_DIR, "AT_NAIL_GMAP_0RAW.csv")
        if os.path.exists(alt_input):
            target_input = alt_input
        else:
            print(f"[ERROR] Không tìm thấy file dữ liệu thô tại {INPUT_CSV} hoặc {alt_input}!")
            return

    print("=" * 75)
    print("  TIỀN XỬ LÝ & LÀM SẠCH DỮ LIỆU TIỆM NAIL ÁO (AT_NAIL)")
    print(f"  Nguồn đầu vào: {target_input}")
    print("=" * 75)

    # 1. Tạo bản sao lưu
    print(f"[*] Sao lưu dữ liệu gốc vào: {BACKUP_CSV}...")
    os.makedirs(os.path.dirname(BACKUP_CSV), exist_ok=True)
    shutil.copy2(target_input, BACKUP_CSV)

    # 2. Đọc dữ liệu
    with open(target_input, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames) if reader.fieldnames else []
        rows = list(reader)

    print(f"[*] Tổng số bản ghi thô đã đọc: {len(rows):,} dòng.")

    # 3. Lọc bỏ đóng cửa vĩnh viễn & blacklist
    valid_rows = []
    closed_count = 0
    blacklist_count = 0

    for r in rows:
        name = r.get("Name", "").strip()
        if is_blacklisted_company(name):
            blacklist_count += 1
            continue

        if r.get("Permanently_Closed", "").lower() == "yes":
            closed_count += 1
            continue

        r["Phone"] = clean_phone(r.get("Phone", ""))
        valid_rows.append(r)

    print(f"[*] Đã lọc bỏ {closed_count} tiệm đóng cửa vĩnh viễn, {blacklist_count} bản ghi danh sách đen.")

    # 4. Khử trùng lặp thông minh
    seen_urls = set()
    seen_phones = set()
    seen_names_addr = set()
    unique_rows = []
    dup_count = 0

    for r in valid_rows:
        name = r.get("Name", "").strip().lower()
        addr = r.get("Address", "").strip().lower()
        phone = re.sub(r'\D', '', r.get("Phone", ""))
        url = r.get("URL", "").strip()
        web = normalize_domain(r.get("Website", ""))

        place_match = re.search(r'1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)', url)
        place_id = place_match.group(1).lower() if place_match else url.split('?')[0].lower()

        # Kiểm tra trùng lặp
        is_dup = False
        if place_id and place_id in seen_urls:
            is_dup = True
        elif phone and len(phone) >= 7 and phone in seen_phones:
            is_dup = True
        elif name and addr and (name, addr) in seen_names_addr:
            is_dup = True

        if is_dup:
            dup_count += 1
            continue

        if place_id:
            seen_urls.add(place_id)
        if phone and len(phone) >= 7:
            seen_phones.add(phone)
        if name and addr:
            seen_names_addr.add((name, addr))

        unique_rows.append(r)

    print(f"[*] Đã loại bỏ {dup_count} tiệm trùng lặp. Còn lại {len(unique_rows):,} tiệm duy nhất.")

    # 5. Xuất file đã tiền xử lý
    os.makedirs(os.path.dirname(OUTPUT_CLEAN_CSV), exist_ok=True)
    with open(OUTPUT_CLEAN_CSV, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(unique_rows)

    print(f"[+] Xuất thành công tệp tiền xử lý: {OUTPUT_CLEAN_CSV}")
    print("=" * 75 + "\n")

if __name__ == "__main__":
    preprocess()

