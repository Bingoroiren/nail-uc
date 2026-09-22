# -*- coding: utf-8 -*-
import asyncio
from curl_cffi.requests import AsyncSession
import re
import html
from bs4 import BeautifulSoup
import urllib.parse

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,7}\b')
OBF_REGEX = re.compile(r'([A-Za-z0-9._%+-]{2,40})\s*(?:@|\[at\]|\(at\)|\[ät\]|\(ät\)|\s+at\s+|\s+ät\s+)\s*([A-Za-z0-9.-]+\.[A-Za-z]{2,7})', re.I)

async def test_url(url):
    print(f"\n==========================================", flush=True)
    print(f"Testing URL: {url}", flush=True)
    async with AsyncSession(impersonate="chrome120") as s:
        try:
            r = await s.get(url, timeout=5, allow_redirects=True)
            print(f"Status: {r.status_code}, Final URL: {r.url}, Length: {len(r.text)}", flush=True)
            raw = r.text
            unesc = html.unescape(raw)
            emails = EMAIL_REGEX.findall(unesc)
            obf = OBF_REGEX.findall(unesc)
            print(f"Home page emails: {set(emails)}", flush=True)
            print(f"Home page obfuscated: {set(obf)}", flush=True)
            
            # Contact links
            soup = BeautifulSoup(raw, 'html.parser')
            links = []
            for a in soup.find_all('a', href=True):
                h = a['href'].strip()
                t = a.get_text(strip=True)
                if any(k in h.lower() or k in t.lower() for k in ['yhtey', 'contact', 'ota', 'meist', 'tiimi', 'info', 'yritys', 'rekry']):
                    full_u = urllib.parse.urljoin(str(r.url), h)
                    if full_u not in [x[0] for x in links]:
                        links.append((full_u, t))
            print(f"Found {len(links)} contact links:", flush=True)
            for cl, t in links[:4]:
                print(f"  -> {cl} ('{t}')", flush=True)
                try:
                    cr = await s.get(cl, timeout=5, allow_redirects=True)
                    c_unesc = html.unescape(cr.text)
                    c_emails = EMAIL_REGEX.findall(c_unesc)
                    c_obf = OBF_REGEX.findall(c_unesc)
                    if c_emails or c_obf:
                        print(f"     [!] FOUND: emails={set(c_emails)}, obf={set(c_obf)}", flush=True)
                except Exception as ce:
                    print(f"     Fetch error: {ce}", flush=True)
        except Exception as e:
            print(f"Error testing {url}: {e}", flush=True)

async def main():
    urls = [
        'https://www.hunajaworks.fi',
        'https://www.clevry.com/fi',
        'https://idealscouting.com',
        'https://wulffworks.fi',
        'https://www.keystaff.fi',
        'https://lisapalvelu.net'
    ]
    for u in urls:
        await test_url(u)

if __name__ == '__main__':
    asyncio.run(main())
