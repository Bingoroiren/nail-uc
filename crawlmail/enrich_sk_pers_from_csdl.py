#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ĐỐI CHIẾU & LÀM GIÀU DỮ LIỆU SK_AGCY_PERS_0RAW.CSV TỪ CSDL NỘI BỘ
Nguồn CSDL đối chiếu:
1. SK_AGCY_ALL_2COL.csv & csdl_sk_agcy/SK_AGCY_ALL_2COL.csv
2. data/formatted/SK_UDZC_UPSV_1ENR.csv & SK_UDZC_UPSV_2COL.csv
3. data/formatted/SK_ADZC_UPSV_1ENR.csv & SK_ADZC_UPSV_2COL.csv
4. csdl_sk_agcy/dnb_slovakia_agcy_detailed.csv
5. SK_AGCY_SAN_SANG_GUI.csv & SK_AGCY_LEAD_MOI_CHUA_GUI.csv
6. data/formatted/SK_AUTO_GMAP_1ENR.csv & SK_CONT_STAV_2COL.csv
7. archive/sk_old_industries/*.csv
"""

import os
import sys
import re
import glob
import json
import unicodedata
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_TARGET = BASE_DIR / "SK_AGCY_PERS_0RAW.csv"
OUTPUT_1ENR = BASE_DIR / "SK_AGCY_PERS_1ENR.csv"
OUTPUT_2COL = BASE_DIR / "SK_AGCY_PERS_2COL.csv"

COLDMAIL_COLUMNS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

# Rule #12: Permanent Blacklist
PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre', 'daigre'
]

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

def norm_name(s):
    if not s or not isinstance(s, str):
        return ""
    n = unicodedata.normalize('NFKD', s).lower()
    n = ''.join(c for c in n if not unicodedata.combining(c))
    for legal in ['s.r.o.', 's. r. o.', 'spol. s r.o.', 'a.s.', 'a. s.', 'k.s.', 'v.o.s.', 'sro', 'as', 'spol s r.o.']:
        n = re.sub(r'\b' + re.escape(legal) + r'\b', '', n)
    n = re.sub(r'[^\w\s]', ' ', n)
    return ' '.join(n.split())

def clean_ico(v):
    if not v or pd.isna(v):
        return ""
    m = re.search(r'\b\d{6,8}\b', str(v).strip())
    if m:
        return m.group(0).zfill(8)
    return ""

def clean_phone_sk(phone):
    if not phone or not isinstance(phone, str) or phone.strip() in ['nan', '', 'None']:
        return ""
    p = re.sub(r"[^\d+]", "", phone.strip().lstrip("'"))
    if not p:
        return ""
    if p.startswith("0") and len(p) == 10:
        p = "+421" + p[1:]
    elif not p.startswith("+") and len(p) == 9:
        p = "+421" + p
    return f"'{p}" if not p.startswith("'") else p

def is_valid_email(email):
    if not email or not isinstance(email, str) or email.strip() in ['nan', '', 'None']:
        return False
    e = email.strip().lower().replace('%20', '')
    if '@' not in e or '.' not in e or ' ' in e:
        return False
    if any(k in e for k in ['sentry', 'wixpress', 'example', 'yourdomain', 'domain.com', 'email.com', 'test@']):
        return False
    return True

def score_email_b2b(email, domain=""):
    if not is_valid_email(email):
        return -1
    e = email.lower().strip()
    u, _, d = e.partition('@')
    score = 0
    if domain and domain in d:
        score += 50
    hr_keys = ['praca', 'kariera', 'hr', 'personalne', 'jobs', 'recruitment', 'nabor', 'career']
    boss_keys = ['vedenie', 'riaditel', 'konatel', 'ceo', 'director', 'manager', 'obchod', 'sales']
    contact_keys = ['info', 'kontakt', 'contact', 'office', 'biuro', 'sekretariat', 'recepcia', 'kancelaria']
    if any(k in u for k in hr_keys):
        score += 50
    elif any(k in u for k in boss_keys):
        score += 45
    elif any(k in u for k in contact_keys):
        score += 40
    elif '.' in u or '_' in u:
        score += 25
    elif d in ['gmail.com', 'zoznam.sk', 'seznam.cz', 'azet.sk', 'post.sk', 'centrum.sk']:
        score += 10
    else:
        score += 20
    return score

def main():
    print("=" * 80)
    print(" LÀM GIÀU SK_AGCY_PERS_0RAW.CSV BẰNG CSDL CÓ SẴN TRONG WORKSPACE")
    print(f" Target File: {INPUT_TARGET}")
    print("=" * 80)

    if not INPUT_TARGET.exists():
        print(f"[!] Khong tim thay file {INPUT_TARGET}!")
        return

    df_target = pd.read_csv(INPUT_TARGET, encoding='utf-8-sig', dtype=str).fillna('')
    print(f"[*] Tong so dong trong target: {len(df_target):,}")

    # Build lookup index from target
    target_by_ico = {}
    target_by_name = {}

    for idx, r in df_target.iterrows():
        comp_name = r.get('Name', '').strip()
        ico = clean_ico(r.get('IČO'))
        nm = norm_name(comp_name)
        if ico:
            target_by_ico[ico] = idx
        if nm:
            target_by_name[nm] = idx

    print(f"[*] Chi muc ICO: {len(target_by_ico):,} | Chi muc Ten: {len(target_by_name):,}")

    # Danh sách các tệp CSDL ưu tiên theo thứ tự độ tin cậy
    csdl_priority_files = [
        # Nhóm 1: CSDL Môi giới & Cold Mail chính thức
        BASE_DIR / "SK_AGCY_ALL_2COL.csv",
        BASE_DIR / "SK_AGCY_SAN_SANG_GUI.csv",
        BASE_DIR / "SK_AGCY_LEAD_MOI_CHUA_GUI.csv",
        BASE_DIR / "csdl_sk_agcy" / "SK_AGCY_ALL_1ENR.csv",
        BASE_DIR / "csdl_sk_agcy" / "SK_AGCY_ALL_2COL.csv",
        # Nhóm 2: Dữ liệu chính phủ UPSV (ADZ & SZU)
        BASE_DIR / "data" / "formatted" / "SK_UDZC_UPSV_1ENR.csv",
        BASE_DIR / "data" / "formatted" / "SK_UDZC_UPSV_2COL.csv",
        BASE_DIR / "data" / "formatted" / "SK_ADZC_UPSV_1ENR.csv",
        BASE_DIR / "data" / "formatted" / "SK_ADZC_UPSV_2COL.csv",
        # Nhóm 3: D&B Chi tiết
        BASE_DIR / "csdl_sk_agcy" / "dnb_slovakia_agcy_detailed.csv",
        BASE_DIR / "csdl_sk_agcy" / "SK_AGCY_DNB_1ENR.csv",
        BASE_DIR / "csdl_sk_agcy" / "SK_AGCY_DNB_2COL.csv",
        # Nhóm 4: Các nguồn khác
        BASE_DIR / "Mail Tracker - mail.csv",
        BASE_DIR / "data" / "formatted" / "SK_AUTO_GMAP_1ENR.csv",
        BASE_DIR / "data" / "formatted" / "SK_CONT_STAV_2COL.csv",
        BASE_DIR / "archive" / "sk_old_industries" / "SK_UDZC_UPSV_2COL.csv",
        BASE_DIR / "archive" / "sk_old_industries" / "SK_ADZC_UPSV_2COL.csv",
        BASE_DIR / "archive" / "sk_old_industries" / "SK_AGCY_WEBD_2COL.csv"
    ]

    # Bảng lưu thông tin làm giàu cho từng dòng target
    enriched_data = {
        idx: {
            'email': '',
            'phone': '',
            'web': '',
            'contact_person': '',
            'position': '',
            'sources': []
        }
        for idx in range(len(df_target))
    }

    total_files_scanned = 0
    total_hits = 0

    for f_path in csdl_priority_files:
        if not f_path.exists():
            continue
        try:
            df_src = pd.read_csv(f_path, encoding='utf-8-sig', dtype=str, on_bad_lines='skip').fillna('')
            cols = df_src.columns.tolist()

            ico_col = next((c for c in cols if any(k == c.lower().strip() for k in ['ico', 'ičo', 'reg_code'])), None)
            if not ico_col:
                ico_col = next((c for c in cols if any(k in c.lower() for k in ['ico', 'ičo'])), None)

            name_col = next((c for c in cols if any(k == c.lower().strip() for k in ['công ty', 'name', 'company', 'nazov_spolocnosti', 'cong_ty'])), None)
            if not name_col:
                name_col = next((c for c in cols if any(k in c.lower() for k in ['công ty', 'name', 'nazov', 'title'])), None)

            mail_col = next((c for c in cols if any(k == c.lower().strip() for k in ['email', 'mail'])), None)
            if not mail_col:
                mail_col = next((c for c in cols if 'mail' in c.lower() and 'check' not in c.lower() and 'box' not in c.lower()), None)

            phone_col = next((c for c in cols if any(k == c.lower().strip() for k in ['sđt', 'phone', 'tel', 'telefon', 'mobil', 'sdt', 'sdt_chuan'])), None)
            if not phone_col:
                phone_col = next((c for c in cols if any(k in c.lower() for k in ['sđt', 'phone', 'tel', 'mobil'])), None)

            web_col = next((c for c in cols if any(k == c.lower().strip() for k in ['web', 'website', 'liên hệ', 'link', 'url'])), None)
            if not web_col:
                web_col = next((c for c in cols if any(k in c.lower() for k in ['web', 'liên hệ', 'site'])), None)

            contact_col = next((c for c in cols if any(k in c.lower() for k in ['người liên hệ', 'key_principal', 'contact_person', 'director'])), None)
            pos_col = next((c for c in cols if any(k in c.lower() for k in ['chức danh', 'position', 'title'])), None)

            hits_in_file = 0
            for _, r in df_src.iterrows():
                email = r.get(mail_col, '').strip() if mail_col else ''
                phone = r.get(phone_col, '').strip() if phone_col else ''
                web = r.get(web_col, '').strip() if web_col else ''
                contact = r.get(contact_col, '').strip() if contact_col else ''
                pos = r.get(pos_col, '').strip() if pos_col else ''

                if not email and not phone and not web:
                    continue

                matched_idx = None
                # 1. Khớp theo IČO
                if ico_col:
                    ico_val = clean_ico(r.get(ico_col))
                    if ico_val and ico_val in target_by_ico:
                        matched_idx = target_by_ico[ico_val]

                # 2. Khớp theo Tên chuẩn hóa
                if matched_idx is None and name_col:
                    nm_val = norm_name(r.get(name_col))
                    if nm_val and nm_val in target_by_name:
                        matched_idx = target_by_name[nm_val]

                if matched_idx is not None:
                    hits_in_file += 1
                    total_hits += 1
                    entry = enriched_data[matched_idx]

                    # Cập nhật Email (chấm điểm nếu đã có)
                    if is_valid_email(email):
                        if not entry['email']:
                            entry['email'] = email
                        else:
                            # So sánh điểm
                            if score_email_b2b(email) > score_email_b2b(entry['email']):
                                entry['email'] = email

                    # Cập nhật Phone
                    clean_p = clean_phone_sk(phone)
                    if clean_p and not entry['phone']:
                        entry['phone'] = clean_p

                    # Cập nhật Web
                    if web and web.startswith('http') and not any(b in web for b in ['facebook.com', 'google.com']):
                        if not entry['web']:
                            entry['web'] = web

                    # Cập nhật Người liên hệ / Chức danh
                    if contact and not entry['contact_person']:
                        entry['contact_person'] = contact
                    if pos and not entry['position']:
                        entry['position'] = pos

                    if f_path.name not in entry['sources']:
                        entry['sources'].append(f_path.name)

            total_files_scanned += 1
            print(f"[+] Scan {f_path.name:35s}: Khop {hits_in_file:4d} ban ghi")

        except Exception as e:
            print(f"[!] Loi khi doc {f_path.name}: {e}")

    # Ghi dữ liệu đã làm giàu vào Dataframe
    matched_companies = 0
    emails_added = 0
    phones_added = 0
    webs_added = 0

    rows_1enr = []
    rows_2col = []

    for idx, r in df_target.iterrows():
        comp_name = str(r.get('Name', '')).strip()
        if is_blacklisted_company(comp_name):
            continue

        enr = enriched_data[idx]
        cur_email = str(r.get('Email', '')).strip()
        cur_phone = str(r.get('Phone', '')).strip()
        cur_web = str(r.get('Web', '')).strip()

        final_email = enr['email'] if is_valid_email(enr['email']) else (cur_email if is_valid_email(cur_email) else '')
        final_phone = clean_phone_sk(enr['phone']) if enr['phone'] else clean_phone_sk(cur_phone)
        final_web = enr['web'] if enr['web'] else cur_web
        contact_person = enr['contact_person']
        position = enr['position']
        source_enr = ", ".join(enr['sources']) if enr['sources'] else r.get('Source', '')

        if enr['sources']:
            matched_companies += 1
        if final_email and not cur_email:
            emails_added += 1
        if final_phone and not cur_phone:
            phones_added += 1
        if final_web and not cur_web:
            webs_added += 1

        # Cột cho 1ENR (kế thừa đầy đủ 0RAW)
        row_1enr = dict(r)
        row_1enr['Email'] = final_email
        row_1enr['Phone'] = final_phone
        row_1enr['Web'] = final_web
        row_1enr['Source_Enriched'] = source_enr
        rows_1enr.append(row_1enr)

        # Cột cho 2COL (Cold Mail 20 cột)
        addr = str(r.get('Address', '')).strip()
        city = str(r.get('City', '')).strip()
        full_addr = addr if addr else city

        row_2col = {
            'No.': 0,
            'Công ty': comp_name,
            'Chức danh': position,
            'Người liên hệ': contact_person,
            'SĐT': final_phone,
            'Liên Hệ': final_web,
            'Email': final_email,
            'Liên Hệ mail': f"mailto:{final_email}" if final_email else "",
            'Địa chỉ': full_addr,
            'Lương': "",
            'Ngày đăng': "",
            'Hạn tuyển': "",
            'Check gửi': "",
            'Last Subject': "",
            'Last Body HTML': "",
            'Trạng thái Reply': "",
            'Lần Follow-up': "",
            'Ngày Follow-up gần nhất': "",
            'Mailbox đã dùng': "",
            'Category': r.get('NACE', 'Činnosti agentúr sprostredkujúcich zamestnania')
        }
        rows_2col.append(row_2col)

    # Đưa 100% doanh nghiệp có Email lên đầu tệp CSV theo Rule #3
    with_email_2col = [r for r in rows_2col if r['Email']]
    without_email_2col = [r for r in rows_2col if not r['Email']]
    sorted_2col = with_email_2col + without_email_2col

    for i, r in enumerate(sorted_2col, 1):
        r['No.'] = i

    with_email_1enr = [r for r in rows_1enr if r['Email']]
    without_email_1enr = [r for r in rows_1enr if not r['Email']]
    sorted_1enr = with_email_1enr + without_email_1enr
    for i, r in enumerate(sorted_1enr, 1):
        r['No.'] = i

    # Xuất file CSV UTF-8 with BOM
    df_out_1enr = pd.DataFrame(sorted_1enr)
    df_out_1enr.to_csv(OUTPUT_1ENR, index=False, encoding='utf-8-sig')

    df_out_2col = pd.DataFrame(sorted_2col, columns=COLDMAIL_COLUMNS)
    df_out_2col.to_csv(OUTPUT_2COL, index=False, encoding='utf-8-sig')

    print("\n" + "=" * 80)
    print(" KẾT QUẢ LÀM GIÀU DỮ LIỆU TỪ CSDL:")
    print(f" - Tổng số doanh nghiệp xử lý : {len(rows_2col):,}")
    print(f" - Số doanh nghiệp khớp CSDL  : {matched_companies:,} ({matched_companies/len(rows_2col)*100:.1f}%)")
    print(f" - Số Email được bổ sung      : {emails_added:,}")
    print(f" - Số SĐT được bổ sung        : {phones_added:,}")
    print(f" - Số Website được bổ sung    : {webs_added:,}")
    print(f" - Tổng doanh nghiệp CÓ EMAIL : {len(with_email_2col):,} ({len(with_email_2col)/len(rows_2col)*100:.1f}%)")
    print(f"   --> 100% ({len(with_email_2col)}) doanh nghiệp có Email nằm tại các dòng 1..{len(with_email_2col)}")
    print(f" - File 1ENR: {OUTPUT_1ENR}")
    print(f" - File 2COL: {OUTPUT_2COL}")
    print("=" * 80)

if __name__ == '__main__':
    main()
