# -*- coding: utf-8 -*-
"""
Chuẩn hóa dữ liệu Cold Mail 20 cột cho Bộ dữ liệu Doanh nghiệp Cung ứng Lao động Áo (Austria Agency):
Tệp nguồn: AT_AGCY_SHET_1ENR.csv
Tệp đích:  AT_AGCY_SHET_2COL.csv & data/formatted/AT_AGCY_SHET_2COL.csv
Cập nhật làm sạch in-place: AT_AGCY_SHET_1ENR.csv

Quy chuẩn tuân thủ nghiêm ngặt:
1. Chuẩn hóa tên tệp 17 ký tự: AT_AGCY_SHET_2COL.csv ([CC]_[IND4]_[SRC4]_[STG4].csv).
2. Chuẩn 20 cột Cold Mail hoàn chỉnh, định dạng CSV UTF-8 with BOM (utf-8-sig).
3. SĐT luôn có dấu nháy đơn ' ở đầu ('+43... hoặc '0...).
4. Loại bỏ 100% email vi phạm quyền riêng tư / rủi ro pháp lý (Data Privacy / GDPR / DPO / Legal):
   - dataprivacy@vtu.com -> Thay thế bằng email văn phòng hợp lệ (office.graz@vtu.com).
   - spdl.datenschutz.at@siemens.com -> Thay thế bằng email chính thức của Siemens Personaldienstleistungen (spdl1.at@siemens.com).
   - office@datenschutz-nord.de -> Thay thế bằng email văn phòng chính thức (info@rts-wind.de).
   - datenschutz@jku.at, datenschutz@jimdo.com -> Loại bỏ triệt để.
   - Quét và loại bỏ toàn bộ các email chứa privacy, gdpr, dpo, legal, compliance, abuse, sentry, noreply...
5. Đẩy 100% doanh nghiệp có Email lên đầu danh sách (dòng 1 -> N) để sẵn sàng gửi Cold Mail ngay lập tức.
"""

import sys
import os
import re
import csv
import urllib.parse
from pathlib import Path

# Cấu hình UTF-8 cho console Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = str(ROOT_DIR / "AT_AGCY_SHET_1ENR.csv")
OUTPUT_ROOT_CSV = str(ROOT_DIR / "AT_AGCY_SHET_2COL.csv")
OUTPUT_FMT_DIR = ROOT_DIR / "data" / "formatted"
OUTPUT_FMT_CSV = str(OUTPUT_FMT_DIR / "AT_AGCY_SHET_2COL.csv")

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

EMAIL_REGEX = re.compile(r'^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,10}$')
INVALID_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf', '.css', '.js', '.ico', '.woff', '.woff2')

LEGAL_PRIVACY_PATTERNS = [
    # Quyền riêng tư & Bảo vệ dữ liệu (GDPR / DPO / Privacy)
    'dataprivacy', 'data-privacy', 'data_privacy', 'data.privacy',
    'privacy', 'privacypolicy', 'gdpr', 'dpo', 'dataprotection',
    'data-protection', 'data_protection', 'datenschutz',
    'ochrana-udajov', 'ochrananadatu', 'ochranaou', 'ochrana_udajov',
    # Pháp lý & Tranh chấp & Tuân thủ
    'compliance', 'legal', 'pravne', 'pravnik', 'advokat', 'notar',
    'dispute', 'litigation', 'claim', 'claims',
    # Bảo mật, Báo cáo rác, Hủy nhận tin
    'abuse', 'security', 'phishing', 'spam', 'blacklist',
    'unsubscribe', 'optout', 'opt-out', 'remove',
    # Hệ thống tự động & Email vô hiệu
    'noreply', 'no-reply', 'donotreply', 'do-not-reply',
    'postmaster', 'postmater', 'hostmaster', 'webmaster', 'mailer-daemon', 'sentry',
    # Hóa đơn & Khiếu nại
    'faktury', 'faktura', 'invoice', 'invoices', 'reklamac', 'reklamacie',
    # Demo & Placeholder
    'youremail', 'your-email', 'your_email', 'yourname', 'your-name',
    'someone@', 'user@domain.com', 'example@', 'domain@'
]

