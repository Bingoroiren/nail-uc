import sys
import os
import re
import requests
import urllib3
from bs4 import BeautifulSoup
import json

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding='utf-8')

headers = {
    'Host': 'www.koswec.or.kr',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
}

all_postings = []
base_ip = 'https://219.253.224.215'

for page in range(1, 20):
    url = f'{base_ip}/koswec/job/marine/selectMarineList.do?pageIndex={page}'
    try:
        r = requests.get(url, headers=headers, verify=False, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        rows = soup.find_all('a', href=True)
        detail_links = [a['href'] for a in rows if 'selectMarineDetail' in a['href']]
        if not detail_links:
            print(f"No detail links on page {page}, stopping.")
            break
        print(f"Page {page}: found {len(detail_links)} postings")
        for link in detail_links:
            full_link = base_ip + link if link.startswith('/') else base_ip + '/' + link
            all_postings.append(full_link)
    except Exception as e:
        print(f"Error page {page}: {e}")
        break

unique_links = list(dict.fromkeys(all_postings))
print(f"Total unique detail links: {len(unique_links)}")

results = []
for idx, link in enumerate(unique_links, 1):
    try:
        r = requests.get(link, headers=headers, verify=False, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        info = {'link': link}
        for tr in soup.find_all('tr'):
            ths = [th.text.strip() for th in tr.find_all('th')]
            tds = [td.text.strip().replace('\n', ' ') for td in tr.find_all('td')]
            for i in range(min(len(ths), len(tds))):
                key = ths[i]
                val = tds[i]
                if key and val:
                    info[key] = val
                    
        full_text = soup.get_text()
        emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', full_text)
        clean_emails = [e for e in emails if not any(j in e.lower() for j in ['sentry', 'wix', 'example', 'domain', 'support@koswec', 'privacy', 'security', 'png', 'jpg'])]
        info['emails'] = list(dict.fromkeys(clean_emails))
        results.append(info)
        comp = info.get('업체명', '')
        contact = info.get('담당자', '')
        print(f"[{idx}/{len(unique_links)}] {comp} | Contact: {contact} | Emails: {info['emails']}")
    except Exception as e:
        print(f"Error detail {link}: {e}")

os.makedirs('data/cache', exist_ok=True)
with open('data/cache/koswec_job_postings.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("Saved KOSWEC postings to data/cache/koswec_job_postings.json")
