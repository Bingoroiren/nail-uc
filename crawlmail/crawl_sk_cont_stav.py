# -*- coding: utf-8 -*-
"""
Crawler & Classifier for Slovakia Construction Companies (Stavbari):
Source: https://stavbari.profesionalnyregister.sk/#this
Output: SK_CONT_STAV_0RAW.csv (Tuan thu quy chuan 17 ky tu [CC]_[IND4]_[SRC4]_[STG4].csv)

Quy chuan workspace:
- CSV UTF-8 with BOM (utf-8-sig).
- KHONG EXCEL.
- SDT luon co dau nhay don ' o dau (+421...).
- Loc bo cac cong ty khong lien quan den xay dung (nha si, y te, spa, tham my, nong nghiep, nha hang...).
- Day 100% doanh nghiep co Email len dau danh sach.
- Luu tang dan va co co che Checkpoint Resume an toan.
"""

import sys
import os
import re
import csv
import json
import time
import urllib.parse
from pathlib import Path
import concurrent.futures
from bs4 import BeautifulSoup
from curl_cffi import requests

# Cau hinh UTF-8 cho console Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_CSV = str(ROOT_DIR / "SK_CONT_STAV_0RAW.csv")
CHECKPOINT_FILE = str(ROOT_DIR / "crawlmail" / "checkpoint_sk_cont_stav.json")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'X-Requested-With': 'XMLHttpRequest'
}

FIELDNAMES = [
    'No.', 'Công ty', 'SĐT', 'Liên Hệ', 'Email', 'Liên Hệ mail',
    'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển', 'Check gửi',
    'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng',
    'Category', 'Dịch vụ / Services'
]

LEGAL_FORMS_SK = [
    'spol. s r.o.', 'spol. s r. o.', 's.r.o.', 's. r. o.', 'sro',
    'spolocnost s rucenim obmedzenym', 'spoločnosť s ručením obmedzeným',
    'akciova spolocnost', 'akciová spoločnosť', 'a.s.', 'a. s.', 'as',
    'komanditna spolocnost', 'komanditná spoločnosť', 'k.s.', 'k. s.',
    'verejna obchodna spolocnost', 'verejná obchodná spoločnosť', 'v.o.s.', 'v. o. s.',
    'druzstvo', 'družstvo', 'gmbh', 'ltd', 'z.z.p.o.', 'e.u.'
]

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Z|a-z]{2,10}\b')

# Bo loc cac nganh phi xay dung (loai bo triet de)
NON_CONSTRUCTION_KEYWORDS = [
    # Nha khoa & Y te & Duoc pham
    'zub', 'stomatol', 'dent', 'lekar', 'lekár', 'ambulanc', 'medic', 'zdravot',
    'klinik', 'optik', 'lekáreň', 'lekaren', 'farmac', 'farmacia', 'zverolekár', 'veterin',
    'psycholog', 'fyzioterap', 'chirurg', 'očn', 'pediatr', 'gynekolog', 'urolog',
    'kardiolog', 'nemocnic', 'hospic', 'masér', 'rehabilitác', 'mudr', 'mvdr',
    # Lam dep, Toc, Spa, Nail
    'kadern', 'kozmet', 'manik', 'pedik', 'necht', 'salón krásy', 'salon krasy',
    'solárium', 'solarium', 'tetov', 'piercing', 'kaderníctvo', 'kozmetika',
    # Am thuc, Nha hang, Quan an, Khach san thuan tuy
    'reštaurác', 'restauracia', 'pizzeri', 'kaviareň', 'kaviaren', 'cukráreň',
    'cukraren', 'bistro', 'potravin', 'mäsiar', 'masiar', 'pekár', 'pekar',
    'lahôdk', 'lahodk', 'hostinec', 'pohostinstvo', 'krčma', 'bar', 'pub', 'penzión',
    # Nong nghiep, Chan nuoi, Thuc pham
    'agrodružstv', 'agrodruzstvo', 'poľnohospodár', 'polnohospodar', 'chov', 'pšenica',
    'kureniec', 'dobytok', 'ošípané', 'mlieko', 'mäso', 'ovocie', 'zelenina',
    'rybolov', 'včelár', 'agrofarma', 'hospodárstv',
    # Phap ly, Ke toan, Tai chinh, Bao hiem, Giao duc, Bat dong san
    'advokát', 'advokat', 'notár', 'notar', 'právn', 'pravn', 'účtov', 'uctov',
    'daňov', 'danov', 'audit', 'exekútor', 'exekutor', 'poistn', 'autoškol',
    'jazykov', 'škôlk', 'skolka', 'škola', 'doučov', 'cestovn', 'realitná kancelária',
    # Am nhac, Nghe thuat, Giai tri, Truyen thong
    'music trio', 'music box', 'hudb', 'hudobn', 'kapel', 'orchester', 'koncert', 'divadl', 'kino',
    'umelecká agentúra', 'audio-video', 'ozvučenie',
    # Cac nganh ban le phi xay dung khac, Cuu ho, Giat ui
    'pohreb', 'krematórium', 'kvetinárstv', 'kvetinarstvo', 'zlatníctv', 'odev', 'mód', 'obuv',
    'odťahová služba', 'odtahova', 'daddytoys', 'práčovňa', 'čistiareň', 'tepovanie'
]