# Bảng tra cứu thay thế thủ công các email đã kiểm tra tính chính xác
MANUAL_REPLACEMENTS = {
    'dataprivacy@vtu.com': 'office.graz@vtu.com',
    'spdl.datenschutz.at@siemens.com': 'spdl1.at@siemens.com',
    'office@datenschutz-nord.de': 'info@rts-wind.de'
}

def clean_phone(p):
    if not p:
        return ""
    p = p.replace('\xa0', ' ').strip()
    parts = re.split(r'[,;]', p)
    first_phone = parts[0].strip() if parts else p
    first_phone = re.sub(r'[\s/()-]+', '', first_phone)
    if first_phone and not first_phone.startswith("'"):
        first_phone = f"'{first_phone}"
    return first_phone

def is_legal_or_privacy_email(email):
    if not email or '@' not in email:
        return True
    e = email.lower().strip()
    u, d = e.split('@', 1)
    tokens = re.split(r'[-_.]', u)

    for kw in LEGAL_PRIVACY_PATTERNS:
        if kw in u:
            if len(kw) <= 4:
                if kw in tokens:
                    return True
            else:
                return True

    junk_domains = {'example.com', 'domain.com', 'yourdomain.com', 'email.com', 'sentry.io', 'wixpress.com', 'jimdo.com'}
    if d in junk_domains or any(d.endswith('.' + jd) for jd in junk_domains):
        return True

    return False

def clean_email(email_str):
    if not email_str:
        return ""
    e = email_str.replace('%20', '').strip().rstrip('.,;:/\\')

    # Kiểm tra bảng thay thế thủ công
    e_lower = e.lower()
    if e_lower in MANUAL_REPLACEMENTS:
        return MANUAL_REPLACEMENTS[e_lower]

    if is_legal_or_privacy_email(e_lower):
        return ""

    if EMAIL_REGEX.match(e):
        return e_lower
    return ""

