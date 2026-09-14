import asyncio
from playwright.async_api import async_playwright

async def inspect_card_container():
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
            const firstA = document.querySelector('a.title-link');
            if (!firstA) return 'No a.title-link';
            let curr = firstA.parentElement;
            const chain = [];
            while (curr && curr.tagName !== 'BODY') {
                chain.push({tag: curr.tagName, id: curr.id, class: curr.className});
                curr = curr.parentElement;
            }
            // Also get html of the card
            let card = firstA.closest('.result-card') || firstA.closest('[class*="card"]') || firstA.parentElement.parentElement;
            return {chain: chain.slice(0, 5), cardHTML: card ? card.outerHTML.slice(0, 500) : ''};
        }""")
        print("Container Info:", info)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_card_container())
