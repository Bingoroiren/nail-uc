import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto('https://firmen.wko.at/arbeitskr%c3%a4fte%c3%bcberlassung/', wait_until='domcontentloaded', timeout=30000)
        await page.evaluate("""() => {
            const b = document.getElementById('cmp-root'); if (b) b.remove();
            const d = document.getElementById('cmp-backdrop'); if (d) d.remove();
        }""")
        for i in range(10):
            btn = page.locator('input#ctl00_ContentPlaceHolder1_nextPageButton').first
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click(force=True)
                await page.wait_for_timeout(600)
                cur = await page.locator("a[href*='firmaid=']").count()
                print(f"Click {i+1}: ~{cur} listings")
            else:
                print("Button not found/visible")
                break
        links = await page.locator("a[href*='firmaid=']").all()
        print(f"Total company links: {len(links)}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test())