# Cac tu khoa manh xac nhan linh vuc Xay dung (Construction)
CONSTRUCTION_KEYWORDS = [
    'stavb', 'stavebn', 'rekonštrukc', 'rekonstrukc', 'montáž', 'montaz', 'zatepl',
    'omietk', 'fasád', 'fasad', 'strech', 'pokrývač', 'pokryvac', 'klampiar',
    'tesár', 'tesar', 'obklad', 'dlažb', 'dlazb', 'murár', 'murar', 'sadrokartón',
    'inštalatér', 'instalater', 'elektroinštalác', 'vodoinštalác', 'kúren', 'kuren',
    'plyn', 'vetranie', 'klimatizác', 'potrub', 'búrac', 'burac', 'výkop', 'vykop',
    'zemné práce', 'zemne prace', 'okn', 'dver', 'podlah', 'parket', 'betón', 'beton',
    'armov', 'žeriav', 'zeriav', 'lešenie', 'lesenie', 'architekt', 'projektov',
    'inžinier', 'inzinier', 'geodéz', 'geodez', 'pozemné', 'inžinierske',
    'oceľové', 'ocelove', 'kovovýrob', 'kovovyrob', 'zámočníc', 'zamocnic',
    'stolár', 'stolar', 'sklenár', 'sklenar', 'drevostavb', 'chladiaren', 'bazén',
    'plot', 'brán', 'izolác', 'izolac', 'hydroizolác', 'sanác', 'sanac', 'vrtné',
    'studn', 'kanalizác', 'kanalizac', 'čov', 'asfalt', 'cesty', 'most', 'búranie',
    'demolác', 'domy', 'hala', 'haly', 'priemyselné stavby', 'bytové', 'nebytové',
    'prefabrik', 'hrubá stavba', 'materiál', 'železo'
]

def clean_phone(p):
    if not p:
        return ""
    p = p.replace('\xa0', ' ').strip()
    parts = re.split(r'[,;]', p)
    first_phone = parts[0].strip() if parts else p
    digits = re.sub(r'[^\d+]', '', first_phone)
    if digits and len(digits) >= 6:
        return f"'{digits}" if not digits.startswith("'") else digits
    return ""

def clean_email(e):
    if not e:
        return ""
    clean = urllib.parse.unquote(e.replace('mailto:', '')).replace('%20', '').strip().lower().rstrip('.,;:')
    parts = re.split(r'[,; ]', clean)
    for p in parts:
        p = p.strip()
        if EMAIL_REGEX.match(p):
            return p
    return clean if EMAIL_REGEX.match(clean) else ""

