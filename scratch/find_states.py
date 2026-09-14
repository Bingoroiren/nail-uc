import asyncio
import sys
import codecs
from playwright.async_api import async_playwright

if sys.platform.startswith('win') and hasattr(sys.stdout, 'buffer'):
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

async def find_all_state_urls():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = browser.contexts[0].pages[1]
        
        await page.goto("https://firmen.wko.at/arbeitskr%c3%a4fte%c3%bcberlassung/", wait_until="domcontentloaded")
        await page.wait_for_timeout(1000)
        
        links = await page.evaluate("""() => {
            const as = Array.from(document.querySelectorAll('a'));
            return as.map(a => ({
                text: a.innerText.trim(),
                href: a.getAttribute('href')
            })).filter(x => x.text.includes('Arbeitskräfteüberlassung in'));
        }""")
        for l in links:
            print(f"{l['text']} -> {l['href']}")

if __name__ == "__main__":
    asyncio.run(find_all_state_urls())
