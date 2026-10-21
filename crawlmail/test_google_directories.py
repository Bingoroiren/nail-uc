# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import asyncio
import urllib.parse
import re
from playwright.async_api import async_playwright

test_companies = [
    ("안산일일취업센터직업소개소", "전상록", "안산"),
    ("한화교역주식회사", "박지환", "안산"),
    ("(주)제일엔에스", "이경택", "평택"),
    ("동해인력직업소개소", "정강수", "동해"),
    ("남광인력", "안효관", "창원")
]

async def test_search():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=['--lang=ko-KR', '--window-size=1280,800'])
        page = await browser.new_page()
        
        for name, rep, city in test_companies:
            print(f"\n=======================================================")
            print(f"Testing Google Search for: {name} | {rep} | {city}")
            print(f"=======================================================")
            
            # Query 1: Tên cty + đại diện / địa phương
            query = f'"{name}" {city}'
            url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&hl=ko"
            
            await page.goto(url, wait_until='domcontentloaded')
            await page.wait_for_timeout(2000)
            
            # Extract result links and snippets
            results = await page.query_selector_all('div.g, div.tF2Cxc')
            print(f"Found {len(results)} search results on Google:")
            for idx, res in enumerate(results[:5], 1):
                link_el = await res.query_selector('a')
                title_el = await res.query_selector('h3')
                snippet_el = await res.query_selector('div.VwiC3b, span.aCOpRe')
                
                href = await link_el.get_attribute('href') if link_el else ''
                title = await title_el.inner_text() if title_el else ''
                snippet = await snippet_el.inner_text() if snippet_el else ''
                
                print(f"  Result {idx}:")
                print(f"    Title: {title}")
                print(f"    URL: {href}")
                print(f"    Snippet: {snippet[:120]}")
                
                # Check for emails in snippet
                emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', snippet)
                if emails:
                    print(f"    [!] EMAILS FOUND IN SNIPPET: {emails}")
                    
        await browser.close()

if __name__ == '__main__':
    asyncio.run(test_search())
