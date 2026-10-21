# -*- coding: utf-8 -*-
"""
Loại bỏ các công ty trong SK_MANU_ZLAT_0RAW.csv đã có trong SK_AUTO_ZLAT_2COL.csv:
Tránh tình trạng gửi trùng, spam khách hàng đã được gửi ở chiến dịch Automotive.

Quy trình:
1. Sao lưu file gốc: SK_MANU_ZLAT_0RAW_backup.csv.
2. Trích xuất chỉ mục từ SK_AUTO_ZLAT_2COL.csv:
   - Tên công ty chuẩn hóa (bỏ hậu tố pháp lý s.r.o., a.s..., bỏ dấu tiếng Slovak).
   - Domain website doanh nghiệp (loại trừ domain rác/mạng xã hội).
   - Email doanh nghiệp riêng biệt (loại trừ webmail công cộng).
   - SĐT trùng khớp kèm từ khóa thương hiệu tương đồng.
3. Lọc bỏ các dòng trùng lặp khỏi SK_MANU_ZLAT_0RAW.csv.
4. Xuất báo cáo đối soát: SK_MANU_ZLAT_removed_duplicates.csv để kiểm tra minh bạch.
5. Đánh lại số thứ tự No. tăng dần và lưu file UTF-8 with BOM (utf-8-sig).
"""

import sys
import os
import re
import csv
import shutil
import unicodedata
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
MANU_CSV = str(ROOT_DIR / "SK_MANU_ZLAT_0RAW.csv")
AUTO_CSV = str(ROOT_DIR / "SK_AUTO_ZLAT_2COL.csv")
BACKUP_CSV = str(ROOT_DIR / "SK_MANU_ZLAT_0RAW_backup.csv")
REMOVED_CSV = str(ROOT_DIR / "SK_MANU_ZLAT_removed_duplicates.csv")

LEGAL_FORMS = [
    'spol. s r.o.', 'spol. s r. o.', 's.r.o.', 's. r. o.', 'sro',
    'akciova spolocnost', 'akciová spoločnosť', 'a.s.', 'a. s.', 'as',
    'komanditna spolocnost', 'komanditná spoločnosť', 'k.s.', 'k. s.',
    'verejna obchodna spolocnost', 'verejná obchodná spoločnosť', 'v.o.s.', 'v. o. s.',
    'druzstvo', 'družstvo', 'gmbh', 'ltd', 'z.z.p.o.', 'e.u.'
]

COMMON_EMAIL_DOMAINS = {
    'gmail.com', 'zoznam.sk', 'seznam.cz', 'centrum.sk', 'post.sk', 'azet.sk',
    'atlas.sk', 'inmail.sk', 'email.cz', 'yahoo.com', 'hotmail.com', 'outlook.com',
    'pobox.sk', 'szm.sk', 'chello.sk', 't-zones.sk', 'telekom.sk', 'datacom.eu'
}

def strip_accents(text):
    if not text:
        return ""
    text = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in text if not unicodedata.combining(c))

def normalize_name(name):
    if not name:
        return ""
    n = strip_accents(name.lower().strip())
    for lf in sorted(LEGAL_FORMS, key=len, reverse=True):
        clean_lf = strip_accents(lf.lower())
        n = re.sub(rf'\b{re.escape(clean_lf)}\b', ' ', n)
    n = re.sub(r'["\'„“”«»`\^\-–—]', ' ', n)
    n = re.sub(r'[^\w\s]', ' ', n)
    return re.sub(r'\s+', ' ', n).strip()

def clean_phone(p):
    if not p:
        return ""
    digits = re.sub(r'\D', '', str(p))
    if len(digits) >= 8:
        return digits[-8:]
    return ""

def clean_domain(url):
    if not url:
        return ""
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
        p = urllib.parse.urlparse(url)
        d = p.netloc.lower().replace('www.', '').split(':')[0]
        if any(x in d for x in ['zlatestranky', 'facebook', 'instagram', 'google']):
            return ""
        return d
    except Exception:
        return ""

def clean_email(em):
    if not em:
        return ""
    e = em.replace('%20', '').strip().lower().rstrip('.,;:/\\')
    if '@' in e and '.' in e:
        return e
    return ""

