import asyncio
import sys
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# Set console output encoding to UTF-8
if sys.platform.startswith('win'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

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
        
        import urllib.parse
        query = "서울 강남구 파견"
        url = f"https://m.map.naver.com/search2/search.naver?query={urllib.parse.quote(query)}"
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(3000)
        
        # Scroll to bottom
        print("[*] Scrolling to bottom of page...")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)
        
        # Count list items
        list_items = await page.locator("li[class*='_list_item']").count()
        print(f"[+] Total place items found: {list_items}")
        
        # Find any "More" or "Next" buttons
        print("\n[*] Looking for pagination or 'More' buttons...")
        links = await page.locator("a, button").all()
        for b in links:
            text = await b.inner_text()
            text = text.strip()
            if text and ("더보기" in text or "다음" in text or "페이지" in text or "more" in text.lower() or "next" in text.lower()):
                print(f"Found match: Text='{text}', class='{await b.get_attribute('class')}'")
                
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
