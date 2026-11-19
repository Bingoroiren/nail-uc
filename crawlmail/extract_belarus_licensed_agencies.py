# -*- coding: utf-8 -*-
"""
EXTRACT BELARUS LICENSED RECRUITMENT AGENCIES 2026 (BY_AGCY_PDF0)
================================================================
Source: https://labourbooking.com/files/Belarus-Licensed-Recruitment-Agencies-2026.pdf
Input:  scratch/belarus_agencies_2026.pdf (Official Registry of Licensed Manpower Agencies)
Output: BY_AGCY_PDF0_0RAW.csv + BY_AGCY_PDF0_2COL.csv + Sync to csdl_mlt/ & archive/by_belarus/
Rules:  GEMINI.md (Rule 1, 2, 3, 10, 11, 12)
"""

import os
import sys
import re
import csv
import shutil
import unicodedata
from pathlib import Path
import pandas as pd
import pdfplumber

# UTF-8 console output
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

PDF_FILE = ROOT_DIR / "scratch" / "belarus_agencies_2026.pdf"

OUTPUT_0RAW_PATH = ROOT_DIR / "BY_AGCY_PDF0_0RAW.csv"
OUTPUT_2COL_PATH = ROOT_DIR / "BY_AGCY_PDF0_2COL.csv"
OUTPUT_READY_PATH = ROOT_DIR / "BY_AGCY_PDF0_ONLY_EMAILS_READY.csv"

CSDL_DIR = ROOT_DIR / "csdl_mlt"
ARCHIVE_DIR = ROOT_DIR / "archive" / "by_belarus"

COLDMAIL_COLUMNS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

# Rule 12: Permanent blacklist
BLACKLIST = ['scandi standard', 'scandi-standard', 'scandi standart', 'biliarta', 'daigre']

def is_blacklisted(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in clean for b in BLACKLIST)

def clean_phone_by(raw_phone):
    """Rule 2: Chuẩn hóa SĐT Belarus bắt buộc có nháy đơn (') ở đầu"""
    if not raw_phone or str(raw_phone).strip() in ['', 'None', 'nan']:
        return ""
    p = str(raw_phone).strip().lstrip("'").strip()
    digits = re.sub(r'[^\d+]', '', p)
    if not digits:
        return ""
    if digits.startswith('+375'):
        pass
    elif digits.startswith('375'):
        digits = '+' + digits
    elif digits.startswith('80') and len(digits) >= 9:
        digits = '+375' + digits[2:]
    else:
        digits = '+375' + digits

    # Định dạng dễ đọc: +375 XX XXX XX XX
    if digits.startswith('+375') and len(digits) == 13:
        formatted = f"+375 {digits[4:6]} {digits[6:9]} {digits[9:11]} {digits[11:]}"
        return f"'{formatted}"
    return f"'{digits}"

