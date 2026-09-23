import csv
from curl_cffi import requests
from bs4 import BeautifulSoup
import re, json

with open('NOPROFF.csv', encoding='utf-8-sig') as f:
    r = list(csv.DictReader(f))

no_web = [x for x in r if not x['website'] and x['proff_url']][:3]
for item in no_web:
    print('----------------------------------------------------')
    print('Testing company:', item['name'])
    print('Proff URL:', item['proff_url'])
    print('Orgnr:', item['orgnr'])
    
    # 1. Proff.no detail page
    resp = requests.get(item['proff_url'], impersonate='chrome124', timeout=20)
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', resp.text, re.DOTALL)
    if m:
        data = json.loads(m.group(1))
        p_props = data.get('props', {}).get('pageProps', {})
        hydration = p_props.get('hydrationData', {})
        comp_store = hydration.get('companyStore', {})
        c_detail = comp_store.get('company', {})
        if not c_detail:
            c_detail = p_props.get('company', {})
        print('Proff detail keys:', list(c_detail.keys())[:20])
        print('homePage:', c_detail.get('homePage'))
        print('email:', c_detail.get('email'))
        print('phone:', c_detail.get('phone'))
    
    # 2. Check Brreg official API (Norway open government API: https://data.brreg.no/enhetsregisteret/api/enheter/{orgnr})
    clean_org = item['orgnr'].replace("'", "").strip()
    if clean_org:
        try:
            brreg_api = f"https://data.brreg.no/enhetsregisteret/api/enheter/{clean_org}"
            b_resp = requests.get(brreg_api, timeout=10)
            if b_resp.status_code == 200:
                b_data = b_resp.json()
                print('Brreg API homepage:', b_data.get('hjemmeside'))
                print('Brreg API email:', b_data.get('epostadresse'))
                print('Brreg API phone:', b_data.get('telefon'))
                print('Brreg API naeringskode:', b_data.get('naeringskode1'))
        except Exception as e:
            print('Brreg API err:', e)
