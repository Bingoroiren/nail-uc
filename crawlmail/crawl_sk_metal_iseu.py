# -*- coding: utf-8 -*-
"""
Crawler & Consolidator for Slovakia Metal Production Companies (Kovovyroba):
Nguon cao:
1. https://www.instituciafiriem.sk/sluzby/kovovyroba/sk/
2. https://stavbari.profesionalnyregister.sk/sluzby/kovovyroba/sk/
3. https://europskefirmy.sk/sluzby/kovovroba/

Quy chuan workspace:
- Tep xuat: SK_MTAL_ISEU_0RAW.csv (dung 17 ky tu).
- Dinh dang CSV UTF-8 with BOM (utf-8-sig).
- So dien thoai luon co dau nhay don ' o dau ('+421...).
- Loc trung thong minh theo ten phap ly chuan hoa & domain website.
- Merge hop nhat thong tin tu nhieu nguon cho cung 1 cong ty.
- Day 100% doanh nghiep co Email len dau danh sach.
"""

import sys
import os
import re
import csv
import json
import urllib.parse
from pathlib import Path
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
OUTPUT_CSV = str(ROOT_DIR / "SK_MTAL_ISEU_0RAW.csv")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'Accept-Language': 'sk-SK,sk;q=0.9,en;q=0.8',
    'X-Requested-With': 'XMLHttpRequest'
}

LEGAL_FORMS_SK = [
    'spol. s r.o.', 'spol. s r. o.', 's.r.o.', 's. r. o.', 'sro',
    'spolocnost s rucenim obmedzenym', 'spoločnosť s ručením obmedzeným',
    'akciova spolocnost', 'akciová spoločnosť', 'a.s.', 'a. s.', 'as',
    'komanditna spolocnost', 'komanditná spoločnosť', 'k.s.', 'k. s.',
    'verejna obchodna spolocnost', 'verejná obchodná spoločnosť', 'v.o.s.', 'v. o. s.',
    'druzstvo', 'družstvo', 'gmbh', 'ltd', 'z.z.p.o.', 'e.u.'
]

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Z|a-z]{2,10}\b')

