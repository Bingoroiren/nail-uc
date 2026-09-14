import asyncio
from playwright.async_api import async_playwright

async def verify_dom():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        page = [pg for pg in context.pages if "firmen.wko.at" in pg.url][0]
        
        data = await page.evaluate("""() => {
            const containers = document.querySelectorAll('.result-container');
            const results = [];
            for (const c of containers) {
                const titleEl = c.querySelector('h2, .title, a[href*="firmaid="]');
                const name = titleEl ? titleEl.innerText.trim() : '';
                
                const linkEl = c.querySelector('a[href*="firmaid="]');
                const url = linkEl ? linkEl.getAttribute('href') : '';
                
                const telEl = c.querySelector('a[href^="tel:"]');
                const phone = telEl ? telEl.getAttribute('href').replace('tel:', '').trim() : '';
                
                const mailEl = c.querySelector('a[href^="mailto:"]');
                const email = mailEl ? mailEl.getAttribute('href').replace('mailto:', '').split('?')[0].trim() : '';
                
                let website = '';
                const extLinks = c.querySelectorAll('a[target="_blank"]');
                for (const a of extLinks) {
                    const h = a.getAttribute('href') || '';
                    if (h.startsWith('http') && !h.includes('wko.at') && !h.includes('google.com')) {
                        website = h;
                        break;
                    }
                }
                
                const text = c.innerText;
                const m = text.match(/(\\d{4}\\s+[A-ZÄÖÜa-zäöüß\\s-]+)/);
                const address = m ? m[1].trim() : '';
                
                if (name) {
                    results.push({name, phone, email, website, address, url});
                }
            }
            return {
                totalContainers: containers.length,
                extractedCount: results.length,
                sample: results.slice(0, 5)
            };
        }""")
        print(f"[+] Total containers: {data['totalContainers']}")
        print(f"[+] Extracted valid companies: {data['extractedCount']}")
        print("\nSample 5:")
        for s in data['sample']:
            print(" ", s)

if __name__ == "__main__":
    asyncio.run(verify_dom())
