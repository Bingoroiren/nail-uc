import asyncio
import sys
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# Set console output encoding to UTF-8
if sys.platform.startswith('win'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

async def check_place(context, name, url):
    page = None
    try:
        page = await context.new_page()
        await stealth_async(page)
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(2000)
        
        print(f"\n=== Inspecting: {name} ({url}) ===")
        links = await page.locator("a").all()
        found_website = False
        for link in links:
            href = await link.get_attribute("href") or ""
            text = await link.inner_text() or ""
            text = text.strip().replace("\n", " ")
            if href.startswith(("http://", "https://")):
                href_lower = href.lower()
                if not any(x in href_lower for x in ["naver.com", "facebook.com/sharer", "twitter.com", "instagram.com"]):
                    print(f"  [Found Website Link] Text: '{text}', Href: '{href}'")
                    found_website = True
        if not found_website:
            print("  [No Website Link Found on Naver Place page]")
    except Exception as e:
        print(f"  [Error] {e}")
    finally:
        if page:
            await page.close()

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 14_8 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1",
            viewport={"width": 375, "height": 812},
            locale="ko-KR"
        )
        # Everbrain Search Place URL (from our CSV output)
        await check_place(context, "에버브레인써치", "https://m.place.naver.com/place/2086460176/home")
        
        # Power People Consulting Place URL
        await check_place(context, "파워피플컨설팅", "https://m.place.naver.com/place/1326573181/home")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
