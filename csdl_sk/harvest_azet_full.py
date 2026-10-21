# -*- coding: utf-8 -*-
"""
CSDL SK - Module Thu Thap Azet Toan Dien (All Pages):
Cào toàn bộ 2,589+ doanh nghiệp ô tô trên Azet Katalóg qua toàn bộ các trang phân trang:
1. https://www.azet.sk/katalog/vyroba-automobilov-a-autodoplnkov/<page>/ (~104 trang)
2. https://www.azet.sk/katalog/vyroba-osobnych-automobilov/<page>/ (~10 trang)

Lưu tăng dần vào csdl_sk/azet_auto_database.csv để làm tài nguyên làm giàu dữ liệu lâu dài.
"""

import sys
import os
import re
import csv
import time
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
AZET_CSV = OUTPUT_DIR / "azet_auto_database.csv"

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

def harvest_azet_category(base_url, category_name, max_pages=110):
    print(f"\n[*] Bắt đầu cào danh mục: {category_name} ({base_url})...")
    
    seen_details = set()
    if AZET_CSV.exists():
        with open(AZET_CSV, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for r in reader:
                if r.get('Detail_URL'):
                    seen_details.add(r['Detail_URL'])
    else:
        with open(AZET_CSV, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()

    total_harvested = len(seen_details)
    print(f"[*] Đã có sẵn {total_harvested} bản ghi trong CSDL Azet. Đang cào tiếp tục...")

    for p in range(1, max_pages + 1):
        page_url = f"{base_url}{p}/" if p > 1 else base_url
        try:
            r = requests.get(page_url, impersonate='chrome120', timeout=15)
            if r.status_code != 200:
                print(f"    [-] Trang {p} trả về mã {r.status_code}, dừng phân trang danh mục này.")
                break

            soup = BeautifulSoup(r.text, 'html.parser')
            # Tìm tất cả link công ty
            found_on_page = 0
            for a in soup.find_all('a', href=re.compile(r'/firma/\d+/')):
                cname = a.get_text(strip=True)
                if not cname or len(cname) < 4 or any(k in cname.lower() for k in ['hodnotenie', 'kontakt', 'azet']):
                    continue
                if re.search(r'\d{3}\s*\d{2}', cname): # bỏ qua dòng địa chỉ
                    continue
                
                href = a['href']
                full_detail = f"https://www.azet.sk{href}" if href.startswith('/') else href
                if full_detail in seen_details:
                    continue
                seen_details.add(full_detail)
                found_on_page += 1

                # Tìm card ngoài cùng để lấy địa chỉ/web nhanh nếu có
                card = a.find_parent(['div', 'article', 'li'])
                web = ''
                phone = ''
                email = ''
                address = ''
                if card:
                    # tìm địa chỉ
                    addr_link = card.find('a', href=re.compile(r'/firma/\d+/'), string=re.compile(r'\d{3}\s*\d{2}'))
                    if addr_link:
                        address = addr_link.get_text(strip=True)
                    w_tag = card.find('a', href=re.compile(r'^https?://(?!www\.azet|onas\.azet|.*ringier|.*aktuality|.*cas\.sk)'))
                    if w_tag:
                        wh = w_tag['href'].split('?')[0].rstrip('/')
                        if not any(k in wh for k in ['ringier', 'aktuality', 'cas.sk', 'azet']):
                            web = wh
                    p_tag = card.find('a', href=re.compile(r'^tel:'))
                    if p_tag:
                        phone = clean_phone(p_tag['href'])

                # Nếu chưa có web hoặc phone, cào nhanh trang chi tiết
                if not web or not phone:
                    try:
                        dr = requests.get(full_detail, impersonate='chrome120', timeout=10)
                        if dr.status_code == 200:
                            dsoup = BeautifulSoup(dr.text, 'html.parser')
                            if not web:
                                dw = dsoup.find('a', href=re.compile(r'^https?://(?!www\.azet|onas\.azet|prihlasenie\.azet)'))
                                if dw:
                                    web = dw['href'].split('?')[0].rstrip('/')
                            if not phone:
                                dp = dsoup.find('a', href=re.compile(r'^tel:'))
                                if dp:
                                    phone = clean_phone(dp['href'])
                            if not email:
                                dm = dsoup.find('a', href=re.compile(r'^mailto:'))
                                if dm:
                                    email = clean_email(dm['href'])
                    except Exception:
                        pass

                # Lưu tăng dần ngay vào CSV
                rec = {
                    'Name': cname,
                    'Detail_URL': full_detail,
                    'Web': web,
                    'Phone': phone,
                    'Email': email,
                    'Address': address,
                    'Category': category_name,
                    'Source': 'azet.sk'
                }
                with open(AZET_CSV, 'a', encoding='utf-8-sig', newline='') as af:
                    w = csv.DictWriter(af, fieldnames=FIELDNAMES)
                    w.writerow(rec)

                print(f"  [+] Azet P{p:02d}: {cname:<35} | Web: {web[:30]} | SĐT: {phone}")

            if found_on_page == 0:
                print(f"[*] Trang {p} không còn công ty mới, hoàn tất danh mục {category_name}.")
                break
            else:
                print(f"[*] Đã cào trang {p:02d}: +{found_on_page} công ty mới (Tổng CSDL: {len(seen_details):,}).")

        except Exception as e:
            print(f"[-] Lỗi cào trang {p}: {e}")
            time.sleep(2)

    print(f"[✔] Hoàn tất danh mục {category_name}! Tổng số công ty Azet: {len(seen_details):,}")

if __name__ == '__main__':
    harvest_azet_category('https://www.azet.sk/katalog/vyroba-automobilov-a-autodoplnkov/', 'Výroba automobilov a autodoplnkov', max_pages=110)
    harvest_azet_category('https://www.azet.sk/katalog/vyroba-osobnych-automobilov/', 'Výroba osobných automobilov', max_pages=15)
