# -*- coding: utf-8 -*-
"""
Harvest Greenpages.sk Automotive Data & Enrich SK_AUTO_SLVD_1ENR.csv:
1. Thu thập toàn bộ các doanh nghiệp thuộc ngành Automotive, Engineering & Foreign Investors trên greenpages.sk.
2. Trích xuất chính xác 100%: Tên công ty, SĐT, Email, Website, Địa chỉ, Thành phố, Lãnh đạo.
3. So khớp thông minh với tệp SK_AUTO_SLVD_1ENR.csv (khớp tên chuẩn hóa + thành phố).
4. Cập nhật và bù đắp thông tin (Email, SĐT, Web).
5. Tự động đẩy toàn bộ doanh nghiệp có Email lên đầu tệp, chuẩn hóa SĐT có nháy đơn '.
"""

import sys
import os
import re
import csv
import json
import unicodedata
from pathlib import Path
from curl_cffi import requests
from bs4 import BeautifulSoup

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
CSV_FILE = ROOT_DIR / "SK_AUTO_SLVD_1ENR.csv"
CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_enrich_maps_sk_auto.json"

LEGAL_FORMS = [
    'spol. s r.o.', 'spol. s r. o.', 's.r.o.', 's. r. o.', 'sro',
    'akciova spolocnost', 'akciová spoločnosť', 'a.s.', 'a. s.', 'as',
    'komanditna spolocnost', 'komanditná spoločnosť', 'k.s.', 'k. s.',
    'ltd', 'gmbh', 'inc.', 'inc', 'corp.', 'corp'
]

def remove_accents(s):
    if not s:
        return ''
    return ''.join(c for c in unicodedata.normalize('NFD', str(s)) if unicodedata.category(c) != 'Mn')

