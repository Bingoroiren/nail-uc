# -*- coding: utf-8 -*-
import urllib.request
import ssl
import re
import html
from bs4 import BeautifulSoup

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

url = 'https://www.kopaser.fi'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

req = urllib.request.Request(url, headers=headers)
try:
    with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
        raw = r.read().decode('utf-8', errors='ignore')
        print(f"Status: {r.status}, length: {len(raw)}")
        
        # Check emails in raw
        emails = re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}', raw)
        print("Emails directly on home page:", emails)
        
        # Check unescaped
        unescaped = html.unescape(raw)
        emails_u = re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}', unescaped)
        print("Emails unescaped:", emails_u)
        
        # Check obfuscated [at] or (at) or (ät)
        obf = re.findall(r'([A-Za-z0-9._%+-]+)\s*(?:@|\[at\]|\(at\)|\[ät\]|\(ät\)|\s+at\s+|\s+ät\s+)\s*([A-Za-z0-9.-]+\.[A-Za-z]{2,7})', unescaped, re.I)
        print("Obfuscated emails:", obf)
        
        soup = BeautifulSoup(raw, 'html.parser')
        links = []
        for a in soup.find_all('a', href=True):
            links.append((a['href'], a.get_text(strip=True)))
            
        print("\nAll links on page:")
        for h, t in links:
            if any(k in h.lower() or k in t.lower() for k in ['yhtey', 'contact', 'ota', 'meist', 'tiimi', 'info', 'yritys', 'palvelu']):
                print(f"  Link: {h} | Text: {t}")
except Exception as e:
    print("Error:", e)
