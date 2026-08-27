import asyncio
import os
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900}
        )
        page = await context.new_page()
        await stealth_async(page)
        
        url = "https://map.naver.com/p/"
        print(f"[*] Navigating to: {url}")
        
        await page.goto(url, wait_until="networkidle")
        
        scr_path_1 = r"C:\Users\Admin\.gemini\antigravity-ide\brain\f1cd8f96-441a-435a-9265-9c17ea67161b\scratch\naver_load.png"
        await page.screenshot(path=scr_path_1)
        print(f"[+] Saved initial screenshot to: {scr_path_1}")
        
        # Check if search input is visible
        # Naver Map search input is usually selector: "input.input_search" or ".input_box input"
        print("[*] Looking for search input...")
        search_input = page.locator("input.input_search").first
        if await search_input.count() > 0:
            print("[+] Found search input! Typing query...")
            await search_input.fill("서울 강남구 파견")
            await search_input.press("Enter")
            
            print("[*] Waiting 5 seconds for results...")
            await page.wait_for_timeout(5000)
            
            # Print frames
            print("\n--- Available Frames after search ---")
            for idx, f in enumerate(page.frames):
                print(f"Frame {idx}: name='{f.name}', url='{f.url}'")
                
            scr_path_2 = r"C:\Users\Admin\.gemini\antigravity-ide\brain\f1cd8f96-441a-435a-9265-9c17ea67161b\scratch\naver_search_result.png"
            await page.screenshot(path=scr_path_2)
            print(f"[+] Saved search screenshot to: {scr_path_2}")
        else:
            print("[-] Search input selector 'input.input_search' not found.")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
