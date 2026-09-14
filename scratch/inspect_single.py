import asyncio
from playwright.async_api import async_playwright

SAMPLE_URL = "https://firmen.wko.at/bundh-projekt-und-personalmanagement-gmbh-ingenieurb%c3%bcro-projektmanagement-arbeitskr%c3%a4fte%c3%bcberlassung-p/ober%c3%b6sterreich/?firmaid=113097bd-92b4-4946-ac05-74a3ad864d17&suchbegriff=arbeitskr%c3%a4fte%c3%bcberlassung"

async def test_single():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = browser.contexts[0].pages[1]
        
        await page.wait_for_timeout(2000)
        info = await page.evaluate("""async (url) => {
            const resp = await fetch(url);
            const html = await resp.text();
            return {
                status: resp.status,
                htmlLength: html.length,
                preview: html.slice(0, 300)
            };
        }""", SAMPLE_URL)
        print("Info:", info)

if __name__ == "__main__":
    asyncio.run(test_single())
