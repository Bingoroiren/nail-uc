import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            viewport={"width": 1400, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await stealth_async(page)
        
        await page.goto("https://firmen.wko.at/arbeitskr%c3%a4fte%c3%bcberlassung/", wait_until="networkidle")
        await page.wait_for_timeout(2000)
        
        # Count result-container
        cards = await page.locator(".result-container").count()
        print(f"[*] Initial .result-container count: {cards}")
        
        # Inspect the first container HTML
        first_html = await page.locator(".result-container").first.inner_html()
        print("\n[*] First .result-container innerHTML:\n", first_html[:600])
        
        # Scroll down to bottom
        for _ in range(5):
            await page.mouse.wheel(0, 3000)
            await page.wait_for_timeout(1000)
            
        cards_after_scroll = await page.locator(".result-container").count()
        print(f"\n[*] .result-container count after scrolling: {cards_after_scroll}")
        
        # Now find Mehr laden button
        btn = page.locator("input#ctl00_ContentPlaceHolder1_nextPageButton, input[value='Mehr laden']")
        print(f"[*] Mehr laden button visible: {await btn.is_visible()}")
        
        # Click button
        await btn.click()
        await page.wait_for_timeout(3000)
        
        cards_after_click = await page.locator(".result-container").count()
        print(f"[*] .result-container count after click 1: {cards_after_click}")
        
        # Click again
        await btn.click()
        await page.wait_for_timeout(3000)
        cards_after_click2 = await page.locator(".result-container").count()
        print(f"[*] .result-container count after click 2: {cards_after_click2}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
