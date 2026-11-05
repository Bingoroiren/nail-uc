# -*- coding: utf-8 -*-
"""
FILTER AND CLEAN BELGIUM MEAT DATASET (Rule 1, Rule 2, Rule 3, Rule 11, Rule 12)
================================================================================
Lọc danh sách thịt Bỉ (BE_MEAT):
- Chỉ giữ lại các công ty có EMAIL hoặc SĐT hợp lệ.
- Loại bỏ hoàn toàn 2,014 công ty không có thông tin liên hệ.
- Làm sạch triệt để icon glyphs (\\uE000-\\uF8FF: , ) trong SĐT và Địa chỉ.
- Loại bỏ 100% email sàn danh bạ địa phương (localservices.be, trendstop.be...) và đuôi file ảnh giả mạo (2x.jpg).
- Chuẩn hóa SĐT có nháy đơn '+' (Rule 2).
- Sắp xếp 100% công ty có Email lên đầu tệp CSV (Rule 3).
- Đồng bộ sang BE_MEAT_GMAP_2COL.csv, BE_MEAT_GMAP_1ENR.csv, BE_MEAT_2COL_READY.csv, csdl_mlt/ và archive/.
"""

import os
import sys
import re
import csv
import shutil
import urllib.parse
import unicodedata
from pathlib import Path

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

FILE_2COL = ROOT_DIR / "BE_MEAT_GMAP_2COL.csv"
FILE_1ENR = ROOT_DIR / "BE_MEAT_GMAP_1ENR.csv"
FILE_READY = ROOT_DIR / "BE_MEAT_2COL_READY.csv"
FILE_EMAILS_ONLY = ROOT_DIR / "BE_MEAT_ONLY_EMAILS_READY.csv"

# Rule 12: Danh sách đen vĩnh viễn
PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

def is_blacklisted_company(name):
    if not name or not isinstance(name, str):
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

def clean_phone_number(p):
    if not p or str(p).lower() in ['nan', 'none', '-', "'-", "''"]:
        return ""
    # Cắt bỏ ký tự icon font PUA (\ue000-\uf8ff như )
    s = re.sub(r'[\ue000-\uf8ff]', '', str(p))
    s = s.replace('\u00a0', ' ').replace('\xa0', ' ').replace('&nbsp;', ' ')
    s = re.sub(r'\s+', ' ', s).strip()
    s = re.sub(r"^[^\d+]+", '', s)
    digits = re.sub(r'\D', '', s)
    if not s or len(digits) < 5:
        return ""
    # Rule 2: Luôn có nháy đơn ở đầu
    return f"'{s}"

def clean_address(a):
    if not a or str(a).lower() in ['nan', 'none', '-']:
        return ""
    # Cắt bỏ icon pin \ue0c8 ()
    s = re.sub(r'[\ue000-\uf8ff]', '', str(a))
    s = s.replace('\u00a0', ' ').replace('\xa0', ' ').replace('&nbsp;', ' ')
    s = re.sub(r'[\r\n]+', ', ', s)
    s = re.sub(r'\s+', ' ', s).strip(' ,.-')
    return s

def clean_and_validate_email(email):
    if not email or str(email).lower() in ['nan', 'none', '-', '']:
        return ""
    em = urllib.parse.unquote(str(email).strip().lower())
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\ufeff', '\u202f', '\u3000']:
        em = em.replace(bad, '')
    em = re.sub(r'^mailto:\s*', '', em, flags=re.I)
    em = re.sub(r'\s+', '', em)
    em = em.strip(" .,;:\"'<>[](){}\\/")
    
    if '@' not in em or '.' not in em.split('@')[1]:
        return ""
    
    u, d = em.split('@', 1)
    
    # Loại file giả mạo email
    if any(em.endswith('.' + ext) for ext in ['jpg', 'png', 'gif', 'svg', 'webp', 'css', 'js', 'pdf', 'woff', 'ico']):
        return ""
        
    # Loại email sàn danh bạ địa phương, theme builder, tracking
    junk_domains = [
        'localservices.be', 'bizbook.be', 'pagesdor.be', 'goudengids.be', 'trendstop.be',
        'trendstop.knack.be', 'staatsbladmonitor.be', 'horaires-societe.com', 'wixpress.com',
        'sentry.io', 'example.com', 'domain.com', 'email.com', 'jouwweb.nl', 'yourdomain.com',
        'schema.org', 'test.com', 'sample.com'
    ]
    if any(jd == d or d.endswith('.' + jd) for jd in junk_domains):
        return ""
        
    # Loại user rác
    if any(u.startswith(ju) for ju in ['youremail', 'your-email', 'someone', 'nobody', 'no-reply', 'noreply', 'donotreply', 'privacy', 'gdpr', 'abuse']):
        return ""
        
    return em

