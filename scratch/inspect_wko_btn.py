import asyncio
from playwright.async_api import async_playwright

async def inspect_btn():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            extra_http_headers={"Accept-Language": "de-AT,de;q=0.9,en-US;q=0.8,en;q=0.7"}
        )
        page = await context.new_page()
        await page.goto("https://firmen.wko.at/arbeitskr%c3%a4fte%c3%bcberlassung/", wait_until="networkidle")
        await page.wait_for_timeout(2000)
        
        info = await page.evaluate("""() => {
            const btn = document.getElementById('ctl00_ContentPlaceHolder1_nextPageButton');
            if (!btn) return {found: false};
            return {
                found: true,
                tagName: btn.tagName,
                type: btn.type,
                onclick: btn.getAttribute('onclick'),
                outerHTML: btn.outerHTML
            };
        }""")
        print("Button Info:", info)
        
        # Try clicking via JS evaluate
        js_result = await page.evaluate("""() => {
            const btn = document.getElementById('ctl00_ContentPlaceHolder1_nextPageButton');
            if (btn) {
                btn.click();
                return 'Clicked via JS';
            }
            return 'Btn not found';
        }""")
        print("JS Click Result:", js_result)
        await page.wait_for_timeout(3000)
        
        cards = await page.locator("a[href*='firmaid=']").all()
        print("Cards after JS Click:", len(cards))
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_btn())
