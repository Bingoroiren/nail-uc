from curl_cffi import requests
import re
import json

url = "https://www.proff.no/bransjes%C3%B8k?q=Arbeidskrafttjenester&page=2"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "no,nb,nn,en-US,en;q=0.9",
}

r = requests.get(url, headers=headers, impersonate="chrome124", timeout=30)
m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.DOTALL)
if m:
    data = json.loads(m.group(1))
    comp_store = data['props']['pageProps']['hydrationData']['searchStore']['companies']
    companies = comp_store.get('companies', [])
    print(f"Page 2: count = {len(companies)}")
    print(f"First company on page 2: {companies[0].get('name')}")
    print(f"Website: {companies[0].get('homePage')}")
    print(f"Email: {companies[0].get('email')}")
    print(f"Phone: {companies[0].get('phone')}")
else:
    print("Failed to find __NEXT_DATA__ on page 2")
