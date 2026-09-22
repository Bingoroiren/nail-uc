# -*- coding: utf-8 -*-
import asyncio
import os
import sys
import urllib.parse
from playwright.async_api import async_playwright
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scratch.test_name_match_fi import is_valid_name_match_fi, clean_company_name_fi

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

EXCLUDED_DOMAINS = {
    'finder.fi', 'kauppalehti.fi', 'asiakastieto.fi', 'yritystele.fi', 'proff.fi', 
    'fonecta.fi', 'suomi.fi', 'duunitori.fi', 'oikotie.fi', 'monster.fi', 'jobly.fi', 
    'tori.fi', 'yritysopas.fi', 'yrityshaku.fi', 'wikipedia.org', 'facebook.com', 
    'linkedin.com', 'instagram.com', 'youtube.com', 'google.com', 'google.fi'
}

async def test_bing():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, channel="chrome")
        page = await browser.new_page()
        
        c_name = "Järvimäki HR Services Oy"
        q_clean = clean_company_name_fi(c_name)
        query = f'"{q_clean}" Suomi'
        print(f"[+] Tìm kiếm Bing trên trình duyệt hiển thị: {query}")
        
        bing_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
        await page.goto(bing_url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(2)
        
        # Handle Bing cookie consent if any
        try:
            accept_btn = page.locator('#bnp_btn_accept, button#bnp_btn_accept, button:has-text("Hyväksy"), button:has-text("Accept")')
            if await accept_btn.count() > 0:
                await accept_btn.first.click()
                await asyncio.sleep(1)
        except Exception:
            pass
            
        results = page.locator('li.b_algo')
        count = await results.count()
        print(f"  Thấy {count} kết quả trên Bing:")
        
        for i in range(min(count, 5)):
            h2 = results.nth(i).locator('h2')
            link = results.nth(i).locator('h2 a')
            t_text = await h2.text_content() if await h2.count() > 0 else ""
            href = await link.get_attribute('href') if await link.count() > 0 else ""
            parsed = urllib.parse.urlparse(href)
            domain = parsed.netloc.lower().replace('www.', '')
            print(f"    #{i+1}: [{domain}] {t_text}")
            
        await asyncio.sleep(3)
        await browser.close()

if __name__ == '__main__':
    asyncio.run(test_bing())