def main():
    print("=" * 80)
    print("QUY TRINH CHUAN HOA DU LIEU COLD MAIL 20 COT: AT_AGCY_SHET_2COL.csv")
    print(f"File nguon: {INPUT_CSV}")
    print(f"File xuat 1 (Root): {OUTPUT_ROOT_CSV}")
    print(f"File xuat 2 (Formatted): {OUTPUT_FMT_CSV}")
    print("=" * 80)

    if not os.path.exists(INPUT_CSV):
        print(f"[-] Khong tim thay file nguon: {INPUT_CSV}")
        return

    with open(INPUT_CSV, 'r', encoding='utf-8-sig', errors='ignore') as f:
        reader = csv.DictReader(f)
        raw_rows = list(reader)

    print(f"[*] Tong so doanh nghiep trong file: {len(raw_rows)}")

    cleaned_records = []
    privacy_fixed_count = 0
    privacy_removed_count = 0

    for r in raw_rows:
        company = r.get('Công ty', '').strip()
        phone_raw = r.get('SĐT', '').strip()
        web_raw = r.get('Liên Hệ', '') or r.get('Website', '')
        web_raw = web_raw.strip()
        email_raw = r.get('Email', '').strip()
        addr = r.get('Địa chỉ', '').strip()

        # Lam sach va kiem tra email phap ly
        cleaned_em = clean_email(email_raw)
        if email_raw and cleaned_em != email_raw.lower():
            if cleaned_em:
                print(f"  [REPLACED] {company}: '{email_raw}' -> '{cleaned_em}'")
                privacy_fixed_count += 1
            else:
                print(f"  [REMOVED PRIVACY] {company}: '{email_raw}' bi loai bo de tranh rui ro phap ly.")
                privacy_removed_count += 1

        phone_cleaned = clean_phone(phone_raw)

        # Chuan hoa link website
        web_clean = web_raw
        if web_clean:
            if web_clean.startswith('http://https://'):
                web_clean = web_clean.replace('http://https://', 'https://')
            elif web_clean.startswith('http://http://'):
                web_clean = web_clean.replace('http://http://', 'http://')
            elif not web_clean.startswith(('http://', 'https://')):
                web_clean = 'http://' + web_clean

        check_gui = "OK" if cleaned_em else ""

        rec = {
            "No.": "",
            "Công ty": company,
            "Chức danh": r.get('Chức danh', '').strip(),
            "Người liên hệ": r.get('Người liên hệ', '').strip(),
            "SĐT": phone_cleaned,
            "Liên Hệ": web_clean,
            "Email": cleaned_em,
            "Liên Hệ mail": r.get('Liên Hệ mail', '').strip(),
            "Địa chỉ": addr,
            "Lương": r.get('Lương', '').strip(),
            "Ngày đăng": r.get('Ngày đăng', '').strip(),
            "Hạn tuyển": r.get('Hạn tuyển', '').strip(),
            "Check gửi": check_gui,
            "Last Subject": r.get('Last Subject', '').strip(),
            "Last Body HTML": r.get('Last Body HTML', '').strip(),
            "Trạng thái Reply": r.get('Trạng thái Reply', '').strip(),
            "Lần Follow-up": r.get('Lần Follow-up', '').strip(),
            "Ngày Follow-up gần nhất": r.get('Ngày Follow-up gần nhất', '').strip(),
            "Mailbox đã dùng": r.get('Mailbox đã dùng', '').strip(),
            "Category": "Cung ứng lao động Áo (Arbeitskräfteüberlassung)"
        }
        cleaned_records.append(rec)

    # Phan loai DAY 100% EMAIL LEN DAU
    with_email = [r for r in cleaned_records if r.get('Email')]
    without_email = [r for r in cleaned_records if not r.get('Email')]

    print(f"\n[*] Ket qua phan loai Cold Mail:")
    print(f"  [1] Nhom co Email hop le (San sang gui Cold Mail ngay): {len(with_email)} doanh nghiep")
    print(f"  [2] Nhom khong co Email (Telesale / Nghiên cứu tiep): {len(without_email)} doanh nghiep")
    print(f"  [*] So email Privacy/GDPR da duoc thay the bang email van phong hop le: {privacy_fixed_count}")
    print(f"  [*] So email Privacy/GDPR khong co thay the da bi xoa bo: {privacy_removed_count}")

    sorted_records = with_email + without_email

    for idx, r in enumerate(sorted_records, 1):
        r['No.'] = str(idx)

    # Xuat file ra cac duong dan
    OUTPUT_FMT_DIR.mkdir(parents=True, exist_ok=True)

    for out_path in [OUTPUT_ROOT_CSV, OUTPUT_FMT_CSV, INPUT_CSV]:
        temp_out = out_path + ".tmp"
        with open(temp_out, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=COLDMAIL_FIELDNAMES)
            writer.writeheader()
            writer.writerows(sorted_records)
        try:
            if os.path.exists(out_path):
                try:
                    os.remove(out_path)
                except Exception:
                    pass
            shutil.move(temp_out, out_path)
            print(f"[+] Da xuat file thanh cong: {out_path}")
        except Exception as e:
            # Fallback direct write if move fails
            try:
                with open(out_path, 'w', encoding='utf-8-sig', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=COLDMAIL_FIELDNAMES)
                    writer.writeheader()
                    writer.writerows(sorted_records)
                print(f"[+] Da ghi de truc tiep thanh cong: {out_path}")
                if os.path.exists(temp_out):
                    try:
                        os.remove(temp_out)
                    except Exception:
                        pass
            except Exception as e2:
                print(f"[!] Canh bao: Khong the ghi file {out_path} (co the dang mo trong Excel): {e2}")

    print("\n" + "=" * 80)
    print("HOAN TAT CHUAN HOA DU LIEU COLD MAIL CHO AO (AT_AGCY)!")
    print(f"Tong so doanh nghiep: {len(sorted_records)}")
    print(f"100% Doanh nghiep co Email nam o cac dong dau tien: 1 -> {len(with_email)}")
    print(f"File Cold Mail goc: {OUTPUT_ROOT_CSV}")
    print(f"File Cold Mail formatted: {OUTPUT_FMT_CSV}")
    print("=" * 80)

if __name__ == "__main__":
    main()
