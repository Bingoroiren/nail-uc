import csv
import re
import sys

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

with open('SK_AUTO_SLVD_1ENR.csv', mode='r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for idx, r in enumerate(reader, 1):
        phone = r.get('SĐT', '')
        if phone:
            # check for non-ascii or newlines or icon chars
            if any(ord(c) > 127 for c in phone) or '\n' in phone or '\r' in phone:
                print(f"Dòng {idx}: {r.get('Công ty')} | Phone raw: {repr(phone)}")
