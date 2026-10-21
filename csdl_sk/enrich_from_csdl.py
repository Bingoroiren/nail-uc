# -*- coding: utf-8 -*-
"""
CSDL SK - Module Doi Chieu & Lam Giau Du Lieu Tu CSDL Tong Hop:
Doi chieu toan bo cac tep du lieu trong csdl_sk/ vao SK_AUTO_SLVD_1ENR.csv:
- azet_auto_database.csv
- greenpages_auto_database.csv
- zlatestranky_auto_database.csv
- zapsr_members_master.csv

QUY CHUAN:
- Ghi de/cap nhat Web, SDT, Email vao dung 1,513 doanh nghiep co san.
- Khong them dong moi, khong xoa dong.
- Deep crawl website de tim email B2B neu chua co email.
- Day 100% doanh nghiep co email len dau tep.
"""

import sys
import os
import re
import csv
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
CSDL_DIR = ROOT_DIR / "csdl_sk"
if len(sys.argv) > 1 and sys.argv[1].endswith('.csv'):
    TARGET_CSV = Path(sys.argv[1]) if os.path.isabs(sys.argv[1]) else (ROOT_DIR / sys.argv[1])
else:
    TARGET_CSV = ROOT_DIR / "SK_MANU_SLVD_1ENR.csv"

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

