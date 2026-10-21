# -*- coding: utf-8 -*-
"""
Chuẩn Hóa Danh Sách Sprostredkovanie zamestnania za úhradu (SZÚ) Từ ÚPSVaR Slovakia
Đầu vào: SK_UDZC_UPSV_0RAW.xlsx
Đầu ra:
  1. SK_UDZC_UPSV_2COL.csv (Chuẩn 20 cột Cold Mail, 100% Email đẩy lên đầu, SĐT có nháy đơn)
  2. data/formatted/SK_UDZC_UPSV_2COL.csv
  3. data/formatted/SK_UDZC_UPSV_1ENR.csv (Bản chi tiết lưu giữ IČO, ngày cấp phép, ghi chú)
  4. Sao lưu bản thô: data/raw/SK_UDZC_UPSV_0RAW.xlsx
"""

import os
import sys
import re
import csv
import shutil
import openpyxl
import pandas as pd
from urllib.parse import urlparse

# Đảm bảo UTF-8 cho Windows Console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_XLSX = os.path.join(ROOT_DIR, "SK_UDZC_UPSV_0RAW.xlsx")
ROOT_COLDMAIL_CSV = os.path.join(ROOT_DIR, "SK_UDZC_UPSV_2COL.csv")
FMT_COLDMAIL_CSV = os.path.join(ROOT_DIR, "data", "formatted", "SK_UDZC_UPSV_2COL.csv")
FMT_DETAIL_CSV = os.path.join(ROOT_DIR, "data", "formatted", "SK_UDZC_UPSV_1ENR.csv")
RAW_BACKUP_XLSX = os.path.join(ROOT_DIR, "data", "raw", "SK_UDZC_UPSV_0RAW.xlsx")

COLDMAIL_FIELDNAMES = [
    "No.",
    "Công ty",
    "Chức danh",
    "Người liên hệ",
    "SĐT",
    "Liên Hệ",
    "Email",
    "Liên Hệ mail",
    "Địa chỉ",
    "Lương",
    "Ngày đăng",
    "Hạn tuyển",
    "Check gửi",
    "Last Subject",
    "Last Body HTML",
    "Trạng thái Reply",
    "Lần Follow-up",
    "Ngày Follow-up gần nhất",
    "Mailbox đã dùng",
    "Category"
]

DETAIL_FIELDNAMES = [
    "No.",
    "ICO",
    "Cong_Ty",
    "Dia_Chi",
    "SDT",
    "Email",
    "Website",
    "Datum_Vzniku",
    "Poznamky",
    "Check_Gui",
    "Trang_Thai_Reply",
    "Category"
]

def clean_company_name(name):
    if not name:
        return ""
    name = re.sub(r'[\r\n\t]+', ' ', str(name))
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def norm_name(n):
    n = str(n).lower()
    for s in ['spol. s r.o.', 'spol s r. o.', 'spol. s r. o.', 's.r.o.', 's. r. o.', 'a.s.', 'a. s.', 'v.o.s.', 'k.s.', 'k. s.', ',', '.', '-', '"', "'", '/', '\\']:
        n = n.replace(s, ' ')
    return ' '.join(n.split())

def clean_phone(p):
    if not p:
        return ""
    p = str(p).strip()
    if not p:
        return ""
    if not p.startswith("'"):
        p = f"'{p}"
    return p

def clean_digits(p):
    nums = re.sub(r'\D', '', str(p))
    return nums[-9:] if len(nums) >= 9 else ''

def clean_email(raw_email):
    if not raw_email:
        return ""
    e = str(raw_email).strip().lower()
    e = re.sub(r'^(e-mail:|email:|mail:)\s*', '', e)
    emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', e)
    if not emails:
        return ""
    
    # Bộ chấm điểm tuyển chọn 1 mail giá trị nhất cho B2B Manpower
    def score_email(em):
        u, d = em.split('@', 1)
        score = 10
        if any(hr in u for hr in ['praca', 'kariera', 'hr', 'jobs', 'nabor', 'personalne']):
            score += 50
        elif any(lead in u for lead in ['vedenie', 'riaditel', 'konatel', 'ceo', 'director', 'manager']):
            score += 45
        elif any(c in u for c in ['info', 'kontakt', 'contact', 'office', 'biuro', 'sekretariat']):
            score += 40
        if '.' in u:
            score += 25
        if not any(f in d for f in ['gmail.com', 'seznam.cz', 'azet.sk', 'zoznam.sk', 'post.sk']):
            score += 15
        return score

    emails.sort(key=score_email, reverse=True)
    return emails[0]