def clean_company_name_sk(name):
    if not name:
        return ""
    n = re.sub(r'["\'„“”«»]', '', str(name)).strip().lower()
    for lf in sorted(LEGAL_FORMS_SK, key=len, reverse=True):
        n = re.sub(rf'\b{re.escape(lf)}\b', '', n)
    n = re.sub(r'[^\w\s]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n

def extract_domain(url):
    if not url:
        return ""
    try:
        p = urllib.parse.urlparse(url)
        d = p.netloc.lower().replace('www.', '')
        return d.split(':')[0]
    except Exception:
        return ""

def is_construction_company(name, services, details_text=""):
    """
    Kiem tra va loai bo cac cong ty phi xay dung (nha si, y te, nong nghiep, nha hang, spa...).
    """
    full_text = f"{name} {' '.join(services)} {details_text}".lower()

    # Danh xuyen bac si / luat su trong ten
    if any(title in name.lower() for title in ['mudr.', 'mvdr.', 'judr.', 'phdr.', 'rndr.', 'dent']):
        return False

    has_non_const = any(kw in full_text for kw in NON_CONSTRUCTION_KEYWORDS)
    has_const = any(kw in full_text for kw in CONSTRUCTION_KEYWORDS)

    # Neu co tu khoa phi xay dung ma khong he co tu khoa xay dung nao -> LOAI BO
    if has_non_const and not has_const:
        return False

    # Neu co danh sach dich vu, kiem tra toan bo dich vu
    if services:
        services_text = " ".join(services).lower()
        if any(kw in services_text for kw in NON_CONSTRUCTION_KEYWORDS) and not any(kw in services_text for kw in CONSTRUCTION_KEYWORDS):
            return False

    return True

def fetch_page_items(offset):
    data = {
        'ajax': '1',
        'page': 'kereses',
        'lng': 'sk',
        'ResultStart': str(offset),
        'ResultLimit': '20'
    }
    try:
        r = requests.post(
            'https://stavbari.profesionalnyregister.sk/',
            data=data,
            headers=HEADERS,
            impersonate='chrome120',
            timeout=25
        )
        if r.status_code != 200:
            return offset, []

        soup = BeautifulSoup(r.text, 'html.parser')
        headers = soup.select('.result-item-header')
        if not headers:
            return offset, []

        items_data = []
        for h in headers:
            name = h.get_text().strip()
            if not name:
                continue

            item = h.find_next_sibling(class_='result-item')
            if not item:
                continue

            labels = [l.get_text().strip().rstrip(':') for l in item.select('.label')]
            datas = [d.get_text().strip() for d in item.select('.data')]
            kv = dict(zip(labels, datas))

            # Dich vu / Tags
            services = [a.get_text().strip() for a in item.select('a[href*="/sluzby/"]')]

            # Web
            web_tag = item.select_one('a[href^="http"]:not([href*="profesionalnyregister"]):not([href^="mailto:"]):not([href^="tel:"])')
            web = web_tag['href'].strip() if web_tag else kv.get('Web', '')
            if web:
                # Xu ly loi double scheme http://https://
                if web.startswith('http://https://'):
                    web = web.replace('http://https://', 'https://')
                elif web.startswith('http://http://'):
                    web = web.replace('http://http://', 'http://')
                elif not web.startswith(('http://', 'https://')):
                    web = 'http://' + web

            # Email
            mail_tag = item.select_one('a[href^="mailto:"]')
            mail = mail_tag['href'] if mail_tag else kv.get('E-mail', '')

            # Phone & Address
            phone = kv.get('Telefónne čislo') or kv.get('Mobil') or kv.get('Telefón') or kv.get('Tel') or ''
            addr = kv.get('Sídlo') or kv.get('Poštová adresa') or kv.get('Adresa') or ''

            items_data.append({
                'company': name,
                'phone': clean_phone(phone),
                'website': web,
                'email': clean_email(mail),
                'address': addr,
                'services': services,
                'details': item.get_text().strip()
            })

        return offset, items_data
    except Exception as e:
        print(f"[-] Loi fetch offset {offset}: {e}")
        return offset, []

def save_csv_and_checkpoint(companies_dict, current_offsets_done):
    # Chuyen thanh danh sach dong chuan hoa
    rows = []
    for c in companies_dict.values():
        row = {
            'No.': '',
            'Công ty': c['company'],
            'SĐT': c['phone'],
            'Liên Hệ': c['website'],
            'Email': c['email'],
            'Liên Hệ mail': '',
            'Địa chỉ': c['address'],
            'Lương': '',
            'Ngày đăng': '',
            'Hạn tuyển': '',
            'Check gửi': '',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': 'Stavebníctvo',
            'Dịch vụ / Services': ' | '.join(c.get('services', []))
        }
        rows.append(row)

    # Phan loai with_email va without_email: DAY 100% EMAIL LEN DAU
    with_email = [r for r in rows if r.get('Email')]
    without_email = [r for r in rows if not r.get('Email')]
    final_rows = with_email + without_email

    for idx, r in enumerate(final_rows, 1):
        r['No.'] = str(idx)

    temp_csv = OUTPUT_CSV + ".tmp"
    with open(temp_csv, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(final_rows)

    if os.path.exists(OUTPUT_CSV):
        try:
            os.remove(OUTPUT_CSV)
        except Exception:
            pass
    os.rename(temp_csv, OUTPUT_CSV)

    # Luu checkpoint
    try:
        with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'offsets_done': sorted(list(current_offsets_done)),
                'companies_count': len(companies_dict)
            }, f, indent=2)
    except Exception:
        pass

