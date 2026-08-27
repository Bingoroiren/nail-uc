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
        
        url = "https://m.map.naver.com/search2/search.naver?query=%EC%84%9C%EC%9A%B8%20%EA%B0%95%EB%82%A8%EA%B5%AC%20%ED%8C%A8%EA%B2%AC"
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(3000)
        
        # Find element containing "맨파워코리아"
        el = page.locator("text=맨파워코리아").first
        if await el.count() > 0:
            print("[+] Found element with '맨파워코리아'")
            parent = el.locator("xpath=..")
            grandparent = el.locator("xpath=../..")
            greatgrandparent = el.locator("xpath=../../..")
            greatgreatgrandparent = el.locator("xpath=../../../..")
            
            print("\n=== Parent HTML ===")
            print(await parent.inner_html())
            
            print("\n=== Grandparent HTML ===")
            print(await grandparent.inner_html())
            
            print("\n=== Great-grandparent HTML ===")
            print(await greatgrandparent.inner_html())
            
            print("\n=== Great-great-grandparent HTML ===")
            print(await greatgreatgrandparent.inner_html())
        else:
            print("[-] '맨파워코리아' not found on page.")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
