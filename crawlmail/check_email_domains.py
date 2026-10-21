import csv
import urllib.parse
import sys

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

with open('SK_AUTO_SLVD_1ENR.csv', mode='r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for idx, r in enumerate(reader, 1):
        em = r.get('Email', '').strip()
        web = r.get('Web', '').strip()
        if em and idx >= 105:
            parsed = urllib.parse.urlparse(web)
            domain = parsed.netloc.lower().replace('www.', '')
            print(f"Dòng {idx:3d} | {r.get('Công ty')[:30]:30} | {domain:25} | {em}")
