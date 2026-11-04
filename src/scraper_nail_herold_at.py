# -*- coding: utf-8 -*-
"""
HỆ THỐNG CÀO DỮ LIỆU DANH BẠ VÀNG HEROLD.AT CHO TIỆM NAIL ÁO (AT_NAIL_HERO)
=============================================================================
Nguồn: https://www.herold.at/gelbe-seiten/nagelstudio/?term=Nagelstudio
Quy mô: 73 trang toàn quốc (~1.400+ tiệm nail)
Đặc thù: Cực kỳ giàu Email, SĐT, Website và địa chỉ chuẩn Schema.org
"""

import sys
import os
import re
import csv
import json
import time
import unicodedata
from pathlib import Path
from bs4 import BeautifulSoup
import curl_cffi.requests as requests

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_RAW_CSV = DATA_DIR / "AT_NAIL_HERO_0RAW.csv"
OUTPUT_RAW_JSON = DATA_DIR / "AT_NAIL_HERO_0RAW.json"
CHECKLIST_FILE = ROOT_DIR / "progress" / "progress_nail_herold_at.json"
CHECKLIST_FILE.parent.mkdir(parents=True, exist_ok=True)

ROOT_RAW_CSV = ROOT_DIR / "AT_NAIL_HERO_0RAW.csv"

BASE_URL = "https://www.herold.at/gelbe-seiten/nagelstudio/"
TOTAL_PAGES = 73

PERMANENT_BLACKLIST = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta', 'daigre', 'daigrė'
]

def is_blacklisted(name):
    if not name:
        return False
    norm = unicodedata.normalize('NFKD', str(name)).lower()
    clean = ''.join(c for c in norm if not unicodedata.combining(c))
    return any(b in clean for b in PERMANENT_BLACKLIST)

def clean_phone(p):
    if not p:
        return ""
    p_str = str(p).replace('\ue0b0', '').replace('\n', '').replace('\r', '').strip().strip("'")
    p_clean = re.sub(r'[^\d+\s]', '', p_str).strip()
    p_clean = re.sub(r'\s+', ' ', p_clean)
    return f"'{p_clean}" if p_clean else ""

def clean_email(email):
    if not email or not isinstance(email, str):
        return ""
    em = email.strip()
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\ufeff', '\u202f', '\u3000']:
        em = em.replace(bad, '')
    em = re.sub(r'^(?:mailto:|https?://)\s*', '', em, flags=re.I)
    em = re.sub(r'\s+', '', em)
    em = em.strip(" .,;:\"'<>[](){}\\/").lower()
    if re.match(r'^[a-zA-Z0-9._%+-]{1,64}@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}$', em):
        return em
    return ""

