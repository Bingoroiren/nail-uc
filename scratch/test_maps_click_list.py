# -*- coding: utf-8 -*-
import asyncio
import os
import sys
from playwright.async_api import async_playwright
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scratch.test_name_match import is_valid_name_match

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, channel="chrome")
        context = await browser.new_context(locale="lt-LT", viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        
        q = "UAB Biovela Lietuva"
        print(f"[+] Tìm: {q}", flush=True)
        url = f"https://www.google.com/maps/search/{q}?hl=lt"
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(4)
        
        # Check consent
        try:
            btn = page.locator('button[aria-label*="Priimti"], button[aria-label*="Atmesti"]')
            if await btn.count() > 0:
                await btn.first.click()
                await asyncio.sleep(2)
        except Exception:
            pass
            
        # If list, click first matching card
        cards = page.locator('a.hfpxzc')
        card_count = await cards.count()
        if card_count > 0:
            print(f"  Thấy {card_count} thẻ. Đang duyệt thẻ khớp...", flush=True)
            for i in range(card_count):
                title = await cards.nth(i).get_attribute('aria-label')
                matched, reason = is_valid_name_match("Biovela", title or "")
                if matched:
                    print(f"  -> Bấm vào thẻ #{i+1}: {title} ({reason})", flush=True)
                    await cards.nth(i).click()
                    await asyncio.sleep(3)
                    break
                    
        # Now read details
        title_elem = page.locator('h1.DUwDvf, h1[class*="fontHeadlineLarge"]')
        if await title_elem.count() > 0:
            title = await title_elem.first.text_content()
            cat_elem = page.locator('button.DkEaL, button[jsaction*="category"], span.DkEaL')
            tag = await cat_elem.first.text_content() if await cat_elem.count() > 0 else ""
            phone_elem = page.locator('button[data-item-id*="phone"]')
            phone = await phone_elem.first.text_content() if await phone_elem.count() > 0 else ""
            web_elem = page.locator('a[data-item-id="authority"]')
            website = await web_elem.first.get_attribute("href") if await web_elem.count() > 0 else ""
            print(f"  CHI TIẾT: Tên: {title} | Tag (LT): {tag} | SĐT: {phone.strip()} | Web: {website}", flush=True)
            
        await browser.close()

if __name__ == '__main__':
    asyncio.run(test())
