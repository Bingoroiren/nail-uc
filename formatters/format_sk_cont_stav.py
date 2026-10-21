# -*- coding: utf-8 -*-
"""
Chuẩn hóa dữ liệu Cold Mail 20 cột cho ngành Xây dựng Slovakia (Stavbári):
Tệp nguồn: SK_CONT_STAV_0RAW.csv
Tệp đích:  SK_CONT_STAV_2COL.csv & data/formatted/SK_CONT_STAV_2COL.csv

Quy chuẩn tuân thủ nghiêm ngặt:
1. Chuẩn hóa tên tệp 17 ký tự: SK_CONT_STAV_2COL.csv ([CC]_[IND4]_[SRC4]_[STG4].csv).
2. Chuẩn 20 cột Cold Mail hoàn chỉnh, định dạng CSV UTF-8 with BOM (utf-8-sig).
3. SĐT luôn có dấu nháy đơn ' ở đầu ('+421... hoặc '09...).
4. Loại bỏ 100% email vi phạm quyền riêng tư / rủi ro pháp lý (Data Privacy / GDPR / DPO / Legal):
   - dataprivacy@, privacy@, gdpr@, dpo@, data-protection@, compliance@, legal@, pravne@...
   - no-reply@, noreply@, donotreply@, postmaster@, abuse@, sentry@...
   - demo/placeholder emails: youremail@, yourname@, user@domain...
5. Lọc bỏ triệt để các công ty phi xây dựng còn sót (nhà thuốc, mai táng, khách sạn thuần túy, nha sĩ...).
6. Đẩy 100% doanh nghiệp có Email lên đầu danh sách để sẵn sàng gửi Cold Mail ngay lập tức.
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
INPUT_CSV = str(ROOT_DIR / "SK_CONT_STAV_0RAW.csv")
OUTPUT_ROOT_CSV = str(ROOT_DIR / "SK_CONT_STAV_2COL.csv")
OUTPUT_FMT_DIR = ROOT_DIR / "data" / "formatted"
OUTPUT_FMT_CSV = str(OUTPUT_FMT_DIR / "SK_CONT_STAV_2COL.csv")

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

LEGAL_FORMS_SK = [
    'spol. s r.o.', 'spol. s r. o.', 's.r.o.', 's. r. o.', 'sro',
    'spolocnost s rucenim obmedzenym', 'spoločnosť s ručením obmedzeným',
    'akciova spolocnost', 'akciová spoločnosť', 'a.s.', 'a. s.', 'as',
    'komanditna spolocnost', 'komanditná spoločnosť', 'k.s.', 'k. s.',
    'verejna obchodna spolocnost', 'verejná obchodná spoločnosť', 'v.o.s.', 'v. o. s.',
    'druzstvo', 'družstvo', 'gmbh', 'ltd', 'z.z.p.o.', 'e.u.'
]

EMAIL_REGEX = re.compile(r'^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,10}$')
INVALID_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf', '.css', '.js', '.ico', '.woff', '.woff2')

# Bộ lọc từ khóa email vi phạm quyền riêng tư và rủi ro pháp lý (BẮT BUỘC LOẠI BỎ)
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
    # Hóa đơn & Khiếu nại (Không phù hợp kết nối nhân sự)
    'faktury', 'faktura', 'invoice', 'invoices', 'reklamac', 'reklamacie',
    # Demo & Placeholder
    'youremail', 'your-email', 'your_email', 'yourname', 'your-name',
    'someone@', 'user@domain.com', 'example@', 'domain@'
]

# Các từ khóa công ty phi xây dựng cần loại bỏ dứt điểm
STRICT_NON_CONSTRUCTION_NAMES = [
    'hotel', 'penzión', 'penzion', 'lekáreň', 'lekaren',
    'pohrebné služby', 'pohrebnictvo', 'pohrebníctvo',
    'zubná ambulancia', 'stomatológia', 'stomatologia'
]

def clean_company_name_sk(name):
    if not name:
        return ""
    n = re.sub(r'["\'„“”«»]', '', str(name)).strip().lower()
    for lf in sorted(LEGAL_FORMS_SK, key=len, reverse=True):
        n = re.sub(rf'\b{re.escape(lf)}\b', '', n)
    n = re.sub(r'[^\w\s]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n

def extract_domain(url):
    if not url:
        return ""
    try:
        p = urllib.parse.urlparse(url)
        d = p.netloc.lower().replace('www.', '')
        return d.split(':')[0]
    except Exception:
        return ""

def clean_phone(p):
    if not p:
        return ""
    p = p.replace('\xa0', ' ').strip()
    parts = re.split(r'[,;]', p)
    first_phone = parts[0].strip() if parts else p
    digits = re.sub(r'[^\d+]', '', first_phone)
    if digits and len(digits) >= 6:
        return f"'{digits}" if not digits.startswith("'") else digits
    return ""

def is_legal_or_privacy_email(email):
    """
    Nhận diện các email liên quan đến GDPR, Data Privacy, Compliance, Legal Officer
    để loại bỏ 100%, tránh rủi ro khiếu nại pháp lý khi Cold Mail.
    """
    if not email or '@' not in email:
        return True
    e = email.lower().strip()
    u, d = e.split('@', 1)
    tokens = re.split(r'[-_.]', u)

    for kw in LEGAL_PRIVACY_PATTERNS:
        if kw in u:
            # Nếu từ khóa ngắn (<= 4 ký tự như dpo, spam), bắt buộc phải khớp token hoàn chỉnh
            if len(kw) <= 4:
                if kw in tokens:
                    return True
            else:
                return True

    # Loại trừ các domain rác hệ thống
    junk_domains = {'example.com', 'domain.com', 'yourdomain.com', 'email.com', 'sentry.io', 'wixpress.com'}
    if d in junk_domains or any(d.endswith('.' + jd) for jd in junk_domains):
        return True

    return False

def score_email_b2b(email, domain=""):
    """
    Chấm điểm email tối ưu cho B2B Manpower Agency theo Rule 3:
    - Tuyển dụng/Nhân sự: +50đ
    - Ban giám đốc/Điều hành: +45đ
    - Cổng liên hệ chính thức info/office/kontakt: +40đ
    - Khớp domain: +50đ
    """
    if not email or '@' not in email:
        return -1
    e = email.lower().strip()
    if is_legal_or_privacy_email(e):
        return -1
    if not EMAIL_REGEX.match(e):
        return -1
    if any(e.endswith(ext) for ext in INVALID_EXTENSIONS):
        return -1

    u, d = e.split('@', 1)
    score = 10

    if domain and (domain in d or d in domain):
        score += 50
    elif d.endswith('.sk'):
        score += 20
    elif d.endswith('.cz') or d.endswith('.eu'):
        score += 10

    # Ưu tiên nhân sự
    if any(u == k or u.startswith(k) for k in ['praca', 'kariera', 'hr', 'personalne', 'jobs', 'recruitment', 'nabor']):
        score += 50
    # Ưu tiên lãnh đạo
    elif any(u == k or u.startswith(k) for k in ['vedenie', 'riaditel', 'konatel', 'ceo', 'director', 'manager', 'obchod', 'sales']):
        score += 45
    # Cổng liên hệ chính thức
    elif any(u == k or u.startswith(k) for k in ['info', 'kontakt', 'contact', 'office', 'sekretariat', 'recepcia', 'kancelaria']):
        score += 40
    elif '.' in u and score >= 60:
        score += 25
    elif d in ['gmail.com', 'zoznam.sk', 'seznam.cz', 'centrum.sk', 'post.sk', 'azet.sk']:
        score += 10
    elif any(u == k or u.startswith(k) for k in ['servis', 'support']):
        score += 5

    return score

def clean_and_select_best_email(email_field, domain=""):
    if not email_field:
        return ""
    # Tách nếu có nhiều email
    raw_emails = re.split(r'[,;\s]+', str(email_field).replace('%20', ''))
    valid_candidates = []

    for em in raw_emails:
        clean = em.strip().rstrip('.,;:/\\')
        if not clean or '@' not in clean:
            continue
        # Xử lý trường hợp bị dính 2 email
        if clean.count('@') > 1:
            sub_matches = EMAIL_REGEX.findall(clean)
            for sm in sub_matches:
                s = score_email_b2b(sm, domain)
                if s > 0:
                    valid_candidates.append((s, sm.lower()))
            continue

        s = score_email_b2b(clean, domain)
        if s > 0:
            valid_candidates.append((s, clean.lower()))

    if not valid_candidates:
        return ""

    valid_candidates.sort(key=lambda x: x[0], reverse=True)
    return valid_candidates[0][1]

def is_strictly_non_construction(company_name, services_str=""):
    name_lower = company_name.lower().strip()
    serv_lower = services_str.lower().strip()

    # Kiểm tra tên vi phạm
    for trig in STRICT_NON_CONSTRUCTION_NAMES:
        if trig in name_lower:
            # Loại trừ nếu là dịch vụ xây dựng cho khách sạn (ví dụ: stavba bazénov pre hotely)
            if any(k in serv_lower for k in ['stavebn', 'rekonštrukc', 'montáž', 'omietky', 'strechy']):
                continue
            return True

    # Kiểm tra nếu dịch vụ chỉ toàn là nhà thuốc / dược
    if 'lekáreň' in serv_lower and not any(k in serv_lower for k in ['stavb', 'stavebn', 'montáž']):
        return True

    # Kiểm tra nếu chỉ là dịch vụ mai táng
    if 'pohrebné' in serv_lower and not any(k in serv_lower for k in ['stavb', 'stavebn', 'montáž']):
        return True

    return False

def main():
    print("=" * 80)
    print("QUY TRINH CHUAN HOA DU LIEU COLD MAIL 20 COT: SK_CONT_STAV_2COL.csv")
    print(f"File nguon: {INPUT_CSV}")
    print(f"File dich 1: {OUTPUT_ROOT_CSV}")
    print(f"File dich 2: {OUTPUT_FMT_CSV}")
    print("=" * 80)

    if not os.path.exists(INPUT_CSV):
        print(f"[-] Khong tim thay file nguon: {INPUT_CSV}")
        return

    with open(INPUT_CSV, 'r', encoding='utf-8-sig', errors='ignore') as f:
        reader = csv.DictReader(f)
        raw_rows = list(reader)

    print(f"[*] Tong so dong ban dau trong 0RAW: {len(raw_rows)}")

    # 1. Loc bo cac cong ty phi xay dung con sot va lam sach du lieu
    processed_records = {}
    excluded_non_const = 0
    privacy_emails_filtered = 0

    for r in raw_rows:
        company = r.get('Công ty', '').strip()
        services = r.get('Dịch vụ / Services', '').strip()
        phone_raw = r.get('SĐT', '').strip()
        web_raw = r.get('Liên Hệ', '').strip()
        email_raw = r.get('Email', '').strip()
        addr = r.get('Địa chỉ', '').strip()

        # Loai bo cty phi xay dung
        if is_strictly_non_construction(company, services):
            excluded_non_const += 1
            continue

        domain = extract_domain(web_raw)

        # Chon duy nhat 1 email B2B gia tri nhat va loai bo hoan toan privacy/legal
        best_email = clean_and_select_best_email(email_raw, domain)
        if email_raw and not best_email:
            privacy_emails_filtered += 1

        phone_clean = clean_phone(phone_raw)

        # Chuan hoa link web
        web_clean = web_raw
        if web_clean:
            if web_clean.startswith('http://https://'):
                web_clean = web_clean.replace('http://https://', 'https://')
            elif web_clean.startswith('http://http://'):
                web_clean = web_clean.replace('http://http://', 'http://')
            elif not web_clean.startswith(('http://', 'https://')):
                web_clean = 'http://' + web_clean

        key = clean_company_name_sk(company) or domain or company
        if key not in processed_records:
            processed_records[key] = {
                'company': company,
                'phone': phone_clean,
                'web': web_clean,
                'email': best_email,
                'address': addr,
                'category': 'Stavebníctvo',
                'services': services
            }
        else:
            # Merge hop nhat thong tin
            exist = processed_records[key]
            if not exist['email'] and best_email:
                exist['email'] = best_email
            if not exist['phone'] and phone_clean:
                exist['phone'] = phone_clean
            if not exist['web'] and web_clean:
                exist['web'] = web_clean
            if not exist['address'] and addr:
                exist['address'] = addr

    records = list(processed_records.values())

    # 2. Phan loai de DAY 100% EMAIL LEN DAU
    with_email = [r for r in records if r.get('email')]
    without_email = [r for r in records if not r.get('email')]

    print(f"\n[*] Ket qua phan loai Cold Mail:")
    print(f"  [1] Nhom co Email hop le (San sang Cold Mail ngay): {len(with_email)} doanh nghiep")
    print(f"  [2] Nhom khong co Email (Phuc vu Telesale / Research): {len(without_email)} doanh nghiep")
    print(f"  [*] So email vi pham Privacy / Legal da bi triet tieu: {privacy_emails_filtered}")
    print(f"  [*] So cty phi xay dung bi loai them: {excluded_non_const}")

    sorted_records = with_email + without_email

    # 3. Tao 20 cot chuan Cold Mail
    coldmail_rows = []
    for idx, r in enumerate(sorted_records, 1):
        coldmail_rows.append({
            "No.": str(idx),
            "Công ty": r['company'],
            "Chức danh": "",
            "Người liên hệ": "",
            "SĐT": r['phone'],
            "Liên Hệ": r['web'],
            "Email": r['email'],
            "Liên Hệ mail": "",
            "Địa chỉ": r['address'],
            "Lương": "",
            "Ngày đăng": "",
            "Hạn tuyển": "",
            "Check gửi": "",
            "Last Subject": "",
            "Last Body HTML": "",
            "Trạng thái Reply": "",
            "Lần Follow-up": "",
            "Ngày Follow-up gần nhất": "",
            "Mailbox đã dùng": "",
            "Category": r['category']
        })

    # 4. Xuat file UTF-8 with BOM sang thu muc goc va data/formatted
    OUTPUT_FMT_DIR.mkdir(parents=True, exist_ok=True)

    for out_path in [OUTPUT_ROOT_CSV, OUTPUT_FMT_CSV]:
        temp_out = out_path + ".tmp"
        with open(temp_out, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=COLDMAIL_FIELDNAMES)
            writer.writeheader()
            writer.writerows(coldmail_rows)
        if os.path.exists(out_path):
            try:
                os.remove(out_path)
            except Exception:
                pass
        os.rename(temp_out, out_path)
        print(f"[+] Da xuat file Cold Mail chuan thanh cong: {out_path}")

    print("\n" + "=" * 80)
    print("HOAN TAT CHUAN HOA COLD MAIL 20 COT!")
    print(f"Tong so doanh nghiep Xay dung: {len(coldmail_rows)}")
    print(f"100% Doanh nghiep co Email nam o cac dong: 1 -> {len(with_email)}")
    print(f"Tep goc: {OUTPUT_ROOT_CSV}")
    print(f"Tep formatted: {OUTPUT_FMT_CSV}")
    print("=" * 80)

if __name__ == "__main__":
    main()
