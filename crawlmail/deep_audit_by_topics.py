import sys
import os
import csv
import json
import urllib.parse
from curl_cffi import requests
from bs4 import BeautifulSoup
import time

sys.stdout.reconfigure(encoding='utf-8')

with open('KR_AGCY_SHIP_2COL.csv', 'r', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))[:189]

headers = {
    'Referer': 'https://section.blog.naver.com/Search/Post.naver',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
}

flagged_to_purge = []

# Keywords that definitely prove it's NOT a shipyard welder / seafarer agency:
BAD_TOPIC_WORDS = [
    '농가', '농업', '소프트웨어', '조달', '사단법인', '비영리', '가정폭력', '음주운전',
    '영업정지', '토지', '보상', '유치원', '어린이집', 'd-2', 'd-4', 'd-10', 'd2',
    'd4', 'd10', '유학생', '어학연수', '학폭', '체불', '손해배상'
]

print(f"Auditing blog topics for {len(rows)} agencies...")

for idx, r in enumerate(rows, 1):
    c = r['Công ty']
    em = r['Email']
    cat = r['Category']
    
    # If the category is explicitly Seafarer or Shipyard Manpower (from KOSMA or physical shipyard regions), it's safe
    if any(k in c for k in ['개미인력', '거제중앙', '거성기업인력', '광야인력', '조선인력', '해사인', '해율', '더마린', '리스탱 마린', '해인']):
        continue
        
    url = f"https://section.blog.naver.com/ajax/SearchList.naver?countPerPage=3&currentPage=1&keyword={urllib.parse.quote(c)}&type=post"
    try:
        res = requests.get(url, headers=headers, impersonate='chrome120', timeout=6)
        raw_text = res.text
        j_idx = raw_text.find('{')
        if j_idx != -1:
            data = json.loads(raw_text[j_idx:])
            posts = data.get('result', {}).get('searchList', [])
            if posts:
                titles = " ".join([BeautifulSoup(p.get('title', ''), 'html.parser').get_text().strip() for p in posts]).lower()
                matched_bad = [bw for bw in BAD_TOPIC_WORDS if bw in titles]
                if matched_bad:
                    flagged_to_purge.append((idx, c, em, f"Matched bad topic: {', '.join(matched_bad)}", titles[:60]))
                    print(f"  [X] #{idx} {c} | {em} | Bad: {matched_bad}")
    except Exception as e:
        pass
    time.sleep(0.15)

print(f"\nTotal flagged to purge in topic audit: {len(flagged_to_purge)}")
with open('data/cache/flagged_topic_purge.json', 'w', encoding='utf-8') as f:
    json.dump(flagged_to_purge, f, ensure_ascii=False, indent=2)
