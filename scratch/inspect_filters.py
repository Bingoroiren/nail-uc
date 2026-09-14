import asyncio
from playwright.async_api import async_playwright

async def inspect_filters():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        page = [pg for pg in context.pages if "firmen.wko.at" in pg.url][0]
        
        filter_data = await page.evaluate("""() => {
            const filterBtn = document.querySelector('.search-filter, [data-target*="filter"], .btn-filter') || Array.from(document.querySelectorAll('button, a')).find(el => el.innerText && el.innerText.trim() === 'Filter');
            
            // Check all links with state names or filter URLs
            const allLinks = Array.from(document.querySelectorAll('a')).map(a => ({
                text: a.innerText.trim(),
                href: a.getAttribute('href')
            })).filter(x => x.href && (
                x.href.includes('wien') || 
                x.href.includes('niederoesterreich') || 
                x.href.includes('oberoesterreich') || 
                x.href.includes('steiermark') || 
                x.href.includes('tirol') || 
                x.href.includes('salzburg') || 
                x.href.includes('kaernten') || 
                x.href.includes('vorarlberg') || 
                x.href.includes('burgenland') ||
                x.href.includes('filter')
            ));
            
            return {
                filterBtn: filterBtn ? filterBtn.outerHTML : null,
                stateLinks: allLinks
            };
        }""")
        print("[*] Filter Info:", filter_data)

if __name__ == "__main__":
    asyncio.run(inspect_filters())
