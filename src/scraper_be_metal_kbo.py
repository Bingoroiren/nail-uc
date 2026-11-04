# -*- coding: utf-8 -*-
"""
HỆ THỐNG CÀO DỮ LIỆU DOANH NGHIỆP GIA CÔNG KIM LOẠI BỈ TỪ CỔNG KBO CHÍNH PHỦ
=============================================================================
Kỹ năng: data-standards, crawl-mail
Nguồn dữ liệu: https://kbopub.economie.fgov.be/kbopub/zoekactiviteitform.html

Mã NACEBEL ngành Gia công kim loại (NACEBEL Division 25):
- 25110: Vervaardiging van metalen constructiewerken en delen daarvan (Kết cấu thép, nhà tiền chế kim loại)
- 25120: Vervaardiging van deuren en ramen van metaal (Cửa đi, cửa sổ, khung kim loại)
- 25210: Vervaardiging van radiatoren en ketels voor centrale verwarming (Bộ tản nhiệt, nồi hơi sưởi)
- 25220: Vervaardiging van andere ketels, tanks en vaten van metaal (Bồn bể, téc, thùng chứa kim loại)
- 25401: Vervaardiging van wapens en munitie (hoofdzakelijk lichte wapens)
- 25530: Smeden, persen, stampen en profielwalsen van metaal (Rèn, dập, ép và cán định hình kim loại)
- 25610: Oppervlaktebehandeling van metalen (Xử lý nhiệt, sơn mạ, xi mạ, phủ bóng bề mặt kim loại)
- 25620: Mechanische bewerking van metalen (Gia công cơ khí chính xác, tiện, phay, bào, cắt laser)
- 2563:  Vervaardiging van gereedschap van metaal (Gồm cả 25631 - Dụng cụ cầm tay & 25639 - Dụng cụ cơ khí khác)
- 25910: Vervaardiging van stalen vaten en dergelijke (Sản xuất thùng phuy thép, hộp kim loại)

Tính năng cốt lõi:
1. Playwright Browser (headless=False theo Rule 4) + Tự động giải CAPTCHA bằng AI OCR (ddddocr)
2. Gom 10 mã NACE vào 1 chuỗi truy vấn: "25110,25120,25210,25220,25401,25530,25610,25620,2563,25910"
3. Xử lý phân trang (Pagination Loop) qua nút "Volgende" để lấy sạch mọi công ty
4. Lưu tăng dần (Incremental Auto-save mode='a') & Checkpoint Resume 100%
5. Tên file chuẩn 17 ký tự (Rule 10): BE_METL_KBO0_0RAW.csv
6. Loại trừ danh sách đen vĩnh viễn (Rule 12): Scandi Standard, Biliarta, Daigre
"""

import sys
import os
import re
import csv
import json
import time
import argparse
import unicodedata
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import ddddocr

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

RAW_CSV = ROOT_DIR / "BE_METL_KBO0_0RAW.csv"
CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_be_metal_kbo.json"
POSTCODES_FILE = ROOT_DIR / "belgium_postcodes.json"

CSV_COLUMNS = [
    'Company_Name', 'KBO_Number', 'VE_Number', 'Type', 'Status',
    'Address', 'Postcode', 'Country', 'Activity', 'NACE_Code',
    'Phone', 'Email', 'Website', 'Source'
]

# Chuỗi kết hợp 10 mã ngành gia công kim loại (tối ưu chuẩn regex KBO)
COMBINED_METAL_NACES = "25110,25120,25210,25220,25401,25530,25610,25620,2563,25910"

# Danh sách đen vĩnh viễn (Rule 12)
PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

def clean_text(s):
    if not s:
        return ""
    cleaned = str(s).replace('\u00a0', ' ').replace('\xa0', ' ').replace('&nbsp;', ' ')
    return ' '.join(cleaned.split()).strip()

