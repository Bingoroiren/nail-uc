import asyncio
import sys
import codecs
from playwright.async_api import async_playwright

if sys.platform.startswith('win') and hasattr(sys.stdout, 'buffer'):
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

KEYWORDS = [
    ("arbeitskr%c3%a4fte%c3%bcberlassung", "Arbeitskräfteüberlassung"),
    ("personalbereitstellung", "Personalbereitstellung"),
    ("personalleasing", "Personalleasing"),
    ("zeitarbeit", "Zeitarbeit"),
    ("leiharbeit", "Leiharbeit")
]

REGIONS = [
    ("", "Toàn quốc"),
    ("wien", "Wien"),
    ("nieder%C3%B6sterreich", "Niederösterreich"),
    ("ober%C3%B6sterreich", "Oberösterreich"),
    ("steiermark", "Steiermark"),
    ("tirol", "Tirol"),
    ("salzburg", "Salzburg"),
    ("k%C3%A4rnten", "Kärnten"),
    ("vorarlberg", "Vorarlberg"),
    ("burgenland", "Burgenland")
]

async def scan():
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            page = browser.contexts[0].pages[1]
        except Exception:
            b = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
            page = await b.new_page()
            
        all_unique = {}
        
        for kw, kw_label in KEYWORDS:
            for reg, reg_label in REGIONS:
                url = f"https://firmen.wko.at/{kw}/{reg}/" if reg else f"https://firmen.wko.at/{kw}/"
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    await page.wait_for_timeout(600)
                    
                    # Extract cards
                    cards = await page.evaluate("""() => {
                        const containers = document.querySelectorAll('.result-container');
                        const res = [];
                        for (const c of containers) {
                            const a = c.querySelector('a[href*="firmaid="]');
                            if (a) {
                                res.push({
                                    name: a.innerText.trim(),
                                    url: a.getAttribute('href')
                                });
                            }
                        }
                        return res;
                    }""")
                    
                    added = 0
                    for c in cards:
                        u = c['url']
                        if u not in all_unique:
                            all_unique[u] = c['name']
                            added += 1
                            
                    print(f"[{kw_label} - {reg_label}] -> Found {len(cards)} on page (+{added} new). Total Unique: {len(all_unique)}")
                    if len(all_unique) >= 1200:
                        break
                except Exception as e:
                    print(f"[-] Error {url}: {e}")
            if len(all_unique) >= 1200:
                break
                
        print(f"\n==========================================")
        print(f"[SUCCESS] Total unique companies discovered: {len(all_unique)}")
        print(f"==========================================")

if __name__ == "__main__":
    asyncio.run(scan())