def parse_pdf():
    if not PDF_FILE.exists():
        print(f"[!] Không tìm thấy tệp {PDF_FILE.name}")
        return []

    print("=" * 80)
    print("📄 ĐANG TRÍCH XUẤT DANH SÁCH CÔNG TY MÔI GIỚI XUẤT KHẨU LAO ĐỘNG BELARUS 2026")
    print(f"   Tệp nguồn: {PDF_FILE}")
    print("=" * 80)

    raw_table_rows = []
    with pdfplumber.open(PDF_FILE) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            table = page.extract_table()
            if table:
                # Bỏ qua dòng tiêu đề ở trang
                data_rows = table[1:] if page_idx == 0 or table[0][0] == 'Лицензиат' else table
                raw_table_rows.extend(data_rows)

    print(f"[*] Đã bóc tách thành công {len(raw_table_rows)} dòng dữ liệu từ 5 trang PDF.")

    records = []
    for idx, r in enumerate(raw_table_rows):
        if not r or len(r) < 5:
            continue

        lic = (r[0] or "").replace('\n', ' ').strip()
        lic_no = (r[1] or "").replace('\n', ' ').strip()
        contact = (r[2] or "").replace('\n', ' ').strip()
        dest = (r[3] or "").replace('\n', ' ').strip()
        spec = (r[4] or "").replace('\n', ' ').strip()

        if not lic:
            continue

        # 1. Bóc tách tên thương hiệu / tên công ty trong ngoặc
        m_name = re.search(r'["«“„]([^"»”]+)', lic)
        short_name = m_name.group(1).strip() if m_name else lic

        # Khử từ khóa legal form nếu bị dính
        for lf_prefix in ['Общество с ограниченной ответственностью', 'Частное унитарное предприятие', 'Сервисное частное']:
            short_name = short_name.replace(lf_prefix, '').strip(' "«“')

        if not short_name:
            short_name = lic

        # Kiểm tra danh sách đen (Rule 12)
        if is_blacklisted(short_name) or is_blacklisted(lic):
            continue

        # 2. Phân loại hình thức doanh nghiệp
        legal_form = "ООО (Công ty TNHH)"
        lic_lower = lic.lower()
        if "ограниченной ответственностью" in lic_lower or "ооо" in lic_lower:
            legal_form = "ООО (LLC / TNHH)"
        elif "унитарное предприятие" in lic_lower or "чуп" in lic_lower or "уп" in lic_lower:
            legal_form = "ЧУП (Unitary Enterprise / Doanh nghiệp Tư nhân)"
        elif "общественное объединение" in lic_lower:
            legal_form = "ОО (Public Association / Đoàn thể)"
        elif "индивидуальный предприниматель" in lic_lower or "ип " in lic_lower:
            legal_form = "ИП (Sole Proprietor / Hộ kinh doanh)"
        elif "акционерное общество" in lic_lower:
            legal_form = "ЗАО / ОАО (JSC / Cổ phần)"

        # 3. Số giấy phép & Ngày cấp phép
        m_lic = re.search(r'([0-9/]+)\s*от\s*([0-9.]+)', lic_no)
        license_code = m_lic.group(1).strip() if m_lic else lic_no
        license_date = m_lic.group(2).strip() if m_lic else ""

        # 4. Bóc tách số điện thoại (Rule 2)
        phones = re.findall(r'\+375[\d\s()-]{7,15}', contact)
        if not phones:
            m_tel = re.findall(r'(?:тел|тел\.|тел:|факс|моб)\s*[:.]?\s*([+0-9\s()-]{7,25})', contact, re.I)
            if m_tel:
                phones = [t.strip() for t in m_tel if any(c.isdigit() for c in t)]

        clean_phones = [clean_phone_by(p) for p in phones if p]
        primary_phone = clean_phones[0] if clean_phones else ""
        all_phones_str = '; '.join(clean_phones)

        # 5. Bóc tách Thành phố tại Belarus
        city = "Минск"  # Mặc định thủ đô Minsk
        m_city = re.search(r'г\.\s*([А-Яа-яЁёA-Za-z-]+)', contact)
        if m_city:
            city = m_city.group(1).strip()
        elif "Минская" in contact or "Минский" in contact:
            city = "Минская обл."
        elif "Брест" in contact:
            city = "Брест"
        elif "Гродно" in contact:
            city = "Гродно"
        elif "Гомель" in contact:
            city = "Гомель"
        elif "Витебск" in contact:
            city = "Витебск"
        elif "Могилев" in contact or "Могилёв" in contact:
            city = "Могилев"

        # 6. Chi nhánh nếu có
        branches = ""
        if "филиал" in contact.lower():
            m_br = re.search(r'филиал[ыа]?\s*[:.]?\s*([^;.]+)', contact, re.I)
            if m_br:
                branches = m_br.group(1).strip()

        # 7. Địa chỉ trụ sở (Làm sạch phần sđt và chi nhánh)
        addr = re.sub(r'(?:тел|факс|моб|филиал).*', '', contact, flags=re.I).strip(' .,-')

        records.append({
            "No.": len(records) + 1,
            "Cong_Ty": short_name,
            "Ten_Phap_Ly": lic,
            "Loai_Hinh": legal_form,
            "So_Giay_Phep": license_code,
            "Ngay_Cap_Phep": license_date,
            "Thanh_Pho": city,
            "Dia_Chi": addr,
            "SDT": primary_phone,
            "Tat_Ca_SDT": all_phones_str,
            "Chi_Nhanh": branches,
            "Thi_Truong_Xuat_Khau": dest,
            "Nganh_Nghe_Tuyen_Dung": spec,
            "Website": "",
            "Email": ""
        })

    return records

