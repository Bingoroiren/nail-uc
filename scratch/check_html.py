import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1400, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            extra_http_headers={"Accept-Language": "de-AT,de;q=0.9,en-US;q=0.8,en;q=0.7"}
        )
        page = await context.new_page()
        await stealth_async(page)
        
        await page.goto("https://firmen.wko.at/arbeitskr%c3%a4fte%c3%bcberlassung/", wait_until="networkidle")
        print("TITLE:", await page.title())
        text = await page.locator("body").inner_text()
        print("BODY (first 300 chars):", text[:300])
        
        # Check what cards or containers exist
        containers = await page.evaluate("""() => {
            const divs = Array.from(document.querySelectorAll('div, section, ul, li'));
            return divs.map(d => d.className).filter(c => c && (c.includes('result') || c.includes('card') || c.includes('item') || c.includes('entry'))).slice(0, 20);
        }""")
        print("Class names found:", set(containers))
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
