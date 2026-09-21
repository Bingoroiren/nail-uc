# -*- coding: utf-8 -*-
import asyncio
import sys
from playwright.async_api import async_playwright
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scratch.test_name_match import is_valid_name_match

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

async def test_maps():
    async with async_playwright() as p:
        # Launch visible browser for observation
        browser = await p.chromium.launch(headless=False, channel="chrome")
        context = await browser.new_context(
            locale="lt-LT",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()
        
        test_queries = ["UAB Biovela Lietuva", "UAB Samsonas Lietuva"]
        
        for q in test_queries:
            print(f"\n[+] Đang tìm trên Google Maps: {q}")
            url = f"https://www.google.com/maps/search/{q}?hl=lt"
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(4)
            
            # Handle cookie consent if shown
            try:
                consent_btns = page.locator('button[aria-label*="Priimti"], button[aria-label*="Atmesti"], form[action*="consent"] button')
                if await consent_btns.count() > 0:
                    await consent_btns.first.click()
                    await asyncio.sleep(2)
            except Exception:
                pass
                
            # Check if direct detail or list
            title_elem = page.locator('h1.DUwDvf, h1[class*="fontHeadlineLarge"]')
            if await title_elem.count() > 0:
                title = await title_elem.first.text_content()
                print(f"  [Trang chi tiết] Tên: {title}")
                
                # Tag / Category
                cat_elem = page.locator('button.DkEaL, button[jsaction*="category"], span.DkEaL')
                tag = await cat_elem.first.text_content() if await cat_elem.count() > 0 else ""
                print(f"  Tag ngành nghề (LT): {tag}")
                
                # Phone
                phone_elem = page.locator('button[data-item-id*="phone"]')
                phone = await phone_elem.first.text_content() if await phone_elem.count() > 0 else ""
                print(f"  SĐT: {phone.strip()}")
                
                # Website
                web_elem = page.locator('a[data-item-id="authority"]')
                website = await web_elem.first.get_attribute("href") if await web_elem.count() > 0 else ""
                print(f"  Website: {website}")
            else:
                # List of results
                print("  [Danh sách kết quả]")
                cards = page.locator('a.hfpxzc')
                count = await cards.count()
                print(f"  Tìm thấy {count} kết quả trong danh sách")
                for i in range(min(count, 3)):
                    c_title = await cards.nth(i).get_attribute('aria-label')
                    matched, reason = is_valid_name_match(q.replace(" Lietuva", ""), c_title or "")
                    print(f"    - Kết quả #{i+1}: {c_title} -> Khớp: {matched} ({reason})")
                    
        print("\n[+] Hoàn thành test Google Maps!")
        await asyncio.sleep(3)
        await browser.close()

if __name__ == '__main__':
    asyncio.run(test_maps())
