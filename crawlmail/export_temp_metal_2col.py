# -*- coding: utf-8 -*-
"""
EXPORT TEMPORARY COLD MAIL DATASET - BELGIUM METAL
=================================================
Xuất file Cold Mail 20 cột tạm thời từ kết quả KBO Backfill (1,181 email)
và gộp thêm các công ty vừa được Google Maps làm giàu trong cache.
Không gây xung đột hoặc ảnh hưởng đến tiến trình enrich_maps_be_metal đang chạy!
"""

import os
import sys
import re
import csv
import json
import unicodedata
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

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

def clean_phone(p):
    if not p:
        return ""
    p_str = str(p).strip()
    return f"'{p_str}" if not p_str.startswith("'") else p_str

def clean_email(em):
    if not em:
        return ""
    e = str(em).strip().lower()
    e = e.replace('\xa0', '').replace('\u00a0', '').replace('%20', '')
    return e.strip(' .,;')

COL_20_HEADERS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ', 'Email', 
    'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển', 'Check gửi', 
    'Last Subject', 'Last Body HTML', 'Trạng thái Reply', 'Lần Follow-up', 
    'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

def export_temp_2col():
    raw_csv = ROOT_DIR / "BE_METL_KBO0_0RAW.csv"
    maps_cache_file = ROOT_DIR / "crawlmail" / "cache_enrich_maps_be_metal.json"
    out_csv = ROOT_DIR / "BE_METL_KBO0_2COL.csv"
    csdl_csv = ROOT_DIR / "csdl_mlt" / "BE_METL_KBO0_2COL.csv"

    # Đọc cache maps hiện tại (nếu có)
    maps_cache = {}
    if maps_cache_file.exists():
        try:
            with open(maps_cache_file, 'r', encoding='utf-8') as f:
                maps_cache = json.load(f)
            print(f"[*] Đọc thành công {len(maps_cache):,} bản ghi từ Maps cache.")
        except Exception as e:
            print(f"[!] Chú ý khi đọc maps cache: {e}")

    # Đọc file RAW (14,316 công ty đã có 1,181 email KBO)
    rows_raw = []
    with open(raw_csv, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows_raw.append(r)

    print(f"[*] Đọc thành công {len(rows_raw):,} bản ghi từ {raw_csv.name}.")

    rows_2col = []
    for r in rows_raw:
        c_name = r.get('Company_Name', '').strip()
        if not c_name or is_blacklisted_company(c_name):
            continue

        kbo_num = r.get('KBO_Number', '').strip()
        clean_kbo = re.sub(r'[^0-9]', '', kbo_num)
        postcode = r.get('Postcode', '').strip()
        unique_key = f"kbo_{clean_kbo}" if len(clean_kbo) == 10 else f"{c_name}_{postcode}"

        # Kiểm tra nếu đã có trong maps cache
        maps_item = maps_cache.get(unique_key)

        if maps_item:
            # Bỏ qua nếu Maps đánh dấu đã đóng cửa
            if maps_item.get('Permanently_Closed') == 'Yes':
                continue
            phone = clean_phone(maps_item.get('Phone') or r.get('Phone', ''))
            email = clean_email(maps_item.get('Email') or r.get('Email', ''))
            addr = maps_item.get('Maps_Address') or maps_item.get('Address') or r.get('Address', '')
            cat = maps_item.get('Maps_Category') or r.get('Activity') or 'Metal Construction'
        else:
            phone = clean_phone(r.get('Phone', ''))
            email = clean_email(r.get('Email', ''))
            addr = r.get('Address', '')
            cat = r.get('Activity') or 'Metal Construction'

        rows_2col.append({
            'No.': 0,
            'Công ty': c_name,
            'Chức danh': '',
            'Người liên hệ': '',
            'SĐT': phone,
            'Liên Hệ': '',
            'Email': email,
            'Liên Hệ mail': '',
            'Địa chỉ': addr,
            'Lương': '',
            'Ngày đăng': '',
            'Hạn tuyển': '',
            'Check gửi': '',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': cat
        })

    # Rule 3: Đẩy 100% doanh nghiệp có Email lên đầu danh sách
    with_email = [r for r in rows_2col if r['Email']]
    without_email = [r for r in rows_2col if not r['Email']]
    sorted_2col = with_email + without_email

    for idx, r in enumerate(sorted_2col, start=1):
        r['No.'] = idx

    # Ghi file chuẩn CSV UTF-8 with BOM
    for target in [out_csv, csdl_csv]:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=COL_20_HEADERS)
            writer.writeheader()
            writer.writerows(sorted_2col)
        print(f"[+] Đã xuất file: {target}")

    print("\n" + "=" * 70)
    print("🏆 KẾT QUẢ XUẤT FILE COLD MAIL TẠM THỜI (BE_METL_KBO0_2COL.csv):")
    print(f"   - Tổng số doanh nghiệp hoạt động   : {len(sorted_2col):,}")
    print(f"   - Doanh nghiệp có EMAIL (lên đầu)  : {len(with_email):,} ({len(with_email)*100/len(sorted_2col):.1f}%)")
    print(f"   - Doanh nghiệp có SĐT              : {len([r for r in sorted_2col if r['SĐT']]):,}")
    print("=" * 70 + "\n")

if __name__ == '__main__':
    export_temp_2col()
