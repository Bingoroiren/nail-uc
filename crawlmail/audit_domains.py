import csv
import urllib.parse
from collections import Counter
import sys

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

domains = Counter()
websites_with_rows = {}

with open('SK_AUTO_SLVD_1ENR.csv', mode='r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for idx, r in enumerate(reader, 1):
        web = r.get('Web', '').strip()
        if web:
            parsed = urllib.parse.urlparse(web)
            domain = parsed.netloc.lower().replace('www.', '')
            domains[domain] += 1
            if domain not in websites_with_rows:
                websites_with_rows[domain] = []
            websites_with_rows[domain].append((idx, r.get('Công ty'), web, r.get('Email')))

print(f"Tổng số unique domains: {len(domains)}")
print("\n--- CÁC DOMAIN XUẤT HIỆN NHIỀU HƠN 1 LẦN (KHẢ NĂNG CAO LÀ TRANG NỀN TẢNG / DANH BẠ) ---")
for dom, count in domains.most_common():
    if count > 1:
        print(f"{dom:35} : {count} lần")

print("\n--- TOÀN BỘ DANH SÁCH DOMAINS ---")
for dom, count in domains.most_common():
    print(f"{dom:35} : {count}")
