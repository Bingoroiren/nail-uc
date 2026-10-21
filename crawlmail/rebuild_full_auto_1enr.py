import csv
import json
import os
import sys

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_CSV = os.path.join(ROOT_DIR, "SK_AUTO_SLVD_0RAW.csv")
ENR_CSV = os.path.join(ROOT_DIR, "SK_AUTO_SLVD_1ENR.csv")
CACHE_FILE = os.path.join(ROOT_DIR, "crawlmail", "cache_enrich_maps_sk_auto.json")

# 1. Load Cache
cache = {}
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        cache = json.load(f)

# Bogus templates to ignore
BOGUS_EMAILS = {
    'nieco@spolocnost.sk', 'vasa.adresa@firma.sk', 'ussales@iee.lu',
    'info@smartmobility.gov.sk', 'office@valaliky.eu', 'info@uvostat.sk'
}
BOGUS_DOMAINS = {
    'uvostat.sk', 'orsf.sk', 'finreg.sk', 'findat.sk', 'peniaze.sk',
    'valida.sk', 'forebears.io', 'dunajskostredsky.sk', 'ongenealogy.com',
    'dnb.com', 'emis.com', 'kompass.com', 'slovakdata.sk', 'finstat.sk'
}

# 2. Read full RAW_CSV (1513 rows)
with open(RAW_CSV, 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    fieldnames = list(reader.fieldnames)
    raw_rows = list(reader)

print(f"[*] Tổng số dòng trong tệp gốc SK_AUTO_SLVD_0RAW.csv: {len(raw_rows):,}")

# Read existing 1ENR in case there were manual edits
existing_1enr = {}
if os.path.exists(ENR_CSV):
    with open(ENR_CSV, 'r', encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            ico = str(r.get('IČO', '')).strip()
            if ico:
                existing_1enr[ico] = r

processed_rows = []
email_count = 0

for r in raw_rows:
    ico = str(r.get('IČO', '')).strip()
    cname = str(r.get('Công ty', '')).strip()
    cache_key = ico if ico else cname.lower()
    
    # Priority 1: Check existing 1ENR
    if ico in existing_1enr and existing_1enr[ico].get('Email'):
        e_row = existing_1enr[ico]
        em = e_row.get('Email', '').strip()
        if em.lower() not in BOGUS_EMAILS:
            r['Email'] = em
            if e_row.get('Web'): r['Web'] = e_row['Web']
            if e_row.get('SĐT'): r['SĐT'] = e_row['SĐT']
            
    # Priority 2: Check Cache
    if cache_key in cache:
        c_data = cache[cache_key]
        c_em = str(c_data.get('email', '')).strip()
        c_web = str(c_data.get('website', '')).strip()
        c_phone = str(c_data.get('phone', '')).strip()
        
        if c_em and c_em.lower() not in BOGUS_EMAILS and not r.get('Email'):
            r['Email'] = c_em
        if c_web and not any(bd in c_web.lower() for bd in BOGUS_DOMAINS) and not r.get('Web'):
            r['Web'] = c_web
        if c_phone and not r.get('SĐT'):
            r['SĐT'] = c_phone
            
    # Clean phone format
    phone = str(r.get('SĐT', '')).strip()
    if phone and not phone.startswith("'"):
        r['SĐT'] = f"'{phone}"
        
    if r.get('Email'):
        email_count += 1
        
    processed_rows.append(r)

# Rule 3: Sort so 100% of companies WITH EMAIL are at the top
with_email = []
without_email = []

for r in processed_rows:
    em = str(r.get('Email', '')).strip()
    if em and em != 'nan':
        with_email.append(r)
    else:
        without_email.append(r)

# Sort with_email by headcount descending
def sort_key(r):
    size = r.get('Quy mô nhân sự', '')
    if '4000-' in size or '5000-' in size: return 1
    if '3000-' in size: return 2
    if '2000-' in size: return 3
    if '1000-' in size: return 4
    if '500-' in size: return 5
    if '250-' in size: return 6
    if '200-' in size: return 7
    if '150-' in size: return 8
    if '100-' in size: return 9
    if '50-' in size: return 10
    if '25-' in size: return 11
    if '20-' in size: return 12
    if '10-' in size: return 13
    return 20

with_email.sort(key=sort_key)

final_rows = with_email + without_email
for idx, r in enumerate(final_rows, 1):
    r['No.'] = str(idx)

# Save to SK_AUTO_SLVD_1ENR.csv
temp_file = ENR_CSV + ".tmp"
with open(temp_file, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(final_rows)

if os.path.exists(ENR_CSV):
    os.remove(ENR_CSV)
os.rename(temp_file, ENR_CSV)

print(f"[+] Đã ghi lại file {ENR_CSV}:")
print(f"    - Tổng số dòng: {len(final_rows):,} dòng (bảo toàn 100% tệp gốc!)")
print(f"    - Số công ty có Email: {len(with_email):,} công ty (đẩy lên các dòng đầu tiên)")
print(f"    - Số công ty chưa có Email: {len(without_email):,} công ty (xếp tiếp theo bên dưới)")
