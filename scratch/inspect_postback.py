import asyncio
from playwright.async_api import async_playwright

async def inspect_events():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            extra_http_headers={"Accept-Language": "de-AT,de;q=0.9,en-US;q=0.8,en;q=0.7"}
        )
        page = await context.new_page()
        
        # Listen to requests
        page.on("request", lambda r: print(f"REQ: {r.method} {r.url[:80]} - {r.post_data[:60] if r.post_data else ''}"))
        
        await page.goto("https://firmen.wko.at/arbeitskr%c3%a4fte%c3%bcberlassung/", wait_until="networkidle")
        await page.wait_for_timeout(2000)
        
        # Click cookie
        try:
            agree = page.locator("#cmp-banner-agree-all, button:has-text('Alle akzeptieren')")
            if await agree.count() > 0:
                await agree.first.click(force=True)
                await page.wait_for_timeout(1000)
        except Exception:
            pass

        print("\n--- TRIGGERING ASP.NET POSTBACK ---")
        # ASP.NET postback trigger
        res = await page.evaluate("""() => {
            if (typeof __doPostBack === 'function') {
                __doPostBack('ctl00$ContentPlaceHolder1$nextPageButton', '');
                return '__doPostBack called';
            }
            return 'No __doPostBack';
        }""")
        print("Postback result:", res)
        await page.wait_for_timeout(4000)
        
        cards = await page.locator("a[href*='firmaid=']").count()
        print("Cards after postback:", cards)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_events())
