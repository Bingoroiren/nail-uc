# -*- coding: utf-8 -*-
"""
HỆ THỐNG LỌC TRÙNG TÊN CÔNG TY & HỢP NHẤT THÔNG TIN TỐI ƯU
DÀNH CHO DỮ LIỆU GỖ & NỘI THẤT LITVA (LT_WOOD)
==========================================================
Quy tắc xử lý:
1. Chuẩn hóa tên thông minh: Khử dấu NFKD, loại bỏ dấu ngoặc kép, loại bỏ legal forms
   (UAB, MB, IĮ, VšĮ, AB, filialas, skyrius, įmonė...) để gom các chi nhánh và công ty mẹ.
2. Bảo toàn và hợp nhất thông tin tối đa (Smart Merge):
   - Nếu 1 dòng có Email, dòng kia không -> Giữ lại Email.
   - Nếu cả 2 dòng đều có Email -> Chấm điểm B2B (Rule 3) chọn DUY NHẤT 1 email giá trị nhất.
   - Bù đắp Mã số DN (Company Code), Giám đốc (Vadovas), SĐT có nháy đơn ('), Website, Lương, Nhân sự.
   - Gộp danh mục ngành nghề (Tag_Chinh / Category).
3. Sắp xếp chuẩn Cold Mail: Đẩy 100% doanh nghiệp có Email lên đầu tệp (Dòng 1..N).
4. Đồng bộ vào csdl_mlt/ và archive/lt_lithuania/.
"""

import os
import sys
import re
import csv
import json
import unicodedata
import urllib.parse
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent

CSDL_DIR = ROOT_DIR / "csdl_mlt"
ARCHIVE_DIR = ROOT_DIR / "archive" / "lt_lithuania"

# Danh sách đen cố định (Rule 12)
PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

HEADERS_20COL = [
    "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ", "Email",
    "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển", "Check gửi",
    "Last Subject", "Last Body HTML", "Trạng thái Reply", "Lần Follow-up",
    "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
]

COLUMNS_RAW = [
    'No.', 'Company_Code', 'Cong ty', 'Ten phap ly', 'SDT', 'Email', 'Website',
    'Dia chi', 'Ma buu dien', 'Khu vuc', 'Thanh pho',
    'Tag_Chinh', 'All_Tags', 'VAT_Code', 'Nguoi quan ly', 'Chuc danh',
    'Average_Wage', 'So nhan vien', 'Nam thanh lap', 'Source_URL'
]

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

def clean_company_name_key(name):
    """Chuẩn hóa tên công ty Litva phục vụ so khớp và khử trùng lặp triệt để"""
    if not name:
        return ""
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n = ''.join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r'["„“”«»\']', '', n)
    legal_terms = [
        'uab', 'mb', 'vsi', 'ii', 'ab', 'as', 'sro', 'gmbh', 'ltd', 
        'filialas', 'skyrius', 'imone', 'ir ko', 'ir partneriai',
        'viesoji istaiga', 'akcine bendrove', 'uzdaroji akcine bendrove',
        'mazoji bendrija', 'individuali veikla', 'individuali imone'
    ]
    for term in legal_terms:
        n = re.sub(rf'\b{term}\b', '', n)
    n = re.sub(r'[^a-z0-9]', '', n)
    return n.strip()

def clean_phone(raw):
    """Chuẩn hóa SĐT Litva: luôn có nháy đơn (') ở đầu theo Rule 2."""
    if not raw or str(raw).strip() in ['', 'None', 'nan']:
        return ""
    p = re.sub(r"[^\d+]", "", str(raw).strip().lstrip("'"))
    if not p:
        return ""
    if p.startswith("8") and len(p) == 9:
        p = "+370" + p[1:]
    elif p.startswith("0") and (len(p) == 9 or len(p) == 10):
        p = "+370" + p[1:]
    elif not p.startswith("+") and len(p) == 8:
        p = "+370" + p
    elif p.startswith("370") and not p.startswith("+"):
        p = "+" + p

    digits = re.sub(r'\D', '', p)
    if digits.startswith('370') and len(digits) == 11:
        if digits[3] == '6':
            formatted = f"+370 {digits[3:6]} {digits[6:]}"
        elif digits[3] == '5':
            formatted = f"+370 {digits[3]} {digits[4:7]} {digits[7:]}"
        else:
            formatted = f"+370 {digits[3:5]} {digits[5:8]} {digits[8:]}"
        return f"'{formatted}"
    return f"'{p}" if not p.startswith("'") else p