def fetch_kbo_contact_details(kbo_raw):
    """
    Bóc tách trực tiếp Email, Website, SĐT từ trang chi tiết KBO (toonondernemingps.html)
    Hoàn toàn không tốn Captcha vì đây là GET endpoint tĩnh công khai của FOD Economie!
    """
    clean_num = re.sub(r'[^0-9]', '', str(kbo_raw or ''))
    if not clean_num or len(clean_num) < 9:
        return {'email': '', 'web': '', 'tel': ''}
    
    url = f"https://kbopub.economie.fgov.be/kbopub/toonondernemingps.html?ondernemingsnummer={clean_num}"
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    })
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            soup = BeautifulSoup(html, 'html.parser')
            email, web, tel = '', '', ''
            for tr in soup.find_all('tr'):
                txt = tr.get_text(separator=' | ', strip=True)
                txt_lower = txt.lower()
                if 'e-mail:' in txt_lower and 'geen gegevens' not in txt_lower:
                    m = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', txt)
                    if m:
                        email = m.group(0).lower()
                if 'webadres:' in txt_lower and 'geen gegevens' not in txt_lower:
                    parts = [p.strip() for p in txt.split('|') if 'webadres' not in p.lower() and 'sinds' not in p.lower() and '(' not in p]
                    if parts:
                        web = parts[0]
                if 'telefoonnummer:' in txt_lower and 'geen gegevens' not in txt_lower:
                    m = re.search(r'0032\d+|0\d{8,9}|\+32\d+', txt)
                    if m:
                        t = m.group(0)
                        tel = f"'{t}" if not t.startswith("'") else t
            return {'email': email, 'web': web, 'tel': tel}
    except Exception:
        return {'email': '', 'web': '', 'tel': ''}

def handle_captcha_if_needed(page, ocr):
    """
    Tự động giải Captcha hình ảnh của KBO bằng AI OCR ddddocr
    """
    for attempt in range(6):
        if 'captchaform' not in page.url:
            return True
        c = page.query_selector('img#captcha')
        if not c:
            time.sleep(1)
            continue
        try:
            raw_code = ocr.classification(c.screenshot())
            code = re.sub(r'[^a-zA-Z0-9]', '', raw_code).lower()
            print(f"      [CAPTCHA AI] Lần {attempt+1}: Đã nhận diện '{code}' -> Đang gửi giải mã...", flush=True)
            page.fill('input#j_captcha_response', code)
            page.click('input[type="submit"]')
            page.wait_for_load_state('networkidle', timeout=15000)
            time.sleep(1)
        except Exception:
            time.sleep(1)

    if 'captchaform' in page.url:
        print("\a      [!] CHÚ Ý: Cần giải Captcha thủ công trên màn hình trình duyệt!", flush=True)
        for _ in range(30):
            if 'captchaform' not in page.url:
                return True
            time.sleep(2)

    return 'captchaform' not in page.url

