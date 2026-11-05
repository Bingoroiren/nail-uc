# -*- coding: utf-8 -*-
"""
DEDUPLICATION TOOL - BELGIUM METAL ENTERPRISES (KBO)
===================================================
Quy chuẩn áp dụng:
- data-standards (.agents/skills/data-standards/SKILL.md)
- Rule 1: CSV UTF-8 with BOM (utf-8-sig)
- Rule 2: Phone with single quote '+32...
- Rule 10: Quy chuẩn 17 ký tự (BE_METL_KBO0_0RAW.csv)
- Rule 11: So khớp tên thông minh, chuẩn hóa legal forms & NFKD
- Rule 12: Permanent Company Blacklist (Scandi Standard, Biliarta, Daigre)

Mục tiêu xử lý:
1. Gom toàn bộ các cơ sở chi nhánh (VE) và pháp nhân (ENT RP, ENT NP) trùng mã KBO về 1 doanh nghiệp duy nhất.
2. Thông minh hóa dữ liệu khi gộp:
   - Ưu tiên tên thương mại / tên doanh nghiệp thay vì họ tên cá nhân đảo ngược (vd 'COSTERMANS BVBA' thay vì 'Gasper, Claude').
   - Lấy địa chỉ thực tế hoạt động (VE thường có địa chỉ phân xưởng đầy đủ, tránh dòng trống ở ENT NP).
   - Loại trừ địa chỉ bị gạch bỏ (Ambsthalve doorgehaald adres) nếu có địa chỉ hoạt động khác.
   - Giữ lại đầy đủ SĐT, Email, Website nếu có.
   - Trạng thái ưu tiên 'Actief'.
3. Đồng bộ kết quả ra cả 3 thư mục:
   - Thư mục gốc: BE_METL_KBO0_0RAW.csv
   - csdl_mlt: csdl_mlt/BE_METL_KBO0_0RAW.csv
   - archive: archive/be_belgium/BE_METL_KBO0_0RAW.csv
   Đồng thời sao lưu bản gốc trước khi lọc vào archive/be_belgium/BE_METL_KBO0_0RAW_before_dedup.csv.
"""

import os
import sys
import re
import csv
import shutil
import unicodedata
from pathlib import Path
from collections import defaultdict

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

INPUT_CSV = ROOT_DIR / "BE_METL_KBO0_0RAW.csv"
BACKUP_CSV = ROOT_DIR / "archive" / "be_belgium" / "BE_METL_KBO0_0RAW_before_dedup.csv"
CSDL_CSV = ROOT_DIR / "csdl_mlt" / "BE_METL_KBO0_0RAW.csv"
ARCHIVE_CSV = ROOT_DIR / "archive" / "be_belgium" / "BE_METL_KBO0_0RAW.csv"

# Rule 12: Permanent Company Blacklist
PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

def clean_kbo_number(kbo_raw):
    if not kbo_raw:
        return ""
    digits = re.sub(r'[^0-9]', '', str(kbo_raw))
    return digits if len(digits) == 10 else ""

def format_kbo_display(kbo_raw):
    digits = re.sub(r'[^0-9]', '', str(kbo_raw or ''))
    if len(digits) == 10:
        return f"{digits[:4]}.{digits[4:7]}.{digits[7:]}"
    return str(kbo_raw or '').strip()

def format_phone(phone):
    if not phone:
        return ""
    p = str(phone).strip()
    return f"'{p}" if not p.startswith("'") else p

def is_person_name_format(name):
    """Kiểm tra nếu tên có dạng 'Họ, Tên' (ví dụ Gasper, Claude hoặc Boghean, Emilian)"""
    if not name:
        return False
    parts = [p.strip() for p in name.split(',')]
    if len(parts) == 2:
        p1_words = parts[0].split()
        p2_words = parts[1].split()
        if len(p1_words) <= 3 and len(p2_words) <= 2:
            return True
    return False

def reformat_person_name(name):
    """Chuyển 'Boghean, Emilian' thành 'Emilian Boghean'"""
    if is_person_name_format(name):
        parts = [p.strip() for p in name.split(',')]
        return f"{parts[1]} {parts[0]}"
    return name

