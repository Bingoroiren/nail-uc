import sys
import os
import json
import re
import requests
import urllib.parse
from bs4 import BeautifulSoup
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

# 1. Fetch all 161 KOSMA member companies
print("Fetching KOSMA member agencies...")
url = 'http://www.kosma.or.kr/selectCompanyInfoList.do'
data = {'PAGE_INDEX': 1, 'PAGE_ROW': 200, 'searchString': ''}
r = requests.post(url, data=data, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
kosma_list = r.json().get('list', [])
print(f"Total KOSMA agencies fetched: {len(kosma_list)}")

# Save to scratch for persistence
with open('scratch/kosma_raw.json', 'w', encoding='utf-8') as f:
    json.dump(kosma_list, f, ensure_ascii=False, indent=2)
print("Saved KOSMA raw list to scratch/kosma_raw.json")
