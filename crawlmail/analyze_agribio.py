import csv
import sys
from collections import Counter

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

FILE_PATH = "AT_AGRI_WBIO_0RAW.csv"

total_rows = 0
has_email = 0
has_phone = 0
has_web = 0
has_contact = 0
by_category = Counter()
by_cat_email = Counter()
email_domains = Counter()

with open(FILE_PATH, mode='r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for r in reader:
        total_rows += 1
        cat = r.get('Category', '').strip() or '[Không rõ Category]'
        by_category[cat] += 1
        
        em = r.get('Email', '').strip()
        ph = r.get('SĐT', '').strip()
        wb = r.get('Liên Hệ', '').strip() or r.get('Web', '').strip()
        cp = r.get('Người liên hệ', '').strip()
        
        if em:
            has_email += 1
            by_cat_email[cat] += 1
            if '@' in em:
                dom = em.split('@')[1].lower()
                email_domains[dom] += 1
        if ph:
            has_phone += 1
        if wb:
            has_web += 1
        if cp:
            has_contact += 1

print(f"==================================================")
print(f"📊 PHÂN TÍCH TỔNG QUAN TỆP {FILE_PATH}")
print(f"==================================================")
print(f"Tổng số bản ghi: {total_rows:,}")
print(f"Có Email        : {has_email:,} ({has_email/total_rows*100:.2f}%)")
print(f"Có Số điện thoại: {has_phone:,} ({has_phone/total_rows*100:.2f}%)")
print(f"Có Website/Link : {has_web:,} ({has_web/total_rows*100:.2f}%)")
print(f"Có Người liên hệ: {has_contact:,} ({has_contact/total_rows*100:.2f}%)")

print(f"\n--------------------------------------------------")
print(f"📈 TỈ LỆ EMAIL THEO TỪNG NGUỒN / CATEGORY:")
print(f"--------------------------------------------------")
for cat, cnt in by_category.most_common():
    em_cnt = by_cat_email[cat]
    pct = em_cnt / cnt * 100 if cnt > 0 else 0
    print(f"• {cat}:")
    print(f"   Tổng: {cnt:,} | Có Email: {em_cnt:,} | Tỉ lệ: {pct:.2f}%")

print(f"\n--------------------------------------------------")
print(f"📧 TOP 15 DOMAIN EMAIL PHỔ BIẾN:")
print(f"--------------------------------------------------")
for dom, cnt in email_domains.most_common(15):
    print(f"  {dom:30}: {cnt:,} ({cnt/has_email*100:.1f}%)")