def clean_date(d):
    if not d or pd.isna(d):
        return ""
    s = str(d).strip()
    # If datetime object or ISO string like 2010-10-06 00:00:00
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})', s)
    if m:
        return f"{m.group(3)}.{m.group(2)}.{m.group(1)}"
    return s

def categorize_status(s):
    s_lower = str(s).lower()
    if any(k in s_lower for k in ['k có nhu cầu', 'không có nhu cầu', 'k hợp', 'ko hợp', 'chỉ tuyển lao động điạ phương', 'chưa lấy ngoài eu', 'chỉ làm ở đức', 'chỉ làm việc ở séc', 'chỉ tuyển cho séc', 'sai ngành', 'không tuyển người']):
        return 'Đã từ chối'
    if any(k in s_lower for k in ['không tồn tại', 'k tồn tại', 'k tônf tại', 'sai số', 'offline', 'k gọi đc', 'k gọi được', 'không có quyền gọi', 'nhầm máy']):
        return 'Số hỏng'
    if any(k in s_lower for k in ['knm', 'k nhấc máy', 'chưa nghe máy', 'bận chưa nghe máy', 'tắt máy']):
        return 'Đã gọi - KNM'
    if any(k in s_lower for k in ['nhấc máy', 'nghe máy', 'gửi mail', 'gửi lại mail', 'nhắn wa', 'nhắn viber', 'hẹn họp', 'có nhu cầu', 'gửi em thơ']):
        return 'Đã gọi - Tiếp cận'
    return 'Đã gọi'

