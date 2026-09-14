import asyncio
from playwright.async_api import async_playwright

async def inspect():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        # Inspect active page
        for page in context.pages:
            if "3s-net-gmbh" in page.url:
                title = await page.title()
                body = await page.locator("body").inner_text()
                print("URL:", page.url)
                print("Title:", title)
                print("BODY preview:\n", body[:800])
                break

if __name__ == "__main__":
    asyncio.run(inspect())
