# -*- coding: utf-8 -*-
"""
Harvest Greenpages.sk Employment Agencies:
Bóc tách toàn diện các công ty môi giới lao động / tuyển dụng nhân sự trên Greenpages.sk
qua các danh mục:
1. agentury-docasneho-zamestnavania (Dočasné zamestnávanie)
2. personalne-agentury (Personálne agentúry)
3. executive-search-spolocnosti (Executive Search)
4. poradenske-firmy-ludsky-kapital (Ľudský kapitál)

Lưu trữ vào csdl_sk_agcy/greenpages_agcy_database.csv
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

OUTPUT_DIR = Path("D:/glc/nail uc/csdl_sk_agcy")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CSV_FILE = OUTPUT_DIR / "greenpages_agcy_database.csv"

FIELDNAMES = [
    'Name', 'Address', 'City', 'Postal_Code', 'Phone', 'Email', 'Web', 'Director', 'Category', 'Detail_URL', 'Source'
]

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Z|a-z]{2,10}\b')

CATEGORIES = [
    ('agentury-docasneho-zamestnavania', 'Agentúry dočasného zamestnávania'),
    ('personalne-agentury', 'Personálne agentúry'),
    ('executive-search-spolocnosti', 'Executive Search spoločnosti'),
    ('poradenske-firmy-ludsky-kapital', 'Poradenské firmy - Ľudský kapitál')
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
    elif clean_d.startswith('421') and len(clean_d) == 11:
        res = f"+421 {clean_d[3:5]} {clean_d[5:8]} {clean_d[8:11]}"
    elif clean_d.startswith('0') and len(clean_d) == 10:
        res = f"+421 {clean_d[1:4]} {clean_d[4:7]} {clean_d[7:10]}"
    else:
        res = f"+{clean_d}" if not digits.startswith('+') else digits
    return f"'{res}" if not res.startswith("'") else res

def clean_email(em):
    if not em:
        return ''
    e = re.sub(r'^mailto:\s*', '', str(em), flags=re.I).strip().lower().rstrip('.,;:')
    if not EMAIL_REGEX.match(e):
        return ''
    if any(k in e for k in ['wix', 'sentry', 'example', 'domain', 'support@', 'no-reply', 'asset', 'image']):
        return ''
    return e

def harvest_greenpages():
    print("=" * 70)
    print("[*] BẮT ĐẦU CÀO DỮ LIỆU TỪ: greenpages.sk (MÔI GIỚI LAO ĐỘNG)")
    print("=" * 70)

    seen_links = set()
    records = []

    for cat_slug, cat_title in CATEGORIES:
        print(f"\n[*] Đang quét danh mục: {cat_title} ({cat_slug})...")
        p = 1
        cat_count = 0

        while True:
            url = f"https://greenpages.sk/sk/c/{cat_slug}.html?page={p}"
            try:
                r = requests.get(url, impersonate='chrome120', timeout=15)
                if r.status_code != 200:
                    break
                soup = BeautifulSoup(r.text, 'html.parser')
                links = []
                for a in soup.find_all('a', href=re.compile(r'/sk/r/')):
                    t = a.get_text(strip=True)
                    if t and 'show details' not in t.lower() and a['href'] not in seen_links:
                        links.append((t, a['href']))
                        seen_links.add(a['href'])

                if not links:
                    break

                for cname, durl in links:
                    name = cname
                    street = ''
                    postal = ''
                    city = ''
                    phone = ''
                    email = ''
                    web = ''
                    director = ''

                    try:
                        dr = requests.get(durl, impersonate='chrome120', timeout=10)
                        if dr.status_code == 200:
                            dsoup = BeautifulSoup(dr.text, 'html.parser')
                            holder = dsoup.find('div', class_='company-holder')
                            
                            if holder:
                                h1 = holder.find('h1')
                                if h1:
                                    name = h1.get_text(strip=True)
                                
                                st_el = holder.find('span', itemprop='streetAddress')
                                if st_el:
                                    street = st_el.get_text(strip=True)
                                    
                                pc_el = holder.find('span', itemprop='postalCode')
                                if pc_el:
                                    postal = pc_el.get_text(strip=True)
                                    
                                loc_el = holder.find('span', itemprop='addressLocality')
                                if loc_el:
                                    city = loc_el.get_text(strip=True)
                                    
                                tel_el = holder.find('span', itemprop='telephone')
                                if tel_el:
                                    phone = clean_phone(tel_el.get_text(strip=True))
                                    
                                em_el = holder.find('span', itemprop='email')
                                if em_el:
                                    email = clean_email(em_el.get_text(strip=True))
                                
                                # Web
                                for wa in holder.find_all('a', href=True):
                                    whref = wa['href']
                                    if whref.startswith('http') and not any(k in whref for k in ['greenpages', 'sme.sk', 'petitpress', 'facebook', 'twitter', 'linkedin', 'google']):
                                        web = whref.rstrip('/')
                                        break
                                
                            # Fallback qua text toàn trang nếu thiếu
                            full_text = dsoup.get_text(separator=' \n ', strip=True)
                            if not email:
                                em_match = re.search(r'Email:\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', full_text)
                                if em_match:
                                    email = clean_email(em_match.group(1))
                            if not phone:
                                tel_match = re.search(r'Tel:\s*([+\d\s/]+)', full_text)
                                if tel_match:
                                    phone = clean_phone(tel_match.group(1))
                            if not web:
                                web_match = re.search(r'Web:\s*([a-zA-Z0-9.\-]+\.[a-z]{2,}[^\s\n]*)', full_text)
                                if web_match:
                                    wb = web_match.group(1).strip()
                                    if not wb.startswith('http'):
                                        wb = f"http://{wb}"
                                    web = wb
                            
                            dir_match = re.search(r'(?:Výkonný riaditeľ|Riaditeľ|Konateľ|Managing Director):\s*([^\n\r,]+)', full_text)
                            if dir_match:
                                director = dir_match.group(1).strip()

                    except Exception as err:
                        pass

                    full_address = f"{street}, {postal} {city}".strip(', ')

                    rec = {
                        'Name': name,
                        'Address': full_address,
                        'City': city,
                        'Postal_Code': postal,
                        'Phone': phone,
                        'Email': email,
                        'Web': web,
                        'Director': director,
                        'Category': cat_title,
                        'Detail_URL': durl,
                        'Source': 'greenpages.sk'
                    }
                    records.append(rec)
                    cat_count += 1
                    print(f"  [+] {name:<35} | Email: {email:<25} | SĐT: {phone}")

                p += 1

            except Exception as e:
                print(f"[-] Lỗi tải trang {p} danh mục {cat_slug}: {e}")
                break

        print(f"  -> Hoàn thành danh mục {cat_title}: {cat_count} doanh nghiệp.")

    # Ghi file CSV
    with open(CSV_FILE, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(records)

    print("\n" + "=" * 70)
    print(f"[✔] HOÀN TẤT CÀO greenpages.sk!")
    print(f"[*] Tổng số doanh nghiệp bóc tách: {len(records)}")
    print(f"[*] Lưu tại: {CSV_FILE}")
    print("=" * 70)

if __name__ == '__main__':
    harvest_greenpages()