def filter_and_clean_meat():
    print("=" * 80)
    print("🥩  LỌC DANH SÁCH THỊT BỈ (CHỈ GIỮ CÔNG TY CÓ EMAIL HOẶC SĐT)")
    print("=" * 80)

    if not FILE_2COL.exists():
        print(f"[!] Không tìm thấy tệp {FILE_2COL.name}")
        return

    # 1. Đọc và lọc tệp 2COL
    with open(FILE_2COL, mode='r', encoding='utf-8-sig') as f:
        reader_2col = list(csv.DictReader(f))
    
    total_raw_2col = len(reader_2col)
    fieldnames_2col = list(reader_2col[0].keys())

    cleaned_2col = []
    valid_company_names = set()

    for r in reader_2col:
        c_name = r.get('Công ty', '').strip()
        if is_blacklisted_company(c_name):
            continue

        valid_email = clean_and_validate_email(r.get('Email', ''))
        valid_phone = clean_phone_number(r.get('SĐT', ''))
        valid_addr = clean_address(r.get('Địa chỉ', ''))

        if valid_email or valid_phone:
            item = dict(r)
            item['Email'] = valid_email
            item['SĐT'] = valid_phone
            item['Địa chỉ'] = valid_addr
            cleaned_2col.append(item)
            valid_company_names.add(c_name.lower())

    # Sắp xếp 100% công ty có Email lên đầu (Rule 3)
    with_email_2col = [r for r in cleaned_2col if r['Email']]
    without_email_2col = [r for r in cleaned_2col if not r['Email']]
    sorted_2col = with_email_2col + without_email_2col

    for i, r in enumerate(sorted_2col, 1):
        r['No.'] = i

    # Ghi tệp BE_MEAT_GMAP_2COL.csv và BE_MEAT_2COL_READY.csv
    with open(FILE_2COL, mode='w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames_2col)
        writer.writeheader()
        writer.writerows(sorted_2col)
    print(f"[✓] Đã cập nhật tệp chuẩn Cold Mail 20 cột: {FILE_2COL.name} ({len(sorted_2col):,} dòng)")

    with open(FILE_READY, mode='w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames_2col)
        writer.writeheader()
        writer.writerows(sorted_2col)
    print(f"[✓] Đã tạo tệp tiện ích sẵn sàng gửi: {FILE_READY.name} ({len(sorted_2col):,} dòng)")

    # Ghi tệp riêng các công ty chỉ có Email (phục vụ Cold Email chiến dịch cao điểm)
    with open(FILE_EMAILS_ONLY, mode='w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames_2col)
        writer.writeheader()
        for i, r in enumerate(with_email_2col, 1):
            r_copy = dict(r)
            r_copy['No.'] = i
            writer.writerow(r_copy)
    print(f"[✓] Đã tạo tệp chỉ có EMAIL: {FILE_EMAILS_ONLY.name} ({len(with_email_2col):,} dòng)")

    # 2. Đồng bộ làm sạch cho cả tệp 1ENR (nếu có)
    if FILE_1ENR.exists():
        with open(FILE_1ENR, mode='r', encoding='utf-8-sig') as f:
            reader_1enr = list(csv.DictReader(f))
        fieldnames_1enr = list(reader_1enr[0].keys())

        cleaned_1enr = []
        for r in reader_1enr:
            c_name = r.get('Company_Name', '').strip()
            if is_blacklisted_company(c_name):
                continue
            
            valid_email = clean_and_validate_email(r.get('Email', ''))
            valid_phone = clean_phone_number(r.get('Phone', ''))
            valid_addr = clean_address(r.get('Maps_Address') or r.get('Address') or '')

            if valid_email or valid_phone:
                item = dict(r)
                item['Email'] = valid_email
                item['Phone'] = valid_phone
                if item.get('Maps_Address'):
                    item['Maps_Address'] = clean_address(item['Maps_Address'])
                cleaned_1enr.append(item)

        # Sắp xếp có email lên đầu
        with_email_1enr = [r for r in cleaned_1enr if r.get('Email')]
        without_email_1enr = [r for r in cleaned_1enr if not r.get('Email')]
        sorted_1enr = with_email_1enr + without_email_1enr

        with open(FILE_1ENR, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames_1enr)
            writer.writeheader()
            writer.writerows(sorted_1enr)
        print(f"[✓] Đã đồng bộ làm sạch tệp làm giàu: {FILE_1ENR.name} ({len(sorted_1enr):,} dòng)")

    # 3. Đồng bộ vào csdl_mlt/ và archive/be_belgium/
    sync_dirs = [ROOT_DIR / "csdl_mlt", ROOT_DIR / "archive" / "be_belgium"]
    for d in sync_dirs:
        d.mkdir(parents=True, exist_ok=True)
        shutil.copy2(FILE_2COL, d / FILE_2COL.name)
        shutil.copy2(FILE_READY, d / FILE_READY.name)
        shutil.copy2(FILE_EMAILS_ONLY, d / FILE_EMAILS_ONLY.name)
        if FILE_1ENR.exists():
            shutil.copy2(FILE_1ENR, d / FILE_1ENR.name)
        print(f"[✓] Đã đồng bộ sang thư mục: {d.name}/")

    print("=" * 80)
    print("📊 THỐNG KÊ KẾT QUẢ LỌC DANH SÁCH THỊT BỈ:")
    print(f"   - Tổng số doanh nghiệp ban đầu       : {total_raw_2col:,}")
    print(f"   - Đã loại bỏ (không có email và sđt) : {total_raw_2col - len(sorted_2col):,}")
    print(f"   - DOANH NGHIỆP CÒN LẠI (CÓ THÔNG TIN): {len(sorted_2col):,}")
    print(f"     + Có EMAIL (đẩy lên đầu)           : {len(with_email_2col):,} ({len(with_email_2col)*100/len(sorted_2col):.1f}%)")
    print(f"     + Có SĐT                           : {sum(1 for r in sorted_2col if r['SĐT']):,} ({sum(1 for r in sorted_2col if r['SĐT'])*100/len(sorted_2col):.1f}%)")
    print(f"     + Có CẢ HAI (Email + SĐT)          : {sum(1 for r in sorted_2col if r['Email'] and r['SĐT']):,}")
    print(f"     + Chỉ có SĐT                       : {len(without_email_2col):,}")
    print("=" * 80)

if __name__ == '__main__':
    filter_and_clean_meat()

