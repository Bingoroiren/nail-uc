import asyncio
from playwright.async_api import async_playwright

async def inspect_wko_network():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            extra_http_headers={"Accept-Language": "de-AT,de;q=0.9,en-US;q=0.8,en;q=0.7"}
        )
        page = await context.new_page()
        
        async def on_response(response):
            if "firmen.wko.at" in response.url and response.request.method == "POST":
                print(f"[POST RESPONSE] {response.status} {response.url}")
                try:
                    text = await response.text()
                    print(f"  Length: {len(text)}, Snippet: {text[:200]}")
                except Exception as e:
                    print("  Text error:", e)

        page.on("response", on_response)
        
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

        btn = page.locator("input#ctl00_ContentPlaceHolder1_nextPageButton").first
        print(f"Clicking button: count={await btn.count()}, visible={await btn.is_visible()}")
        await btn.click()
        await page.wait_for_timeout(4000)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_wko_network())
