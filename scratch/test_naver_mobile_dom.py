import asyncio
import sys
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# Set console output encoding to UTF-8 to prevent print errors
if sys.platform.startswith('win'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 14_8 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1",
            viewport={"width": 375, "height": 812},
            locale="ko-KR",
            extra_http_headers={"Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"}
        )
        page = await context.new_page()
        await stealth_async(page)
        
        query = "서울 강남구 파견"
        url = f"https://m.map.naver.com/search2/search.naver?query={urllib.parse.quote(query)}"
        print(f"[*] Navigating to: {url}")
        
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(3000)
        
        # Find all result list items (usually 'li' elements)
        # We can look for list items by class or tag
        items = await page.locator("ul.lst_site > li, #search_result_list > li, li").all()
        print(f"[+] Found {len(items)} raw li items.")
        
        parsed_count = 0
        for idx, item in enumerate(items):
            # Check if this li looks like a place card
            # A place card usually has a title element
            title_el = item.locator("a.a_item_title, a.search_title, a.title, .tit a, a").first
            if await title_el.count() > 0:
                title = await title_el.inner_text()
                title = title.strip()
                if not title:
                    continue
                    
                # Let's inspect the HTML of this item
                html = await item.inner_html()
                
                # Check for category
                category = ""
                cat_el = item.locator("span.category, .cate, span.cate").first
                if await cat_el.count() > 0:
                    category = await cat_el.inner_text()
                    category = category.strip()
                
                # Check for address
                address = ""
                addr_el = item.locator("p.addr, .address, .addr").first
                if await addr_el.count() > 0:
                    address = await addr_el.inner_text()
                    address = address.strip()
                    
                # Check for phone
                phone = ""
                # Phone is often in a button with a data-tel attribute or a link with tel:
                tel_link = item.locator("a[href^='tel:']").first
                if await tel_link.count() > 0:
                    phone = await tel_link.get_attribute("href")
                    phone = phone.replace("tel:", "").strip()
                else:
                    # Check for data-phone or data-tel attributes
                    tel_btn = item.locator("a[data-tel], button[data-tel], a[data-phone]").first
                    if await tel_btn.count() > 0:
                        phone = await tel_btn.get_attribute("data-tel") or await tel_btn.get_attribute("data-phone")
                
                # Check if there is a website button
                website = ""
                web_link = item.locator("a.btn_homepage, a[href*='http']").first
                if await web_link.count() > 0:
                    website = await web_link.get_attribute("href")
                
                print(f"\n--- Item {parsed_count + 1} ---")
                print(f"Title: {title}")
                print(f"Category: {category}")
                print(f"Address: {address}")
                print(f"Phone: {phone}")
                print(f"Website: {website}")
                print(f"Raw HTML Snippet: {html[:400]}")
                
                parsed_count += 1
                if parsed_count >= 5:
                    break
                    
        await browser.close()

import urllib.parse
if __name__ == "__main__":
    asyncio.run(main())
