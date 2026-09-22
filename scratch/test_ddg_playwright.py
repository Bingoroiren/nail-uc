# -*- coding: utf-8 -*-
import asyncio
import os
import sys
import urllib.parse
from playwright.async_api import async_playwright
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scratch.test_name_match_fi import is_valid_name_match_fi, clean_company_name_fi

async def test_ddg():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, channel="chrome")
        page = await browser.new_page()
        
        c_name = "Barona Oy"
        q_clean = clean_company_name_fi(c_name)
        query = f'"{q_clean}" Suomi yhteystiedot'
        print(f"[+] Tìm kiếm DuckDuckGo trên trình duyệt: {query}")
        
        ddg_url = f"https://duckduckgo.com/?q={urllib.parse.quote(query)}"
        await page.goto(ddg_url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(2)
        
        results = page.locator('article[data-testid="result"]')
        count = await results.count()
        print(f"  Thấy {count} kết quả trên DuckDuckGo:")
        for i in range(min(count, 5)):
            title_el = results.nth(i).locator('h2 a')
            t_text = await title_el.text_content() if await title_el.count() > 0 else ""
            href = await title_el.get_attribute('href') if await title_el.count() > 0 else ""
            print(f"    #{i+1}: {href} | {t_text}")
            
        await asyncio.sleep(3)
        await browser.close()

if __name__ == '__main__':
    asyncio.run(test_ddg())
