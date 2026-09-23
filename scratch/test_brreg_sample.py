import csv, time
from curl_cffi import requests

with open('NOPROFF.csv', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))[:25]

s = requests.Session()
t0 = time.time()
found_email = 0
found_web = 0
found_phone = 0

for r in rows:
    orgnr = r['orgnr'].replace("'", "").strip()
    res = s.get(f'https://data.brreg.no/enhetsregisteret/api/enheter/{orgnr}', timeout=5)
    if res.status_code == 200:
        d = res.json()
        em = d.get('epostadresse')
        web = d.get('hjemmeside')
        tel = d.get('telefon') or d.get('mobil')
        if em: found_email += 1
        if web: found_web += 1
        if tel: found_phone += 1
        print(f"{r['name'][:30]:<30} | Web: {str(web)[:25]:<25} | Email: {str(em)[:25]:<25} | Phone: {tel}")
    elif res.status_code == 404:
        # Check underenhet
        res2 = s.get(f'https://data.brreg.no/enhetsregisteret/api/underenheter/{orgnr}', timeout=5)
        if res2.status_code == 200:
            d = res2.json()
            em = d.get('epostadresse')
            web = d.get('hjemmeside')
            tel = d.get('telefon') or d.get('mobil')
            if em: found_email += 1
            if web: found_web += 1
            if tel: found_phone += 1
            print(f"[SUB] {r['name'][:24]:<24} | Web: {str(web)[:25]:<25} | Email: {str(em)[:25]:<25} | Phone: {tel}")
        else:
            print(f"404: {r['name']}")
    else:
        print(f"HTTP {res.status_code}: {r['name']}")

print('=' * 70)
print(f"25 items in {time.time()-t0:.2f}s | Emails: {found_email}, Webs: {found_web}, Phones: {found_phone}")
