import sys
import urllib.parse
from bs4 import BeautifulSoup
from curl_cffi import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

q = "강림중공업 홈페이지"
url = f"https://search.naver.com/search.naver?where=nexearch&query={urllib.parse.quote(q)}"
r = requests.get(url, impersonate="chrome124", timeout=10)
soup = BeautifulSoup(r.text, 'html.parser')

docs = soup.select('div[class*="fds-web-doc-root"]')
print("Found fds-web-doc-root:", len(docs))
if docs:
    for i, d in enumerate(docs[:3]):
        print(f"\n--- Doc {i+1} ---")
        for a in d.find_all('a', href=True):
            print("  Href:", a.get('href'))
            print("  Text:", a.get_text(" ", strip=True)[:50])
            print("  Class:", a.get('class'))
