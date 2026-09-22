# -*- coding: utf-8 -*-
import asyncio
import re
import urllib.parse
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,7}\b')

async def test():
    urls = ['https://www.clevry.com/fi', 'https://www.eezy.fi']
    async with AsyncSession(impersonate='chrome124', verify=False) as s:
        for u in urls:
            print(f"\nTesting: {u}")
            res = await s.get(u, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # Find candidate contact links by text and href
            contact_candidates = []
            keywords_text = ['ota yhteytt', 'yhteystiedot', 'yhteys', 'ota yhteyttä', 'asiakaspalvelu', 'tiimi', 'rekrytoijat', 'contact']
            keywords_href = ['/yhteystiedot', '/yhteys', '/ota-yhteytta', '/contact', '/tiimi', '/rekrytoijat']
            
            for a in soup.find_all('a', href=True):
                href = a['href'].strip()
                txt = a.get_text(strip=True).lower()
                href_l = href.lower()
                
                # Ignore anchor only or file
                if href.startswith('#') or any(href_l.endswith(ext) for ext in ['.pdf', '.jpg', '.png']):
                    continue
                # Ignore investor relation / report links
                if any(bad in href_l for bad in ['informaatio', 'sijoittaj', 'raport', 'taloustiet', 'blog/']):
                    continue
                    
                is_match = any(k in txt for k in keywords_text) or any(k in href_l for k in keywords_href)
                if is_match:
                    full_u = urllib.parse.urljoin(u, href)
                    if full_u not in contact_candidates and full_u != u:
                        contact_candidates.append(full_u)
                        
            print("  Contact pages found:", contact_candidates[:5])
            
            # Now fetch contact pages
            all_emails = set()
            for cu in contact_candidates[:4]:
                try:
                    c_res = await s.get(cu, timeout=8)
                    matches = EMAIL_REGEX.findall(c_res.text)
                    for m in matches:
                        if not m.endswith(('.png', '.jpg', '.webp')) and 'sentry' not in m:
                            all_emails.add(m.lower())
                except Exception as e:
                    print(f"  Error fetching {cu}: {e}")
                    
            print("  ==> EMAILS EXTRACTED:", list(all_emails)[:8])

if __name__ == '__main__':
    asyncio.run(test())
