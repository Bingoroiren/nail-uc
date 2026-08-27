import asyncio
import os
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 14_8 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1",
            viewport={"width": 375, "height": 812},
            locale="ko-KR",
            extra_http_headers={"Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"}
        )
        page = await context.new_page()
        await stealth_async(page)
        
        query = "서울 강남구 파견"
        url = f"https://m.map.naver.com/search2/search.naver?query={urllib.parse.quote(query)}"
        print(f"[*] Navigating to: {url}")
        
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(5000)
        
        # Save HTML
        html = await page.content()
        html_path = r"d:\glc\nail uc\scratch\naver_mobile_search_correct.html"
        os.makedirs(os.path.dirname(html_path), exist_ok=True)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[+] Saved HTML to: {html_path}")
        
        # Save screenshot
        scr_path = r"C:\Users\Admin\.gemini\antigravity-ide\brain\f1cd8f96-441a-435a-9265-9c17ea67161b\scratch\naver_mobile_search_correct.png"
        await page.screenshot(path=scr_path)
        print(f"[+] Saved screenshot to: {scr_path}")
        
        await browser.close()

import urllib.parse
if __name__ == "__main__":
    asyncio.run(main())
