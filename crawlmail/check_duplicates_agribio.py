import csv
import re
from collections import Counter, defaultdict
import sys

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

FILE_PATH = "AT_AGRI_WBIO_0RAW.csv"

def normalize_name(name):
    if not name:
        return ""
    n = name.lower()
    n = re.sub(r'["\'„“”«»]', '', n)
    # Loại bỏ legal forms và danh xưng
    legal_terms = ['gmbh', 'og', 'kg', 'gesbr', 'ag', 'e.u.', 'eu', 'ing.', 'mag.', 'dr.', 'dipl.-ing.']
    for term in legal_terms:
        n = re.sub(rf'\b{re.escape(term)}\b', '', n)
    n = re.sub(r'[^\w\s]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n

raw_names = Counter()
norm_names = Counter()
emails = Counter()
phones = Counter()

norm_to_rows = defaultdict(list)
email_to_rows = defaultdict(list)

with open(FILE_PATH, mode='r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for idx, r in enumerate(reader, 1):
        cname = r.get('Công ty', '').strip()
        em = r.get('Email', '').strip().lower()
        ph = re.sub(r'[^\d+]', '', r.get('SĐT', '').strip())
        
        raw_names[cname] += 1
        n_name = normalize_name(cname)
        if n_name:
            norm_names[n_name] += 1
            norm_to_rows[n_name].append((idx, cname, em, r.get('Địa chỉ'), r.get('Category')))
            
        if em:
            emails[em] += 1
            email_to_rows[em].append((idx, cname, em, r.get('Địa chỉ')))
            
        if ph and len(ph) >= 7:
            phones[ph] += 1

dup_raw_names = {k: v for k, v in raw_names.items() if v > 1}
dup_norm_names = {k: v for k, v in norm_names.items() if v > 1}
dup_emails = {k: v for k, v in emails.items() if v > 1}
dup_phones = {k: v for k, v in phones.items() if v > 1}

print("==================================================")
print("📊 BÁO CÁO KIỂM TRA TRÙNG LẶP TRONG TỆP AT_AGRI_WBIO_0RAW.csv")
print("==================================================")
print(f"Tổng số bản ghi: {sum(raw_names.values()):,}")
print(f"1. Trùng tên công ty chính xác (Exact Name): {len(dup_raw_names)} cụm tên bị trùng (Tổng {sum(dup_raw_names.values())} dòng)")
print(f"2. Trùng tên công ty sau chuẩn hóa (Normalized Name): {len(dup_norm_names)} cụm tên bị trùng (Tổng {sum(dup_norm_names.values())} dòng)")
print(f"3. Trùng Email: {len(dup_emails)} email bị trùng lặp (Tổng {sum(dup_emails.values())} dòng)")
print(f"4. Trùng Số điện thoại: {len(dup_phones)} SĐT bị trùng lặp (Tổng {sum(dup_phones.values())} dòng)")

print("\n--- TOP 10 CỤM TÊN BỊ TRÙNG LẶP NHIỀU NHẤT ---")
for n_name, count in sorted(dup_norm_names.items(), key=lambda x: -x[1])[:10]:
    sample_rows = norm_to_rows[n_name]
    print(f"\n[x{count}] '{n_name}':")
    for row in sample_rows[:4]:
        print(f"   Dòng {row[0]}: {row[1]} | Mail: {row[2] or '[Trống]'} | Đ/C: {row[3][:40]}... | Cat: {row[4][:30]}...")

print("\n--- TOP 10 EMAIL BỊ TRÙNG LẶP NHIỀU NHẤT ---")
for em, count in sorted(dup_emails.items(), key=lambda x: -x[1])[:10]:
    sample_rows = email_to_rows[em]
    print(f"\n[x{count}] '{em}':")
    for row in sample_rows[:3]:
        print(f"   Dòng {row[0]}: {row[1]} | Đ/C: {row[3][:40]}...")
