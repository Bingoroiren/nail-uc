# -*- coding: utf-8 -*-
import asyncio
from playwright.async_api import async_playwright
import re
import html
from bs4 import BeautifulSoup
import urllib.parse

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,7}\b')
OBF_EMAIL_REGEX = re.compile(
    r'([A-Za-z0-9._%+-]{2,40})\s*(?:@|\[at\]|\(at\)|\[ät\]|\(ät\)|\s+at\s+|\s+ät\s+)\s*([A-Za-z0-9.-]+\.[A-Za-z]{2,7})',
    re.IGNORECASE
)

def extract_emails(html_str):
    if not html_str: return set()
    found = set()
    unesc = html.unescape(html_str)
    for m in EMAIL_REGEX.findall(unesc):
        em = m.strip().lower().rstrip('.,;:')
        if len(em) >= 6 and not any(em.endswith(x) for x in ['.png', '.jpg', '.pdf', '.css', '.js']):
            found.add(em)
    for u, d in OBF_EMAIL_REGEX.findall(unesc):
        em = f"{u.strip()}@{d.strip()}".lower()
        found.add(em)
    return found

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        urls = ['https://wulffworks.fi', 'https://www.keystaff.fi']
        for u in urls:
            print(f"Opening in Chrome: {u}")
            try:
                await page.goto(u, wait_until="domcontentloaded", timeout=12000)
                await asyncio.sleep(1.5)
                content = await page.content()
                emails = extract_emails(content)
                print(f"  Home emails: {len(emails)}")
                
                # Find contact link on page
                contact_links = page.locator('a[href*="yhtey"], a[href*="ota-yhteytta"], a[href*="meista"], a:has-text("Yhteystiedot"), a:has-text("Meistä")')
                cnt = await contact_links.count()
                if cnt > 0:
                    href = await contact_links.first.get_attribute('href')
                    full_u = urllib.parse.urljoin(u, href)
                    print(f"  Opening contact page in Chrome: {full_u}")
                    await page.goto(full_u, wait_until="domcontentloaded", timeout=12000)
                    await asyncio.sleep(1.5)
                    c_content = await page.content()
                    c_emails = extract_emails(c_content)
                    print(f"  Contact page emails: {len(c_emails)} -> {list(c_emails)[:4]}")
            except Exception as e:
                print(f"Error: {e}")
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
