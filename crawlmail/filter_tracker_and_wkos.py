# -*- coding: utf-8 -*-
"""
Doi chieu AT_AGCY_COMB_2COL.csv voi:
1. Mail Tracker (Mail Tracker - mail.csv): loai bo neu trung email.
2. WKOS CleanData ((xong 10_11) AT_AGCY_WKOS - CleanData.csv):
   - Xoa bo cty neu trung email da reply hoac cty da reply.
   - Xoa bo cty neu trung email loi (bounce / khong dung duoc).
3. Luu backup, xuat file log da xoa va dong bo lai:
   - AT_AGCY_COMB_2COL.csv
   - data/AT_AGCY_COMB_2COL.csv
   - AT_AGCY_GMAP_2COL.csv
   - data/AT_AGCY_REMOVED_TRACKER_BOUNCE.csv
"""

import sys
import os
import re
import csv
import shutil
import unicodedata
from pathlib import Path

# Cau hinh UTF-8 cho console Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

FILE_COMB = ROOT_DIR / "AT_AGCY_COMB_2COL.csv"
FILE_DATA_COMB = ROOT_DIR / "data" / "AT_AGCY_COMB_2COL.csv"
FILE_GMAP_COMB = ROOT_DIR / "AT_AGCY_GMAP_2COL.csv"
FILE_TRACKER = ROOT_DIR / "Mail Tracker - mail.csv"
FILE_CLEANDATA = ROOT_DIR / "(xong 10_11) AT_AGCY_WKOS - CleanData.csv"

BACKUP_COMB = ROOT_DIR / "data" / "AT_AGCY_COMB_2COL_pre_filter_backup.csv"
OUT_REMOVED_LOG = ROOT_DIR / "data" / "AT_AGCY_REMOVED_TRACKER_BOUNCE.csv"

from crawlmail.enrich_maps_at_agcy import (
    clean_company_name_at,
    is_valid_name_match_at
)

PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre', 'daigrė'
]

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in ['scandi standard', 'scandi-standard', 'scandi standart', 'biliarta', 'daigre'])

def extract_phone_key(phone_str):
    if not phone_str:
        return ""
    digits = re.sub(r'\D', '', str(phone_str))
    return digits[-8:] if len(digits) >= 8 else digits

