import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = await browser.new_page(viewport={"width": 1400, "height": 900})
        await stealth_async(page)
        
        await page.goto("https://firmen.wko.at/arbeitskr%c3%a4fte%c3%bcberlassung/", wait_until="networkidle")
        await page.wait_for_timeout(2000)
        
        # Check all links inside ResultList
        links_info = await page.evaluate("""() => {
            const res = [];
            const resultLists = document.querySelectorAll('[id*="ResultList"]');
            for (const r of resultLists) {
                const as = r.querySelectorAll('a');
                for (const a of as) {
                    res.push({
                        listId: r.id,
                        text: a.innerText.trim(),
                        href: a.getAttribute('href'),
                        className: a.className
                    });
                }
            }
            return {
                resultListsCount: resultLists.length,
                totalLinks: res.length,
                sampleLinks: res.slice(0, 10)
            };
        }""")
        print("[*] Info:", links_info)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