def deep_crawl_email(web_url):
    if not web_url or not web_url.startswith('http'):
        return ''
    found_emails = set()
    try:
        r = requests.get(web_url, impersonate='chrome120', timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        for em in EMAIL_REGEX.findall(r.text):
            e = em.replace('mailto:', '').strip().lower().rstrip('.,;:')
            if not any(k in e for k in ['wix', 'sentry', 'example', 'domain', 'support@', 'no-reply', 'asset', 'image']):
                found_emails.add(e)

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
                    e = em.replace('mailto:', '').strip().lower().rstrip('.,;:')
                    if not any(k in e for k in ['wix', 'sentry', 'example', 'domain', 'support@', 'no-reply', 'asset', 'image']):
                        found_emails.add(e)
            except Exception:
                pass
    except Exception:
        pass

    if not found_emails:
        return ''
    parsed_domain = re.sub(r'^www\.', '', web_url.split('/')[2].lower()) if '//' in web_url else ''
    scored = sorted(found_emails, key=lambda em: score_email_b2b(em, parsed_domain), reverse=True)
    return scored[0]

def match_target(c_clean, c_tokens, target_name):
    t_clean = clean_name(target_name)
    if c_clean and t_clean and c_clean == t_clean:
        return True
    t_tokens = extract_distinctive_tokens(target_name)
    if len(c_tokens) >= 1 and len(t_tokens) >= 1:
        if c_tokens == t_tokens and all(len(t) >= 4 for t in c_tokens):
            return True
        intersection = c_tokens.intersection(t_tokens)
        union = c_tokens.union(t_tokens)
        if len(intersection) >= 2 and (len(intersection) / len(union)) >= 0.75:
            return True
    return False

def enrich_from_csdl():
    print("=" * 75)
    print("🚀 BẮT ĐẦU ĐỐI CHIẾU LÀM GIÀU DỮ LIỆU TỪ TOÀN BỘ CSDL SK")
    print("=" * 75)

    if not TARGET_CSV.exists():
        print(f"[-] Không tìm thấy tệp đích: {TARGET_CSV}")
        return

    with open(TARGET_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    print(f"[*] Tệp đích cố định: {len(rows):,} dòng (KHÔNG THÊM DÒNG MỚI).")

    # Load all records from csdl_sk/
    csdl_records = []
    for csv_path in CSDL_DIR.glob("*.csv"):
        print(f"[*] Đang tải dữ liệu từ CSDL: {csv_path.name}...")
        try:
            with open(csv_path, 'r', encoding='utf-8-sig') as cf:
                for r in csv.DictReader(cf):
                    csdl_records.append(r)
        except Exception as e:
            print(f"[-] Lỗi đọc {csv_path.name}: {e}")

    print(f"[*] Tổng số bản ghi tham chiếu trong CSDL SK: {len(csdl_records):,} bản ghi.")

    # Match and enrich
    updated_web = 0
    updated_phone = 0
    updated_email = 0
    matched_set = set()

    # Pre-index target rows
    ico_map = {r['IČO'].strip(): r for r in rows if r.get('IČO', '').strip()}
    name_map = {clean_name(r['Công ty']): r for r in rows if clean_name(r['Công ty'])}
    precomputed_targets = [
        (r, clean_name(r['Công ty']), extract_distinctive_tokens(r['Công ty']))
        for r in rows
    ]

    email_cache = {}

    for idx, rec in enumerate(csdl_records, 1):
        r_name = rec.get('Name', '').strip()
        r_ico = rec.get('ICO', '').strip()
        if not r_name and not r_ico:
            continue
        c_clean = clean_name(r_name)
        c_tokens = extract_distinctive_tokens(r_name)
        
        target = None
        # 1. Match by official ICO
        if r_ico and r_ico in ico_map:
            target = ico_map[r_ico]
        elif c_clean in name_map:
            target = name_map[c_clean]
        else:
            for r, t_clean, t_tokens in precomputed_targets:
                if len(c_tokens) >= 1 and len(t_tokens) >= 1:
                    if c_tokens == t_tokens and all(len(t) >= 4 for t in c_tokens):
                        target = r
                        break
                    intersection = c_tokens.intersection(t_tokens)
                    union = c_tokens.union(t_tokens)
                    if len(intersection) >= 2 and (len(intersection) / len(union)) >= 0.75:
                        target = r
                        break

        if target:
            cname = target['Công ty']
            matched_set.add(cname)
            added = []

            # 1. Update Web
            raw_w = rec.get('Web', '').strip()
            if raw_w and not target.get('Web') and not any(k in raw_w.lower() for k in ['ringier', 'aktuality', 'cas.sk', 'azet', 'greenpages', 'google']):
                target['Web'] = raw_w
                updated_web += 1
                added.append(f"Web: {raw_w}")

            # 2. Update Phone
            if rec.get('Phone') and not target.get('SĐT'):
                target['SĐT'] = clean_phone(rec['Phone'])
                updated_phone += 1
                added.append(f"SĐT: {target['SĐT']}")

            # 3. Update Email
            if rec.get('Email') and not target.get('Email'):
                target['Email'] = rec['Email']
                updated_email += 1
                added.append(f"Email: {rec['Email']}")

            # Deep crawl website nếu có Web mà chưa có Email
            if target.get('Web') and not target.get('Email'):
                domain_key = target['Web'].split('?')[0].rstrip('/')
                if domain_key in email_cache:
                    deep_em = email_cache[domain_key]
                else:
                    deep_em = deep_crawl_email(target['Web'])
                    email_cache[domain_key] = deep_em

                if deep_em:
                    target['Email'] = deep_em
                    updated_email += 1
                    added.append(f"Deep Email: {deep_em}")

            if added:
                print(f"  [+] LÀM GIÀU: {cname:<35} -> {' | '.join(added)} (Nguồn: {rec.get('Source')})", flush=True)

    # Đẩy các dòng có Email lên đầu tệp
    with_email = [r for r in rows if r.get('Email', '').strip()]
    without_email = [r for r in rows if not r.get('Email', '').strip()]
    sorted_rows = with_email + without_email

    for idx, r in enumerate(sorted_rows, 1):
        r['No.'] = str(idx)
        p = str(r.get('SĐT', '')).strip()
        if p and p != 'nan' and not p.startswith("'"):
            r['SĐT'] = f"'{p}"

    with open(TARGET_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sorted_rows)

    print("\n" + "=" * 75)
    print("🎉 HOÀN TẤT ĐỐI CHIẾU LÀM GIÀU TỪ CSDL SK!")
    print(f"[*] Doanh nghiệp khớp thành công     : {len(matched_set):,} công ty")
    print(f"[*] Bổ sung mới                       : +{updated_web} Website, +{updated_phone} SĐT, +{updated_email} Email.")
    print(f"[*] Tổng số dòng dữ liệu (Cố định)   : {len(sorted_rows):,} dòng (ĐÚNG 100% SỐ DÒNG GỐC).")
    print(f"[*] Tổng số doanh nghiệp có Email    : {len(with_email):,} ({len(with_email)/len(sorted_rows)*100:.1f}%)")
    print(f"[*] Toàn bộ {len(with_email):,} công ty có Email đã được đẩy lên các dòng đầu tiên (Dòng 1 đến {len(with_email):,}).")
    print(f"📁 Tệp kết quả: {TARGET_CSV}")
    print("=" * 75)

if __name__ == '__main__':
    enrich_from_csdl()
