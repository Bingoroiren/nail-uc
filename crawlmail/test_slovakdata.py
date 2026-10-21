import re
from curl_cffi import requests
import json

with open('data_sample_slovakdata.html', 'r', encoding='utf-8') as f:
    text = f.read()

chunks = re.findall(r'src=["\'](/_next/static/chunks/[^"\']+)["\']', text)
print('Script chunks count:', len(chunks))

api_endpoints = set()
for c in chunks:
    c_url = f"https://slovakdata.sk{c}"
    try:
        r = requests.get(c_url, impersonate='chrome120', timeout=10)
        # Search for api paths in JS
        matches = re.findall(r'["\'](/api/[^"\']+)["\']', r.text)
        for m in matches:
            api_endpoints.add(m)
        # Search for other query endpoints
        queries = re.findall(r'["\'](https?://[^"\']*(?:api|search|vyhladavanie|query)[^"\']*)["\']', r.text)
        for q in queries:
            api_endpoints.add(q)
    except Exception as e:
        print(f"Error fetching chunk {c}: {e}")

print('Discovered API endpoints in JS chunks:')
for ep in sorted(api_endpoints):
    print(" -", ep)