def main():
    print("=" * 70)
    print("BẮT ĐẦU XỬ LÝ: SK_UDZC_UPSV_0RAW.xlsx -> Chuẩn Hóa Danh Sách SZÚ ÚPSVaR")
    print("=" * 70)

    if not os.path.exists(INPUT_XLSX):
        print(f"[LỖI] Không tìm thấy file nguồn: {INPUT_XLSX}")
        return

    # 1. Đọc sheet hoạt động Zoznam SZÚ
    print(f"[*] Đang đọc file Excel: {INPUT_XLSX} (Sheet: 'Zoznam SZÚ')...")
    df_raw = pd.read_excel(INPUT_XLSX, sheet_name='Zoznam SZÚ', header=2)
    df_raw = df_raw.dropna(subset=['IČO', 'Názov']).copy()
    print(f"[+] Tìm thấy {len(df_raw)} công ty đang hoạt động hợp pháp trong danh sách SZÚ.")

    # 2. Xây dựng bộ tham chiếu làm giàu dữ liệu từ cơ sở dữ liệu hiện có
    print("[*] Đang nạp cơ sở dữ liệu làm giàu (SK_ADZC_UPSV_2COL, SK_AGCY_WEBD_2COL, SK_AGCY_DONE_0RAW)...")
    enrich_db = {}
    
    # Nạp từ SK_ADZC_UPSV_2COL
    f_adzc = os.path.join(ROOT_DIR, "SK_ADZC_UPSV_2COL.csv")
    if os.path.exists(f_adzc):
        df_adzc = pd.read_csv(f_adzc, encoding='utf-8-sig', dtype=str).fillna('')
        for _, r in df_adzc.iterrows():
            nm = norm_name(r['Công ty'])
            if nm and nm not in enrich_db:
                enrich_db[nm] = {
                    'phone': r.get('SĐT', ''),
                    'email': r.get('Email', ''),
                    'web': r.get('Liên Hệ', ''),
                    'check_gui': r.get('Check gửi', ''),
                    'reply': r.get('Trạng thái Reply', '')
                }

    # Nạp từ SK_AGCY_WEBD_2COL
    f_webd = os.path.join(ROOT_DIR, "SK_AGCY_WEBD_2COL.csv")
    if os.path.exists(f_webd):
        df_webd = pd.read_csv(f_webd, encoding='utf-8-sig', dtype=str).fillna('')
        for _, r in df_webd.iterrows():
            nm = norm_name(r['Công ty'])
            if nm:
                if nm not in enrich_db:
                    enrich_db[nm] = {
                        'phone': r.get('SĐT', ''),
                        'email': r.get('Email', ''),
                        'web': r.get('Liên Hệ', ''),
                        'check_gui': r.get('Check gửi', ''),
                        'reply': r.get('Trạng thái Reply', '')
                    }
                else:
                    # Bổ sung thông tin nếu còn trống
                    if not enrich_db[nm]['phone']: enrich_db[nm]['phone'] = r.get('SĐT', '')
                    if not enrich_db[nm]['email']: enrich_db[nm]['email'] = r.get('Email', '')
                    if not enrich_db[nm]['web']: enrich_db[nm]['web'] = r.get('Liên Hệ', '')

    # Nạp lịch sử cuộc gọi từ SK_AGCY_DONE_0RAW
    done_db = {}
    f_done = os.path.join(ROOT_DIR, "SK_AGCY_DONE_0RAW.csv")
    if os.path.exists(f_done):
        df_done = pd.read_csv(f_done, encoding='utf-8-sig', dtype=str).fillna('')
        col_status = next(c for c in df_done.columns if 'tình trạng' in c.lower() or 'trạng' in c.lower())
        for _, r in df_done.iterrows():
            st = str(r[col_status]).strip()
            if not st:
                continue
            nm = norm_name(r.get('Công ty', ''))
            ph = clean_digits(r.get('SĐT', ''))
            em = str(r.get('Email', '')).strip().lower()
            if nm: done_db[('name', nm)] = st
            if ph: done_db[('phone', ph)] = st
            if em: done_db[('email', em)] = st

    print(f"[+] Cơ sở dữ liệu đối chiếu sẵn sàng với {len(enrich_db)} doanh nghiệp và {len(done_db)} bản ghi lịch sử cuộc gọi.")

    # 3. Duyệt và chuẩn hóa từng doanh nghiệp
    processed_records = []
    CATEGORY_STR = "Môi giới việc làm / Sprostredkovanie zamestnania za úhradu (SZÚ)"

    count_enriched_phone = 0
    count_enriched_email = 0
    count_enriched_web = 0
    count_matched_call = 0

    for idx, row in df_raw.iterrows():
        raw_ico = str(row['IČO']).strip().replace('.0', '')
        # Chuẩn hóa IČO thành 8 chữ số
        if raw_ico.isdigit() and len(raw_ico) < 8:
            raw_ico = raw_ico.zfill(8)
            
        company_name = clean_company_name(row['Názov'])
        address = clean_company_name(row['Adresa sídla'])
        datum = clean_date(row['Dátum vzniku oprávnenia'])
        poznamky = clean_company_name(row.get('Poznámky ', ''))

        # Làm giàu thông tin từ CSDL
        nm_key = norm_name(company_name)
        phone = ""
        email = ""
        web = ""
        check_gui = ""
        reply_note = ""

        if nm_key in enrich_db:
            info = enrich_db[nm_key]
            phone = clean_phone(info.get('phone', ''))
            email = clean_email(info.get('email', ''))
            web = str(info.get('web', '')).strip()
            check_gui = str(info.get('check_gui', '')).strip()
            reply_note = str(info.get('reply', '')).strip()

        # Đối chiếu bổ sung lịch sử cuộc gọi từ DONE
        ph_digits = clean_digits(phone)
        call_status = ""
        if ph_digits and ('phone', ph_digits) in done_db:
            call_status = done_db[('phone', ph_digits)]
        elif email and ('email', email.lower()) in done_db:
            call_status = done_db[('email', email.lower())]
        elif ('name', nm_key) in done_db:
            call_status = done_db[('name', nm_key)]

        if call_status:
            reply_note = call_status
            check_gui = categorize_status(call_status)
            count_matched_call += 1

        if phone: count_enriched_phone += 1
        if email: count_enriched_email += 1
        if web: count_enriched_web += 1

        processed_records.append({
            'ico': raw_ico,
            'company': company_name,
            'address': address,
            'datum': datum,
            'poznamky': poznamky,
            'phone': phone,
            'email': email,
            'web': web,
            'check_gui': check_gui,
            'reply_note': reply_note,
            'category': CATEGORY_STR
        })

    print("\n" + "=" * 50)
    print("KẾT QUẢ ĐỐI CHIẾU & LÀM GIÀU DỮ LIỆU:")
    print(f"  - Tổng số công ty SZÚ đang hoạt động: {len(processed_records)}")
    print(f"  - Số công ty được làm giàu SĐT: {count_enriched_phone}")
    print(f"  - Số công ty được làm giàu Email: {count_enriched_email}")
    print(f"  - Số công ty được làm giàu Website: {count_enriched_web}")
    print(f"  - Số công ty khớp nhật ký gọi điện: {count_matched_call}")
    print("=" * 50 + "\n")

    # 4. Phân nhóm và sắp xếp chuẩn Cold Mail (Email lên đầu)
    with_email = [r for r in processed_records if r['email']]
    with_phone_only = [r for r in processed_records if not r['email'] and r['phone']]
    remaining = [r for r in processed_records if not r['email'] and not r['phone']]

    sorted_records = with_email + with_phone_only + remaining
    print(f"[*] Sắp xếp thứ tự danh sách:")
    print(f"  1. Nhóm có Email (ưu tiên Cold Mail): dòng 1 -> {len(with_email)}")
    print(f"  2. Nhóm có SĐT (phục vụ Telesale): dòng {len(with_email)+1} -> {len(with_email)+len(with_phone_only)}")
    print(f"  3. Nhóm chỉ có thông tin pháp nhân (IČO, địa chỉ): dòng {len(with_email)+len(with_phone_only)+1} -> {len(sorted_records)}")

    # 5. Xuất file Cold Mail 20 cột (SK_UDZC_UPSV_2COL.csv)
    coldmail_rows = []
    detail_rows = []

    for no, r in enumerate(sorted_records, 1):
        coldmail_rows.append({
            "No.": no,
            "Công ty": r['company'],
            "Chức danh": "",
            "Người liên hệ": "",
            "SĐT": r['phone'],
            "Liên Hệ": r['web'],
            "Email": r['email'],
            "Liên Hệ mail": "",
            "Địa chỉ": r['address'],
            "Lương": "",
            "Ngày đăng": r['datum'],
            "Hạn tuyển": "",
            "Check gửi": r['check_gui'],
            "Last Subject": "",
            "Last Body HTML": "",
            "Trạng thái Reply": r['reply_note'],
            "Lần Follow-up": "",
            "Ngày Follow-up gần nhất": "",
            "Mailbox đã dùng": "",
            "Category": r['category']
        })

        detail_rows.append({
            "No.": no,
            "ICO": r['ico'],
            "Cong_Ty": r['company'],
            "Dia_Chi": r['address'],
            "SDT": r['phone'],
            "Email": r['email'],
            "Website": r['web'],
            "Datum_Vzniku": r['datum'],
            "Poznamky": r['poznamky'],
            "Check_Gui": r['check_gui'],
            "Trang_Thai_Reply": r['reply_note'],
            "Category": r['category']
        })

    # Tạo thư mục đích
    os.makedirs(os.path.join(ROOT_DIR, "data", "formatted"), exist_ok=True)
    os.makedirs(os.path.join(ROOT_DIR, "data", "raw"), exist_ok=True)

    # Ghi file Cold Mail tại root
    with open(ROOT_COLDMAIL_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLDMAIL_FIELDNAMES)
        writer.writeheader()
        writer.writerows(coldmail_rows)
    print(f"[V] Đã ghi file Cold Mail chuẩn 20 cột: {ROOT_COLDMAIL_CSV}")

    # Ghi file Cold Mail tại data/formatted/
    with open(FMT_COLDMAIL_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLDMAIL_FIELDNAMES)
        writer.writeheader()
        writer.writerows(coldmail_rows)
    print(f"[V] Đã đồng bộ file Cold Mail: {FMT_COLDMAIL_CSV}")

    # Ghi file Metadata chi tiết tại data/formatted/
    with open(FMT_DETAIL_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=DETAIL_FIELDNAMES)
        writer.writeheader()
        writer.writerows(detail_rows)
    print(f"[V] Đã ghi file Metadata chi tiết (IČO, ngày cấp phép): {FMT_DETAIL_CSV}")

    # Sao lưu file raw
    shutil.copy2(INPUT_XLSX, RAW_BACKUP_XLSX)
    print(f"[V] Đã sao lưu file gốc: {RAW_BACKUP_XLSX}")

    print("\n" + "=" * 70)
    print("HOÀN TẤT XỬ LÝ 100% THÀNH CÔNG!")
    print("=" * 70)

if __name__ == '__main__':
    main()
