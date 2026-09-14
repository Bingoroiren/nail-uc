import asyncio
from playwright.async_api import async_playwright

async def inspect_dom():
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
            const h2s = Array.from(document.querySelectorAll('h2')).map(h => ({
                text: h.innerText,
                parentClass: h.parentElement ? h.parentElement.className : '',
                grandParentClass: h.parentElement && h.parentElement.parentElement ? h.parentElement.parentElement.className : '',
                links: Array.from(h.querySelectorAll('a')).map(a => a.href)
            }));
            const allLinks = Array.from(document.querySelectorAll("a[href*='firmaid=']")).map(a => ({
                text: a.innerText,
                href: a.href,
                classes: a.className
            }));
            return {h2Count: h2s.length, h2s: h2s.slice(0, 5), linkCount: allLinks.length, links: allLinks.slice(0, 5)};
        }""")
        print("DOM Info:", info)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_dom())
