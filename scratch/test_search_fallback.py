# -*- coding: utf-8 -*-
import asyncio
import sys
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

async def test_search():
    query = '"Samsonas" Lietuva kontaktai'
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36"}
    
    # 1. DuckDuckGo HTML
    print("[1] Test DuckDuckGo:")
    try:
        async with AsyncSession(impersonate='chrome124') as s:
            r = await s.get(f"https://html.duckduckgo.com/html/?q={query}", timeout=8)
            print("  Status:", r.status_code)
            soup = BeautifulSoup(r.text, 'html.parser')
            results = soup.find_all('a', class_='result__url')
            for a in results[:3]:
                print("  - DDG:", a.get_text(strip=True))
    except Exception as e:
        print("  DDG error:", e)

    # 2. Bing Search
    print("\n[2] Test Bing Search:")
    try:
        async with AsyncSession(impersonate='chrome124') as s:
            r = await s.get(f"https://www.bing.com/search?q={query}", timeout=8)
            print("  Status:", r.status_code)
            soup = BeautifulSoup(r.text, 'html.parser')
            results = soup.find_all('li', class_='b_algo')
            for li in results[:3]:
                h2 = li.find('h2')
                cite = li.find('cite')
                t = h2.get_text(strip=True) if h2 else ""
                c = cite.get_text(strip=True) if cite else ""
                print(f"  - Bing: {t} -> {c}")
    except Exception as e:
        print("  Bing error:", e)

if __name__ == '__main__':
    asyncio.run(test_search())
