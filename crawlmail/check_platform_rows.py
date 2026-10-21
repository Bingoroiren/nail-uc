import csv
import urllib.parse
import sys

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

PLATFORM_DOMAINS = {
    'adresarfiriem.sk',
    'efirma.sk',
    'cybo.com',
    'northdata.com',
    'opencorporates.com',
    'cylex.sk',
    'autoyas.com',
    'doveryhodnafirma.eu',
    'search.infobelpro.com',
    'memoryofnations.sk',
    'motointegrator.com'
}

with open('SK_AUTO_SLVD_1ENR.csv', mode='r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for idx, r in enumerate(reader, 1):
        web = r.get('Web', '').strip()
        parsed = urllib.parse.urlparse(web)
        domain = parsed.netloc.lower().replace('www.', '')
        if domain in PLATFORM_DOMAINS:
            print(f"Dòng {idx:4d} | {r.get('Công ty')[:30]:30} | Web: {web:35} | Email: {r.get('Email') or '[Trống]'} | SĐT: {r.get('SĐT') or '[Trống]'}")