def score_company_name(name, record_type):
    """
    Chấm điểm chất lượng tên công ty để phục vụ tìm kiếm Google Maps:
    - Tên thương mại/pháp nhân (COSTERMANS BVBA, Art Métal Inox): điểm cao
    - Tên cá nhân đảo ngược (Gasper, Claude): điểm thấp hơn
    """
    if not name:
        return 0
    s = str(name).strip()
    score = 50
    t_upper = str(record_type or '').upper()

    # Có chứa từ khóa chỉ công ty / xưởng / ngành kim loại
    metal_keywords = [
        'construct', 'metal', 'inox', 'acier', 'staal', 'atelier', 'works', 'tech',
        'engineering', 'bvba', 'nv', 'bv', 'sprl', 'sa', 'srl', 'vof', 'solutions'
    ]
    s_lower = s.lower()
    if any(k in s_lower for k in metal_keywords):
        score += 40

    if is_person_name_format(s):
        score -= 30
    elif ',' not in s and len(s.split()) >= 2:
        score += 20

    if 'ENT RP' in t_upper:
        score += 15
    elif 'VE' in t_upper:
        score += 10

    return score

def score_address(addr):
    """Chấm điểm chất lượng địa chỉ"""
    if not addr:
        return 0
    a = str(addr).strip()
    if len(a) < 5:
        return 0
    score = 50 + min(len(a), 40)
    a_lower = a.lower()
    # Bị gạch bỏ bởi cơ quan chức năng
    if 'ambsthalve doorgehaald' in a_lower or 'geschrapt' in a_lower:
        score -= 40
    # Có số nhà và tên đường
    if re.search(r'\d+', a):
        score += 15
    return score

def merge_company_records(records):
    """
    Gộp các bản ghi có cùng mã KBO hoặc cùng tên doanh nghiệp:
    Lấy thông tin tối ưu nhất cho từng trường.
    """
    if len(records) == 1:
        r = dict(records[0])
        r['Company_Name'] = reformat_person_name(r.get('Company_Name', ''))
        r['Phone'] = format_phone(r.get('Phone', ''))
        r['KBO_Number'] = format_kbo_display(r.get('KBO_Number', ''))
        return r

    # 1. Chọn tên công ty tối ưu nhất
    best_name = ""
    best_name_score = -999
    for r in records:
        name = r.get('Company_Name', '').strip()
        rtype = r.get('Type', '')
        sc = score_company_name(name, rtype)
        if sc > best_name_score:
            best_name_score = sc
            best_name = name

    best_name = reformat_person_name(best_name)

    # 2. Chọn địa chỉ tối ưu nhất
    best_addr = ""
    best_addr_score = -999
    best_postcode = ""
    for r in records:
        addr = r.get('Address', '').strip()
        sc = score_address(addr)
        if sc > best_addr_score:
            best_addr_score = sc
            best_addr = addr
            best_postcode = r.get('Postcode', '').strip()

    # Nếu không tìm thấy postcode đi kèm địa chỉ, lấy postcode đầu tiên có
    if not best_postcode:
        for r in records:
            if r.get('Postcode', '').strip():
                best_postcode = r.get('Postcode', '').strip()
                break

    # 3. KBO number & VE number
    kbo = ""
    for r in records:
        k = clean_kbo_number(r.get('KBO_Number', ''))
        if k:
            kbo = format_kbo_display(k)
            break
    if not kbo and records:
        kbo = format_kbo_display(records[0].get('KBO_Number', ''))

    ve_num = ""
    # Giữ VE_Number của bản ghi có địa chỉ hoặc bản ghi đầu tiên có VE
    for r in records:
        v = r.get('VE_Number', '').strip()
        if v and v != '-' and v != 'None':
            ve_num = v
            break

    # 4. Status: Ưu tiên 'Actief'
    status = "Actief"
    statuses = [r.get('Status', '').strip() for r in records if r.get('Status', '').strip()]
    if statuses and not any('actief' in s.lower() for s in statuses):
        status = statuses[0]

    # 5. Type: ENT RP > VE > ENT NP
    rec_type = "ENT RP"
    types = [r.get('Type', '').strip().upper() for r in records if r.get('Type', '').strip()]
    if any('ENT RP' in t for t in types):
        rec_type = "ENT RP"
    elif any('VE' in t for t in types):
        rec_type = "VE"
    elif any('ENT NP' in t for t in types):
        rec_type = "ENT NP"
    elif types:
        rec_type = types[0]

    # 6. SĐT, Email, Website: Giữ bất kỳ giá trị nào có được
    phone = ""
    for r in records:
        if r.get('Phone', '').strip():
            phone = format_phone(r.get('Phone', '').strip())
            break

    email = ""
    for r in records:
        if r.get('Email', '').strip():
            email = r.get('Email', '').strip().lower()
            break

    website = ""
    for r in records:
        if r.get('Website', '').strip():
            website = r.get('Website', '').strip()
            break

    # 7. Activity & NACE_Code: Lấy mô tả chi tiết nhất
    activity = ""
    nace = ""
    for r in records:
        act = r.get('Activity', '').strip()
        if len(act) > len(activity):
            activity = act
            nace = r.get('NACE_Code', '').strip()
    if not nace:
        for r in records:
            if r.get('NACE_Code', '').strip():
                nace = r.get('NACE_Code', '').strip()
                break

    source = "KBO Public Search (Deduplicated)"

    return {
        'Company_Name': best_name,
        'KBO_Number': kbo,
        'VE_Number': ve_num,
        'Type': rec_type,
        'Status': status,
        'Address': best_addr,
        'Postcode': best_postcode,
        'Country': 'Belgium',
        'Activity': activity,
        'NACE_Code': nace,
        'Phone': phone,
        'Email': email,
        'Website': website,
        'Source': source
    }