FIELDNAMES = [
    'No.', 'Công ty', 'SĐT', 'Liên Hệ', 'Email', 'Liên Hệ mail',
    'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển', 'Check gửi',
    'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

def clean_phone(p):
    if not p:
        return ""
    p = p.replace('\xa0', ' ').strip()
    # Tách số đầu tiên nếu có nhiều số ngăn cách bằng dấu phẩy hoặc chấm phẩy
    parts = re.split(r'[,;]', p)
    first_phone = parts[0].strip() if parts else p
    # Lấy toàn bộ chữ số và dấu + (không bị cắt bởi dấu gạch chéo mã vùng 045/ 041/ 02/)
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

def crawl_instituciafiriem():
    print("[1/3] Đang cào dữ liệu từ: instituciafiriem.sk (Dịch vụ: kovovýroba)...")
    results = []
    offset = 0
    while True:
        data = {
            'ajax': '1',
            'page': 'tevekenyseg',
            'lng': 'sk',
            'SEARCH[URL_SERVICE]': 'kovovyroba',
            'ResultStart': str(offset),
            'ResultLimit': '20'
        }
        try:
            r = requests.post('https://www.instituciafiriem.sk/', data=data, headers=HEADERS, impersonate='chrome120', timeout=25)
            soup = BeautifulSoup(r.text, 'html.parser')
            items = soup.select('.companies-item')
            if not items:
                break

            for c in items:
                h1 = c.select_one('h1')
                name = h1.get_text().strip() if h1 else ""
                if not name:
                    continue

                befores = [b.get_text().strip().rstrip(':') for b in c.select('.before')]
                afters = [a.get_text().strip() for a in c.select('.after')]
                kv = dict(zip(befores, afters))

                web_tag = c.select_one('a[href^="http"]:not([href*="instituciafiriem"]):not([href^="mailto:"]):not([href^="tel:"])')
                web = web_tag['href'].strip() if web_tag else kv.get('Web', '')
                if web and not web.startswith(('http://', 'https://')):
                    web = 'http://' + web

                mail_tag = c.select_one('a[href^="mailto:"]')
                mail = mail_tag['href'] if mail_tag else kv.get('E-mail', '')

                phone = kv.get('Telefónne čislo') or kv.get('Mobil') or kv.get('Telefón') or kv.get('Tel') or ''
                addr = kv.get('Sídlo') or kv.get('Poštová adresa') or ''

                results.append({
                    'company': name,
                    'phone': clean_phone(phone),
                    'website': web,
                    'email': clean_email(mail),
                    'address': addr,
                    'source': 'instituciafiriem.sk'
                })

            offset += 20
            if len(items) < 20:
                break
        except Exception as e:
            print(f"[-] Lỗi trang instituciafiriem offset {offset}: {e}")
            break

    print(f"    [+] Thu thập được: {len(results)} doanh nghiệp.")
    return results

def crawl_profesionalnyregister():
    print("[2/3] Đang cào dữ liệu từ: stavbari.profesionalnyregister.sk (Dịch vụ: kovovýroba)...")
    results = []
    offset = 0
    while True:
        data = {
            'ajax': '1',
            'page': 'tevekenyseg',
            'lng': 'sk',
            'SEARCH[URL_SERVICE]': 'kovovyroba',
            'ResultStart': str(offset),
            'ResultLimit': '20'
        }
        try:
            r = requests.post('https://stavbari.profesionalnyregister.sk/', data=data, headers=HEADERS, impersonate='chrome120', timeout=25)
            soup = BeautifulSoup(r.text, 'html.parser')
            headers = soup.select('.result-item-header')
            if not headers:
                break

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

                web_tag = item.select_one('a[href^="http"]:not([href*="profesionalnyregister"]):not([href^="mailto:"]):not([href^="tel:"])')
                web = web_tag['href'].strip() if web_tag else kv.get('Web', '')
                if web and not web.startswith(('http://', 'https://')):
                    web = 'http://' + web

                mail_tag = item.select_one('a[href^="mailto:"]')
                mail = mail_tag['href'] if mail_tag else kv.get('E-mail', '')

                phone = kv.get('Telefónne čislo') or kv.get('Mobil') or kv.get('Telefón') or kv.get('Tel') or ''
                addr = kv.get('Sídlo') or kv.get('Poštová adresa') or kv.get('Adresa') or ''

                results.append({
                    'company': name,
                    'phone': clean_phone(phone),
                    'website': web,
                    'email': clean_email(mail),
                    'address': addr,
                    'source': 'profesionalnyregister.sk'
                })

            offset += 20
            if len(headers) < 20:
                break
        except Exception as e:
            print(f"[-] Lỗi trang profesionalnyregister offset {offset}: {e}")
            break

    print(f"    [+] Thu thập được: {len(results)} doanh nghiệp.")
    return results

def crawl_europskefirmy():
    print("[3/3] Đang cào dữ liệu từ: europskefirmy.sk (Dịch vụ: kovovroba)...")
    results = []
    offset = 0
    while True:
        data = {
            'ajax': '1',
            'page': 'tevekenyseg',
            'lng': 'sk',
            'partnerSearchData[s_service]': 'kovovroba',
            'resultFrom': str(offset),
            'resultTo': '20',
            'search[orszag]': '1',
            'partners_order_sort': 'ASC',
            'selected_order_by': '1',
            'partners_order_by': '`portal_partners`.`name` ASC'
        }
        try:
            r = requests.post('https://europskefirmy.sk/', data=data, headers=HEADERS, impersonate='chrome120', timeout=25)
            soup = BeautifulSoup(r.text, 'html.parser')
            rh = soup.select_one('.resultHolder')
            if not rh:
                break

            h1_list = rh.select('h1')
            if not h1_list:
                break

            for h1 in h1_list:
                b = h1.select_one('b')
                name = b.get_text().strip() if b else h1.get_text().strip()
                if not name:
                    continue

                item = h1.find_next_sibling(class_='resultItem')
                if not item:
                    continue

                txt = item.get_text()

                web_tag = item.select_one('a[href^="http"]:not([href*="europskefirmy"]):not([href^="mailto:"]):not([href^="tel:"])')
                web = web_tag['href'].strip() if web_tag else ''
                if not web:
                    web_m = re.search(r'Web\s*:\s*([^\s\n\r]+)', txt)
                    if web_m:
                        web = web_m.group(1).strip()
                if web and not web.startswith(('http://', 'https://')):
                    web = 'http://' + web

                mail_tag = item.select_one('a[href^="mailto:"]')
                mail = mail_tag['href'] if mail_tag else ''
                if not mail:
                    mail_m = re.search(r'E-mail\s*:\s*([^\s\n\r]+)', txt)
                    if mail_m:
                        mail = mail_m.group(1).strip()

                phone_m = re.search(r'(?:Telefónne čislo|Mobil|Telefón|Tel)\s*:\s*([^\n\r]+?)(?:Fax|Web|E-mail|Služby|$)', txt)
                phone = phone_m.group(1).strip() if phone_m else ''

                addr_m = re.search(r'(?:Sídlo|Prevádzka)\s*:\s*([^\n\r]+?)(?:Telefónne|Mobil|Web|E-mail|Služby|$)', txt)
                addr = addr_m.group(1).strip() if addr_m else ''

                results.append({
                    'company': name,
                    'phone': clean_phone(phone),
                    'website': web,
                    'email': clean_email(mail),
                    'address': addr,
                    'source': 'europskefirmy.sk'
                })

            offset += 20
            if len(h1_list) < 20:
                break
        except Exception as e:
            print(f"[-] Lỗi trang europskefirmy offset {offset}: {e}")
            break

    print(f"    [+] Thu thập được: {len(results)} doanh nghiệp.")
    return results

def main():
    print("=" * 80)
    print("QUY TRINH CAO DU LIEU NGANH KOVOVYROBA (SLOVAKIA) & LOC TRUNG")
    print(f"File dau ra: {OUTPUT_CSV}")
    print("=" * 80)

    # 1. Thu thap tu ca 3 nguon
    all_raw = []
    all_raw.extend(crawl_instituciafiriem())
    all_raw.extend(crawl_profesionalnyregister())
    all_raw.extend(crawl_europskefirmy())

    total_crawled = len(all_raw)
    print("\n" + "-" * 80)
    print(f"[*] Tong so ban ghi thu thap duoc: {total_crawled}")

    # 2. Loc trung thong minh & Merge du lieu
    print("[*] Dang tien hanh loc trung va hop nhat thong tin...")
    deduped = {}
    domain_map = {}

    for item in all_raw:
        comp_raw = item['company']
        comp_clean = clean_company_name_sk(comp_raw)
        dom = extract_domain(item['website'])

        # Xac dinh key so khop
        key = None
        if comp_clean and len(comp_clean) >= 3:
            key = comp_clean
        elif dom:
            key = dom
        else:
            key = comp_raw.lower().strip()

        # Kiem tra trung domain da gap truoc do
        if dom and dom in domain_map:
            key = domain_map[dom]

        if key not in deduped:
            deduped[key] = dict(item)
            if dom:
                domain_map[dom] = key
        else:
            # Merge thong tin: uu tien bo sung phan con thieu
            existing = deduped[key]
            if not existing.get('email') and item.get('email'):
                existing['email'] = item['email']
            if not existing.get('website') and item.get('website'):
                existing['website'] = item['website']
            if not existing.get('phone') and item.get('phone'):
                existing['phone'] = item['phone']
            if not existing.get('address') and item.get('address'):
                existing['address'] = item['address']
            # Neu ten hien tai co day du dau / legal form hon
            if len(item['company']) > len(existing['company']):
                existing['company'] = item['company']
            # Ghi nhan nguon da cao
            if item['source'] not in existing['source']:
                existing['source'] += f" + {item['source']}"

    unique_companies = list(deduped.values())
    print(f"[+] So luong doanh nghiep duy nhat sau loc trung: {len(unique_companies)} (Da loai bo {total_crawled - len(unique_companies)} ban ghi trung lap)")

    # 3. Phan loai & Day 100% doanh nghiep co Email len dau (Quy chuan Rule 3)
    with_email = [c for c in unique_companies if c.get('email')]
    without_email = [c for c in unique_companies if not c.get('email')]

    sorted_companies = with_email + without_email

    # 4. Format theo chuan 18 cot Workspace
    rows_to_save = []
    for idx, c in enumerate(sorted_companies, start=1):
        row = {
            'No.': idx,
            'Công ty': c['company'],
            'SĐT': c['phone'],
            'Liên Hệ': c['website'],
            'Email': c['email'],
            'Liên Hệ mail': '',
            'Địa chỉ': c['address'],
            'Lương': '',
            'Ngày đăng': '',
            'Hạn tuyển': '',
            'Check gửi': 'OK' if c['email'] else '',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '0',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': f"Kovovýroba (Slovakia) [{c['source']}]"
        }
        rows_to_save.append(row)

    # 5. Xuat tep CSV UTF-8 with BOM
    temp_path = OUTPUT_CSV + ".tmp"
    with open(temp_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows_to_save)

    if os.path.exists(OUTPUT_CSV):
        try:
            os.remove(OUTPUT_CSV)
        except Exception:
            pass
    os.rename(temp_path, OUTPUT_CSV)

    print("\n" + "=" * 80)
    print("HOAN TAT CAO DU LIEU & XUAT TEP CHUAN 17 KY TU!")
    print(f"File dau ra: {OUTPUT_CSV}")
    print(f"Tong so doanh nghiep: {len(rows_to_save)}")
    print(f" - Co Email (nam ngay dau file) : {len(with_email)}")
    print(f" - Chua co Email               : {len(without_email)}")
    print(f" - Co Website                  : {sum(1 for c in rows_to_save if c['Liên Hệ'])}")
    print(f" - Co SĐT                      : {sum(1 for c in rows_to_save if c['SĐT'])}")
    print("=" * 80)

if __name__ == '__main__':
    main()