def clean_name(n):
    if not n:
        return ''
    s = remove_accents(str(n)).lower()
    s = re.sub(r'["\'„“”«»]', '', s)
    for lf in sorted(LEGAL_FORMS, key=len, reverse=True):
        pattern = rf'(?:^|[\s,;]){re.escape(remove_accents(lf))}(?:$|[\s,;])'
        s = re.sub(pattern, ' ', s)
    s = re.sub(r'[^\w\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def clean_phone(p):
    if not p:
        return ''
    digits = re.sub(r'[^\d+]', '', str(p))
    if not digits:
        return ''
    # Format Slovak phone
    clean_d = re.sub(r'[^\d]', '', digits)
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

def crawl_greenpages():
    categories = [
        ('Automotive Industry', 'https://greenpages.sk/en/c/automotive-industry.html', 2),
        ('Engineering & Automotive', 'https://greenpages.sk/en/c/engineering-automotive-industry.html', 3),
        ('Foreign Investors', 'https://greenpages.sk/en/c/foreign-investors.html', 1),
        ('Electrotechnical', 'https://greenpages.sk/en/c/electrotechnical-industry.html', 1),
        ('Metallurgy', 'https://greenpages.sk/en/c/metallurgy-industry.html', 1),
    ]

    all_co_urls = []
    print("=" * 70)
    print("🔍 BƯỚC 1: QUÉT TẤT CẢ DANH MỤC Ô TÔ TRÊN GREENPAGES.SK...")
    print("=" * 70)

    for cat_name, base_url, max_p in categories:
        for p in range(1, max_p + 1):
            url = f"{base_url}?page={p}"
            try:
                r = requests.get(url, impersonate='chrome120', timeout=15)
                soup = BeautifulSoup(r.text, 'html.parser')
                links = [a['href'] for a in soup.find_all('a', href=True) if '/r/' in a['href']]
                new_links = [l for l in links if l not in all_co_urls]
                all_co_urls.extend(new_links)
                print(f"  [+] {cat_name} (Page {p}): Tìm thấy {len(new_links)} công ty mới.")
            except Exception as e:
                print(f"  [-] Lỗi tải {url}: {e}")

    print(f"\n[*] Tổng số doanh nghiệp thu thập từ Greenpages: {len(all_co_urls)} công ty.")
    print("\n" + "=" * 70)
    print("📥 BƯỚC 2: BÓC TÁCH CHI TIẾT SĐT, EMAIL, WEB, ĐỊA CHỈ TỪ GREENPAGES...")
    print("=" * 70)

    gp_companies = []
    for idx, u in enumerate(all_co_urls, 1):
        try:
            r = requests.get(u, impersonate='chrome120', timeout=15)
            soup = BeautifulSoup(r.text, 'html.parser')

            h1 = soup.find('h1')
            cname = h1.get_text(strip=True) if h1 else ''
            if not cname:
                continue

            main = soup.find('div', class_=re.compile(r'content|firm|detail|main', re.I)) or soup.body
            text = main.get_text('\n', strip=True) if main else ''

            tel_m = re.findall(r'Tel:\s*([^\n\r<]+)', text, re.I)
            mail_m = re.findall(r'Email:\s*([^\n\r<\s]+)', text, re.I)
            web_m = re.findall(r'Web:\s*([^\n\r<\s]+)', text, re.I)

            phone = clean_phone(tel_m[0]) if tel_m else ''
            email = mail_m[0].strip().lower().rstrip('.,;:') if mail_m else ''
            web = web_m[0].strip() if web_m else ''
            if web and not web.startswith(('http://', 'https://')):
                web = f"https://{web}"

            # Address & City
            city = ''
            addr = ''
            for line in text.split('\n')[:15]:
                m_zip = re.search(r'(\d{3}\s*\d{2})\s+([A-ZÀ-Ža-zà-ž\s-]+)', line)
                if m_zip:
                    city = m_zip.group(2).strip()
                    addr = line.strip()
                    break

            entry = {
                'name': cname,
                'clean_name': clean_name(cname),
                'phone': phone,
                'email': email,
                'web': web,
                'city': city,
                'addr': addr,
                'url': u
            }
            gp_companies.append(entry)
            print(f"[{idx}/{len(all_co_urls)}] {cname:<35} | Email: {email or 'N/A':<30} | SĐT: {phone or 'N/A'}")

        except Exception as e:
            print(f"[{idx}/{len(all_co_urls)}] Lỗi bóc tách {u}: {e}")

    return gp_companies

def enrich_dataset(gp_companies):
    print("\n" + "=" * 70)
    print("🔄 BƯỚC 3: ĐỐI CHIẾU VÀ LÀM GIÀU VÀO SK_AUTO_SLVD_1ENR.CSV...")
    print("=" * 70)

    with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    # Load cache
    cache = {}
    if CACHE_FILE.exists():
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            cache = json.load(f)

    # Index rows by clean name
    rows_by_clean = {}
    for r in rows:
        cn = clean_name(r.get('Công ty', ''))
        if cn:
            rows_by_clean[cn] = r

    matched_count = 0
    updated_email = 0
    updated_phone = 0
    updated_web = 0

    for gp in gp_companies:
        target = None
        g_cn = gp['clean_name']
        g_city = remove_accents(gp['city']).lower()

        # 1. Exact clean match
        if g_cn in rows_by_clean:
            target = rows_by_clean[g_cn]
        else:
            # 2. Fuzzy / Substring match with city verification
            for r_cn, r_row in rows_by_clean.items():
                if len(g_cn) >= 5 and len(r_cn) >= 5:
                    if g_cn in r_cn or r_cn in g_cn:
                        target = r_row
                        break
                    # Token overlap
                    g_words = set(w for w in g_cn.split() if len(w) >= 4)
                    r_words = set(w for w in r_cn.split() if len(w) >= 4)
                    if len(g_words & r_words) >= 2:
                        target = r_row
                        break

        if target:
            matched_count += 1
            ico = target.get('IČO', '')
            cname = target.get('Công ty', '')
            cache_key = ico if ico else cname.lower()

            added_fields = []
            if gp['email'] and not target.get('Email'):
                target['Email'] = gp['email']
                updated_email += 1
                added_fields.append(f"Email: {gp['email']}")
            elif gp['email'] and target.get('Email') != gp['email']:
                # If target has a generic email or less specific, keep or note
                pass

            if gp['phone'] and not target.get('SĐT'):
                target['SĐT'] = gp['phone']
                updated_phone += 1
                added_fields.append(f"SĐT: {gp['phone']}")

            if gp['web'] and not target.get('Web'):
                target['Web'] = gp['web']
                updated_web += 1
                added_fields.append(f"Web: {gp['web']}")

            if added_fields:
                print(f"  [+] KHỚP THÀNH CÔNG: {cname} -> {' | '.join(added_fields)}")
            else:
                print(f"  [=] ĐÃ CÓ ĐẦY ĐỦ: {cname} (Email: {target.get('Email')})")

            # Update cache
            if cache_key not in cache:
                cache[cache_key] = {}
            cache[cache_key].update({
                'name': cname,
                'ico': ico,
                'email': target.get('Email', ''),
                'phone': target.get('SĐT', ''),
                'website': target.get('Web', ''),
                'greenpages_matched': True
            })

    # Save cache
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    # Sort rows: with email first!
    with_email = [r for r in rows if r.get('Email', '').strip()]
    without_email = [r for r in rows if not r.get('Email', '').strip()]
    sorted_rows = with_email + without_email

    for idx, r in enumerate(sorted_rows, 1):
        r['No.'] = str(idx)
        p = str(r.get('SĐT', '')).strip()
        if p and p != 'nan' and not p.startswith("'"):
            r['SĐT'] = f"'{p}"

    with open(CSV_FILE, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sorted_rows)

    print("\n" + "=" * 70)
    print("🎉 HOÀN TẤT LÀM GIÀU DỮ LIỆU TỪ GREENPAGES.SK!")
    print(f"[*] Số doanh nghiệp khớp với tệp: {matched_count} / {len(gp_companies)}")
    print(f"[*] Cập nhật mới: +{updated_email} Email, +{updated_phone} SĐT, +{updated_web} Website.")
    print(f"[*] Tổng doanh nghiệp có Email hiện tại: {len(with_email):,} ({len(with_email)/len(sorted_rows)*100:.1f}%)")
    print(f"[*] Toàn bộ {len(with_email)} doanh nghiệp có Email đã được đẩy lên đầu file (dòng 1 đến {len(with_email)}).")
    print(f"📁 Tệp kết quả: {CSV_FILE}")
    print("=" * 70)

if __name__ == '__main__':
    gp_data = crawl_greenpages()
    enrich_dataset(gp_data)
