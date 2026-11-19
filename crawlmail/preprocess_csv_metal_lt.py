# -*- coding: utf-8 -*-
"""
PREPROCESS GOOGLE MAPS RAW DATA - LITHUANIAN METAL & FABRICATION FACTORIES (LT_METL_GMAP)
========================================================================================
Input:  LT_METL_GMAP_0RAW.csv
Output: Cleaned and Deduplicated LT_METL_GMAP_0RAW.csv
Rules:  GEMINI.md (Rule 1, 2, 10, 11, 12)
"""

import os
import sys
import re
import csv
import shutil
import unicodedata
from pathlib import Path

# Đảm bảo UTF-8 cho Windows Console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = ROOT_DIR / "LT_METL_GMAP_0RAW.csv"
RAW_DATA_CSV = ROOT_DIR / "data" / "raw" / "LT_METL_GMAP_0RAW.csv"
BACKUP_CSV = ROOT_DIR / "data" / "raw" / "LT_METL_GMAP_0RAW_backup.csv"

# Rule 12: Permanent blacklist companies
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

def clean_phone_lt(raw_phone):
    """Rule 2: Chuẩn hóa SĐT Litva luôn có nháy đơn (') ở đầu"""
    if not raw_phone or str(raw_phone).strip() in ['', 'None', 'nan']:
        return ""
    s = str(raw_phone).strip().lstrip("'").strip()
    digits = re.sub(r'[^0-9]', '', s)
    if not digits:
        return ""
    if digits.startswith('370'):
        pass
    elif digits.startswith('8') and len(digits) == 9:
        digits = '370' + digits[1:]
    elif digits.startswith('0') and (len(digits) == 9 or len(digits) == 10):
        digits = '370' + digits[1:]
    elif len(digits) == 8:
        digits = '370' + digits

    if digits.startswith('370') and len(digits) == 11:
        return f"'+370 {digits[3:5]} {digits[5:8]} {digits[8:]}"
    return f"'+{digits}"

def normalize_website(url):
    if not url:
        return ""
    u = url.strip()
    # Loại bỏ link redirect của Google nếu có
    if "google.com/url?q=" in u:
        m = re.search(r'google\.com/url\?q=([^&]+)', u)
        if m:
            u = urllib.parse.unquote(m.group(1))
    return u.split('?')[0].rstrip('/')

def preprocess():
    src_file = INPUT_CSV if INPUT_CSV.exists() else RAW_DATA_CSV
    if not src_file.exists():
        print(f"[!] Không tìm thấy tệp {INPUT_CSV.name} để tiền xử lý.")
        return

    print("=" * 80)
    print("🧹 TIỀN XỬ LÝ & KHỬ TRÙNG LẶP DỮ LIỆU KIM LOẠI LITVA (LT_METL_GMAP_0RAW)")
    print(f"   Tệp nguồn: {src_file}")
    print("=" * 80)

    # 1. Tạo bản sao lưu dự phòng an toàn
    BACKUP_CSV.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_file, BACKUP_CSV)
    print(f"[*] Đã sao lưu dữ liệu gốc vào: {BACKUP_CSV.name}")

    # 2. Đọc dữ liệu
    with open(src_file, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames) if reader.fieldnames else []
        rows = list(reader)

    print(f"[*] Đã nạp {len(rows):,} dòng dữ liệu thô.")

    # 3. Lọc trùng lặp & Loại trừ danh sách đen (Rule 12)
    seen_ids = set()
    unique_rows = []
    dup_count = 0
    blacklisted_count = 0

    for r in rows:
        name = str(r.get('Name', '')).strip()
        if not name:
            continue

        if is_blacklisted_company(name):
            blacklisted_count += 1
            continue

        # Định danh duy nhất theo Place ID hoặc Tên + SĐT + Thành phố
        url = r.get('URL', '')
        m_pid = re.search(r'1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)', url)
        pid = m_pid.group(1).lower() if m_pid else ""
        
        ph = clean_phone_lt(r.get('Phone', ''))
        r['Phone'] = ph
        r['Website'] = normalize_website(r.get('Website', ''))
        
        dedup_key = pid if pid else f"{name.lower()}::{ph}::{r.get('Location_Name', '').lower()}"
        
        if dedup_key in seen_ids:
            dup_count += 1
            continue
            
        seen_ids.add(dedup_key)
        unique_rows.append(r)

    print(f"[*] Đã loại bỏ {dup_count:,} dòng trùng lặp.")
    if blacklisted_count > 0:
        print(f"[*] Đã loại trừ {blacklisted_count:,} doanh nghiệp thuộc danh sách đen vĩnh viễn (Rule 12).")
    print(f"[*] Số doanh nghiệp kim loại hợp lệ còn lại: {len(unique_rows):,}")

    # 4. Lưu lại cả ở thư mục gốc và data/raw/
    for out_p in [INPUT_CSV, RAW_DATA_CSV]:
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, mode="w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(unique_rows)

    print(f"[+] Hoàn tất! Đã lưu dữ liệu làm sạch vào {INPUT_CSV.name} ({len(unique_rows):,} doanh nghiệp).\n")

if __name__ == "__main__":
    preprocess()