def clean_email(email):
    if not email or not isinstance(email, str):
        return ""
    em = urllib.parse.unquote(str(email).strip())
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\u200e', '\u200f', '\ufeff', '\u202f', '\u3000']:
        em = em.replace(bad, '')
    em = re.sub(r'^mailto:\s*', '', em, flags=re.I)
    em = re.sub(r'\s+', '', em)
    em = em.strip(" .,;:\"'<>[](){}\\/")
    if re.match(r'^20[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', em) and not em.startswith('202'):
        if re.match(r'^20[a-zA-Z]', em):
            em = em[2:]
    return em.lower()

def is_valid_email(email):
    e = clean_email(email)
    if not e or '@' not in e or len(e) < 6 or len(e) > 80:
        return False
    bad_parts = ['sentry', 'wixpress', 'wordpress', 'example', 'domain', 'youremail', 'someone', 'no-reply', 'donotreply', 'privacy', 'gdpr']
    if any(b in e for b in bad_parts):
        return False
    ext = e.split('.')[-1]
    if ext in ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'css', 'js', 'pdf']:
        return False
    return bool(re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', e))

def score_email_b2b_lt(email, domain=""):
    """Chấm điểm email B2B cho thị trường Litva theo Rule 3"""
    e = clean_email(email)
    if not is_valid_email(e):
        return -1
    u, d = e.split('@', 1)
    score = 10
    clean_d = domain.lower().replace('www.', '').split('/')[0] if domain else ""
    if clean_d and (clean_d in d or d in clean_d):
        score += 50
    elif d.endswith('.lt'):
        score += 25

    if u in ['karjera', 'cv', 'atranka', 'personalo', 'darbas', 'hr', 'jobs', 'recruitment', 'work']:
        score += 50
    elif u in ['direktorius', 'vadovas', 'ceo', 'director', 'valdymas', 'manager', 'prezidentas']:
        score += 45
    elif u in ['info', 'kontaktai', 'biuras', 'office', 'administracija', 'sekretoriatas', 'bendras']:
        score += 40
    elif u in ['komercija', 'pardavimai', 'uzsakymai', 'sales', 'prekyba']:
        score += 35
    elif '.' in u and score >= 60:
        score += 25
    return score

def select_best_email(emails, domain=""):
    cleaned = [clean_email(e) for e in emails if e]
    valid = [e for e in set(cleaned) if e and score_email_b2b_lt(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b_lt(e, domain))

def merge_record_group(records):
    """
    Hợp nhất một nhóm bản ghi trùng tên:
    Giữ lại bản ghi đầy đủ nhất, bù đắp mọi trường thiếu từ các bản ghi khác
    """
    if len(records) == 1:
        return records[0]

    # Ưu tiên bản ghi có tên chính (không chứa 'filialas' hay 'skyrius')
    records.sort(key=lambda r: 0 if not any(k in r.get('Cong ty', '').lower() for k in ['filialas', 'skyrius']) else 1)
    base = dict(records[0])

    all_emails = [r.get('Email', '') for r in records if r.get('Email')]
    all_phones = [clean_phone(r.get('SDT', '')) for r in records if r.get('SDT')]
    all_codes = [r.get('Company_Code', '').strip() for r in records if r.get('Company_Code', '').strip()]
    all_vat = [r.get('VAT_Code', '').strip() for r in records if r.get('VAT_Code', '').strip()]
    all_managers = [r.get('Nguoi quan ly', '').strip() for r in records if r.get('Nguoi quan ly', '').strip()]
    all_webs = [r.get('Website', '').strip() for r in records if r.get('Website', '').strip()]
    all_wages = [r.get('Average_Wage', '').strip() for r in records if r.get('Average_Wage', '').strip()]
    all_employees = [r.get('So nhan vien', '').strip() for r in records if r.get('So nhan vien', '').strip()]
    all_addrs = [r.get('Dia chi', '').strip() for r in records if r.get('Dia chi', '').strip()]
    all_tags = []
    for r in records:
        for t in [r.get('Tag_Chinh', ''), r.get('All_Tags', '')]:
            if t:
                for sub in t.split('|'):
                    sub_clean = sub.strip()
                    if sub_clean and sub_clean not in all_tags:
                        all_tags.append(sub_clean)

    # 1. Company Code
    if not base.get('Company_Code') and all_codes:
        base['Company_Code'] = all_codes[0]

    # 2. VAT Code
    if not base.get('VAT_Code') and all_vat:
        base['VAT_Code'] = all_vat[0]

    # 3. Phone
    if not base.get('SDT') and all_phones:
        base['SDT'] = all_phones[0]
    else:
        base['SDT'] = clean_phone(base.get('SDT', ''))

    # 4. Website
    if not base.get('Website') and all_webs:
        base['Website'] = all_webs[0]

    # 5. Email (Chọn email tối ưu nhất qua chấm điểm B2B)
    domain = urllib.parse.urlparse(base.get('Website', '')).netloc if base.get('Website') else ''
    base['Email'] = select_best_email(all_emails, domain)

    # 6. Người quản lý / Giám đốc
    if not base.get('Nguoi quan ly') and all_managers:
        base['Nguoi quan ly'] = all_managers[0]
        base['Chuc danh'] = 'Vadovas / Direktorius'

    # 7. Lương & Nhân viên
    if not base.get('Average_Wage') and all_wages:
        base['Average_Wage'] = all_wages[0]
    if not base.get('So nhan vien') and all_employees:
        base['So nhan vien'] = all_employees[0]

    # 8. Địa chỉ
    if not base.get('Dia chi') and all_addrs:
        base['Dia chi'] = max(all_addrs, key=len)

    # 9. Danh mục ngành nghề
    if all_tags:
        base['Tag_Chinh'] = ' | '.join(all_tags)
        base['All_Tags'] = ' | '.join(all_tags)

    return base

def deduplicate_dataset(raw_input_path, raw_output_path, col2_output_path, ready_output_path):
    """Xử lý lọc trùng tên công ty cho một bộ dữ liệu CSV"""
    if not raw_input_path.exists():
        print(f"[!] Không tìm thấy file: {raw_input_path.name}")
        return

    print("\n" + "=" * 80)
    print(f" TIẾN HÀNH LỌC TRÙNG TÊN CÔNG TY: {raw_input_path.name}")
    print("=" * 80)

    df = pd.read_csv(raw_input_path, encoding='utf-8-sig', dtype=str).fillna('')
    init_count = len(df)
    print(f"[*] Số dòng ban đầu: {init_count:,}")

    # Gom nhóm theo clean_key
    grouped = {}
    ungrouped = []

    for _, row in df.iterrows():
        rec = row.to_dict()
        comp_name = rec.get('Cong ty', '').strip()

        # Kiểm tra danh sách đen
        if is_blacklisted_company(comp_name):
            continue

        key = clean_company_name_key(comp_name)
        if not key or len(key) < 3:
            ungrouped.append(rec)
        else:
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(rec)

    # Hợp nhất từng nhóm
    merged_records = []
    dup_resolved_count = 0

    for key, records in grouped.items():
        if len(records) > 1:
            dup_resolved_count += (len(records) - 1)
        merged = merge_record_group(records)
        merged_records.append(merged)

    merged_records.extend(ungrouped)

    # Phân loại: ĐẨY 100% CÔNG TY CÓ EMAIL LÊN ĐẦU
    with_em = [r for r in merged_records if r.get('Email') and '@' in r.get('Email')]
    without_em = [r for r in merged_records if not r.get('Email') or '@' not in r.get('Email')]
    sorted_all = with_em + without_em

    for idx, r in enumerate(sorted_all, 1):
        r['No.'] = str(idx)

    # 1. Ghi file RAW
    raw_output_path.parent.mkdir(parents=True, exist_ok=True)
    df_raw_out = pd.DataFrame(sorted_all, columns=COLUMNS_RAW)
    df_raw_out.to_csv(raw_output_path, index=False, encoding='utf-8-sig')

    # 2. Ghi file Cold Mail 20 cột
    col20_rows = []
    for r in sorted_all:
        c_name = r.get('Cong ty', '')
        c_leader = r.get('Nguoi quan ly', '')
        c_phone = clean_phone(r.get('SDT', ''))
        c_email = r.get('Email', '')
        c_web = r.get('Website', '')
        c_addr = r.get('Dia chi', '')

        row_20 = {
            'No.': r.get('No.', ''),
            'Công ty': c_name,
            'Chức danh': r.get('Chuc danh', '') or 'Vadovas / Direktorius',
            'Người liên hệ': c_leader,
            'SĐT': c_phone,
            'Liên Hệ': c_web,
            'Email': c_email,
            'Liên Hệ mail': f"mailto:{c_email}" if c_email else '',
            'Địa chỉ': c_addr,
            'Lương': r.get('Average_Wage', ''),
            'Ngày đăng': '',
            'Hạn tuyển': '',
            'Check gửi': 'Chưa gửi' if c_email else '',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': r.get('Tag_Chinh', 'Gỗ & Nội thất')
        }
        col20_rows.append(row_20)

    col2_output_path.parent.mkdir(parents=True, exist_ok=True)
    df_col2_out = pd.DataFrame(col20_rows, columns=HEADERS_20COL)
    df_col2_out.to_csv(col2_output_path, index=False, encoding='utf-8-sig')

    # 3. Ghi file ONLY_EMAILS_READY
    ready_output_path.parent.mkdir(parents=True, exist_ok=True)
    df_ready_out = df_col2_out[df_col2_out['Email'].str.contains('@', na=False)].copy()
    for i, _ in enumerate(df_ready_out.index, 1):
        df_ready_out.iloc[i-1, df_ready_out.columns.get_loc('No.')] = str(i)
    df_ready_out.to_csv(ready_output_path, index=False, encoding='utf-8-sig')

    # 4. Đồng bộ vào csdl_mlt và archive
    CSDL_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR = ROOT_DIR / "archive" / "lt_lithuania"
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    df_col2_out.to_csv(CSDL_DIR / col2_output_path.name, index=False, encoding='utf-8-sig')
    df_col2_out.to_csv(ARCHIVE_DIR / col2_output_path.name, index=False, encoding='utf-8-sig')
    df_raw_out.to_csv(ARCHIVE_DIR / raw_output_path.name, index=False, encoding='utf-8-sig')
    df_ready_out.to_csv(ARCHIVE_DIR / ready_output_path.name, index=False, encoding='utf-8-sig')

    final_count = len(sorted_all)
    print(f"[*] Đã lọc bỏ & hợp nhất thông tin: {dup_resolved_count:,} dòng trùng tên.")
    print(f"[*] Số dòng duy nhất còn lại: {final_count:,} (Giảm từ {init_count:,} -> {final_count:,})")
    print(f"[*] Doanh nghiệp CÓ EMAIL B2B (Dòng 1..N): {len(with_em):,}")
    print(f"[*] File RAW: {raw_output_path.name}")
    print(f"[*] File Cold Mail: {col2_output_path.name}")
    print(f"[*] File Ready Mail: {ready_output_path.name}")

def main():
    # 1. Lọc trùng cho tệp HỢP NHẤT TỔNG (LT_WOOD_COMB)
    comb_raw = ROOT_DIR / "LT_WOOD_COMB_0RAW.csv"
    comb_col2 = ROOT_DIR / "LT_WOOD_COMB_2COL.csv"
    comb_ready = ROOT_DIR / "LT_WOOD_COMB_ONLY_EMAILS_READY.csv"
    if comb_raw.exists():
        deduplicate_dataset(comb_raw, comb_raw, comb_col2, comb_ready)

    # 2. Lọc trùng cho tệp INFO.LT (LT_WOOD_INLT)
    inlt_raw = ROOT_DIR / "LT_WOOD_INLT_0RAW.csv"
    inlt_col2 = ROOT_DIR / "LT_WOOD_INLT_2COL.csv"
    inlt_ready = ROOT_DIR / "LT_WOOD_INLT_ONLY_EMAILS_READY.csv"
    if inlt_raw.exists():
        deduplicate_dataset(inlt_raw, inlt_raw, inlt_col2, inlt_ready)

if __name__ == '__main__':
    main()
