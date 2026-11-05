# -*- coding: utf-8 -*-
"""
DEDUPLICATE BELGIUM KBO ENTERPRISES (Rule 11 & Rule 3)
======================================================
Module chuyên biệt lọc trùng tên công ty và mã số doanh nghiệp KBO Bỉ:
1. Gom nhóm Disjoint-Set (Union-Find) theo KBO Number (10 số) và Clean Company Name.
2. Khử toàn bộ legal forms Bỉ (BV, NV, BVBA, SRL, SPRL, SA, VOF, SNC, CVBA...).
3. Hợp nhất thông tin liên hệ đa tầng:
   - Email: Giữ email có điểm B2B cao nhất (score_email_b2b).
   - Phone: Giữ SĐT chuẩn có dấu nháy đơn '+' (Rule 2).
   - Website: Giữ website hợp lệ.
   - Address: Lấy địa chỉ cơ sở hoạt động thực tế nếu trụ sở cá nhân ENT NP bị ẩn.
   - NACE / Activity: Gom nhóm toàn bộ mã ngành hoạt động.
4. Loại trừ danh sách đen vĩnh viễn (Rule 12: Scandi Standard, Biliarta, Daigre).
5. Sắp xếp 100% doanh nghiệp có Email lên đầu tệp CSV (Rule 3).
6. Tự động sao lưu bản thô và đồng bộ dữ liệu vào csdl_mlt/ và archive/.
"""

import os
import sys
import re
import csv
import shutil
import argparse
import urllib.parse
import unicodedata
from collections import defaultdict
from pathlib import Path

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

# Rule 12: Danh sách đen vĩnh viễn
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

