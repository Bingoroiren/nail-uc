# -*- coding: utf-8 -*-
"""
BỘ LÀM SẠCH VÀ LỌC BỎ MAIL RÁC / PLACEHOLDER / DUMMY CHO DOANH NGHIỆP PHÁP
========================================================================
Áp dụng theo GEMINI.md Rule 3:
- Lọc bỏ 100% mail rác, template, placeholder, file ảnh retina @2x, package version npm
- Loại bỏ mail GDPR/DPO, web developer ngoại lai
- Đẩy 100% dòng có Email hợp lệ lên đầu danh sách (with_email + without_email)
- Giữ nguyên số điện thoại có dấu nháy đơn '
- Xuất file CSV UTF-8 with BOM (utf-8-sig)
"""

import os
import sys
import re
import csv
import json
import urllib.parse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

FILE_1ENR = ROOT_DIR / "FR_AGCY_PJAU_1ENR.csv"
FILE_2COL = ROOT_DIR / "FR_AGCY_PJAU_2COL.csv"
FILE_READY = ROOT_DIR / "FR_AGCY_PJAU_ONLY_EMAILS_READY.csv"
CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_enrich_maps_fr_agcy.json"

IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.bmp', '.pdf', '.js', '.css')

DUMMY_DOMAINS = {
    'may4bewith.you', 'email.com', 'company.com', 'vite.com', 'domain.com',
    'example.com', 'yoursite.com', 'sentry.io', 'wixpress.com', 'wordpress.org', 'wix.com'
}

DUMMY_USERS = {
    'mon.email', 'john', 'johndoe', 'someone', 'yourname', 'youremail',
    'luke.skywalker', 'user', 'name', 'test', 'username', 'dummy'
}

GDPR_USERS = {
    'delegueprotectiondcp', 'donnees', 'rgpd', 'dpo', 'u003edpo', 'privacy',
    'dataprotection', 'compliance', 'abuse', 'postmaster'
}

EXTERNAL_DEV_EMAILS = {
    'tech@maetva.com', 'support@pharmao.fr'
}

def clean_and_validate_email(em):
    if not em:
        return "", "EMPTY"
        
    raw = urllib.parse.unquote(str(em)).strip()
    raw = raw.replace('\u00a0', '').replace('\xa0', '').replace('&nbsp;', '')
    raw = raw.replace('%20', '').replace('\u200b', '').replace('\ufeff', '')
    raw = re.sub(r'^(?:20)+', '', raw)
    raw = re.sub(r'^(?:mailto:|u003e)', '', raw, flags=re.I).strip()
    raw = raw.strip('<>"\';:,()[]{} ')
    
    if '@' not in raw:
        return "", "NO_AT"
        
    em_low = raw.lower()
    
    # 1. Loại bỏ file ảnh / file tĩnh
    if any(em_low.endswith(ext) for ext in IMAGE_EXTENSIONS):
        return "", f"IMAGE_FILE ({em_low})"
        
    parts = em_low.split('@')
    if len(parts) != 2:
        return "", "INVALID_PARTS"
        
    user, domain = parts[0], parts[1]
    
    # 2. Loại bỏ package version npm (VD: contacts-web@5.0.65, react@18.3.1, lodash@4.18.1)
    if re.match(r'^\d+(\.\d+)+$', domain):
        return "", f"VERSION_TAG ({domain})"
        
    # 3. Kiểm tra TLD hợp lệ (ít nhất 2 chữ cái, không được là số)
    d_parts = domain.split('.')
    if len(d_parts) < 2:
        return "", f"NO_TLD ({domain})"
    tld = d_parts[-1]
    if not re.match(r'^[a-z]{2,12}$', tld) or re.match(r'^\d+$', tld):
        return "", f"INVALID_TLD ({tld})"
        
    # 4. Loại bỏ domain template / dummy
    if domain in DUMMY_DOMAINS or any(d in domain for d in ['example.com', 'yourdomain', 'domain.com']):
        return "", f"DUMMY_DOMAIN ({domain})"
        
    # 5. Loại bỏ user template / dummy
    if user in DUMMY_USERS:
        return "", f"DUMMY_USER ({user})"
        
    # 6. Loại bỏ email GDPR / DPO
    if any(g == user or user.startswith(g) or user.endswith(g) for g in GDPR_USERS):
        return "", f"GDPR_LEGAL ({user})"
        
    # 7. Loại bỏ mail web developer ngoại lai
    if em_low in EXTERNAL_DEV_EMAILS:
        return "", f"EXTERNAL_DEV ({em_low})"
        
    # 8. Ký tự lạ
    if any(c in em_low for c in ['<', '>', '"', "'", '\\', ';', ':', ' ']):
        return "", "WEIRD_CHARS"
        
    # 9. Regex email chuẩn
    if not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', em_low):
        return "", "REGEX_MISMATCH"
        
    return em_low, "VALID"

def format_french_phone(phone_raw):
    if not phone_raw:
        return ""
    clean = re.sub(r"[^\d+]", "", str(phone_raw).strip())
    if clean.startswith("0") and len(clean) == 10:
        clean = "+33" + clean[1:]
    elif clean.startswith("0033"):
        clean = "+33" + clean[4:]
    elif clean.startswith("33") and len(clean) == 11:
        clean = "+" + clean
    return f"'{clean}" if clean and not clean.startswith("'") else clean