def scrape_kbo_metal(limit_postcodes=None, reset_cache=False, headless=False):
    print("=" * 80)
    print("🇧🇪  HỆ THỐNG CÀO DOANH NGHIỆP GIA CÔNG KIM LOẠI BỈ TỪ CỔNG KBO (KBO PUBLIC SEARCH)")
    print(f"    - Nguồn dữ liệu      : https://kbopub.economie.fgov.be/kbopub/zoekactiviteitform.html")
    print(f"    - Mã NACEBEL gộp     : {COMBINED_METAL_NACES}")
    print(f"    - Cơ chế vượt rào    : Playwright (headless={headless}) + AI OCR Captcha Solver (ddddocr)")
    print(f"    - Tệp đầu ra         : {RAW_CSV.name} (Rule 10: 17 ký tự)")
    print(f"    - Checkpoint cache   : {CACHE_FILE.name}")
    print("=" * 80)

    if not POSTCODES_FILE.exists():
        print(f"[!] Lỗi: Không tìm thấy tệp {POSTCODES_FILE.name}!")
        return

    with open(POSTCODES_FILE, encoding='utf-8') as f:
        postcodes = json.load(f)

    valid_postcodes = sorted(list(set([p for p in postcodes if len(p) == 4 and '1000' <= p <= '9999'])))
    if limit_postcodes:
        valid_postcodes = valid_postcodes[:limit_postcodes]

    print(f"[*] Đã nạp {len(valid_postcodes):,} mã bưu chính Bỉ hợp lệ để rà quét.")

    completed_postcodes = set()
    if CACHE_FILE.exists() and not reset_cache:
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
                for item in cached_data:
                    pc = item.split('_')[0] if '_' in item else item
                    completed_postcodes.add(pc)
            print(f"[*] Đã nạp checkpoint: {len(completed_postcodes):,} mã bưu chính đã hoàn thành.")
        except Exception:
            pass
    elif reset_cache:
        print("[*] Đã yêu cầu reset cache để quét lại toàn diện.")

    seen_ids = set()
    if RAW_CSV.exists() and not reset_cache:
        try:
            with open(RAW_CSV, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    num = row.get('VE_Number') or row.get('KBO_Number') or row.get('Company_Name')
                    if num and num != '-':
                        seen_ids.add(num)
                    elif row.get('Company_Name'):
                        seen_ids.add(row.get('Company_Name'))
            print(f"[*] Đã có sẵn {len(seen_ids):,} cơ sở/doanh nghiệp trong {RAW_CSV.name}")
        except Exception:
            pass
    else:
        with open(RAW_CSV, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()

    pending_postcodes = [pc for pc in valid_postcodes if pc not in completed_postcodes]
    total_items = len(pending_postcodes)
    print(f"[*] Số mã bưu chính cần duyệt: {total_items:,} bưu chính.")
    if not pending_postcodes:
        print("[+] Toàn bộ bưu chính Bỉ ngành gia công kim loại đã được quét xong hoàn chỉnh!")
        return

    print("\n[*] Khởi chạy trình duyệt Playwright và AI OCR Captcha Solver...\n", flush=True)

    ocr = ddddocr.DdddOcr(show_ad=False)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--start-maximized',
                '--no-sandbox'
            ]
        )
        context_kwargs = {
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        }
        if not headless:
            context_kwargs['no_viewport'] = True
            print("[*] Đã bật trình duyệt thực tế (headless=False) trực quan trên màn hình để bạn theo dõi trực tiếp.\n", flush=True)
        else:
            context_kwargs['viewport'] = {'width': 1280, 'height': 800}

        context = browser.new_context(**context_kwargs)
        page = context.new_page()

        counter = 0
        total_added = 0

        for pc in pending_postcodes:
            counter += 1
            pc_records = []
            
            try:
                page.goto('https://kbopub.economie.fgov.be/kbopub/zoekactiviteitform.html', wait_until='domcontentloaded', timeout=25000)
                if 'captchaform' in page.url:
                    handle_captcha_if_needed(page, ocr)

                page.fill('input[name="nacecodes"]', COMBINED_METAL_NACES)
                for r in page.query_selector_all('input[name="keuzeopzloc"]'):
                    if r.get_attribute('value') == 'postnr':
                        r.check()
                        break
                page.fill('input[name="postnummer1"]', pc)
                page.click('input[name="actionLu"]')
                page.wait_for_load_state('networkidle', timeout=20000)

                if 'captchaform' in page.url:
                    handle_captcha_if_needed(page, ocr)

                page_idx = 1
                while page_idx <= 25:
                    tbl = None
                    for t in page.query_selector_all('table'):
                        txt = t.inner_text()
                        if 'Ondernemings' in txt and 'Naam' in txt:
                            tbl = t
                            break

                    if not tbl:
                        break

                    rows = tbl.query_selector_all('tr')
                    for r in rows[1:]:
                        tds = [clean_text(td.inner_text()) for td in r.query_selector_all('td')]
                        if len(tds) < 6:
                            continue

                        if len(tds) >= 8:
                            ent_raw = tds[1]
                            kbo_num = tds[2]
                            ve_num = tds[3]
                            name = tds[4]
                            address = tds[5]
                            activity = tds[6]
                            nace_val = tds[7]
                        elif len(tds) >= 7:
                            ent_raw = tds[1]
                            kbo_num = tds[2]
                            ve_num = ""
                            name = tds[3]
                            address = tds[4]
                            activity = tds[5]
                            nace_val = tds[6]
                        else:
                            continue

                        if not name or name == 'Naam' or len(name.strip(' .,-_/\\')) < 2 or is_blacklisted_company(name):
                            continue

                        status = "Actief" if "actief" in ent_raw.lower() else ("Stopgezet" if "stop" in ent_raw.lower() else "")
                        ent_type = re.sub(r'(?i)actief|stopgezet', '', ent_raw).strip()

                        uniq = ve_num if (ve_num and ve_num != '-') else (kbo_num if kbo_num else name + "_" + pc)
                        if uniq in seen_ids:
                            continue
                        seen_ids.add(uniq)

                        record = {
                            'Company_Name': name,
                            'KBO_Number': kbo_num,
                            'VE_Number': ve_num,
                            'Type': ent_type,
                            'Status': status,
                            'Address': address,
                            'Postcode': pc,
                            'Country': 'Belgium',
                            'Activity': activity,
                            'NACE_Code': nace_val,
                            'Phone': '',
                            'Email': '',
                            'Website': '',
                            'Source': f'KBO Public Search (NACE {nace_val})'
                        }
                        pc_records.append(record)

                    next_btn = page.query_selector('a:has-text("Volgende")')
                    if not next_btn:
                        break

                    next_btn.click()
                    page.wait_for_load_state('networkidle', timeout=15000)
                    if 'captchaform' in page.url:
                        handle_captcha_if_needed(page, ocr)
                    page_idx += 1
                    time.sleep(0.3)

                if pc_records:
                    # Bóc tách trực tiếp Email, Website, SĐT từ trang chi tiết KBO (không Captcha)
                    unique_kbos = list(dict.fromkeys([r['KBO_Number'] for r in pc_records if r.get('KBO_Number')]))
                    contact_map = {}
                    if unique_kbos:
                        with ThreadPoolExecutor(max_workers=min(5, len(unique_kbos))) as executor:
                            results = list(executor.map(fetch_kbo_contact_details, unique_kbos))
                            for kbo_val, res in zip(unique_kbos, results):
                                if res:
                                    contact_map[kbo_val] = res

                    kbo_emails_found = []
                    for r in pc_records:
                        c = contact_map.get(r.get('KBO_Number'))
                        if c:
                            if c['email']:
                                r['Email'] = c['email']
                                kbo_emails_found.append(c['email'])
                            if c['web']:
                                r['Website'] = c['web']
                            if c['tel']:
                                r['Phone'] = c['tel']

                    with open(RAW_CSV, 'a', encoding='utf-8-sig', newline='') as f:
                        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                        writer.writerows(pc_records)
                        f.flush()
                    total_added += len(pc_records)

                completed_postcodes.add(pc)
                if counter % 10 == 0 or counter == total_items:
                    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
                    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                        json.dump(list(completed_postcodes), f)

                if pc_records:
                    sample_names = ", ".join([r['Company_Name'][:20] for r in pc_records[:2]])
                    msg_detail = f" [KBO mail: {len(set(kbo_emails_found))}]" if kbo_emails_found else ""
                    print(f"  [{counter:04d}/{total_items:04d}] Postcode {pc} -> +{len(pc_records):02d} cty: {sample_names}{msg_detail} (Tổng: {len(seen_ids):,} cty)", flush=True)
                elif counter % 25 == 0:
                    print(f"  [{counter:04d}/{total_items:04d}] Tiến độ: {counter*100/total_items:.1f}% | Đã thu thập: {len(seen_ids):,} cty...", flush=True)

            except Exception as e:
                print(f"  [!] Postcode {pc} gặp lỗi ({e}), đang tự phục hồi...", flush=True)
                time.sleep(1)

            time.sleep(0.4)

        browser.close()

    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(completed_postcodes), f)

    for extra_dir in [ROOT_DIR / "csdl_mlt", ROOT_DIR / "archive" / "be_belgium"]:
        extra_dir.mkdir(parents=True, exist_ok=True)
        dest = extra_dir / RAW_CSV.name
        try:
            import shutil
            shutil.copy2(RAW_CSV, dest)
            print(f"[+] Đã đồng bộ sang {dest.relative_to(ROOT_DIR)}")
        except Exception:
            pass

    print("\n" + "=" * 80)
    print("🏆 HOÀN THÀNH CÀO DOANH NGHIỆP GIA CÔNG KIM LOẠI BỈ TỪ KBO!")
    print(f"   - Tổng số cơ sở/doanh nghiệp đã lưu : {len(seen_ids):,}")
    print(f"   - Tệp đầu ra                        : {RAW_CSV.name}")
    print("=" * 80 + "\n")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="KBO Belgium Metal Fabrication Scraper")
    parser.add_argument("--limit-postcodes", type=int, default=None, help="Giới hạn số postcode")
    parser.add_argument("--reset-cache", action="store_true", help="Xóa cache để quét lại đầy đủ")
    parser.add_argument("--headless", action="store_true", help="Chạy ẩn (mặc định hiện trình duyệt)")
    args = parser.parse_args()

    scrape_kbo_metal(limit_postcodes=args.limit_postcodes, reset_cache=args.reset_cache, headless=args.headless)