def main():
    print("=" * 80)
    print("QUY TRINH CAO VA LOC NGANH XAY DUNG (STAVBARI.PROFESIONALNYREGISTER.SK)")
    print(f"File xuat: {OUTPUT_CSV}")
    print("Che do loc: Loai bo 100% cty phi xay dung (nha si, y te, spa, nong nghiep...)")
    print("=" * 80)

    # 1. Kiem tra checkpoint de Resume neu co
    completed_offsets = set()
    companies = {}
    excluded_count = 0

    if os.path.exists(CHECKPOINT_FILE) and os.path.exists(OUTPUT_CSV):
        try:
            with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
                chk = json.load(f)
                completed_offsets = set(chk.get('offsets_done', []))
                print(f"[*] Tim thay Checkpoint: Da hoan thanh {len(completed_offsets)} pages. Dang doc tiep...")
            
            with open(OUTPUT_CSV, 'r', encoding='utf-8-sig', errors='ignore') as f:
                reader = csv.DictReader(f)
                for r in reader:
                    cname = r.get('Công ty', '').strip()
                    web = r.get('Liên Hệ', '').strip()
                    serv = r.get('Dịch vụ / Services', '').split(' | ')
                    key = clean_company_name_sk(cname) or extract_domain(web) or cname
                    companies[key] = {
                        'company': cname,
                        'phone': r.get('SĐT', ''),
                        'website': web,
                        'email': r.get('Email', ''),
                        'address': r.get('Địa chỉ', ''),
                        'services': serv
                    }
            print(f"[*] Da nap san {len(companies)} doanh nghiep tu checkpoint CSV.")
        except Exception as e:
            print(f"[-] Khong the doc checkpoint ({e}), bat dau quet moi...")

    # 2. Xac dinh tat ca cac offsets can cao (tu 0 den 6060, buoc nhay 20)
    all_offsets = list(range(0, 6080, 20))
    pending_offsets = [off for off in all_offsets if off not in completed_offsets]

    print(f"[*] Tong so pages can duyet: {len(all_offsets)} pages (khoang 6,070 doanh nghiep)")
    print(f"[*] So pages con lai can cao: {len(pending_offsets)} pages")

    if not pending_offsets:
        print("[+] Tat ca cac trang da duoc cao day du!")
        return

    # 3. Chay concurrent fetching voi 6 workers
    batch_size = 30
    total_batches = (len(pending_offsets) + batch_size - 1) // batch_size

    for b_idx in range(total_batches):
        batch = pending_offsets[b_idx * batch_size : (b_idx + 1) * batch_size]
        print(f"\n[*] Dang cao Batch {b_idx + 1}/{total_batches} ({len(batch)} pages, offset {batch[0]} -> {batch[-1]})...")

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            future_to_offset = {executor.submit(fetch_page_items, off): off for off in batch}
            for future in concurrent.futures.as_completed(future_to_offset):
                off = future_to_offset[future]
                try:
                    res_offset, items = future.result()
                    completed_offsets.add(res_offset)

                    for it in items:
                        cname = it['company']
                        serv = it['services']
                        det = it['details']

                        # LOC BO CTY PHI XAY DUNG (Nha si, spa, nong nghiep...)
                        if not is_construction_company(cname, serv, det):
                            excluded_count += 1
                            continue

                        # Loc trung lap
                        key = clean_company_name_sk(cname) or extract_domain(it['website']) or cname
                        if key not in companies:
                            companies[key] = it
                        else:
                            # Merge bo sung thong tin
                            existing = companies[key]
                            if not existing.get('email') and it.get('email'):
                                existing['email'] = it['email']
                            if not existing.get('phone') and it.get('phone'):
                                existing['phone'] = it['phone']
                            if not existing.get('website') and it.get('website'):
                                existing['website'] = it['website']
                            if not existing.get('address') and it.get('address'):
                                existing['address'] = it['address']

                except Exception as e:
                    print(f"[-] Loi xu ly batch tai offset {off}: {e}")

        # Luu tang dan sau moi batch
        save_csv_and_checkpoint(companies, completed_offsets)
        with_mail = sum(1 for c in companies.values() if c.get('email'))
        print(f"    [+] Tien do: {len(completed_offsets)}/{len(all_offsets)} pages | Luu hop le: {len(companies)} cty XD ({with_mail} co email) | Da loai: {excluded_count} phi XD")

    print("\n" + "=" * 80)
    print("HOAN TAT CAO VA LOC NGANH XAY DUNG!")
    print(f"Tong so doanh nghiep Xay dung hop le: {len(companies)}")
    with_mail = sum(1 for c in companies.values() if c.get('email'))
    print(f"So doanh nghiep da co Email: {with_mail}")
    print(f"So doanh nghiep phi xay dung da bi loai bo: {excluded_count}")
    print(f"File ket qua cuoi cung: {OUTPUT_CSV}")
    print("=" * 80)

if __name__ == "__main__":
    main()
