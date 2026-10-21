# -*- coding: utf-8 -*-
"""
CSDL SK - Module Thu Thap Greenpages Toan Dien (All Pages):
Cào toàn bộ doanh nghiệp ô tô trên Greenpages qua toàn bộ phân trang:
https://greenpages.sk/en/c/automotive-industry.html?page=1, 2, ...
Lưu vào csdl_sk/greenpages_auto_database.csv
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
CSV_FILE = OUTPUT_DIR / "greenpages_auto_database.csv"

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

def harvest_greenpages():
    print("[*] Đang cào toàn bộ danh bạ Greenpages Ô tô...")
    seen = set()
    records = []

    # Check existing
    if CSV_FILE.exists():
        with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                if r.get('Detail_URL'):
                    seen.add(r['Detail_URL'])
    else:
        with open(CSV_FILE, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()

    for p in range(1, 20):
        url = f"https://greenpages.sk/en/c/automotive-industry.html?page={p}"
        try:
            r = requests.get(url, impersonate='chrome120', timeout=15)
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.text, 'html.parser')
            detail_links = []
            for a in soup.find_all('a', href=re.compile(r'/en/r/')):
                href = a['href']
                t = a.get_text(strip=True)
                if t and 'show details' not in t.lower() and href not in seen:
                    detail_links.append((t, href))
                    seen.add(href)

            if not detail_links:
                print(f"[*] Trang {p} không còn công ty mới. Dừng cào Greenpages.")
                break

            print(f"[*] Greenpages Trang {p}: Tìm thấy {len(detail_links)} công ty. Đang bóc tách chi tiết...")
            for cname, durl in detail_links:
                web = ''
                phone = ''
                email = ''
                address = ''
                try:
                    dr = requests.get(durl, impersonate='chrome120', timeout=10)
                    dsoup = BeautifulSoup(dr.text, 'html.parser')
                    for da in dsoup.find_all('a', href=True):
                        h = da['href']
                        if h.startswith('http') and not any(k in h for k in ['greenpages', 'google', 'facebook', 'instagram', 'linkedin', 'twitter', 'sme.sk', 'petitpress']):
                            web = h.rstrip('/')
                            break
                    dp = dsoup.find('a', href=re.compile(r'^tel:'))
                    if dp:
                        phone = clean_phone(dp['href'])
                    dm = dsoup.find('a', href=re.compile(r'^mailto:'))
                    if dm:
                        email = clean_email(dm['href'])
                except Exception:
                    pass

                rec = {
                    'Name': cname,
                    'Detail_URL': durl,
                    'Web': web,
                    'Phone': phone,
                    'Email': email,
                    'Address': address,
                    'Category': 'Automotive Industry',
                    'Source': 'greenpages.sk'
                }
                with open(CSV_FILE, 'a', encoding='utf-8-sig', newline='') as af:
                    w = csv.DictWriter(af, fieldnames=FIELDNAMES)
                    w.writerow(rec)
                print(f"  [+] Greenpages: {cname:<35} | Web: {web[:30]} | SĐT: {phone}")

        except Exception as e:
            print(f"[-] Lỗi cào trang {p}: {e}")

    print(f"[✔] Hoàn tất Greenpages! Tổng số bản ghi lưu trong: {CSV_FILE}")

if __name__ == '__main__':
    harvest_greenpages()