def run_cleaning():
    print("=" * 80)
    print("🧹 TIẾN HÀNH LÀM SẠCH VÀ LỌC MAIL RÁC - BỘ DỮ LIỆU PHÁP (FR_AGCY_PJAU)")
    print("=" * 80)
    
    if not FILE_1ENR.exists():
        print(f"[ERROR] Không tìm thấy file {FILE_1ENR}")
        return
        
    with open(FILE_1ENR, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        records = list(reader)
        
    print(f"[*] Tổng số dòng dữ liệu: {len(records)}")
    
    cleaned_records = []
    removed_count = 0
    valid_count = 0
    removed_details = []
    
    for r in records:
        name = r.get("Name", "").strip()
        orig_email = r.get("Email", "").strip()
        phone = format_french_phone(r.get("Phone", "").strip())
        
        valid_email, reason = clean_and_validate_email(orig_email)
        
        if orig_email and not valid_email:
            removed_count += 1
            removed_details.append((name, orig_email, reason, r.get("Website", "")))
        elif valid_email:
            valid_count += 1
            
        r["Email"] = valid_email
        r["Phone"] = phone
        cleaned_records.append(r)
        
    print(f"\n[+] Kết quả thẩm định Email:")
    print(f"    - Email ban đầu   : {removed_count + valid_count}")
    print(f"    - Email hợp lệ    : {valid_count}")
    print(f"    - Mail rác đã xoá : {removed_count}")
    
    print("\n[!] Chi tiết các mail rác / placeholder đã được loại bỏ:")
    print("-" * 80)
    for name, em, reason, web in removed_details:
        print(f"  ❌ [{reason:<22}] {name[:28]:<28} | {em:<35} | {web[:35]}")
    print("-" * 80)
    
    # 1. Cập nhật cache JSON
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            updated_cache_count = 0
            for k, v in cache.items():
                c_em = v.get("Email", "").strip()
                v_em, _ = clean_and_validate_email(c_em)
                if c_em != v_em:
                    v["Email"] = v_em
                    updated_cache_count += 1
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            print(f"\n[*] Đã đồng bộ làm sạch Cache JSON: {updated_cache_count} mục được dọn sạch.")
        except Exception as e:
            print(f"[!] Lỗi cập nhật cache: {e}")
            
    # 2. Xuất file FR_AGCY_PJAU_1ENR.csv
    fieldnames_1enr = [
        "Name", "Activity", "Address", "Postal_Code", "City", "Country",
        "Phone", "Website", "Email", "Rating", "Review_Count", "Google_Maps_URL", "PagesJaunes_URL", "Category_Source"
    ]
    with open(FILE_1ENR, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames_1enr)
        w.writeheader()
        w.writerows(cleaned_records)
    print(f"[✓] Đã ghi đè cập nhật {FILE_1ENR.name} ({len(cleaned_records)} dòng, {valid_count} dòng có email)")
    
    # 3. Xuất file FR_AGCY_PJAU_2COL.csv (20 cột chuẩn Cold Mail, 100% email lên đầu)
    fieldnames_20col = [
        "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ", "Email",
        "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển", "Check gửi",
        "Last Subject", "Last Body HTML", "Trạng thái Reply", "Lần Follow-up",
        "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
    ]
    
    with_email = [r for r in cleaned_records if r.get("Email")]
    without_email = [r for r in cleaned_records if not r.get("Email")]
    sorted_all = with_email + without_email
    
    col20_rows = []
    for i, r in enumerate(sorted_all, 1):
        has_em = bool(r.get("Email"))
        row_20 = {
            "No.": str(i),
            "Công ty": r.get("Name", ""),
            "Chức danh": "Directeur / Responsable Recrutement",
            "Người liên hệ": "",
            "SĐT": r.get("Phone", ""),
            "Liên Hệ": r.get("Website", ""),
            "Email": r.get("Email", ""),
            "Liên Hệ mail": f"mailto:{r.get('Email', '')}" if has_em else "",
            "Địa chỉ": r.get("Address", ""),
            "Lương": "",
            "Ngày đăng": "",
            "Hạn tuyển": "",
            "Check gửi": "Chưa gửi" if has_em else "",
            "Last Subject": "",
            "Last Body HTML": "",
            "Trạng thái Reply": "",
            "Lần Follow-up": "",
            "Ngày Follow-up gần nhất": "",
            "Mailbox đã dùng": "",
            "Category": r.get("Activity", "") or r.get("Category_Source", "Recrutement & Interim")
        }
        col20_rows.append(row_20)
        
    with open(FILE_2COL, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames_20col)
        w.writeheader()
        w.writerows(col20_rows)
    print(f"[✓] Đã ghi đè cập nhật {FILE_2COL.name} (20 cột, 100% có email nằm ở hàng 1..{len(with_email)})")
    
    # 4. Xuất file FR_AGCY_PJAU_ONLY_EMAILS_READY.csv (Chỉ các công ty có email hợp lệ)
    ready_rows = [r for r in col20_rows if r.get("Email")]
    with open(FILE_READY, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames_20col)
        w.writeheader()
        w.writerows(ready_rows)
    print(f"[✓] Đã ghi đè cập nhật {FILE_READY.name} ({len(ready_rows)} công ty sẵn sàng gửi mail)")
    
    print("\n" + "=" * 80)
    print("🎉 HOÀN THÀNH DỌN SẠCH VÀ CHUẨN HOÁ DỮ LIỆU COLD MAIL PHÁP!")
    print(f"    - Tổng công ty    : {len(cleaned_records)}")
    print(f"    - Email sạch B2B  : {len(ready_rows)} ({len(ready_rows)*100/len(cleaned_records):.1f}%)")
    print(f"    - File 1ENR       : {FILE_1ENR.name}")
    print(f"    - File 2COL       : {FILE_2COL.name}")
    print(f"    - File ONLY_EMAILS: {FILE_READY.name}")
    print("=" * 80)

if __name__ == "__main__":
    run_cleaning()