def main():
    print("=" * 80)
    print("QUY TRINH LOC TRUNG DOANH NGHIEP: SK_MANU_ZLAT_0RAW vs SK_AUTO_ZLAT_2COL")
    print(f"File kiem tra: {MANU_CSV}")
    print(f"File doi chieu: {AUTO_CSV}")
    print("=" * 80)

    if not os.path.exists(MANU_CSV):
        print(f"[-] Khong tim thay file: {MANU_CSV}")
        return
    if not os.path.exists(AUTO_CSV):
        print(f"[-] Khong tim thay file: {AUTO_CSV}")
        return

    # 1. Sao luu file MANU truoc khi thao tac
    if not os.path.exists(BACKUP_CSV):
        shutil.copy2(MANU_CSV, BACKUP_CSV)
        print(f"[*] Da sao luu {MANU_CSV} sang {BACKUP_CSV}")

    # 2. Nap va danh chi muc danh sach AUTO
    with open(AUTO_CSV, 'r', encoding='utf-8-sig', errors='ignore') as f:
        auto_rows = list(csv.DictReader(f))

    auto_names = {}
    auto_emails = {}
    auto_domains = {}
    auto_phones = {}

    for r in auto_rows:
        cname = r.get('Công ty', '').strip()
        norm_n = normalize_name(cname)
        if norm_n and len(norm_n) >= 3:
            auto_names[norm_n] = cname

        em = clean_email(r.get('Email', ''))
        if em:
            u, d = em.split('@', 1)
            if d not in COMMON_EMAIL_DOMAINS:
                auto_emails[em] = cname

        dom = clean_domain(r.get('Liên Hệ', ''))
        if dom:
            auto_domains[dom] = cname

        ph = clean_phone(r.get('SĐT', ''))
        if ph:
            auto_phones[ph] = cname

    print(f"[*] Da nap danh muc AUTO ({len(auto_rows)} dong):")
    print(f"    - Ten cong ty chuan hoa: {len(auto_names)}")
    print(f"    - Email doanh nghiep:    {len(auto_emails)}")
    print(f"    - Domain website:        {len(auto_domains)}")
    print(f"    - So dien thoai:         {len(auto_phones)}")

    # 3. Doc file MANU va doi soat
    with open(MANU_CSV, 'r', encoding='utf-8-sig', errors='ignore') as f:
        reader = csv.DictReader(f)
        manu_fields = list(reader.fieldnames)
        manu_rows = list(reader)

    print(f"\n[*] Tong so doanh nghiep trong MANU ban dau: {len(manu_rows)}")

    retained_rows = []
    removed_records = []
    matched_stats = {'name': 0, 'email': 0, 'domain': 0, 'phone': 0}

    for idx, r in enumerate(manu_rows):
        cname = r.get('Công ty', '').strip()
        norm_n = normalize_name(cname)
        em = clean_email(r.get('Email', ''))
        dom = clean_domain(r.get('Liên Hệ', ''))
        ph = clean_phone(r.get('SĐT', ''))

        matched = False
        reason = ""
        matched_auto_company = ""

        # Check 1: Trùng tên pháp lý chuẩn hóa
        if norm_n and norm_n in auto_names:
            matched = True
            matched_auto_company = auto_names[norm_n]
            reason = f"Trùng tên công ty: '{cname}' <==> '{matched_auto_company}'"
            matched_stats['name'] += 1

        # Check 2: Trùng Email doanh nghiệp riêng biệt
        elif em and em in auto_emails:
            matched = True
            matched_auto_company = auto_emails[em]
            reason = f"Trùng Email B2B: {em} (AUTO: '{matched_auto_company}')"
            matched_stats['email'] += 1

        # Check 3: Trùng Domain website riêng biệt
        elif dom and dom in auto_domains:
            matched = True
            matched_auto_company = auto_domains[dom]
            reason = f"Trùng Domain: {dom} (AUTO: '{matched_auto_company}')"
            matched_stats['domain'] += 1

        # Check 4: Trùng SĐT kèm ít nhất 1 từ khóa thương hiệu >= 4 ký tự
        elif ph and ph in auto_phones:
            matched_auto_company = auto_phones[ph]
            auto_norm = normalize_name(matched_auto_company)
            m_tokens = {t for t in norm_n.split() if len(t) >= 4}
            a_tokens = {t for t in auto_norm.split() if len(t) >= 4}
            if m_tokens & a_tokens:
                matched = True
                reason = f"Trùng SĐT ({ph}) + Tên tương đồng '{m_tokens & a_tokens}' (AUTO: '{matched_auto_company}')"
                matched_stats['phone'] += 1

        if matched:
            removed_records.append({
                'Original_No': r.get('No.', ''),
                'MANU_Company': cname,
                'AUTO_Company': matched_auto_company,
                'Reason': reason,
                'Phone': r.get('SĐT', ''),
                'Email': r.get('Email', ''),
                'Website': r.get('Liên Hệ', '')
            })
        else:
            retained_rows.append(r)

    # 4. Đánh số lại No. cho các dòng được giữ lại
    for idx, r in enumerate(retained_rows, 1):
        r['No.'] = str(idx)
        # Đảm bảo SĐT có dấu nháy đơn
        p = r.get('SĐT', '').strip()
        if p and not p.startswith("'"):
            r['SĐT'] = f"'{p}"

    # 5. Ghi đè file MANU đã loại bỏ trùng
    temp_manu = MANU_CSV + ".tmp"
    with open(temp_manu, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=manu_fields)
        writer.writeheader()
        writer.writerows(retained_rows)

    if os.path.exists(MANU_CSV):
        try:
            os.remove(MANU_CSV)
        except Exception:
            pass
    os.rename(temp_manu, MANU_CSV)

    # 6. Ghi file đối soát các công ty đã bị loại bỏ
    if removed_records:
        removed_fields = ['Original_No', 'MANU_Company', 'AUTO_Company', 'Reason', 'Phone', 'Email', 'Website']
        with open(REMOVED_CSV, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=removed_fields)
            writer.writeheader()
            writer.writerows(removed_records)
        print(f"[+] Da xuat bao cao chi tiet {len(removed_records)} cong ty bi loai: {REMOVED_CSV}")

    print("\n" + "=" * 80)
    print("HOAN TAT LOAI BO CONG TY TRUNG LAP!")
    print(f"Tổng số ban đầu trong MANU:           {len(manu_rows)} doanh nghiệp")
    print(f"Số công ty ĐÃ BỊ LOẠI BỎ (trùng AUTO): {len(removed_records)} doanh nghiệp")
    print(f"  - Trùng theo Tên pháp lý:           {matched_stats['name']}")
    print(f"  - Trùng theo Email doanh nghiệp:    {matched_stats['email']}")
    print(f"  - Trùng theo Domain website:        {matched_stats['domain']}")
    print(f"  - Trùng theo SĐT & Tên tương đồng:  {matched_stats['phone']}")
    print(f"Số công ty MANU CÒN LẠI (Sạch 100%):  {len(retained_rows)} doanh nghiệp")
    print(f"File cap nhat: {MANU_CSV}")
    print("=" * 80)

if __name__ == "__main__":
    main()
