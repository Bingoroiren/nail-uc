import sys
import csv
import json
import urllib.parse
from curl_cffi import requests
from bs4 import BeautifulSoup
import time

sys.stdout.reconfigure(encoding='utf-8')

with open('KR_AGCY_SHIP_2COL.csv', 'r', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))[:167]

headers = {
    'Referer': 'https://section.blog.naver.com/Search/Post.naver',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
}

print(f"Bắt đầu thẩm định CHỨNG CỨ THỰC TẾ cho {len(rows)} đơn vị...")

proven_e7_e10 = []
unproven_or_doubtful = []

for idx, r in enumerate(rows, 1):
    c = r['Công ty']
    em = r['Email']
    cat = r['Category']
    
    # 1. Physical shipyard / crewing agencies with verified names:
    if any(k in c for k in ['개미인력개발', '거제중앙인력', '거성기업인력', '광야인력', '조선인력', '해사인', '해율', '더마린', '리스탱 마린', '해인']):
        proven_e7_e10.append({
            'idx': idx, 'comp': c, 'email': em, 'proof': 'Agency nhân lực đóng tàu/hàng hải tại đại bản doanh (Ulsan/Geoje/Yeongam/Busan)'
        })
        continue

    # 2. Check blog contents specifically for E-7, E7, 용접, 선원, 기량검증, e-10
    url = f"https://section.blog.naver.com/ajax/SearchList.naver?countPerPage=5&currentPage=1&keyword={urllib.parse.quote(c)}&type=post"
    try:
        res = requests.get(url, headers=headers, impersonate='chrome120', timeout=6)
        raw_text = res.text
        j_idx = raw_text.find('{')
        if j_idx != -1:
            data = json.loads(raw_text[j_idx:])
            posts = data.get('result', {}).get('searchList', [])
            all_text = " ".join([BeautifulSoup(p.get('title', '') + " " + p.get('contents', ''), 'html.parser').get_text() for p in posts])
            
            # Check positive proof
            has_proof = any(p in all_text for p in [
                'E-7', 'E7', 'e-7', 'e7', 'E-10', 'E10', '용접', '기량검증', '선원', '해무', '조선소', '고용추천서', '특정활동'
            ])
            
            if has_proof:
                # Find matching snippet
                snippet = ""
                for word in ['E-7', 'E7', '용접', '기량검증', '선원', '고용추천서', 'E-10']:
                    if word in all_text:
                        pos = all_text.find(word)
                        snippet = all_text[max(0, pos-20):min(len(all_text), pos+40)].replace('\n', ' ')
                        break
                proven_e7_e10.append({
                    'idx': idx, 'comp': c, 'email': em, 'proof': snippet
                })
            else:
                unproven_or_doubtful.append({
                    'idx': idx, 'comp': c, 'email': em, 'reason': 'Không tìm thấy bài viết nào về E-7/E-10/Hàn tàu/Thuyền viên'
                })
        else:
            unproven_or_doubtful.append({
                'idx': idx, 'comp': c, 'email': em, 'reason': 'Không parse được dữ liệu blog'
            })
    except Exception as e:
        unproven_or_doubtful.append({
            'idx': idx, 'comp': c, 'email': em, 'reason': f'Lỗi kết nối: {e}'
        })
    time.sleep(0.12)

print(f"\n==========================================")
print(f"XÁC MINH CÓ BẰNG CHỨNG E-7/E-10: {len(proven_e7_e10)}")
print(f"NGHI NGỜ / KHÔNG CÓ BẰNG CHỨNG: {len(unproven_or_doubtful)}")
print(f"==========================================")

with open('data/cache/proven_e7_e10.json', 'w', encoding='utf-8') as f:
    json.dump(proven_e7_e10, f, ensure_ascii=False, indent=2)

with open('data/cache/unproven_agencies.json', 'w', encoding='utf-8') as f:
    json.dump(unproven_or_doubtful, f, ensure_ascii=False, indent=2)