def export_all(records):
    if not records:
        print("[!] Không có dữ liệu để xuất!")
        return

    # 1. Xuất file thô chi tiết 15 cột phục vụ làm giàu (BY_AGCY_PDF0_0RAW.csv)
    df_raw = pd.DataFrame(records)
    df_raw.to_csv(OUTPUT_0RAW_PATH, index=False, encoding='utf-8-sig')
    print(f"\n[+] Đã xuất file Master thô 15 cột: {OUTPUT_0RAW_PATH.name} ({len(df_raw)} công ty)")

    # 2. Xuất file Cold Mail 20 cột chuẩn của dự án (BY_AGCY_PDF0_2COL.csv)
    coldmail_rows = []
    for r in records:
        full_addr = f"{r['Dia_Chi']}, {r['Thanh_Pho']}".strip(', ')
        cat_desc = f"Recruitment Agency (Thị trường: {r['Thi_Truong_Xuat_Khau']})"

        coldmail_rows.append({
            'No.': r['No.'],
            'Công ty': r['Cong_Ty'],
            'Chức danh': 'Директор (Director)',
            'Người liên hệ': '',
            'SĐT': r['SDT'],
            'Liên Hệ': '',
            'Email': '',
            'Liên Hệ mail': '',
            'Địa chỉ': full_addr,
            'Lương': '',
            'Ngày đăng': r['Ngay_Cap_Phep'],
            'Hạn tuyển': r['So_Giay_Phep'],  # Lưu số giấy phép vào cột quản lý
            'Check gửi': 'Chưa gửi',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': cat_desc
        })

    df_2col = pd.DataFrame(coldmail_rows, columns=COLDMAIL_COLUMNS)
    df_2col.to_csv(OUTPUT_2COL_PATH, index=False, encoding='utf-8-sig')
    print(f"[+] Đã xuất file Cold Mail 20 cột: {OUTPUT_2COL_PATH.name}")

    # 3. Đồng bộ sang csdl_mlt/ và archive/by_belarus/
    for extra_dir in [CSDL_DIR, ARCHIVE_DIR]:
        extra_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(OUTPUT_0RAW_PATH, extra_dir / OUTPUT_0RAW_PATH.name)
            shutil.copy2(OUTPUT_2COL_PATH, extra_dir / OUTPUT_2COL_PATH.name)
        except Exception:
            pass

    print(f"[+] Đã đồng bộ sang {CSDL_DIR.name}/ và {ARCHIVE_DIR.name}/")

def main():
    records = parse_pdf()
    export_all(records)

    print("\n" + "=" * 80)
    print("🏆 BÁO CÁO TỔNG QUAN DỮ LIỆU ĐÃ TRÍCH XUẤT:")
    print(f"   - Tổng số công ty môi giới được cấp phép : {len(records)} công ty")
    has_phone = len([r for r in records if r['SDT']])
    print(f"   - Công ty có SĐT trực tiếp ('+375...)     : {has_phone} ({has_phone*100/len(records):.1f}%)")
    print("   - Tệp dữ liệu đã sẵn sàng để làm giàu:")
    print(f"     1. {OUTPUT_0RAW_PATH.name} (File thô 15 trường chi tiết nhất)")
    print(f"     2. {OUTPUT_2COL_PATH.name} (File chuẩn 20 cột Cold Mail)")
    print("=" * 80 + "\n")

if __name__ == '__main__':
    main()