def clean_company_name(name):
    """
    Chuẩn hóa tên doanh nghiệp (Rule 11):
    - NFKD Unicode
    - Loại bỏ legal forms của Bỉ (BV, NV, BVBA, SRL, SPRL, SA, VOF, SNC, CVBA...)
    - Xóa chú thích trong ngoặc đơn/vuông
    - Xóa ký tự đặc biệt, chuẩn hóa khoảng trắng
    """
    if not name:
        return ''
    n = unicodedata.normalize('NFKD', str(name))
    n = ''.join(c for c in n if not unicodedata.combining(c)).lower()
    
    legal_forms = [
        'besloten vennootschap met beperkte aansprakelijkheid',
        'societe a responsabilite limitee',
        'naamloze vennootschap',
        'societe anonyme',
        'gewone commanditaire vennootschap',
        'societe en commandite simple',
        'vennootschap onder firma',
        'societe en nom collectif',
        'cooperatieve vennootschap',
        'societe cooperative',
        'b.v.b.a.', 'bvba', 's.p.r.l.', 'sprl',
        'b.v.', 'bv', 's.r.l.', 'srl',
        'n.v.', 'nv', 's.a.', 'sa',
        'v.o.f.', 'vof', 's.n.c.', 'snc',
        'c.v.b.a.', 'cvba', 'c.v.', 'cv',
        'comm.v', 'comm.va', 'gcv', 'scs', 'sca',
        'asbl', 'vzw'
    ]
    for lf in sorted(legal_forms, key=len, reverse=True):
        n = re.sub(r'\b' + re.escape(lf) + r'\b', '', n, flags=re.I)
        
    n = re.sub(r'[\(\[\{].*?[\)\]\}]', '', n)
    n = re.sub(r'[^a-z0-9]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n

def clean_phone(phone_str):
    if not phone_str:
        return ""
    p = str(phone_str).strip()
    if p.lower() in ['nan', '-', 'none', '']:
        return ""
    p = p.replace('\u00a0', ' ').replace('\xa0', ' ').replace('&nbsp;', ' ')
    p = re.sub(r'\s+', ' ', p).strip()
    # Nháy đơn đầu tiên (Rule 2)
    if not p.startswith("'"):
        p = f"'{p}"
    return p

def clean_email(email):
    if not email:
        return ""
    e = urllib.parse.unquote(str(email).strip().lower())
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\ufeff', '\u202f', '\u3000']:
        e = e.replace(bad, '')
    e = re.sub(r'^mailto:\s*', '', e, flags=re.I)
    e = re.sub(r'\s+', '', e)
    e = e.strip(" .,;:\"'<>[](){}\\/")
    # Loại email rác / demo / sàn danh bạ (Rule 3)
    if any(e.startswith(bad) for bad in ['sentry', 'wix', 'wordpress', 'no-reply', 'donotreply', 'privacy', 'gdpr', 'example', 'domain']):
        return ""
    if any(e.endswith(bad) for bad in ['example.com', 'domain.com', 'email.com', 'wixpress.com']):
        return ""
    return e

def score_email_b2b(email, domain=""):
    """Bộ chấm điểm email B2B (Rule 3)"""
    if not email:
        return 0
    em = email.lower()
    score = 0
    if domain and domain in em:
        score += 50
    # Ưu tiên tuyển dụng / nhân sự
    if any(em.startswith(k) for k in ['recruitment@', 'jobs@', 'career@', 'hr@', 'praca@', 'personeel@', 'aanwerving@']):
        score += 50
    # Ưu tiên lãnh đạo / điều hành
    elif any(em.startswith(k) for k in ['ceo@', 'director@', 'manager@', 'direction@', 'bestuur@', 'zaakvoerder@', 'gerant@']):
        score += 45
    # Ưu tiên liên hệ chính thức
    elif any(em.startswith(k) for k in ['info@', 'contact@', 'kontakt@', 'office@', 'secretariat@', 'balie@', 'accueil@']):
        score += 40
    elif any(em.endswith(k) for k in ['@gmail.com', '@hotmail.com', '@yahoo.com', '@telenet.be', '@skynet.be', '@proximus.be']):
        score += 10
    else:
        score += 25
    return score

def deduplicate_dataset(rows):
    """
    LỌC TRÙNG & TỔNG HỢP DỮ LIỆU CÔNG TY THÔNG MINH (KBO & Clean Name):
    1. Gom nhóm Disjoint-Set theo KBO Number (10 số) và Clean Name.
    2. Chọn bản ghi chuẩn nhất (ENT RP > ENT NP > VE).
    3. Hợp nhất thông tin liên hệ (Email, Phone, Website, Địa chỉ).
    4. Sắp xếp các công ty có Email lên đầu danh sách.
    """
    parent = list(range(len(rows)))
    def find(i):
        if parent[i] == i:
            return i
        parent[i] = find(parent[i])
        return parent[i]

    def union(i, j):
        root_i = find(i)
        root_j = find(j)
        if root_i != root_j:
            parent[root_i] = root_j

    kbo_map = {}
    name_map = {}

    valid_indices = []
    for idx, r in enumerate(rows):
        cname = r.get('Company_Name', '').strip()
        if not cname or is_blacklisted_company(cname):
            continue
        valid_indices.append(idx)
        clean_kbo = re.sub(r'[^0-9]', '', r.get('KBO_Number', ''))
        norm_n = clean_company_name(cname)

        if len(clean_kbo) == 10:
            if clean_kbo in kbo_map:
                union(idx, kbo_map[clean_kbo])
            else:
                kbo_map[clean_kbo] = idx

        if len(norm_n) >= 4:
            if norm_n in name_map:
                union(idx, name_map[norm_n])
            else:
                name_map[norm_n] = idx

    groups = defaultdict(list)
    for idx in valid_indices:
        root = find(idx)
        groups[root].append(rows[idx])

    deduped_rows = []

    for root, group in groups.items():
        best_row = None
        best_score = -1

        for r in group:
            score = 0
            t = str(r.get('Type', '')).upper()
            if 'ENT RP' in t:
                score += 100
            elif 'ENT NP' in t:
                score += 80
            elif 'VE' in t:
                score += 50
            else:
                score += 10

            if str(r.get('Status', '')).lower() == 'actief':
                score += 20

            addr = str(r.get('Address', '')).strip()
            score += min(len(addr), 50)

            if r.get('Email'):
                score += 40
            if r.get('Website'):
                score += 20
            if r.get('Phone'):
                score += 10

            if score > best_score:
                best_score = score
                best_row = r

        merged = dict(best_row)

        # 1. Hợp nhất Email (chọn email điểm cao nhất)
        all_emails = set()
        for r in group:
            em = clean_email(r.get('Email', ''))
            if em:
                all_emails.add(em)
        if all_emails:
            best_email = max(all_emails, key=lambda e: score_email_b2b(e))
            merged['Email'] = best_email
        else:
            merged['Email'] = ''

        # 2. Hợp nhất Phone
        if not merged.get('Phone') or merged.get('Phone') == '-':
            for r in group:
                p = clean_phone(r.get('Phone', ''))
                if p:
                    merged['Phone'] = p
                    break
        else:
            merged['Phone'] = clean_phone(merged.get('Phone', ''))

        # 3. Hợp nhất Website
        if not merged.get('Website') or merged.get('Website') == '-':
            for r in group:
                w = str(r.get('Website', '')).strip()
                if w and w != '-' and w.lower() != 'nan':
                    merged['Website'] = w
                    break

        # 4. Hợp nhất Địa chỉ nếu bản ghi chính bị trống (thường gặp ở ENT NP cá nhân)
        if not str(merged.get('Address', '')).strip():
            for r in group:
                addr = str(r.get('Address', '')).strip()
                if addr:
                    merged['Address'] = addr
                    merged['Postcode'] = r.get('Postcode', '')
                    break

        # 5. Hợp nhất NACE Codes & Activities
        nace_codes = set()
        activities = []
        for r in group:
            nc = str(r.get('NACE_Code', '')).strip()
            if nc and nc != '-':
                for code in nc.split(','):
                    c_clean = code.strip()
                    if c_clean:
                        nace_codes.add(c_clean)
            act = str(r.get('Activity', '')).strip()
            if act and act not in activities:
                activities.append(act)

        if nace_codes:
            merged['NACE_Code'] = ', '.join(sorted(nace_codes))
        if activities:
            merged['Activity'] = ' / '.join(activities[:2])

        # 6. Điều chỉnh tên thương mại nếu ENT NP chỉ có họ tên cá nhân
        if 'ENT NP' in str(merged.get('Type', '')).upper() and ',' in merged.get('Company_Name', ''):
            for r in group:
                v_name = r.get('Company_Name', '').strip()
                if v_name and ',' not in v_name and len(v_name) > 3:
                    merged['Company_Name'] = f"{v_name} ({merged['Company_Name']})"
                    break

        deduped_rows.append(merged)

    # Phân loại và đẩy các dòng có Email lên đầu (Rule 3)
    with_email = [r for r in deduped_rows if r.get('Email')]
    with_web_phone = [r for r in deduped_rows if not r.get('Email') and (r.get('Website') or r.get('Phone'))]
    others = [r for r in deduped_rows if not r.get('Email') and not r.get('Website') and not r.get('Phone')]

    final_sorted = with_email + with_web_phone + others
    return final_sorted, len(rows) - len(final_sorted)

def process_file(file_path):
    path = Path(file_path)
    if not path.is_absolute():
        path = ROOT_DIR / path
        
    if not path.exists():
        print(f"[!] Không tìm thấy tệp: {path}")
        return

    print(f"\n=======================================================")
    print(f"[*] Bắt đầu lọc trùng tên công ty cho: {path.name}")
    print(f"=======================================================")

    with open(path, mode='r', encoding='utf-8-sig') as f:
        reader = list(csv.DictReader(f))

    if not reader:
        print("[!] Tệp dữ liệu rỗng.")
        return

    fieldnames = list(reader[0].keys())
    total_raw = len(reader)
    print(f"[*] Tổng số bản ghi thô: {total_raw:,}")

    # 1. Tạo bản sao lưu dự phòng trước khi lọc trùng
    backup_path = path.with_name(f"{path.stem}_backup_raw_{total_raw}.csv")
    if not backup_path.exists():
        shutil.copy2(path, backup_path)
        print(f"[+] Đã tạo bản sao lưu an toàn tại: {backup_path.name}")

    # 2. Thực hiện lọc trùng & hợp nhất
    deduped_rows, removed_count = deduplicate_dataset(reader)
    total_clean = len(deduped_rows)

    print(f"[+] Đã loại bỏ: {removed_count:,} bản ghi trùng lặp (chi nhánh / văn phòng phụ / lặp tên).")
    print(f"[+] Còn lại: {total_clean:,} doanh nghiệp độc nhất sẵn sàng làm giàu Google Maps.")

    # Thống kê nhanh
    n_email = sum(1 for r in deduped_rows if r.get('Email'))
    n_phone = sum(1 for r in deduped_rows if r.get('Phone'))
    n_web = sum(1 for r in deduped_rows if r.get('Website'))
    print(f"[+] Thống kê liên hệ: Email KBO: {n_email:,} | SĐT: {n_phone:,} | Website: {n_web:,}")

    # 3. Ghi tệp sạch UTF-8 with BOM (Rule 1)
    with open(path, mode='w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(deduped_rows)
    print(f"[✓] Đã cập nhật tệp sạch chuẩn: {path.name}")

    # 4. Đồng bộ vào csdl_mlt/ và archive/be_belgium/
    sync_dirs = [
        ROOT_DIR / "csdl_mlt",
        ROOT_DIR / "archive" / "be_belgium"
    ]
    for d in sync_dirs:
        if d.exists():
            dest = d / path.name
            shutil.copy2(path, dest)
            print(f"[✓] Đã đồng bộ sang: {dest.relative_to(ROOT_DIR)}")

def main():
    parser = argparse.ArgumentParser(description="Lọc trùng tên công ty & mã số KBO Bỉ")
    parser.add_argument('--file', type=str, default='BE_WOOD_KBO0_0RAW.csv', help='Tên file CSV cần lọc trùng')
    parser.add_argument('--all', action='store_true', help='Lọc trùng toàn bộ file thô (WOOD, MEAT)')
    args = parser.parse_args()

    if args.all:
        for f in ['BE_WOOD_KBO0_0RAW.csv', 'BE_MEAT_KBO0_0RAW.csv']:
            process_file(f)
    else:
        process_file(args.file)

if __name__ == '__main__':
    main()

