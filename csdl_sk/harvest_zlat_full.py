# -*- coding: utf-8 -*-
"""
CSDL SK - Module Thu Thap Zlaté Stránky Toàn Diện:
Cào toàn bộ danh bạ ô tô trên Zlaté Stránky qua tất cả các trang:
1. https://www.zlatestranky.sk/firmy/-/q_automobilov%C3%BD+priemysel/ (12 trang)
2. https://www.zlatestranky.sk/firmy/-/q_automobily+-+v%C3%BDroba/ (6 trang)
Lưu vào csdl_sk/zlatestranky_auto_database.csv
"""

import sys
import os
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

OUTPUT_DIR = Path("D:/glc/nail uc/csdl_sk")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CSV_FILE = OUTPUT_DIR / "zlatestranky_auto_database.csv"

FIELDNAMES = ['Name', 'Detail_URL', 'Web', 'Phone', 'Email', 'Address', 'Category', 'Source']

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Z|a-z]{2,10}\b')

def clean_phone(p):
    if not p:
        return ''
    raw = re.sub(r'^tel:\s*', '', str(p), flags=re.I)
    digits = re.sub(r'[^\d+]', '', raw)
    if not digits:
        return ''
    clean_d = re.sub(r'[^\d]', '', digits)
    if len(clean_d) < 9 or len(clean_d) > 13:
        return ''
    if clean_d.startswith('421') and len(clean_d) == 12:
        res = f"+421 {clean_d[3:6]} {clean_d[6:9]} {clean_d[9:12]}"
    elif clean_d.startswith('421') and len(clean_d) == 11:
        res = f"+421 {clean_d[3:5]} {clean_d[5:8]} {clean_d[8:11]}"
    elif clean_d.startswith('0') and len(clean_d) == 10:
        res = f"+421 {clean_d[1:4]} {clean_d[4:7]} {clean_d[7:10]}"
    elif clean_d.startswith('0') and len(clean_d) == 9:
        res = f"+421 {clean_d[1:3]} {clean_d[3:6]} {clean_d[6:9]}"
    else:
        res = f"+{clean_d}" if not digits.startswith('+') else digits
    return f"'{res}" if not res.startswith("'") else res

def clean_email(em):
    if not em:
        return ''
    e = em.replace('mailto:', '').strip().lower().rstrip('.,;:')
    if not EMAIL_REGEX.match(e):
        return ''
    if any(k in e for k in ['wix', 'sentry', 'example', 'domain', 'support@', 'no-reply', 'asset', 'image']):
        return ''
    return e

def harvest_zlatestranky():
    print("[*] Đang cào toàn bộ danh mục Zlaté Stránky Ô tô...")
    categories = [
        ('https://www.zlatestranky.sk/firmy/-/q_automobilov%C3%BD+priemysel/', 12, 'Automobilový priemysel'),
        ('https://www.zlatestranky.sk/firmy/-/q_automobily+-+v%C3%BDroba/', 6, 'Automobily - výroba')
    ]

    seen = set()
    if CSV_FILE.exists():
        with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                if r.get('Detail_URL'):
                    seen.add(r['Detail_URL'])
    else:
        with open(CSV_FILE, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()

    for base_url, max_p, cat_name in categories:
        for p in range(1, max_p + 1):
            url = f"{base_url}{p}/"
            try:
                r = requests.get(url, impersonate='chrome120', timeout=15)
                if r.status_code != 200:
                    break
                soup = BeautifulSoup(r.text, 'html.parser')
                items = soup.find_all(class_=re.compile(r'\brd-item\b'))
                for it in items:
                    h2 = it.find('h2')
                    if not h2:
                        continue
                    a_title = h2.find('a')
                    cname = a_title.get_text(strip=True) if a_title else h2.get_text(strip=True)
                    if not cname:
                        continue
                    
                    detail_href = a_title['href'] if a_title and a_title.get('href') else ''
                    full_detail = f"https://www.zlatestranky.sk{detail_href}" if detail_href.startswith('/') else detail_href
                    if full_detail and full_detail in seen:
                        continue
                    if full_detail:
                        seen.add(full_detail)

                    p_tag = it.find('a', href=re.compile(r'^tel:'))
                    phone = clean_phone(p_tag['href']) if p_tag else ''

                    m_tag = it.find('a', href=re.compile(r'^mailto:'))
                    email = clean_email(m_tag['href']) if m_tag else ''

                    web = ''
                    for a in it.find_all('a', href=True):
                        href = a['href']
                        if href.startswith('http') and not any(k in href for k in ['zlatestranky.sk', 'google', 'facebook', 'instagram', 'twitter']):
                            web = href.rstrip('/')
                            break

                    rec = {
                        'Name': cname,
                        'Detail_URL': full_detail,
                        'Web': web,
                        'Phone': phone,
                        'Email': email,
                        'Address': '',
                        'Category': cat_name,
                        'Source': 'zlatestranky.sk'
                    }
                    with open(CSV_FILE, 'a', encoding='utf-8-sig', newline='') as af:
                        w = csv.DictWriter(af, fieldnames=FIELDNAMES)
                        w.writerow(rec)

                    print(f"  [+] Zlate Stranky: {cname:<35} | Web: {web[:30]} | SĐT: {phone}")

            except Exception as e:
                print(f"[-] Lỗi cào trang {p}: {e}")

    print(f"[✔] Hoàn tất Zlaté Stránky! Tổng số bản ghi: {len(seen):,}")

if __name__ == '__main__':
    harvest_zlatestranky()
