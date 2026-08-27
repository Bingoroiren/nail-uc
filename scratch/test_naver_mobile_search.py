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
        await page.wait_for_timeout(3000)
        
        # Save screenshot
        scr_path = r"C:\Users\Admin\.gemini\antigravity-ide\brain\f1cd8f96-441a-435a-9265-9c17ea67161b\scratch\naver_mobile_search.png"
        await page.screenshot(path=scr_path)
        print(f"[+] Saved search results screenshot to: {scr_path}")
        
        # Look for search results list items
        # Let's print body text to check what is in there
        body_text = await page.locator("body").inner_text()
        print("\n--- Body Text Snippet ---")
        print(body_text[:1000])
        
        # Also print list element tags or links
        print("\n--- Links containing places ---")
        links = await page.locator("a").all()
        link_count = 0
        for l in links:
            href = await l.get_attribute("href")
            text = await l.inner_text()
            if href and ("siteId=" in href or "search2/site.naver" in href or "common/site" in href):
                print(f"Text: '{text.strip()}', Href: '{href}'")
                link_count += 1
                if link_count >= 10:
                    break
                    
        await browser.close()

import urllib.parse
if __name__ == "__main__":
    asyncio.run(main())
