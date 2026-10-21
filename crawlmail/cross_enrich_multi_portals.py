# -*- coding: utf-8 -*-
"""
Multi-Portal Cross-Matching and Data Enrichment for SK_AUTO_SLVD_1ENR.csv
Khai thac 7 nguon danh ba oto Slovakia do nguoi dung cung cap:
1. ZAP SR (Hiệp hội Công nghiệp Ô tô Slovakia): https://zapsr.sk/o-zvaze/clenovia/
2. Zlaté Stránky (Automobilový priemysel): https://www.zlatestranky.sk/firmy/-/q_automobilov%C3%BD+priemysel/
3. Zlaté Stránky (Automobily - výroba): https://www.zlatestranky.sk/firmy/-/q_automobily+-+v%C3%BDroba/
4. Inštitúcia Firiem: https://www.instituciafiriem.sk/sluzby/automobilovy_priemysel/sk/
5. Azet Katalóg (Výroba automobilov a autodoplnkov): https://www.azet.sk/katalog/vyroba-automobilov-a-autodoplnkov/
6. Azet Katalóg (Výroba osobných automobilov): https://www.azet.sk/katalog/vyroba-osobnych-automobilov/
7. Zoznam.sk Katalóg: https://www.zoznam.sk/katalog/Auto-moto-preprava-logistika/Automobily-komponenty-vyroba/

QUY CHUAN BAT BUOC:
- CHI doi chieu lam giau Web, SDT, Email cho dung 1,513 doanh nghiep co san trong SK_AUTO_SLVD_1ENR.csv.
- TUYET DOI KHONG them dong moi, khong xoa dong, giu nguyen 1,513 cong ty.
- Uu tien Web va SDT chinh xac (luon co dau nhay don '), loc email B2B tuyen chon.
- Thuat toan so khop da tang chat che (ICO -> Ten chuan hoa -> Token dac trung), tranh tuyet doi false-positive.
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

ROOT_DIR = Path("D:/glc/nail uc")
CSV_FILE = ROOT_DIR / "SK_AUTO_SLVD_1ENR.csv"
RAW_FILE = ROOT_DIR / "SK_AUTO_SLVD_0RAW.csv"

GENERIC_WORDS = {
    'slovakia', 'slovensko', 'slovenska', 'slovensky', 'republika',
    'group', 'holding', 'services', 'trading', 'international',
    'company', 'industry', 'priemysel', 'vyroba', 'spolocnost',
    'auto', 'automotive', 'motors', 'cars', 'car', 'moto', 'diel',
    'diely', 'servis', 'tech', 'technology', 'technologies', 'systems'
}

LEGAL_FORMS = [
    'spol. s r.o.', 'spol. s r. o.', 's.r.o.', 's. r. o.', 'sro',
    'akciova spolocnost', 'akciová spoločnosť', 'a.s.', 'a. s.', 'as',
    'komanditna spolocnost', 'komanditná spoločnosť', 'k.s.', 'k. s.',
    'ltd', 'gmbh', 'inc.', 'inc', 'corp.', 'corp'
]

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Z|a-z]{2,10}\b')

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

def extract_distinctive_tokens(name):
    c = clean_name(name)
    tokens = set()
    for w in c.split():
        if len(w) >= 3 and w not in GENERIC_WORDS:
            tokens.add(w)
    return tokens

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
    if any(k in e for k in ['wix', 'sentry', 'example', 'domain', 'support@', 'no-reply', 'asset', 'image', 'png', 'jpg']):
        return ''
    return e

def score_email_b2b(email, domain=""):
    score = 0
    e = email.lower()
    if domain and domain in e:
        score += 50
    if any(e.startswith(p) for p in ['praca@', 'kariera@', 'hr@', 'personalne@', 'jobs@', 'recruitment@', 'nabor@', 'career@']):
        score += 50
    elif any(e.startswith(p) for p in ['vedenie@', 'riaditel@', 'konatel@', 'ceo@', 'director@', 'manager@', 'obchod@', 'sales@']):
        score += 45
    elif any(e.startswith(p) for p in ['info@', 'kontakt@', 'contact@', 'office@', 'biuro@', 'sekretariat@', 'recepcia@', 'kancelaria@']):
        score += 40
    elif any(e.endswith(d) for d in ['@gmail.com', '@seznam.cz', '@zoznam.sk']):
        score += 10
    else:
        score += 25
    return score

def deep_crawl_email_for_domain(web_url):
    """Quét trang chủ và trang liên hệ của website để lấy Email B2B tối ưu nhất"""
    if not web_url or not web_url.startswith('http'):
        return ''
    found_emails = set()
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}
    try:
        r = requests.get(web_url, impersonate='chrome120', timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        for em in EMAIL_REGEX.findall(r.text):
            cle = clean_email(em)
            if cle:
                found_emails.add(cle)
        # Search contact page
        contact_links = []
        for a in soup.find_all('a', href=True):
            h = a['href'].lower()
            if any(k in h for k in ['kontakt', 'kontakty', 'contact', 'o-nas', 'impressum', 'about']):
                full = a['href']
                if full.startswith('/'):
                    full = web_url.rstrip('/') + full
                elif not full.startswith('http'):
                    full = web_url.rstrip('/') + '/' + full
                contact_links.append(full)
        
        for cl in contact_links[:3]:
            try:
                cr = requests.get(cl, impersonate='chrome120', timeout=10)
                for em in EMAIL_REGEX.findall(cr.text):
                    cle = clean_email(em)
                    if cle:
                        found_emails.add(cle)
            except Exception:
                pass
    except Exception:
        pass

    if not found_emails:
        return ''
    
    # Score emails and return the highest scored
    parsed_domain = re.sub(r'^www\.', '', web_url.split('/')[2].lower()) if '//' in web_url else ''
    scored = sorted(found_emails, key=lambda em: score_email_b2b(em, parsed_domain), reverse=True)
    return scored[0]

# -------------------------------------------------------------
# 1. CRAWL ZAP SR (Hiệp hội Công nghiệp Ô tô Slovakia)
# -------------------------------------------------------------
def harvest_zapsr():
    print("[*] 1/7. Đang cào ZAP SR (zapsr.sk/o-zvaze/clenovia/)...")
    url = 'https://zapsr.sk/o-zvaze/clenovia/'
    records = []
    try:
        r = requests.get(url, impersonate='chrome120', timeout=20)
        soup = BeautifulSoup(r.text, 'html.parser')
        modals = soup.find_all('div', class_=re.compile(r'member-detail'))
        seen = set()
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
            
            ico_el = m.find(class_=re.compile(r'member-ico'))
            ico = ""
            if ico_el:
                ico_m = re.search(r'\d{6,8}', ico_el.get_text())
                if ico_m:
                    ico = ico_m.group(0)

            web = ""
            link_el = m.find(class_=re.compile(r'member-link'))
            if link_el and link_el.find('a', href=True):
                whref = link_el.find('a')['href']
                web = whref.replace('http://https://', 'https://').strip()
            
            phone = ""
            phone_el = m.find(class_=re.compile(r'member-phone'))
            if phone_el:
                raw_p = phone_el.get_text().replace('Telefón:', '').replace('Telefon:', '').strip()
                phone = clean_phone(raw_p)

            records.append({
                'name': cname,
                'ico': ico,
                'web': web,
                'phone': phone,
                'email': '',
                'source': 'zapsr.sk'
            })
    except Exception as e:
        print(f"    [-] Lỗi cào ZAP SR: {e}")
    print(f"    -> Thu thập thành công {len(records)} hội viên ZAP SR.")
    return records

# -------------------------------------------------------------
# 2 & 3. CRAWL ZLATE STRANKY (2 danh mục)
# -------------------------------------------------------------
def harvest_zlatestranky():
    print("[*] 2/7 & 3/7. Đang cào Zlaté Stránky (Automobilový priemysel & Výroba)...")
    categories = [
        ('https://www.zlatestranky.sk/firmy/-/q_automobilov%C3%BD+priemysel/', 12),
        ('https://www.zlatestranky.sk/firmy/-/q_automobily+-+v%C3%BDroba/', 6)
    ]
    records = []
    seen = set()
    for base_url, max_p in categories:
        for p in range(1, max_p + 1):
            url = f"{base_url}{p}/"
            try:
                r = requests.get(url, impersonate='chrome120', timeout=15)
                soup = BeautifulSoup(r.text, 'html.parser')
                items = soup.find_all(class_=re.compile(r'\brd-item\b'))
                for it in items:
                    h2 = it.find('h2')
                    if not h2:
                        continue
                    cname = h2.get_text(strip=True)
                    if not cname or cname in seen:
                        continue
                    seen.add(cname)
                    
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
                    
                    records.append({
                        'name': cname,
                        'ico': '',
                        'web': web,
                        'phone': phone,
                        'email': email,
                        'source': 'zlatestranky.sk'
                    })
            except Exception:
                pass
    print(f"    -> Thu thập thành công {len(records)} bản ghi từ Zlaté Stránky.")
    return records

# -------------------------------------------------------------
# 4. CRAWL INSTITUCIA FIRIEM
# -------------------------------------------------------------
def harvest_instituciafiriem():
    print("[*] 4/7. Đang cào Inštitúcia Firiem (Automobilový priemysel)...")
    sub_urls = [
        'https://www.instituciafiriem.sk/sluzby/automobilovy_priemysel/sk/',
        'https://www.instituciafiriem.sk/sluzby/finalna_vyroba_pre_automobilovy_priemysel/sk/',
        'https://www.instituciafiriem.sk/sluzby/automobilovy_priemysel_nove_zamky/sk/',
        'https://www.instituciafiriem.sk/sluzby/opracovanie_pre_automobilovy_priemysel/sk/'
    ]
    records = []
    seen = set()
    for u in sub_urls:
        try:
            r = requests.get(u, impersonate='chrome120', timeout=15)
            soup = BeautifulSoup(r.text, 'html.parser')
            for a in soup.find_all('a', href=re.compile(r'/partner/')):
                cname = a.get_text(strip=True)
                if not cname or cname in seen:
                    continue
                seen.add(cname)
                parent = a.find_parent(['div', 'li', 'article'])
                web = ''
                email = ''
                phone = ''
                if parent:
                    w_tag = parent.find('a', href=re.compile(r'^https?://(?!www\.instituciafiriem)'))
                    if w_tag:
                        web = w_tag['href'].rstrip('/')
                    m_tag = parent.find('a', href=re.compile(r'^mailto:'))
                    if m_tag:
                        email = clean_email(m_tag['href'])
                    p_tag = parent.find('a', href=re.compile(r'^tel:'))
                    if p_tag:
                        phone = clean_phone(p_tag['href'])
                records.append({
                    'name': cname,
                    'ico': '',
                    'web': web,
                    'phone': phone,
                    'email': email,
                    'source': 'instituciafiriem.sk'
                })
        except Exception:
            pass
    print(f"    -> Thu thập thành công {len(records)} bản ghi từ Inštitúcia Firiem.")
    return records

# -------------------------------------------------------------
# 5 & 6. CRAWL AZET KATALOG (2 danh mục)
# -------------------------------------------------------------
def harvest_azet():
    print("[*] 5/7 & 6/7. Đang cào Azet Katalóg (Výroba automobilov & dielov)...")
    categories = [
        ('https://www.azet.sk/katalog/vyroba-automobilov-a-autodoplnkov/', 10),
        ('https://www.azet.sk/katalog/vyroba-osobnych-automobilov/', 5)
    ]
    records = []
    seen = set()
    for base_url, max_p in categories:
        for p in range(1, max_p + 1):
            url = f"{base_url}?p={p}" if p > 1 else base_url
            try:
                r = requests.get(url, impersonate='chrome120', timeout=15)
                soup = BeautifulSoup(r.text, 'html.parser')
                for a in soup.find_all('a', href=re.compile(r'/firma/\d+/')):
                    cname = a.get_text(strip=True)
                    if not cname or len(cname) < 4 or any(w in cname.lower() for w in ['hodnotenie', 'kontakt', 'azet']):
                        continue
                    if re.search(r'\d{3}\s*\d{2}', cname):
                        continue
                    href = a['href']
                    full_detail = f"https://www.azet.sk{href}" if href.startswith('/') else href
                    if full_detail in seen:
                        continue
                    seen.add(full_detail)
                    records.append({
                        'name': cname,
                        'ico': '',
                        'detail_url': full_detail,
                        'source': 'azet.sk'
                    })
            except Exception:
                pass
    print(f"    -> Thu thập thành công {len(records)} công ty từ Azet Katalóg.")
    return records

# -------------------------------------------------------------
# 7. CRAWL ZOZNAM.SK
# -------------------------------------------------------------
def harvest_zoznam():
    print("[*] 7/7. Đang cào Zoznam.sk (Automobily, komponenty - výroba)...")
    base_url = 'https://www.zoznam.sk/katalog/Auto-moto-preprava-logistika/Automobily-komponenty-vyroba/'
    pages = [base_url] + [f"{base_url}?page={p}" for p in range(2, 5)]
    records = []
    seen = set()
    for u in pages:
        try:
            r = requests.get(u, impersonate='chrome120', timeout=15)
            soup = BeautifulSoup(r.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.startswith('http') and not any(k in href for k in ['zoznam.sk', 'facebook', 'google', 'azet']):
                    parent = a.find_parent(['li', 'div', 'article'])
                    if parent:
                        h = parent.find(['h2', 'h3', 'h4', 'strong'])
                        if h:
                            raw_name = h.get_text(strip=True)
                            parts = [p.strip() for p in raw_name.split(',') if p.strip()]
                            if len(parts) >= 2 and any(k in parts[-1].lower() for k in ['cr', 'čr', 'slovensko', 'sr', 'bratislava', 'trnava', 'kosice', 'zilina', 'praha', 'brno']):
                                cname = ', '.join(parts[:-1])
                            else:
                                cname = raw_name
                            
                            if cname not in seen:
                                seen.add(cname)
                                records.append({
                                    'name': cname,
                                    'ico': '',
                                    'web': href.rstrip('/'),
                                    'phone': '',
                                    'email': '',
                                    'source': 'zoznam.sk'
                                })
        except Exception:
            pass
    print(f"    -> Thu thập thành công {len(records)} bản ghi từ Zoznam.sk.")
    return records

# -------------------------------------------------------------
# THUAT TOAN SO KHOP DA TANG CHAT CHE & LAM GIAU DU LIEU
# -------------------------------------------------------------
def match_companies(query_name, query_ico, target_row):
    # 1. Khop tuyet doi bang ICO (Chinh xac 100%)
    t_ico = target_row.get('IČO', '').strip()
    if query_ico and t_ico and len(query_ico) >= 6 and len(t_ico) >= 6:
        if query_ico == t_ico:
            return True, "ICO_MATCH"

    # 2. Khop tuyet doi bang ten da chuan hoa phap ly
    q_clean = clean_name(query_name)
    t_clean = clean_name(target_row.get('Công ty', ''))
    if q_clean and t_clean and q_clean == t_clean:
        return True, "EXACT_NAME"

    # 3. Khop tap token dac trung (loai tru toan bo tu generic va phap ly)
    q_tokens = extract_distinctive_tokens(query_name)
    t_tokens = extract_distinctive_tokens(target_row.get('Công ty', ''))
    if len(q_tokens) >= 1 and len(t_tokens) >= 1:
        if q_tokens == t_tokens:
            return True, "DISTINCTIVE_EXACT"
        intersection = q_tokens.intersection(t_tokens)
        union = q_tokens.union(t_tokens)
        if len(intersection) >= 2 and (len(intersection) / len(union)) >= 0.75:
            return True, "DISTINCTIVE_SIMILAR"

    return False, "NO_MATCH"

def run_cross_enrichment():
    print("\n" + "=" * 75)
    print("🚀 BẮT ĐẦU QUY TRÌNH ĐỐI CHIẾU & LÀM GIÀU DỮ LIỆU TỪ 7 NGUỒN DANH BẠ")
    print("=" * 75)

    if not CSV_FILE.exists():
        print(f"[-] Không tìm thấy tệp {CSV_FILE}!")
        return

    with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    print(f"[*] Tổng số doanh nghiệp trong tệp: {len(rows):,} công ty (CỐ ĐỊNH 100% SỐ DÒNG).")

    # 1. Harvest all 7 portals
    zapsr = harvest_zapsr()
    zlat = harvest_zlatestranky()
    zoz = harvest_zoznam()
    inst = harvest_instituciafiriem()
    azet = harvest_azet()

    # Index rows
    ico_index = {r['IČO'].strip(): r for r in rows if r.get('IČO', '').strip()}
    name_index = {clean_name(r['Công ty']): r for r in rows if clean_name(r['Công ty'])}

    all_harvested = [
        ('ZAP SR', zapsr),
        ('Zlaté Stránky', zlat),
        ('Zoznam.sk', zoz),
        ('Inštitúcia Firiem', inst),
        ('Azet Katalóg', azet)
    ]

    updated_web = 0
    updated_phone = 0
    updated_email = 0
    matched_companies = set()

    for sname, records in all_harvested:
        print(f"\n[*] Đang so khớp dữ liệu từ nguồn: {sname} ({len(records)} bản ghi)...")
        for rec in records:
            r_name = rec.get('name', '')
            r_ico = rec.get('ico', '')
            target = None
            match_type = None

            if r_ico and r_ico in ico_index:
                target = ico_index[r_ico]
                match_type = "ICO"
            elif clean_name(r_name) in name_index:
                target = name_index[clean_name(r_name)]
                match_type = "EXACT_NAME"
            else:
                for r in rows:
                    is_match, mtype = match_companies(r_name, r_ico, r)
                    if is_match:
                        target = r
                        match_type = mtype
                        break

            if target:
                cname = target.get('Công ty', '')
                matched_companies.add(cname)
                
                # Fetch details if Azet
                if sname == 'Azet Katalóg' and rec.get('detail_url'):
                    if not target.get('Web') or not target.get('SĐT'):
                        try:
                            dr = requests.get(rec['detail_url'], impersonate='chrome120', timeout=12)
                            dsoup = BeautifulSoup(dr.text, 'html.parser')
                            w_tag = dsoup.find('a', href=re.compile(r'^https?://(?!www\.azet|onas\.azet|prihlasenie\.azet)'))
                            p_tag = dsoup.find('a', href=re.compile(r'^tel:'))
                            m_tag = dsoup.find('a', href=re.compile(r'^mailto:'))
                            if w_tag and not target.get('Web'):
                                rec['web'] = w_tag['href'].split('?')[0].rstrip('/')
                            if p_tag and not target.get('SĐT'):
                                rec['phone'] = clean_phone(p_tag['href'])
                            if m_tag and not target.get('Email'):
                                rec['email'] = clean_email(m_tag['href'])
                        except Exception:
                            pass

                added = []
                # 1. Update Web (Ưu tiên)
                if rec.get('web') and not target.get('Web'):
                    target['Web'] = rec['web']
                    updated_web += 1
                    added.append(f"Web: {rec['web']}")

                # 2. Update Phone (Ưu tiên)
                if rec.get('phone') and not target.get('SĐT'):
                    target['SĐT'] = clean_phone(rec['phone'])
                    updated_phone += 1
                    added.append(f"SĐT: {target['SĐT']}")

                # 3. Update Email
                if rec.get('email') and not target.get('Email'):
                    target['Email'] = rec['email']
                    updated_email += 1
                    added.append(f"Email: {rec['email']}")

                # Deep-crawl website nếu có Web nhưng chưa có Email
                if target.get('Web') and not target.get('Email'):
                    deep_em = deep_crawl_email_for_domain(target['Web'])
                    if deep_em:
                        target['Email'] = deep_em
                        updated_email += 1
                        added.append(f"Deep Email: {deep_em}")

                if added:
                    print(f"  [+] LÀM GIÀU THÀNH CÔNG: {cname:<35} -> {' | '.join(added)} ({sname})")

    # Đẩy toàn bộ công ty có Email lên đầu tệp
    with_email = [r for r in rows if r.get('Email', '').strip()]
    without_email = [r for r in rows if not r.get('Email', '').strip()]
    sorted_rows = with_email + without_email

    for idx, r in enumerate(sorted_rows, 1):
        r['No.'] = str(idx)
        p = str(r.get('SĐT', '')).strip()
        if p and p != 'nan' and not p.startswith("'"):
            r['SĐT'] = f"'{p}"

    # Ghi lại CSV
    with open(CSV_FILE, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sorted_rows)

    print("\n" + "=" * 75)
    print("🎉 HOÀN TẤT ĐỐI CHIẾU LÀM GIÀU DỮ LIỆU TỪ 7 NGUỒN DANH BẠ!")
    print(f"[*] Số doanh nghiệp khớp thành công   : {len(matched_companies):,} công ty")
    print(f"[*] Bổ sung mới                       : +{updated_web} Website, +{updated_phone} SĐT, +{updated_email} Email.")
    print(f"[*] Tổng số dòng dữ liệu (Cố định)   : {len(sorted_rows):,} dòng (ĐÚNG 100% SỐ DÒNG GỐC).")
    print(f"[*] Tổng số doanh nghiệp có Email    : {len(with_email):,} ({len(with_email)/len(sorted_rows)*100:.1f}%)")
    print(f"[*] Toàn bộ {len(with_email):,} công ty có Email đã được đẩy lên các dòng đầu tiên (Dòng 1 đến {len(with_email):,}).")
    print(f"📁 Tệp kết quả: {CSV_FILE}")
    print("=" * 75)

if __name__ == '__main__':
    run_cross_enrichment()
