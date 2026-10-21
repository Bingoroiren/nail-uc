# -*- coding: utf-8 -*-
"""
MASTER MERGE & DEDUPLICATION: SLOVAK EMPLOYMENT AGENCIES
Gộp và đối chiếu lọc trùng toàn bộ CSDL Môi giới lao động Slovakia:
1. ADZC (383 công ty từ ÚPSVaR - SK_ADZC_UPSV_2COL.csv)
2. UDZC (3,061 công ty từ ÚPSVaR - SK_UDZC_UPSV_2COL.csv)
3. D&B Slovakia (1,000 công ty từ Dun & Bradstreet - SK_AGCY_DNB_2COL.csv & dnb_slovakia_agcy_detailed.csv)
4. GreenPages (45 công ty - greenpages_agcy_database.csv)
5. PersonalneAgentury (14 công ty - personalneagentury_database.csv)

Chiến lược Lọc trùng (Deduplication):
- Khóa 1: Tên miền Website (Domain Name) đã làm sạch (bỏ www, https, trailing slash).
- Khóa 2: Tên công ty chuẩn hóa Unicode NFKD (khử dấu á->a, č->c, s.r.o., a.s., khoảng trắng, dấu phẩy).
- Hợp nhất dữ liệu phong phú nhất (Richest Data Merge):
  * Giữ Email tốt nhất (Ưu tiên mail domain riêng theo score_email_b2b).
  * Giữ SĐT chuẩn có nháy đơn (').
  * Giữ Người liên hệ / Giám đốc đại diện (Key Principal / Vadovas / Konatel).
  * Giữ Địa chỉ chi tiết, Thành phố.
  * Ghi nhận đầy đủ các nguồn (Sources tag: ADZC, UDZC, DNB, GREEN, PAGENT).
- Sắp xếp: Đẩy 100% doanh nghiệp CÓ EMAIL lên đầu file CSV!
"""

import os
import sys
import re
import csv
import unicodedata
from pathlib import Path
import pandas as pd

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path("D:/glc/nail uc")
AGCY_DIR = ROOT_DIR / "csdl_sk_agcy"

OUTPUT_1ENR = AGCY_DIR / "SK_AGCY_ALL_1ENR.csv"
OUTPUT_2COL = AGCY_DIR / "SK_AGCY_ALL_2COL.csv"
OUTPUT_DEDUP_REPORT = AGCY_DIR / "SK_AGCY_DEDUP_REPORT.txt"

COL_20_HEADERS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ', 'Email', 
    'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển', 'Check gửi', 
    'Last Subject', 'Last Body HTML', 'Trạng thái Reply', 'Lần Follow-up', 
    'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')
INVALID_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.pdf', '.woff', '.ico')

def clean_phone(p):
    if not p or str(p).strip() in ['', 'nan', 'None']:
        return ''
    s = str(p).strip()
    # Loại bỏ khoảng trắng thừa nhưng giữ lại dấu +
    s = re.sub(r'[^\d+]', '', s)
    if s.startswith('0') and len(s) == 10:
        s = '+421' + s[1:]
    return s if s.startswith("'") else f"'{s}"

def normalize_text_core(s):
    if not s:
        return ""
    # 1. Khử dấu Unicode NFKD
    s_norm = unicodedata.normalize('NFKD', str(s)).encode('ASCII', 'ignore').decode('utf-8').lower()
    s_norm = re.sub(r'["\'„“”«»\(\)\[\]]', '', s_norm)
    # 2. Bỏ legal forms
    for lf in ['spol. s r.o.', 'spol. s r. o.', 'spol. s.r.o.', 's.r.o.', 's. r. o.', 'a.s.', 'a. s.', 
               'k.s.', 'v.o.s.', 'druzstvo', 'gmbh', 'v likvidacii', 'v konkurze', 'organizacna zlozka']:
        s_norm = re.sub(rf'\b{re.escape(lf)}\b', '', s_norm)
    # 3. Làm sạch dấu câu
    s_norm = re.sub(r'^[,.\-_/|\s]+|[,.\-_/|\s]+$', '', s_norm)
    s_norm = re.sub(r'\s+', ' ', s_norm).strip()
    return s_norm

