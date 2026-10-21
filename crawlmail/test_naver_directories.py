# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import urllib.parse
from bs4 import BeautifulSoup
from curl_cffi import requests
import re

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

test_cases = [
    "동해인력직업소개소 동해",
    "남광인력 창원",
    "제일인력직업소개소 안산"
]

print("=== TESTING NAVER SEARCH ===")
for q in test_cases:
    url = f"https://search.naver.com/search.naver?query={urllib.parse.quote(q)}"
    r = requests.get(url, headers=headers, impersonate='chrome120', timeout=10)
    soup = BeautifulSoup(r.text, 'html.parser')
    
    print(f"\nQuery: {q}")
    # Extract links from Naver search results
    links = soup.select('a.link_tit, a.name, a.title_link, a.api_txt_lines')
    found_urls = set()
    for a in links[:8]:
        href = a.get('href', '')
        title = a.get_text(strip=True)
        if href.startswith('http') and 'search.naver.com' not in href:
            domain = urllib.parse.urlparse(href).netloc
            found_urls.add(domain)
            print(f"  [{domain}] {title} -> {href}")
            
    # Check phone numbers found on the Naver search result page
    phones = re.findall(r'(0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4})', r.text)
    unique_phones = list(dict.fromkeys(phones))[:5]
    print(f"  Phones detected on page: {unique_phones}")
