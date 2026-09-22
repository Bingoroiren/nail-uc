# -*- coding: utf-8 -*-
import urllib.request
import ssl
import re
import html
from bs4 import BeautifulSoup

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

urls = [
    'https://www.hunajaworks.fi',
    'https://www.bondata.fi',
    'https://www.clevry.com/fi',
    'https://idealscouting.com',
    'https://wulffworks.fi',
    'https://www.keystaff.fi'
]

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,7}\b')
OBF_REGEX = re.compile(r'([A-Za-z0-9._%+-]{2,40})\s*(?:@|\[at\]|\(at\)|\[ät\]|\(ät\)|\s+at\s+|\s+ät\s+)\s*([A-Za-z0-9.-]+\.[A-Za-z]{2,7})', re.I)

for u in urls:
    print(f"\n====================\nTesting: {u}")
    req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=8) as r:
            raw = r.read().decode('utf-8', errors='ignore')
            unesc = html.unescape(raw)
            print(f"Status: {r.status} | Length: {len(raw)}")
            emails = EMAIL_REGEX.findall(unesc)
            obf = OBF_REGEX.findall(unesc)
            print(f"Direct emails on home page: {set(emails)}")
            print(f"Obfuscated emails on home page: {set(obf)}")
            
            soup = BeautifulSoup(raw, 'html.parser')
            # Look at contact links
            contact_links = []
            for a in soup.find_all('a', href=True):
                h = a['href']
                t = a.get_text(strip=True)
                if any(k in h.lower() or k in t.lower() for k in ['yhtey', 'contact', 'ota', 'meist', 'tiimi', 'info', 'yritys', 'palvelu', 'about']):
                    full_u = urllib.parse.urljoin(u, h)
                    contact_links.append((full_u, t))
            print(f"Found {len(contact_links)} candidate links:")
            for cl, t in contact_links[:5]:
                print(f"  -> {cl} (Text: '{t}')")
                # Try fetching contact page
                try:
                    c_req = urllib.request.Request(cl, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(c_req, context=ctx, timeout=6) as cr:
                        c_raw = cr.read().decode('utf-8', errors='ignore')
                        c_unesc = html.unescape(c_raw)
                        c_emails = EMAIL_REGEX.findall(c_unesc)
                        c_obf = OBF_REGEX.findall(c_unesc)
                        if c_emails or c_obf:
                            print(f"     [!] FOUND ON CONTACT PAGE: emails={set(c_emails)}, obf={set(c_obf)}")
                except Exception as ce:
                    print(f"     Error fetching {cl}: {ce}")
    except Exception as e:
        print(f"Error fetching {u}: {e}")
