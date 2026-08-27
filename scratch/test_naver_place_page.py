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
        
        url = "https://m.place.naver.com/place/38310075/home"
        print(f"[*] Navigating to: {url}")
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(3000)
        
        # Save screenshot
        scr_path = r"C:\Users\Admin\.gemini\antigravity-ide\brain\f1cd8f96-441a-435a-9265-9c17ea67161b\scratch\naver_place_detail.png"
        await page.screenshot(path=scr_path)
        print(f"[+] Saved screenshot to: {scr_path}")
        
        # Print all links on the page
        print("\n--- All Links on Naver Place page ---")
        links = await page.locator("a").all()
        for idx, link in enumerate(links):
            href = await link.get_attribute("href") or ""
            text = await link.inner_text() or ""
            text = text.strip().replace("\n", " ")
            if href:
                print(f"Link {idx}: text='{text}', href='{href}'")
                
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
