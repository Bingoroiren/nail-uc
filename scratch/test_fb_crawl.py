import asyncio
import re
import sys
from playwright.async_api import async_playwright

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

async def test_fb():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Emulating Googlebot user agent allows viewing public Facebook page details without aggressive login redirects
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
            viewport={'width': 1280, 'height': 800}
        )
        page = await context.new_page()
        
        urls = [
            'https://www.facebook.com/dreigsas',
            'https://www.facebook.com/nematekas.lt',
            'https://www.facebook.com/vienoskasniouzkandziai'
        ]
        for url in urls:
            try:
                print(f"[*] Visiting: {url}", flush=True)
                await page.goto(url, timeout=15000, wait_until="commit")
                await asyncio.sleep(4)
                
                # Check for mailto links
                mailto = await page.locator('a[href^="mailto:"]').all()
                found_mailto = []
                for m in mailto:
                    href = await m.get_attribute('href')
                    if href:
                        em = href.replace('mailto:', '').split('?')[0].strip().lower()
                        found_mailto.append(em)
                        
                html = await page.content()
                emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b', html)
                cleaned = [e.lower() for e in set(emails + found_mailto) if not e.endswith(('.png', '.jpg', '.jpeg', '.svg', '.webp')) and 'facebook' not in e.lower() and 'sentry' not in e.lower()]
                
                print(f"[+] Found emails on {url}: {cleaned}", flush=True)
            except Exception as e:
                print(f"[-] Error on {url}: {e}", flush=True)
                
        await browser.close()

if __name__ == '__main__':
    asyncio.run(test_fb())
