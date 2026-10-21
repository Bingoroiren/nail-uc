import csv
import re
import os
import shutil
import sys

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_CSV = os.path.join(ROOT_DIR, "AT_AGRI_WBIO_0RAW.csv")
BACKUP_CSV = os.path.join(ROOT_DIR, "AT_AGRI_WBIO_0RAW_backup.csv")

if not os.path.exists(BACKUP_CSV):
    shutil.copy2(INPUT_CSV, BACKUP_CSV)
    print(f"[+] Da tao ban sao luu: {BACKUP_CSV}")

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

with open(INPUT_CSV, mode='r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    rows = list(reader)

total_before = len(rows)

# 1. Loc trung theo Email
seen_emails = {}
dedup_by_email = []
email_dups_count = 0

for r in rows:
    em = r.get('Email', '').strip().lower()
    if em:
        if em in seen_emails:
            email_dups_count += 1
            prev_r = seen_emails[em]
            if completeness_score(r) > completeness_score(prev_r):
                seen_emails[em] = r
        else:
            seen_emails[em] = r
    else:
        dedup_by_email.append(r)

dedup_by_email.extend(seen_emails.values())

# 2. Loc trung theo Ten Cong Ty + Dia chi / PLZ
seen_name_plz = {}
final_rows = []
name_dups_count = 0

for r in dedup_by_email:
    cname = r.get('Công ty', '').strip()
    norm_c = normalize_name(cname)
    plz = extract_plz(r.get('Địa chỉ', ''))
    
    key = (norm_c, plz) if plz else (norm_c, r.get('Địa chỉ', '').strip().lower())
    
    if key in seen_name_plz:
        name_dups_count += 1
        prev_r = seen_name_plz[key]
        if completeness_score(r) > completeness_score(prev_r):
            seen_name_plz[key] = r
    else:
        seen_name_plz[key] = r

final_rows = list(seen_name_plz.values())

# Đánh số lại No.
for idx, r in enumerate(final_rows, 1):
    r['No.'] = str(idx)

# Ghi đè file AT_AGRI_WBIO_0RAW.csv
temp_file = INPUT_CSV + ".tmp"
with open(temp_file, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(final_rows)

if os.path.exists(INPUT_CSV):
    os.remove(INPUT_CSV)
os.rename(temp_file, INPUT_CSV)

print(f"==================================================")
print(f"🎉 HOAN TAT KHU TRUNG LAP AT_AGRI_WBIO_0RAW.csv")
print(f"==================================================")
print(f"- So luong ban dau: {total_before:,} dong")
print(f"- So dong trung email da loai: {email_dups_count:,} dong")
print(f"- So dong trung ten & dia chi da loai: {name_dups_count:,} dong")
print(f"- So luong con lai: {len(final_rows):,} dong duy nhat (100% Unique)")
print(f"- So co Email: {sum(1 for r in final_rows if r.get('Email')):,}")
print(f"- So chua co Email (can enrich): {sum(1 for r in final_rows if not r.get('Email')):,}")
