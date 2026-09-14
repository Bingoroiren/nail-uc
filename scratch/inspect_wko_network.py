import asyncio
from playwright.async_api import async_playwright

async def inspect_page():
    async with async_playwright() as p:
        # Launch with headed or headless Chrome
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1400, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # Listen to requests
        page.on("request", lambda r: print(f"REQ: {r.method} {r.url[:100]} (post_data: {r.post_data[:60] if r.post_data else ''})"))
        
        print("[*] Navigating...")
        await page.goto("https://firmen.wko.at/arbeitskr%c3%a4fte%c3%bcberlassung/", wait_until="networkidle")
        
        # Check cookies and consent banner
        print("[*] Checking consent banner...")
        # Inspect HTML of nextPageButton
        btn_info = await page.evaluate("""() => {
            const btn = document.getElementById('ctl00_ContentPlaceHolder1_nextPageButton');
            if (!btn) return 'Button not found';
            return {
                id: btn.id,
                tagName: btn.tagName,
                type: btn.type,
                name: btn.name,
                value: btn.value,
                onclick: btn.getAttribute('onclick'),
                outerHTML: btn.outerHTML
            };
        }""")
        print("[*] Button Info:", btn_info)
        
        # Check form info
        form_info = await page.evaluate("""() => {
            const f = document.querySelector('form');
            if (!f) return 'No form';
            return {
                id: f.id,
                action: f.action,
                method: f.method
            };
        }""")
        print("[*] Form Info:", form_info)
        
        # Accept cookie properly by clicking the actual agree button if present
        try:
            agree = page.locator("#cmp-banner-agree-all")
            if await agree.is_visible():
                print("[*] Clicking cookie agree...")
                await agree.click()
                await page.wait_for_timeout(2000)
        except Exception as e:
            print("Cookie error:", e)
            
        print("\n[*] Now trying to click nextPageButton...")
        btn = page.locator("#ctl00_ContentPlaceHolder1_nextPageButton")
        print("btn visible:", await btn.is_visible())
        await btn.scroll_into_view_if_needed()
        await page.wait_for_timeout(1000)
        
        # Click with mouse
        box = await btn.bounding_box()
        print("bounding box:", box)
        if box:
            print(f"Clicking at {box['x'] + box['width']/2}, {box['y'] + box['height']/2}")
            await page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
            print("[*] Mouse clicked, waiting 5 seconds for network...")
            await page.wait_for_timeout(5000)
            
        cards = await page.locator("a[href*='firmaid=']").count()
        print(f"[*] Cards count after click: {cards}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_page())
