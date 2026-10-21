import csv
import json
import sys

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

with open('SK_AUTO_SLVD_1ENR.csv', mode='r', encoding='utf-8-sig') as f:
    enr_rows = list(csv.DictReader(f))

large_keywords = [
    '50-', '100-', '150-', '200-', '249', '250-', '499', 
    '500-', '999', '1000-', '1999', '2000-', '2999', 
    '3000-', '3999', '4000-', '4999', '5000-', '10000-'
]

large_in_enr = [r for r in enr_rows if any(k in r.get('Quy mô nhân sự', '') for k in large_keywords)]

print(f"Tổng số nhà máy lớn (>= 50 nv) trong 1ENR: {len(large_in_enr)}")

missing_email = []
has_email = []

for r in large_in_enr:
    em = r.get('Email', '').strip()
    if em:
        has_email.append(r)
    else:
        missing_email.append(r)

print(f"Đã có Email: {len(has_email)}")
print(f"Chưa có Email: {len(missing_email)}")

print("\n--- 23 NHÀ MÁY ĐÃ CÓ EMAIL ---")
for idx, r in enumerate(has_email, 1):
    print(f"{idx}. {r.get('Công ty')} | SĐT: {r.get('SĐT')} | Web: {r.get('Web')} | Email: {r.get('Email')}")

print("\n--- CÁC NHÀ MÁY LỚN CHƯA CÓ EMAIL CẦN ENRICH BẰNG AI ---")
for idx, r in enumerate(missing_email, 1):
    print(f"{idx}. {r.get('Công ty')} (IČO: {r.get('IČO')}, {r.get('Thành phố')}) | Web hiện tại: {r.get('Web')}")
