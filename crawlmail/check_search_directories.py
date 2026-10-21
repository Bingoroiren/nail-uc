# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import urllib.parse
from bs4 import BeautifulSoup
from curl_cffi import requests
import re
import pandas as pd

df = pd.read_csv('KR_AGCY_MOEL_0RAW.csv', encoding='utf-8-sig')

# Pick 10 corporate agencies (법인) which are larger and have online presence
corps = df[df['Chuc danh'].str.contains('법인')].head(10)

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

print("=== CHECKING GOOGLE SEARCH RESULTS FOR DIRECTORY SITES ===")
directory_domains = {}

for idx, r in corps.iterrows():
    cname = r['Cong ty']
    rep = r['Nguoi lien he']
    city = str(r['Dia chi']).split()[0] if pd.notna(r['Dia chi']) else ''
    
    query = f"{cname} {rep}"
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    try:
        resp = requests.get(url, headers=headers, impersonate='chrome120', timeout=8)
        soup = BeautifulSoup(resp.text, 'html.parser')
        links = soup.select('.result__url')
        print(f"\n[{r['No.']}] {cname} ({rep}):")
        found = False
        for l in links[:5]:
            href = l.get_text(strip=True)
            if href:
                found = True
                domain = href.split('/')[0].replace('www.', '')
                directory_domains[domain] = directory_domains.get(domain, 0) + 1
                print(f"    - {href}")
        if not found:
            print("    (No direct result)")
    except Exception as e:
        print(f"    Error: {e}")

print("\n=== TOP DIRECTORY / PORTAL DOMAINS DETECTED ===")
for d, count in sorted(directory_domains.items(), key=lambda x: x[1], reverse=True):
    print(f"  {d:30} : {count} mentions")
