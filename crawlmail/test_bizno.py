# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import urllib.parse
from bs4 import BeautifulSoup
from curl_cffi import requests
import re

query = '한화교역주식회사'
url = f'https://bizno.net/?q={urllib.parse.quote(query)}'

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

resp = requests.get(url, headers=headers, impersonate='chrome120', timeout=10)
soup = BeautifulSoup(resp.text, 'html.parser')

items = soup.select('.titles a, .search-result a, a[href^="/article/"]')
print(f"Found {len(items)} article links for '{query}':")
detail_link = None
for a in items:
    href = a.get('href', '')
    text = a.get_text(strip=True)
    if '/article/' in href:
        print(f"  Link: {href} | Text: {text}")
        if not detail_link:
            detail_link = href

if detail_link:
    detail_url = urllib.parse.urljoin('https://bizno.net', detail_link)
    print(f"\nVisiting detail page: {detail_url}")
    r_detail = requests.get(detail_url, headers=headers, impersonate='chrome120', timeout=10)
    d_soup = BeautifulSoup(r_detail.text, 'html.parser')
    
    # Find all table rows
    rows = d_soup.select('table tr, .table_info tr, dl')
    print(f"Detail table rows: {len(rows)}")
    for r in rows:
        t = r.get_text(separator=' : ', strip=True)
        if any(k in t for k in ['전화번호', '이메일', '대표자', '소재지', '업종', '홈페이지', '사업자등록번호']):
            print(f"    {t}")
            
    # Also find emails by regex
    emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', r_detail.text)
    print(f"\nRegex emails found on page: {emails}")
