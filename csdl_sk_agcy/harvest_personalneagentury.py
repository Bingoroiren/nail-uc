# -*- coding: utf-8 -*-
"""
Harvest personalneagentury.sk
Bóc tách danh sách các công ty môi giới / tuyển dụng nhân sự trên personalneagentury.sk
Lưu trữ vào csdl_sk_agcy/personalneagentury_database.csv
"""

import sys
import re
import csv
from pathlib import Path
from curl_cffi import requests
from bs4 import BeautifulSoup

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

OUTPUT_DIR = Path("D:/glc/nail uc/csdl_sk_agcy")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CSV_FILE = OUTPUT_DIR / "personalneagentury_database.csv"

FIELDNAMES = [
    'Name', 'Address', 'City', 'Phone', 'Email', 'Web', 'Maps_URL', 'Detail_URL', 'Category', 'Source'
]

def clean_phone(p):
    if not p:
        return ''
    raw = re.sub(r'^tel:\s*', '', str(p), flags=re.I).strip()
    digits = re.sub(r'[^\d+]', '', raw)
    if not digits:
        return ''
    clean_d = re.sub(r'[^\d]', '', digits)
    if len(clean_d) < 8 or len(clean_d) > 13:
        return ''
    if clean_d.startswith('421') and len(clean_d) == 12:
        res = f"+421 {clean_d[3:6]} {clean_d[6:9]} {clean_d[9:12]}"
    elif clean_d.startswith('0') and len(clean_d) == 10:
        res = f"+421 {clean_d[1:4]} {clean_d[4:7]} {clean_d[7:10]}"
    else:
        res = f"+{clean_d}" if not digits.startswith('+') else digits
    return f"'{res}" if not res.startswith("'") else res

def clean_email(em):
    if not em:
        return ''
    e = re.sub(r'^mailto:\s*', '', str(em), flags=re.I).strip().lower().rstrip('.,;:')
    if any(k in e for k in ['wix', 'sentry', 'example', 'domain', 'support@', 'no-reply', 'asset', 'image']):
        return ''
    return e

def harvest_personalneagentury():
    print("=" * 70)
    print("[*] BẮT ĐẦU CÀO DỮ LIỆU TỪ: personalneagentury.sk")
    print("=" * 70)

    url = "https://personalneagentury.sk/personalne-agentury?odbor=personalistika-ludske-zdroje"
    try:
        r = requests.get(url, impersonate='chrome120', timeout=20)
        if r.status_code != 200:
            print(f"[-] Lỗi tải trang: HTTP {r.status_code}")
            return
        soup = BeautifulSoup(r.text, 'html.parser')
    except Exception as e:
        print(f"[-] Ngoại lệ khi tải personalneagentury.sk: {e}")
        return

    cards = soup.select('div.flex.flex-1.flex-col.gap-3')
    print(f"[+] Tìm thấy {len(cards)} thẻ doanh nghiệp trên trang.")

    records = []
    seen_names = set()

    for c in cards:
        h = c.find(['h2', 'h3'])
        name = h.get_text(strip=True) if h else ''
        if not name or name.lower() in seen_names:
            continue
        seen_names.add(name.lower())

        address = ''
        city = ''
        maps_url = ''
        web = ''
        email = ''
        phone = ''
        detail_url = ''

        for a in c.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True)
            if 'google.com/maps' in href:
                maps_url = href
                address = text
                # Tách thành phố từ địa chỉ (ví dụ: Mlynské nivy 4959/48, 841 05 Bratislava)
                parts = [p.strip() for p in address.split(',') if p.strip()]
                if len(parts) >= 2:
                    city = parts[-1]
            elif href.startswith('mailto:'):
                email = clean_email(href)
            elif href.startswith('tel:'):
                phone = clean_phone(href)
            elif href.startswith('http') and not any(k in href for k in ['google', 'maps', 'personalneagentury']):
                web = href.rstrip('/')
            elif href.startswith('/personalne-agentury/'):
                detail_url = f"https://personalneagentury.sk{href}"

        # Nếu chưa có web, kiểm tra thêm trong text
        if not web:
            for text_node in c.stripped_strings:
                if text_node.startswith('http://') or text_node.startswith('https://'):
                    if 'google' not in text_node and 'personalneagentury' not in text_node:
                        web = text_node.rstrip('/')
                        break

        rec = {
            'Name': name,
            'Address': address,
            'City': city,
            'Phone': phone,
            'Email': email,
            'Web': web,
            'Maps_URL': maps_url,
            'Detail_URL': detail_url,
            'Category': 'Personálne agentúry a ľudské zdroje',
            'Source': 'personalneagentury.sk'
        }
        records.append(rec)
        print(f"  [+] {name:<35} | Email: {email:<30} | SĐT: {phone}")

    # Ghi ra CSV UTF-8 with BOM
    with open(CSV_FILE, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(records)

    print("\n" + "=" * 70)
    print(f"[✔] HOÀN TẤT CÀO personalneagentury.sk!")
    print(f"[*] Tổng số doanh nghiệp hợp lệ: {len(records)}")
    print(f"[*] Lưu tại: {CSV_FILE}")
    print("=" * 70)

if __name__ == '__main__':
    harvest_personalneagentury()
