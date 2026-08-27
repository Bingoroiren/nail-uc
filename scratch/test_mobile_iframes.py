import asyncio
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
        
        url = "https://m.map.naver.com/search2/search.naver?query=%EC%84%9C%EC%9A%B8%20%EA%B0%95%EB%82%A8%EA%B5%AC%20%ED%8C%A8%EA%B2%AC" # using Guro to test
        await page.goto("https://m.map.naver.com/search2/search.naver?query=%EC%84%9C%EC%9A%B8%20%EA%B0%95%EB%82%A8%EA%B5%AC%20%ED%8C%A8%EA%B2%AC", wait_until="networkidle")
        await page.wait_for_timeout(4000)
        
        # Print frames
        print("\n--- Available Frames ---")
        for idx, f in enumerate(page.frames):
            print(f"Frame {idx}: name='{f.name}', url='{f.url[:80]}'")
            
        # Let's check if there is an iframe with search results
        iframes = await page.locator("iframe").all()
        print(f"\n[*] Total iframes found: {len(iframes)}")
        for idx, iframe in enumerate(iframes):
            name = await iframe.get_attribute("name") or ""
            src = await iframe.get_attribute("src") or ""
            id_val = await iframe.get_attribute("id") or ""
            print(f"Iframe {idx}: id='{id_val}', name='{name}', src='{src[:80]}'")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
