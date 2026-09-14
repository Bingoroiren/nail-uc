import asyncio
from playwright.async_api import async_playwright

async def inspect_all_buttons():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1400, "height": 900})
        await page.goto("https://firmen.wko.at/arbeitskr%c3%a4fte%c3%bcberlassung/", wait_until="networkidle")
        await page.wait_for_timeout(2000)
        
        # Click cookie consent
        try:
            agree = page.locator("#cmp-banner-agree-all")
            if await agree.count() > 0:
                await agree.click()
                await page.wait_for_timeout(1500)
        except Exception:
            pass
            
        elements = await page.evaluate("""() => {
            const all = Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"], a'));
            return all.filter(el => (el.innerText && el.innerText.includes('Mehr')) || (el.value && el.value.includes('Mehr')) || (el.className && el.className.includes('load-more'))).map(el => {
                const rect = el.getBoundingClientRect();
                return {
                    tagName: el.tagName,
                    id: el.id,
                    className: el.className,
                    text: el.innerText || el.value,
                    rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
                    onclick: el.getAttribute('onclick'),
                    outerHTML: el.outerHTML.slice(0, 200)
                };
            });
        }""")
        print("[*] Elements matching 'Mehr':")
        for e in elements:
            print(" ", e)
            
        # Also check fazausgabe.js event listeners or how WKO loads more
        script_content = await page.evaluate("""() => {
            const s = Array.from(document.scripts).map(x => x.src).filter(x => x.includes('faz') || x.includes('ScriptResource'));
            return s;
        }""")
        print("\n[*] Relevant scripts:", script_content)
        
        # Take full page screenshot
        await page.screenshot(path="scratch/wko_full_page.png", full_page=True)
        print("\n[*] Full page screenshot saved to scratch/wko_full_page.png")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_all_buttons())