def run_deduplication():
    print("=" * 70)
    print("   LỌC TRÙNG DỮ LIỆU KIM LOẠI BỈ (BE_METL_KBO0_0RAW.csv)")
    print("   - Loại bỏ trùng lặp mã KBO & gom các cơ sở chi nhánh (VE)")
    print("   - Tối ưu tên công ty và địa chỉ thực tế hoạt động")
    print("   - Áp dụng Rule 1, 2, 10, 11, 12 chuẩn Workspace")
    print("=" * 70)
    print()

    if not INPUT_CSV.exists():
        print(f"[ERROR] Không tìm thấy file nguồn: {INPUT_CSV}")
        return

    # 1. Đọc dữ liệu
    print(f"[*] Đang đọc dữ liệu từ: {INPUT_CSV.name}...")
    with open(INPUT_CSV, mode='r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or [
            'Company_Name', 'KBO_Number', 'VE_Number', 'Type', 'Status',
            'Address', 'Postcode', 'Country', 'Activity', 'NACE_Code',
            'Phone', 'Email', 'Website', 'Source'
        ]
        raw_rows = list(reader)

    initial_count = len(raw_rows)
    print(f"    Tổng số dòng thô ban đầu: {initial_count:,} dòng")

    # 2. Tạo bản sao lưu trước khi xử lý
    BACKUP_CSV.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(INPUT_CSV, BACKUP_CSV)
    print(f"[+] Đã tạo bản sao lưu an toàn tại: {BACKUP_CSV}")

    # 3. Phân nhóm theo mã KBO 10 số
    groups = defaultdict(list)
    no_kbo_rows = []
    blacklist_count = 0

    for r in raw_rows:
        name = r.get('Company_Name', '').strip()
        if not name or len(name.strip(' .,-_/\\')) < 2:
            continue

        if is_blacklisted_company(name):
            blacklist_count += 1
            continue

        kbo_clean = clean_kbo_number(r.get('KBO_Number', ''))
        if kbo_clean:
            groups[kbo_clean].append(r)
        else:
            no_kbo_rows.append(r)

    print(f"    Số doanh nghiệp KBO độc nhất: {len(groups):,}")
    if no_kbo_rows:
        print(f"    Số dòng không có mã KBO: {len(no_kbo_rows):,}")
    if blacklist_count > 0:
        print(f"    Số công ty trong danh sách đen bị loại bỏ (Rule 12): {blacklist_count}")

    # 4. Gộp thông tin tối ưu cho từng doanh nghiệp
    deduped_records = []
    multi_count = 0

    for kbo_clean, recs in groups.items():
        if len(recs) > 1:
            multi_count += 1
        merged = merge_company_records(recs)
        deduped_records.append(merged)

    # Thêm các bản ghi không có KBO (nếu có)
    for r in no_kbo_rows:
        deduped_records.append(merge_company_records([r]))

    final_count = len(deduped_records)
    removed_count = initial_count - final_count

    print(f"\n[*] KẾT QUẢ LỌC TRÙNG:")
    print(f"    - Doanh nghiệp có nhiều chi nhánh/bản ghi đã được gộp: {multi_count:,}")
    print(f"    - Tổng số dòng trùng lặp đã loại bỏ: {removed_count:,} dòng")
    print(f"    - Tổng số doanh nghiệp sạch duy nhất còn lại: {final_count:,} công ty")

    # 5. Lưu kết quả ra file chuẩn UTF-8 with BOM
    output_targets = [INPUT_CSV, CSDL_CSV, ARCHIVE_CSV]
    for target in output_targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(deduped_records)
        print(f"[+] Đã lưu file chuẩn hóa: {target}")

    print("\n" + "=" * 70)
    print(f"[SUCCESS] Lọc trùng hoàn tất! {final_count:,} doanh nghiệp kim loại Bỉ sẵn sàng làm giàu Maps.")
    print("=" * 70)

if __name__ == "__main__":
    run_deduplication()