def load_checkpoint():
    if CHECKLIST_FILE.exists():
        try:
            with open(CHECKLIST_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {"completed_pages": [], "last_page": 0}

def save_checkpoint(data):
    try:
        with open(CHECKLIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[-] Lỗi lưu checkpoint: {e}")

def load_existing_results():
    if OUTPUT_RAW_JSON.exists():
        try:
            with open(OUTPUT_RAW_JSON, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_results(results):
    if not results:
        return
    valid_results = [r for r in results if not is_blacklisted(r.get("name", ""))]
    
    with open(OUTPUT_RAW_JSON, 'w', encoding='utf-8') as f:
        json.dump(valid_results, f, ensure_ascii=False, indent=2)

    fieldnames = [
        "source", "category", "name", "street", "postal_code",
        "city", "phone", "email", "website", "detail_url"
    ]
    for path in [OUTPUT_RAW_CSV, ROOT_RAW_CSV]:
        try:
            with open(path, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for r in valid_results:
                    row = {k: r.get(k, "") for k in fieldnames}
                    row["phone"] = clean_phone(row.get("phone", ""))
                    row["email"] = clean_email(row.get("email", ""))
                    writer.writerow(row)
        except PermissionError:
            print(f"  [!] File {path.name} đang mở, sẽ ghi đè ở lần sau.")
        except Exception as e:
            print(f"[-] Lỗi ghi file {path.name}: {e}")

def scrape_herold_page(page_num):
    if page_num == 1:
        url = BASE_URL
    else:
        url = f"{BASE_URL}seite/{page_num}/"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'de-AT,de;q=0.9,en;q=0.8'
    }

    try:
        r = requests.get(url, headers=headers, impersonate="chrome120", timeout=12)
        if r.status_code != 200:
            print(f"  [!] HTTP {r.status_code} tại trang {page_num}")
            return []
    except Exception as e:
        print(f"  [-] Lỗi kết nối trang {page_num}: {e}")
        return []

    soup = BeautifulSoup(r.text, 'html.parser')
    items = soup.select('.location-search-result')
    results = []

    for it in items:
        # 1. Trích xuất Schema.org meta
        name_meta = it.select_one('meta[itemprop="name"]')
        name = name_meta['content'].strip() if name_meta and name_meta.get('content') else ""
        if not name:
            h2 = it.find(['h2', 'h3'])
            name = h2.get_text().strip() if h2 else ""

        if not name:
            continue

        street_meta = it.select_one('meta[itemprop="streetAddress"]')
        street = street_meta['content'].strip() if street_meta and street_meta.get('content') else ""

        plz_meta = it.select_one('meta[itemprop="postalCode"]')
        postal_code = plz_meta['content'].strip() if plz_meta and plz_meta.get('content') else ""

        city_meta = it.select_one('meta[itemprop="addressRegion"]')
        city = city_meta['content'].strip() if city_meta and city_meta.get('content') else ""

        # 2. SĐT
        tel_link = it.find('a', href=lambda h: h and 'tel:' in h)
        phone = tel_link['href'].replace('tel:', '').strip() if tel_link else ""
        if not phone and tel_link:
            phone = tel_link.get_text().strip()

        # 3. Email
        mail_link = it.find('a', href=lambda h: h and 'mailto:' in h)
        raw_mail = mail_link['href'].replace('mailto:', '').split('?')[0].strip() if mail_link else ""
        email = clean_email(raw_mail)

        # 4. Website
        web_link = it.find('a', href=lambda h: h and h.startswith(('http://', 'https://')) and 'herold.at' not in h)
        website = web_link['href'].strip() if web_link else ""

        # 5. Detail link
        detail_link = it.find('a', href=lambda h: h and '/gelbe-seiten/' in h and len(h.split('/')) >= 5)
        detail_url = ""
        if detail_link:
            dh = detail_link['href'].strip()
            detail_url = f"https://www.herold.at{dh}" if dh.startswith('/') else dh

        results.append({
            "source": "Herold Gelbe Seiten",
            "category": "Nagelstudio",
            "name": name,
            "street": street,
            "postal_code": postal_code,
            "city": city,
            "phone": clean_phone(phone),
            "email": email,
            "website": website,
            "detail_url": detail_url
        })

    return results

def run_herold_scraper():
    print("=" * 80)
    print("🇦🇹  HỆ THỐNG CÀO TIỆM NAIL HEROLD.AT TOÀN NƯỚC ÁO (HEROLD GELBE SEITEN)")
    print(f"    - URL Gốc      : {BASE_URL}")
    print(f"    - Tổng số trang: {TOTAL_PAGES} trang")
    print(f"    - File kết quả : {OUTPUT_RAW_CSV.name}")
    print("=" * 80)

    checkpoint = load_checkpoint()
    existing_results = load_existing_results()
    seen_keys = { (r["name"].lower().strip(), r.get("city", "").lower().strip()) for r in existing_results }
    all_results = list(existing_results)

    completed_pages = set(checkpoint.get("completed_pages", []))
    print(f"[*] Đã nạp {len(all_results):,} tiệm nail sẵn có ({len(completed_pages)}/{TOTAL_PAGES} trang đã cào).")

    new_companies = 0
    new_emails = 0

    for page_num in range(1, TOTAL_PAGES + 1):
        if page_num in completed_pages:
            continue

        print(f"[{page_num:02d}/{TOTAL_PAGES:02d}] Đang tải trang {page_num}...", end="", flush=True)
        t0 = time.time()
        page_items = scrape_herold_page(page_num)
        dur = time.time() - t0

        added_on_page = 0
        emails_on_page = 0
        for item in page_items:
            k = (item["name"].lower().strip(), item.get("city", "").lower().strip())
            if k not in seen_keys:
                seen_keys.add(k)
                all_results.append(item)
                added_on_page += 1
                if item.get("email"):
                    emails_on_page += 1

        new_companies += added_on_page
        new_emails += emails_on_page
        completed_pages.add(page_num)

        checkpoint["completed_pages"] = sorted(list(completed_pages))
        checkpoint["last_page"] = page_num
        save_checkpoint(checkpoint)

        print(f" -> Lấy được {len(page_items):2d} tiệm (+{added_on_page} mới, {emails_on_page} có email) ({dur:.1f}s)", flush=True)

        # Lưu tăng dần mỗi 5 trang
        if page_num % 5 == 0 or page_num == TOTAL_PAGES:
            save_results(all_results)
            tot_em = sum(1 for r in all_results if r.get("email"))
            print(f"  💾 [Auto-Save Checkpoint] Tích lũy: {len(all_results):,} tiệm ({tot_em:,} có email) đã lưu an toàn.")

        time.sleep(0.4)

    save_results(all_results)
    total_emails = sum(1 for r in all_results if r.get("email"))

    print("\n" + "=" * 80)
    print("🏆 HOÀN THÀNH CÀO HEROLD.AT TOÀN BỘ 73 TRANG NƯỚC ÁO:")
    print(f"   - Tổng số tiệm nail thu thập được : {len(all_results):,} tiệm")
    print(f"   - TỔNG SỐ TIỆM CÓ EMAIL XÁC THỰC  : {total_emails:,} tiệm ({total_emails/max(1, len(all_results))*100:.1f}%)")
    print(f"   - File kết quả thô                 : {OUTPUT_RAW_CSV.name}")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    run_herold_scraper()