def clean_domain(url):
    if not url or str(url).strip() in ['', 'nan', 'None']:
        return ''
    u = str(url).strip().lower()
    m = re.search(r'https?://(?:www\.)?([^/]+)', u)
    if m:
        domain = m.group(1)
    else:
        domain = u.replace('www.', '').split('/')[0]
    
    # Loại bỏ mạng xã hội / portal
    for bad in ['facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'google.com', 'dnb.com', 'upsvr.gov.sk']:
        if bad in domain:
            return ''
    return domain.strip()

def score_email(em, dom=""):
    if not em or not isinstance(em, str):
        return -1
    e = em.strip().lower()
    if not EMAIL_REGEX.match(e) or any(e.endswith(ext) for ext in INVALID_EXTS):
        return -1
    u, d = e.split('@', 1)
    if any(bad in d for bad in ['sentry', 'wixpress', 'example.com', 'domain.com']):
        return -1
    score = 10
    if dom and (dom in d or d in dom):
        score += 50
    elif d.endswith('.sk'):
        score += 25
    if u in ['praca', 'kariera', 'hr', 'personalne', 'jobs', 'nabor']:
        score += 50
    elif u in ['konatel', 'riaditel', 'vedenie', 'ceo', 'director', 'sales']:
        score += 45
    elif u in ['info', 'kontakt', 'office', 'sekretariat']:
        score += 40
    return score

def main():
    print("=" * 80)
    print(" BẮT ĐẦU GỘP & ĐỐI CHIẾU LỌC TRÙNG CSDL MÔI GIỚI LAO ĐỘNG SLOVAKIA")
    print("=" * 80)

    # 1. Danh sách các file đầu vào
    input_files = [
        ('ADZC', ROOT_DIR / "SK_ADZC_UPSV_2COL.csv", 'Dočasné zamestnávanie (ADZ ÚPSVaR)'),
        ('UDZC', ROOT_DIR / "SK_UDZC_UPSV_2COL.csv", 'Sprostredkovanie zamestnania (UDZ ÚPSVaR)'),
        ('DNB', AGCY_DIR / "SK_AGCY_DNB_2COL.csv", 'Dun & Bradstreet Slovakia (D&B)'),
        ('GREEN', AGCY_DIR / "greenpages_agcy_database.csv", 'GreenPages Slovakia'),
        ('PAGENT', AGCY_DIR / "personalneagentury_database.csv", 'PersonalneAgentury.sk')
    ]

    # Đồng thời nạp thêm file D&B chi tiết để lấy thông tin Người đại diện / Địa chỉ chuẩn
    dnb_details_map = {}
    f_dnb_det = AGCY_DIR / "dnb_slovakia_agcy_detailed.csv"
    if f_dnb_det.exists():
        df_dnb_det = pd.read_csv(f_dnb_det, dtype=str).fillna('')
        for _, r in df_dnb_det.iterrows():
            cname = r.get('Company', '').strip()
            k = normalize_text_core(cname)
            if k:
                dnb_details_map[k] = {
                    'Key_Principal': r.get('Key_Principal', '').strip(),
                    'Employees': r.get('Employees', '').strip(),
                    'Address': r.get('Address', '').strip(),
                    'City': r.get('City', '').strip(),
                    'Website': r.get('Website', '').strip()
                }

    merged_records = {} # key -> record dict
    stats = {
        'total_read': 0,
        'by_source': {},
        'duplicates_found': 0,
        'exact_domain_matches': 0,
        'exact_name_matches': 0
    }

    # Đọc và đối chiếu từng nguồn
    for src_tag, file_path, src_label in input_files:
        if not file_path.exists():
            print(f"[!] Không tìm thấy file: {file_path}")
            continue

        df = pd.read_csv(file_path, dtype=str).fillna('')
        stats['by_source'][src_tag] = len(df)
        stats['total_read'] += len(df)
        print(f"[*] Đọc nguồn [{src_tag}] ({src_label}): {len(df):,} doanh nghiệp.")

        # Chuẩn hóa tên cột
        name_col = 'Công ty' if 'Công ty' in df.columns else ('Company' if 'Company' in df.columns else 'Name')
        web_col = 'Liên Hệ' if 'Liên Hệ' in df.columns else ('Website' if 'Website' in df.columns else 'Web')
        email_col = 'Email' if 'Email' in df.columns else None
        phone_col = 'SĐT' if 'SĐT' in df.columns else 'Phone'
        contact_col = 'Người liên hệ' if 'Người liên hệ' in df.columns else ('Director' if 'Director' in df.columns else 'Key_Principal')
        addr_col = 'Địa chỉ' if 'Địa chỉ' in df.columns else 'Address'
        cat_col = 'Category' if 'Category' in df.columns else None

        for _, row in df.iterrows():
            comp_name = str(row.get(name_col, '')).strip()
            if not comp_name or comp_name.lower() in ['customer support', 'terms of use', 'company']:
                continue

            name_key = normalize_text_core(comp_name)
            if not name_key:
                continue

            raw_web = str(row.get(web_col, '')).strip()
            dom_key = clean_domain(raw_web)

            raw_email = str(row.get(email_col, '')).strip() if email_col else ''
            raw_phone = clean_phone(row.get(phone_col, ''))
            contact_person = str(row.get(contact_col, '')).strip() if contact_col in row else ''
            addr = str(row.get(addr_col, '')).strip()
            category = str(row.get(cat_col, '')).strip() if cat_col in row else src_label

            # Bổ sung thông tin từ D&B Details nếu có
            if name_key in dnb_details_map:
                d_info = dnb_details_map[name_key]
                if not contact_person and d_info.get('Key_Principal'):
                    contact_person = d_info['Key_Principal']
                if not raw_web and d_info.get('Website'):
                    raw_web = d_info['Website']
                    dom_key = clean_domain(raw_web)
                if not addr and d_info.get('Address'):
                    addr = d_info['Address']

            # TÌM KIẾM ĐỐI CHIẾU LỌC TRÙNG:
            match_key = None

            # 1. Khớp theo domain website duy nhất
            if dom_key:
                for existing_k, existing_rec in merged_records.items():
                    if existing_rec['Domain'] and existing_rec['Domain'] == dom_key:
                        match_key = existing_k
                        stats['exact_domain_matches'] += 1
                        break

            # 2. Khớp theo Tên công ty cốt lõi (sau khử dấu Unicode NFKD)
            if not match_key and name_key in merged_records:
                match_key = name_key
                stats['exact_name_matches'] += 1

            # NẾU TRÙNG LẶP -> HỢP NHẤT DỮ LIỆU TỐI ƯU
            if match_key:
                stats['duplicates_found'] += 1
                rec = merged_records[match_key]
                rec['Sources'].add(src_tag)

                # Giữ tên hiển thị dài hơn/rõ hơn
                if len(comp_name) > len(rec['Company']):
                    rec['Company'] = comp_name

                # Bổ sung người liên hệ
                if not rec['Contact'] and contact_person:
                    rec['Contact'] = contact_person

                # Bổ sung SĐT
                if not rec['Phone'] and raw_phone:
                    rec['Phone'] = raw_phone

                # Bổ sung Website
                if not rec['Web'] and raw_web:
                    rec['Web'] = raw_web
                    rec['Domain'] = dom_key

                # Bổ sung / Nâng cấp Email (Chọn mail có điểm cao hơn)
                curr_em = rec['Email']
                if raw_email:
                    if not curr_em:
                        rec['Email'] = raw_email
                    elif score_email(raw_email, rec['Domain']) > score_email(curr_em, rec['Domain']):
                        rec['Email'] = raw_email

                # Bổ sung địa chỉ
                if not rec['Address'] and addr:
                    rec['Address'] = addr

                # Gộp phân loại ngành
                if category and category not in rec['Categories']:
                    rec['Categories'].append(category)

            # NẾU LÀ CÔNG TY MỚI -> THÊM VÀO MASTER
            else:
                merged_records[name_key] = {
                    'Company': comp_name,
                    'Name_Key': name_key,
                    'Domain': dom_key,
                    'Contact': contact_person,
                    'Phone': raw_phone,
                    'Web': raw_web,
                    'Email': raw_email,
                    'Address': addr,
                    'Sources': {src_tag},
                    'Categories': [category] if category else [src_label]
                }

    print("\n" + "=" * 80)
    print(" KẾT QUẢ ĐỐI CHIẾU LỌC TRÙNG:")
    print("=" * 80)
    print(f"[*] Tổng số bản ghi đọc vào từ 5 nguồn: {stats['total_read']:,}")
    print(f"[*] Số lượt trùng lặp phát hiện & gộp : {stats['duplicates_found']:,}")
    print(f"    - Trùng theo Domain Website        : {stats['exact_domain_matches']:,}")
    print(f"    - Trùng theo Tên công ty (NFKD)    : {stats['exact_name_matches']:,}")
    print(f"[*] TỔNG SỐ CÔNG TY DUY NHẤT SAU GỘP   : {len(merged_records):,}")

    # Chuyển đổi sang DataFrame & Sắp xếp 100% Email lên đầu
    final_rows = []
    for k, rec in merged_records.items():
        src_str = " + ".join(sorted(rec['Sources']))
        cat_str = " | ".join([c for c in rec['Categories'] if c])
        final_rows.append({
            'Company': rec['Company'],
            'Contact': rec['Contact'],
            'Phone': rec['Phone'],
            'Web': rec['Web'],
            'Email': rec['Email'],
            'Address': rec['Address'],
            'Sources': src_str,
            'Category': cat_str
        })

    df_master = pd.DataFrame(final_rows)

    # Phân loại có email vs không có email
    has_em = df_master[df_master['Email'].str.strip() != ''].copy()
    no_em = df_master[df_master['Email'].str.strip() == ''].copy()

    # Sắp xếp có email lên đầu
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)

    print(f"[*] Số công ty CÓ EMAIL xác thực       : {len(has_em):,} (100% gom lên đầu)")
    print(f"[*] Số công ty thiếu Email             : {len(no_em):,}")

    # 1. Xuất file CSDL Đầy đủ 1ENR
    df_sorted.to_csv(OUTPUT_1ENR, index=False, encoding='utf-8-sig')

    # 2. Xuất file Cold Mail Chuẩn 20 Cột 2COL
    col20_list = []
    for idx, r in df_sorted.iterrows():
        em = r['Email']
        col20_list.append({
            'No.': idx + 1,
            'Công ty': r['Company'],
            'Chức danh': 'Konateľ / Director' if r['Contact'] else '',
            'Người liên hệ': r['Contact'],
            'SĐT': r['Phone'],
            'Liên Hệ': r['Web'],
            'Email': em,
            'Liên Hệ mail': f"mailto:{em}" if em else '',
            'Địa chỉ': r['Address'],
            'Lương': '', 'Ngày đăng': '', 'Hạn tuyển': '',
            'Check gửi': 'Chưa gửi',
            'Last Subject': '', 'Last Body HTML': '', 'Trạng thái Reply': '',
            'Lần Follow-up': '0', 'Ngày Follow-up gần nhất': '', 'Mailbox đã dùng': '',
            'Category': f"{r['Category']} [Nguồn: {r['Sources']}]"
        })

    df_2col = pd.DataFrame(col20_list, columns=COL_20_HEADERS)
    df_2col.to_csv(OUTPUT_2COL, index=False, encoding='utf-8-sig')

    # 3. Xuất Báo cáo đối chiếu
    report_text = f"""================================================================================
 BÁO CÁO ĐỐI CHIẾU VÀ LỌC TRÙNG CSDL MÔI GIỚI LAO ĐỘNG SLOVAKIA
================================================================================
Thời gian thực hiện : 2026-10-16
1. Thống kê nguồn dữ liệu ban đầu:
   - ADZC (Dočasné zamestnávanie ÚPSVaR)      : {stats['by_source'].get('ADZC', 0):,} dòng
   - UDZC (Sprostredkovanie zamestnania ÚPSVaR): {stats['by_source'].get('UDZC', 0):,} dòng
   - D&B (Dun & Bradstreet Slovakia)          : {stats['by_source'].get('DNB', 0):,} dòng
   - GreenPages Slovakia                      : {stats['by_source'].get('GREEN', 0):,} dòng
   - PersonalneAgentury.sk                    : {stats['by_source'].get('PAGENT', 0):,} dòng
   -----------------------------------------------------------------------------
   TỔNG SỐ BẢN GHI BAN ĐẦU                    : {stats['total_read']:,} dòng

2. Kết quả đối chiếu & Lọc trùng lặp:
   - Số doanh nghiệp bị trùng lặp đã gộp      : {stats['duplicates_found']:,} lượt
   - Trùng theo Domain Website chính thức      : {stats['exact_domain_matches']:,} lượt
   - Trùng theo Tên công ty cốt lõi (NFKD)    : {stats['exact_name_matches']:,} lượt
   -----------------------------------------------------------------------------
   TỔNG SỐ CÔNG TY DUY NHẤT SAU GỘP (MASTER)  : {len(df_sorted):,} doanh nghiệp

3. Chất lượng dữ liệu liên hệ:
   - Số công ty CÓ EMAIL (Đẩy 100% lên đầu)   : {len(has_em):,} ({len(has_em)/len(df_sorted)*100:.1f}%)
   - Số công ty có SĐT (Chuẩn hóa nháy đơn ')  : {(df_sorted['Phone'].str.strip() != '').sum():,}
   - Số công ty có Website                    : {(df_sorted['Web'].str.strip() != '').sum():,}
   - Số công ty có Tên Giám Đốc/Người đại diện: {(df_sorted['Contact'].str.strip() != '').sum():,}

4. File xuất thành phẩm:
   - CSDL Chi Tiết Master : D:\\glc\\nail uc\\csdl_sk_agcy\\SK_AGCY_ALL_1ENR.csv
   - Cold Mail 20 Cột     : D:\\glc\\nail uc\\csdl_sk_agcy\\SK_AGCY_ALL_2COL.csv
================================================================================
"""
    with open(OUTPUT_DEDUP_REPORT, 'w', encoding='utf-8') as rf:
        rf.write(report_text)

    print(f"\n[✔] ĐÃ XUẤT THÀNH PHẨM MASTER:")
    print(f"[*] File Cold Mail 20 Cột (100% mail lên đầu): {OUTPUT_2COL}")
    print(f"[*] File CSDL Chi Tiết Master                 : {OUTPUT_1ENR}")
    print(f"[*] Báo Cáo Đối Chiếu                         : {OUTPUT_DEDUP_REPORT}")
    print("=" * 80)

if __name__ == '__main__':
    main()
