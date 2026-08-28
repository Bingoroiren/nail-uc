import requests
import re
from bs4 import BeautifulSoup

# We search for Dongwon Industries (동원산업) homepage
url = "https://html.duckduckgo.com/html/?q=동원산업+홈페이지"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

r = requests.get(url, headers=headers)
soup = BeautifulSoup(r.text, 'html.parser')

print("--- Search Results URLs ---")
for a in soup.find_all('a', class_='result__url'):
    print(a.text.strip())
