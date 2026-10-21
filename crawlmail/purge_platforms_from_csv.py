import csv
import urllib.parse
import re
import os
import json
import sys

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_FILE = os.path.join(ROOT_DIR, "SK_AUTO_SLVD_1ENR.csv")
CACHE_FILE = os.path.join(ROOT_DIR, "crawlmail", "cache_enrich_maps_sk_auto.json")

# Danh sách toàn bộ các domain nền tảng / danh bạ / thư bạ / tra cứu dữ liệu
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
    'motointegrator.com',
    'talentflowcorp.com',
    'finstat.sk',
    'zlatestranky.sk',
    'orsr.sk',
    'zrsr.sk',
    'registeruz.sk',
    'slovakdata.sk',
    'uvostat.sk',
    'finreg.sk',
    'findat.sk',
    'peniaze.sk',
    'valida.sk',
    'forebears.io',
    'ongenealogy.com',
    'emis.com',
    'dnb.com',
    'kompass.com',
    'yellowpages.sk',
    'azet.sk'
}

def clean_phone(phone_str):
    if not phone_str:
        return ""
    p = str(phone_str).strip()
    # Loại bỏ các ký tự icon unicode đặc thù như \ue0b0 và xuống dòng
    p = re.sub(r'[\ue000-\uf8ff]', '', p)
    p = re.sub(r'[\r\n]+', ' ', p).strip()
    # Loại bỏ dấu nháy đơn và khoảng trắng ban đầu
    p = p.lstrip("'").strip()
    # Loại bỏ khoảng trắng thừa
    p = re.sub(r'\s+', ' ', p).strip()
    if p:
        p = f"'{p}"
    return p

# 1. Làm sạch CSV
with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    rows = list(reader)

cleaned_web_count = 0
cleaned_phone_count = 0
purged_details = []

for idx, r in enumerate(rows, 1):
    web = r.get('Web', '').strip()
    old_phone = r.get('SĐT', '')
    
    # Clean phone
    new_phone = clean_phone(old_phone)
    if new_phone != old_phone:
        r['SĐT'] = new_phone
        cleaned_phone_count += 1
        
    # Check platform website
    if web:
        parsed = urllib.parse.urlparse(web)
        domain = parsed.netloc.lower().replace('www.', '')
        if domain in PLATFORM_DOMAINS or any(pd in domain for pd in PLATFORM_DOMAINS):
            purged_details.append((idx, r.get('Công ty'), web, domain))
            r['Web'] = ''
            cleaned_web_count += 1

print(f"[*] Đã quét {len(rows):,} bản ghi:")
print(f"    - Đã loại bỏ {cleaned_web_count} trang nền tảng chung khỏi cột Web.")
print(f"    - Đã làm sạch {cleaned_phone_count} số điện thoại bị dính icon/ký tự lạ.")

print("\n--- CHI TIẾT CÁC TRANG NỀN TẢNG ĐÃ LOẠI BỎ KHỎI CỘT WEB ---")
for idx, cname, web, dom in purged_details:
    print(f"Dòng {idx:4d} | {cname[:30]:30} | {dom:22} | {web}")

# Ghi lại CSV
temp_file = CSV_FILE + ".tmp"
with open(temp_file, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

if os.path.exists(CSV_FILE):
    os.remove(CSV_FILE)
os.rename(temp_file, CSV_FILE)
print(f"\n[+] Đã cập nhật tệp CSV: {CSV_FILE}")

# 2. Làm sạch Cache JSON
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        cache = json.load(f)
    
    cache_cleaned_count = 0
    for k, v in cache.items():
        c_web = v.get('website', '').strip()
        c_phone = v.get('phone', '')
        if c_phone:
            v['phone'] = clean_phone(c_phone)
        if c_web:
            parsed = urllib.parse.urlparse(c_web)
            domain = parsed.netloc.lower().replace('www.', '')
            if domain in PLATFORM_DOMAINS or any(pd in domain for pd in PLATFORM_DOMAINS):
                v['website'] = ''
                cache_cleaned_count += 1
                
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    print(f"[+] Đã cập nhật Cache JSON: Đã dọn {cache_cleaned_count} website nền tảng.")
