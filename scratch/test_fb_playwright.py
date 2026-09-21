# -*- coding: utf-8 -*-
import asyncio
import re
import sys
from playwright.async_api import async_playwright

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,7}\b')

async def test_fb_pw():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, channel="chrome")
        context = await browser.new_context(locale="lt-LT")
        page = await context.new_page()
        
        fb_url = "https://www.facebook.com/biovela.lt/"
        print(f"[+] Navigating to {fb_url} in visible Chrome...")
        await page.goto(fb_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(4)
        
        # Close login banner if any
        try:
            close_btn = page.locator('div[aria-label="Uždaryti"], div[aria-label="Close"], i[data-visualcompletion="css-img"]')
            if await close_btn.count() > 0:
                await close_btn.first.click()
                await asyncio.sleep(1)
        except Exception:
            pass
            
        content = await page.content()
        emails = set(EMAIL_REGEX.findall(content))
        valid = [e for e in emails if not e.endswith(('.png', '.jpg', '.webp', '.svg')) and 'facebook' not in e and 'fb.com' not in e]
        print("  Emails found on Facebook page:", valid)
        await asyncio.sleep(2)
        await browser.close()

if __name__ == '__main__':
    asyncio.run(test_fb_pw())
