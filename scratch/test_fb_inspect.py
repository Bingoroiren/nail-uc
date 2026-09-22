# -*- coding: utf-8 -*-
import asyncio
import re
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=False, channel='chrome')
        page = await b.new_page()
        print("Navigating to https://www.facebook.com/eezyoyj ...")
        await page.goto('https://www.facebook.com/eezyoyj', timeout=25000)
        await asyncio.sleep(4)
        c = await page.content()
        print("Content length:", len(c))
        
        # Check for login modal
        has_login_modal = "login" in c.lower() and "password" in c.lower()
        print("Has login prompt:", has_login_modal)
        
        # Try closing cookie / login banner
        try:
            btns = page.locator('div[aria-label="Close"], div[aria-label="Sulje"], div[role="button"]:has-text("Sulje"), i[data-visualcompletion="css-img"]')
            count = await btns.count()
            print(f"Close buttons found: {count}")
            if count > 0:
                await btns.first.click()
                await asyncio.sleep(1)
        except Exception as e:
            print("Error clicking close:", e)

        # Check for mailto
        mailtos = re.findall(r'mailto:[^\s"\'<>]+', c)
        print("Mailtos:", mailtos)
        
        # Regex for any email
        emails = re.findall(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,7}\b', c)
        valid = [e for e in set(emails) if not e.endswith(('.png', '.jpg', '.webp')) and 'facebook' not in e and 'fb.com' not in e]
        print("Emails on FB:", valid)
        
        await b.close()

if __name__ == '__main__':
    asyncio.run(test())
