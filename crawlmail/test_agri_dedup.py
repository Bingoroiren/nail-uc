import csv
import re
import sys
from collections import defaultdict

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

FILE_PATH = "AT_AGRI_WBIO_0RAW.csv"

def normalize_name(name):
    if not name:
        return ""
    n = name.lower()
    n = re.sub(r'["\'„“”«»]', '', n)
    legal_terms = ['gmbh', 'og', 'kg', 'gesbr', 'ag', 'e.u.', 'eu', 'ing.', 'mag.', 'dr.', 'dipl.-ing.']
    for term in legal_terms:
        n = re.sub(rf'\b{re.escape(term)}\b', '', n)
    n = re.sub(r'[^\w\s]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n

def extract_plz(address):
    # Mã bưu chính Áo là 4 chữ số (ví dụ 1010, 7100, 4020...)
    m = re.search(r'\b\d{4}\b', address)
    return m.group(0) if m else ""

def completeness_score(r):
    score = 0
    if r.get('Email'): score += 10
    if r.get('SĐT'): score += 5
    if r.get('Liên Hệ') or r.get('Web'): score += 5
    if r.get('Người liên hệ'): score += 5
    if r.get('Địa chỉ'): score += 3
    if 'Bio Austria' in r.get('Category', ''): score += 2
    return score

with open(FILE_PATH, mode='r', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))

print(f"Tổng số bản ghi ban đầu: {len(rows):,}")

# Bước 1: Khử trùng lặp theo Email (Nếu có email trùng lặp, giữ bản ghi đầy đủ nhất)
seen_emails = {}
dedup_by_email = []
email_dups_removed = 0

for r in rows:
    em = r.get('Email', '').strip().lower()
    if em:
        if em in seen_emails:
            email_dups_removed += 1
            # So sánh độ đầy đủ thông tin
            prev_r = seen_emails[em]
            if completeness_score(r) > completeness_score(prev_r):
                seen_emails[em] = r
        else:
            seen_emails[em] = r
    else:
        dedup_by_email.append(r)

# Thêm các dòng giữ lại từ email
dedup_by_email.extend(seen_emails.values())
print(f"-> Sau khi lọc trùng Email: Loại bỏ {email_dups_removed} dòng trùng email -> Còn lại {len(dedup_by_email):,} dòng.")

# Bước 2: Khử trùng lặp theo Tên Công Ty + Mã bưu chính / Thành phố
seen_name_plz = {}
final_unique_rows = []
name_dups_removed = 0

for r in dedup_by_email:
    cname = r.get('Công ty', '').strip()
    norm_c = normalize_name(cname)
    plz = extract_plz(r.get('Địa chỉ', ''))
    
    # Key định danh cơ sở: Tên công ty chuẩn hóa + Mã bưu chính
    key = (norm_c, plz) if plz else (norm_c, r.get('Địa chỉ', '').strip().lower())
    
    if key in seen_name_plz:
        name_dups_removed += 1
        prev_r = seen_name_plz[key]
        if completeness_score(r) > completeness_score(prev_r):
            seen_name_plz[key] = r
    else:
        seen_name_plz[key] = r

final_unique_rows = list(seen_name_plz.values())
print(f"-> Sau khi lọc trùng Tên + Địa chỉ: Loại bỏ {name_dups_removed} dòng trùng lặp -> Còn lại {len(final_unique_rows):,} dòng duy nhất.")

# Thống kê sau khi lọc trùng
with_em = sum(1 for r in final_unique_rows if r.get('Email'))
print(f"\nSau khi lọc trùng:")
print(f"- Tổng số doanh nghiệp / trang trại duy nhất: {len(final_unique_rows):,}")
print(f"- Đã có Email: {with_em:,}")
print(f"- Chưa có Email (cần làm giàu bằng Google Maps): {len(final_unique_rows) - with_em:,}")
