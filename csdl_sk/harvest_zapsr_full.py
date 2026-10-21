# -*- coding: utf-8 -*-
"""
CSDL SK - Module Thu Thap ZAP SR Toan Dien:
Cào toàn bộ hội viên Hiệp hội Ô tô Slovakia (ZAP SR) kèm IČO, Web, SĐT, Địa chỉ:
https://zapsr.sk/o-zvaze/clenovia/
Lưu vào csdl_sk/zapsr_members_master.csv
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
CSV_FILE = OUTPUT_DIR / "zapsr_members_master.csv"

FIELDNAMES = ['Name', 'ICO', 'Detail_URL', 'Web', 'Phone', 'Email', 'Address', 'City', 'PostalCode', 'Category', 'Source']

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

def harvest_zapsr():
    print("[*] Đang cào toàn bộ hội viên ZAP SR...")
    url = 'https://zapsr.sk/o-zvaze/clenovia/'
    records = []
    seen = set()
    try:
        r = requests.get(url, impersonate='chrome120', timeout=20)
        soup = BeautifulSoup(r.text, 'html.parser')
        modals = soup.find_all('div', class_=re.compile(r'member-detail'))
        for m in modals:
            h = m.find(['h3', 'h4', 'h2'], class_=re.compile(r'title|zap-member-title', re.I))
            if not h:
                h = m.find(['h3', 'h4'])
            if not h:
                continue
            cname = h.get_text(strip=True)
            if not cname or cname in seen:
                continue
            seen.add(cname)

            ico = ''
            ico_el = m.find(class_=re.compile(r'member-ico'))
            if ico_el:
                ico_m = re.search(r'\d{6,8}', ico_el.get_text())
                if ico_m:
                    ico = ico_m.group(0)

            web = ''
            link_el = m.find(class_=re.compile(r'member-link'))
            if link_el and link_el.find('a', href=True):
                wh = link_el.find('a')['href']
                web = wh.replace('http://https://', 'https://').strip()

            phone = ''
            phone_el = m.find(class_=re.compile(r'member-phone'))
            if phone_el:
                raw_p = phone_el.get_text().replace('Telefón:', '').replace('Telefon:', '').strip()
                phone = clean_phone(raw_p)

            street = ''
            s_el = m.find(class_=re.compile(r'member-street'))
            if s_el:
                street = s_el.get_text().replace('Ulice:', '').strip()

            psc = ''
            psc_el = m.find(class_=re.compile(r'member-psc'))
            if psc_el:
                psc = psc_el.get_text().replace('PSČ:', '').strip()

            city = ''
            city_el = m.find(class_=re.compile(r'member-city'))
            if city_el:
                city = city_el.get_text().replace('Mesto:', '').strip()

            records.append({
                'Name': cname,
                'ICO': ico,
                'Detail_URL': url,
                'Web': web,
                'Phone': phone,
                'Email': '',
                'Address': street,
                'City': city,
                'PostalCode': psc,
                'Category': 'Zväz automobilového priemyslu SR',
                'Source': 'zapsr.sk'
            })
    except Exception as e:
        print(f"[-] Lỗi cào ZAP SR: {e}")

    with open(CSV_FILE, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(records)

    print(f"[✔] Hoàn tất ZAP SR! Đã lưu {len(records)} hội viên vào: {CSV_FILE}")

if __name__ == '__main__':
    harvest_zapsr()
