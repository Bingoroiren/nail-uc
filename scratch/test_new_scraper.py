# -*- coding: utf-8 -*-
import asyncio
from curl_cffi.requests import AsyncSession
import re
import html
import urllib.parse
from bs4 import BeautifulSoup

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,7}\b')
OBF_REGEX = re.compile(r'([A-Za-z0-9._%+-]{2,40})\s*(?:@|\[at\]|\(at\)|\[ät\]|\(ät\)|\s+at\s+|\s+ät\s+)\s*([A-Za-z0-9.-]+\.[A-Za-z]{2,7})', re.I)

def clean_email(email_str):
    if not email_str:
        return ""
    em = urllib.parse.unquote(email_str).replace('%20', '').strip().lower().rstrip('.,;:')
    if len(em) < 6 or '@' not in em:
        return ""
    return em

def extract_emails_from_html(html_str):
    if not html_str:
        return set()
    found = set()
    unescaped = html.unescape(html_str)
    
    # 1. mailto:
    for mailto in re.findall(r'mailto:([^\s"\'<>]+)', unescaped, re.IGNORECASE):
        cleaned_m = mailto.split('?')[0]
        for sub_em in re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}', urllib.parse.unquote(cleaned_m)):
            em = clean_email(sub_em)
            if em:
                found.add(em)
                
    # 2. Plain text regex
    for match in EMAIL_REGEX.findall(unescaped):
        em = clean_email(match)
        if em:
            found.add(em)
            
    # 3. Obfuscated emails ([at], (at), [ät], (ät), at, ät)
    for u_part, d_part in OBF_REGEX.findall(unescaped):
        em = clean_email(f"{u_part.strip()}@{d_part.strip()}")
        if em:
            found.add(em)
            
    return found

async def scrape_test(url):
    print(f"\n==========================================")
    print(f"Testing: {url}")
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower().replace('www.', '')
    
    collected_emails = set()
    
    async with AsyncSession(impersonate="chrome120") as http_session:
        homepage_html = ""
        try:
            res = await http_session.get(url, timeout=8, allow_redirects=True)
            if res.status_code == 200:
                homepage_html = res.text
                collected_emails.update(extract_emails_from_html(homepage_html))
        except Exception as e:
            print(f"Error fetching home: {e}")
            
        print(f"Home page emails found: {len(collected_emails)}")
        
        # Discover real contact links from DOM
        discovered = []
        if homepage_html:
            soup = BeautifulSoup(homepage_html, 'html.parser')
            keywords = [
                'ota yhteyt', 'yhteystiedot', 'yhteys', 'asiakaspalvelu', 
                'rekrytoijat', 'tiimi', 'contact', 'meist', 'about', 
                'tietoa', 'henkilost', 'henkilöst', 'ihmiset', 'toimisto'
            ]
            for a in soup.find_all('a', href=True):
                href = urllib.parse.unquote(a['href'].strip())
                txt = a.get_text(strip=True).lower()
                href_l = href.lower()
                
                if href.startswith(('#', 'javascript:', 'tel:', 'mailto:')):
                    continue
                if any(href_l.endswith(ext) for ext in ['.pdf', '.jpg', '.png', '.zip']):
                    continue
                if any(bad in href_l for bad in ['informaatio', 'sijoittaj', 'raport', 'taloustiet', 'blog/']):
                    continue
                    
                is_match = any(k in txt for k in keywords) or any(k in href_l for k in keywords)
                if is_match:
                    full_u = urllib.parse.urljoin(url, href)
                    p_u = urllib.parse.urlparse(full_u)
                    if p_u.netloc.lower().replace('www.', '') == domain and full_u != url:
                        if full_u not in discovered:
                            discovered.append(full_u)
                            if len(discovered) >= 6:
                                break
                                
        contact_urls = discovered
        if not contact_urls:
            for slug in ['/yhteystiedot/', '/ota-yhteytta/', '/yhteystiedot', '/ota-yhteytta', '/meista/']:
                contact_urls.append(urllib.parse.urljoin(url, slug))
                
        print(f"Visiting {len(contact_urls[:5])} contact pages:")
        for cu in contact_urls[:5]:
            print(f"  -> {cu}")
            try:
                c_res = await http_session.get(cu, timeout=6, allow_redirects=True)
                if c_res.status_code == 200:
                    found = extract_emails_from_html(c_res.text)
                    if found:
                        print(f"     [!] FOUND {len(found)} emails on {cu}: {list(found)[:3]}...")
                        collected_emails.update(found)
            except Exception as ce:
                print(f"     Error: {ce}")
                
        print(f"TOTAL EMAILS EXTRACTED: {len(collected_emails)}")
        if collected_emails:
            print(f"Sample: {list(collected_emails)[:5]}")

async def main():
    for u in ['https://wulffworks.fi', 'https://www.keystaff.fi', 'https://lisapalvelu.net']:
        await scrape_test(u)

if __name__ == '__main__':
    asyncio.run(main())
