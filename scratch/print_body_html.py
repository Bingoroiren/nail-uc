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
            locale="ko-KR"
        )
        page = await context.new_page()
        await stealth_async(page)
        
        url = "https://m.map.naver.com/search2/search.naver?query=%EC%84%9C%EC%9A%B8%20%EA%B0%95%EB%82%A8%EA%B5%AC%20%ED%8C%A8%EA%B2%AC"
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(5000)
        
        html = await page.content()
        out_path = r"d:\glc\nail uc\scratch\naver_mobile_body.html"
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[+] Saved HTML to: {out_path}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