def main():
    print("=" * 80)
    print("BAT DAU DOI CHIEU & LOC BO CONG TY TRUNG MAIL TRACKER / WKOS REPLY & BOUNCE")
    print(f"File COMB chinh       : {FILE_COMB}")
    print(f"File Mail Tracker     : {FILE_TRACKER}")
    print(f"File WKOS CleanData   : {FILE_CLEANDATA}")
    print("=" * 80)

    if not FILE_COMB.exists():
        print(f"[-] Khong tim thay file: {FILE_COMB}")
        return
    if not FILE_TRACKER.exists():
        print(f"[-] Khong tim thay file: {FILE_TRACKER}")
        return
    if not FILE_CLEANDATA.exists():
        print(f"[-] Khong tim thay file: {FILE_CLEANDATA}")
        return

    # 1. Đọc Mail Tracker
    tracker_emails = {}
    with open(FILE_TRACKER, 'r', encoding='utf-8-sig', errors='ignore') as f:
        tr_reader = csv.DictReader(f)
        for r in tr_reader:
            sender = r.get('Người gửi', '').strip().lower()
            subject = r.get('Subject', '').strip()
            content = r.get('Nội dung', '').strip()
            status = r.get('Tình trạng phản hồi', '').strip()
            note = status if status else (subject if subject else "Ghi nhận trong Mail Tracker")

            # Quét email từ người gửi
            for em in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', sender):
                if not any(k in em for k in ['glcquocte', 'workforce.asia', 'mobilityworks.asia']):
                    tracker_emails[em] = f"Mail Tracker (Người gửi: {note[:30]})"

            # Quét email từ nội dung
            for em in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', content.lower()):
                if not any(k in em for k in ['glcquocte', 'workforce.asia', 'mobilityworks.asia']):
                    if em not in tracker_emails:
                        tracker_emails[em] = f"Mail Tracker (Nội dung: {note[:30]})"

    print(f"[+] Da nap {len(tracker_emails):,} email tu Mail Tracker")

    # 2. Đọc WKOS CleanData
    wkos_replied_emails = {}
    wkos_replied_companies = []
    wkos_bounced_emails = {}

    with open(FILE_CLEANDATA, 'r', encoding='utf-8-sig', errors='ignore') as f:
        clean_reader = csv.DictReader(f)
        for r in clean_reader:
            c_name = r.get('Công ty', '').strip()
            c_email = r.get('Email', '').strip().lower()
            c_phone = r.get('SĐT', '').strip()
            c_phone_key = extract_phone_key(c_phone)
            st_reply = r.get('Trạng thái Reply', '').strip()

            c_norm = clean_company_name_at(c_name)
            c_tokens = tuple(sorted(set(t for t in c_norm.split() if len(t) > 2)))

            # Mail đã reply
            if 'reply' in st_reply.lower():
                if c_email:
                    wkos_replied_emails[c_email] = st_reply
                wkos_replied_companies.append({
                    'name': c_name,
                    'norm': c_norm,
                    'tokens': c_tokens,
                    'email': c_email,
                    'phone_key': c_phone_key,
                    'status': st_reply
                })

            # Mail lỗi (bounce)
            if any(k in st_reply.lower() for k in ['bounce', 'không dùng được', 'khong dung duoc', 'lỗi', 'loi']):
                if c_email:
                    wkos_bounced_emails[c_email] = st_reply

    print(f"[+] Da nap {len(wkos_replied_companies)} cong ty da reply tu CleanData")
    print(f"[+] Da nap {len(wkos_replied_emails)} email da reply tu CleanData")
    print(f"[+] Da nap {len(wkos_bounced_emails)} email loi (bounce) tu CleanData")

    # 3. Đọc dữ liệu Master COMB
    with open(FILE_COMB, 'r', encoding='utf-8-sig', errors='ignore') as f:
        comb_reader = csv.DictReader(f)
        fieldnames = list(comb_reader.fieldnames)
        comb_rows = list(comb_reader)

    total_initial = len(comb_rows)
    initial_with_email = len([r for r in comb_rows if r.get('Email', '').strip()])
    print(f"\n[*] Tong so dong hien tai trong AT_AGCY_COMB_2COL: {total_initial:,} (Co email: {initial_with_email:,})")

    # Backup trước khi lọc
    ROOT_DIR.joinpath("data").mkdir(exist_ok=True)
    shutil.copy2(FILE_COMB, BACKUP_COMB)
    print(f"[+] Da tao backup: {BACKUP_COMB.name}")

    # 4. Tiến hành đối chiếu & loại bỏ
    active_rows = []
    removed_rows = []

    for idx, r in enumerate(comb_rows):
        company = r.get('Company', '').strip()
        email = r.get('Email', '').strip().lower()
        phone = r.get('Phone', '').strip()
        phone_key = extract_phone_key(phone)
        norm_name = clean_company_name_at(company)
        tokens = tuple(sorted(set(t for t in norm_name.split() if len(t) > 2)))

        is_removed = False
        remove_reason = ""

        # A. Kiểm tra Permanent Blacklist
        if is_blacklisted_company(company):
            is_removed = True
            remove_reason = "Nam trong Blacklist cong ty co dinh"

        # B. Kiểm tra trùng Mail Tracker
        if not is_removed and email and email in tracker_emails:
            is_removed = True
            remove_reason = f"Trung Mail Tracker: {email} ({tracker_emails[email]})"

        # C. Kiểm tra trùng Email đã Reply trong CleanData
        if not is_removed and email and email in wkos_replied_emails:
            is_removed = True
            remove_reason = f"Trung Email da Reply trong CleanData: {email} ({wkos_replied_emails[email]})"

        # D. Kiểm tra công ty đã Reply trong CleanData (so khớp tên/SĐT)
        if not is_removed:
            for rep in wkos_replied_companies:
                # Trùng tên chuẩn hoá
                if norm_name and rep['norm'] and norm_name == rep['norm']:
                    is_removed = True
                    remove_reason = f"Cong ty da Reply trong CleanData: '{company}' == '{rep['name']}' ({rep['status']})"
                    break
                # Trùng token đảo tên
                if len(tokens) >= 2 and len(rep['tokens']) >= 2 and tokens == rep['tokens']:
                    is_removed = True
                    remove_reason = f"Cong ty da Reply trong CleanData (Dao ten): '{company}' ~ '{rep['name']}' ({rep['status']})"
                    break
                # Trùng SĐT
                if phone_key and rep['phone_key'] and phone_key == rep['phone_key']:
                    is_removed = True
                    remove_reason = f"Cong ty da Reply trong CleanData (Trung SDT): {phone} ({rep['status']})"
                    break
                # So khớp nghiêm ngặt
                matched, mtype = is_valid_name_match_at(company, rep['name'])
                if matched:
                    is_removed = True
                    remove_reason = f"Cong ty da Reply trong CleanData ({mtype}): '{company}' ~ '{rep['name']}' ({rep['status']})"
                    break

        # E. Kiểm tra trùng Email lỗi (Bounce) trong CleanData
        if not is_removed and email and email in wkos_bounced_emails:
            is_removed = True
            remove_reason = f"Trung Email loi (Bounce) trong CleanData: {email} ({wkos_bounced_emails[email]})"

        # Xử lý kết quả
        if is_removed:
            row_copy = dict(r)
            row_copy['Remove_Reason'] = remove_reason
            removed_rows.append(row_copy)
            print(f"  ❌ [LOAI BO] {company} | Email: {email or 'Trong'} | {remove_reason}")
        else:
            # Chuẩn hóa SĐT có dấu nháy đơn
            if phone and not phone.startswith("'"):
                r['Phone'] = f"'{phone}"
            active_rows.append(r)

    print("\n" + "=" * 80)
    print(f"📊 KET QUA LOC BO:")
    print(f"  - Tong so cong ty da bi loai bo : {len(removed_rows):,}")
    print(f"  - Tong so cong ty con lai        : {len(active_rows):,}")

    # 5. Đẩy 100% công ty có Email lên đầu danh sách
    with_email = [r for r in active_rows if r.get('Email', '').strip()]
    without_email = [r for r in active_rows if not r.get('Email', '').strip()]

    # Sắp xếp giảm dần theo Lead_Score trong nhóm có email
    try:
        with_email.sort(key=lambda x: float(x.get('Lead_Score', 0) or 0), reverse=True)
    except Exception:
        pass

    final_sorted_rows = with_email + without_email
    print(f"  - So cong ty CO EMAIL (day len dau): {len(with_email):,}")
    print(f"  - So cong ty CHUA CO EMAIL        : {len(without_email):,}")
    print("=" * 80)

    # 6. Ghi đè đồng bộ các file CSV
    targets = [FILE_COMB, FILE_DATA_COMB, FILE_GMAP_COMB]
    for target_path in targets:
        with open(target_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(final_sorted_rows)
        print(f"[OK] Da cap nhat: {target_path}")

    # 7. Xuất file log các công ty đã xoá
    if removed_rows:
        log_fieldnames = fieldnames + ['Remove_Reason']
        with open(OUT_REMOVED_LOG, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=log_fieldnames)
            writer.writeheader()
            writer.writerows(removed_rows)
        print(f"[OK] Da xuat log kiem toan cac cty bi loai: {OUT_REMOVED_LOG}")

    print("\n🎉 HOAN TAT LOC BO DU LIEU THANH CONG!")

if __name__ == '__main__':
    main()
