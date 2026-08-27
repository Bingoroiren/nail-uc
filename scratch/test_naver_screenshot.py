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
        
        query = "서울 강남구 파견"
        url = f"https://map.naver.com/p/search/{urllib.parse.quote(query)}"
        print(f"[*] Navigating to: {url}")
        
        await page.goto(url, wait_until="commit")
        print("[*] Waiting 10 seconds for frames to load...")
        await page.wait_for_timeout(10000)
        
        # Log all frames
        print("\n--- Available Frames ---")
        frames = page.frames
        for idx, f in enumerate(frames):
            print(f"Frame {idx}: name='{f.name}', url='{f.url}'")
            
        # Check if searchIframe selector exists
        search_iframe_exists = await page.locator("#searchIframe").count() > 0
        print(f"\n[*] Selector '#searchIframe' exists on main page: {search_iframe_exists}")
        
        # Save screenshot
        scr_path = r"C:\Users\Admin\.gemini\antigravity-ide\brain\f1cd8f96-441a-435a-9265-9c17ea67161b\scratch\naver_test.png"
        os.makedirs(os.path.dirname(scr_path), exist_ok=True)
        await page.screenshot(path=scr_path)
        print(f"[+] Saved screenshot to: {scr_path}")
        
        await browser.close()

import urllib.parse
if __name__ == "__main__":
    asyncio.run(main())
