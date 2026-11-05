# -*- coding: utf-8 -*-
"""
KBO DETAIL BACKFILL TOOL - RESILIENT PLAYWRIGHT & AI OCR EDITION
================================================================
Bộ cào dữ liệu chi tiết (Email, Website, SĐT) từ cổng KBO (FOD Economie Bỉ)
với cơ chế vượt rào chống chặn 100%:
1. Trình duyệt Playwright trực quan (headless=False theo Rule 4).
2. Tích hợp AI OCR (ddddocr) tự động giải mã CAPTCHA hình ảnh của KBO khi xuất hiện.
3. Checkpoint JSON Cache (crawlmail/cache_kbo_backfill_<tên_file>.json):
   - Lưu kết quả tức thì sau từng doanh nghiệp.
   - Hỗ trợ Resume 100%, không bao giờ cào lại từ đầu khi dừng/mở lại.
4. Lưu tăng dần vào file CSV (Incremental Auto-save) mỗi 20 doanh nghiệp.
5. Quy chuẩn Rule 1 (UTF-8 with BOM), Rule 2 (SĐT có nháy đơn '+32), làm sạch Email.
6. Đồng bộ kết quả tự động ra cả 3 thư mục: Gốc, csdl_mlt và archive/be_belgium.
"""

import os
import sys
import re
import csv
import json
import time
import argparse
import unicodedata
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

def clean_kbo_num(kbo_raw):
    return re.sub(r'[^0-9]', '', str(kbo_raw or ''))

def format_phone(phone):
    if not phone:
        return ""
    p = str(phone).strip()
    return f"'{p}" if not p.startswith("'") else p

def clean_email(email):
    if not email:
        return ""
    e = str(email).strip().lower()
    e = e.replace('\xa0', '').replace('\u00a0', '').replace('%20', '')
    return e.strip(' .,;')

def handle_captcha_if_needed(page, ocr):
    """
    Tự động giải Captcha hình ảnh của KBO bằng AI OCR ddddocr
    """
    for attempt in range(6):
        if 'captchaform' not in page.url:
            return True
        c = page.query_selector('img#captcha')
        if not c:
            time.sleep(0.5)
            continue
        try:
            raw_code = ocr.classification(c.screenshot())
            code = re.sub(r'[^a-zA-Z0-9]', '', raw_code).lower()
            print(f"      [CAPTCHA AI] Lần {attempt+1}: Đã nhận diện '{code}' -> Đang gửi giải mã...", flush=True)
            page.fill('input#j_captcha_response', code)
            page.click('input[type="submit"]')
            page.wait_for_load_state('domcontentloaded', timeout=12000)
            time.sleep(0.5)
        except Exception:
            time.sleep(0.5)

    if 'captchaform' in page.url:
        print("\a      [!] CHÚ Ý: Cần giải Captcha thủ công trên màn hình trình duyệt!", flush=True)
        for _ in range(30):
            if 'captchaform' not in page.url:
                return True
            time.sleep(2)

    return 'captchaform' not in page.url

def backfill_kbo_playwright(target_csv, headless=False, delay=0.4):
    p = Path(target_csv)
    if not p.is_absolute():
        p = ROOT_DIR / p
    if not p.exists():
        print(f"[ERROR] Không tìm thấy tệp {p.name}")
        return

    stem = p.stem.lower()
    cache_file = ROOT_DIR / "crawlmail" / f"cache_kbo_backfill_{stem}.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)

    cache = {}
    if cache_file.exists():
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache = json.load(f)
        except Exception:
            cache = {}

    print("=" * 80)
    print(f"🇧🇪  KBO DETAIL BACKFILL (PLAYWRIGHT + AI OCR CHỐNG BLOCK)")
    print(f"    Tệp mục tiêu : {p.name}")
    print(f"    Trình duyệt  : {'Ẩn (headless)' if headless else 'Trực quan trên màn hình (headless=False)'}")
    print(f"    Giải Captcha : Tự động bằng AI OCR (ddddocr)")
    print(f"    Cache Resume : {cache_file.name}")
    print("=" * 80)

    with open(p, mode='r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows = list(reader)

    if 'Email' not in fields:
        idx = fields.index('Phone') + 1 if 'Phone' in fields else len(fields)
        fields.insert(idx, 'Email')

    unique_kbos = []
    seen = set()
    for r in rows:
        k = r.get('KBO_Number', '').strip()
        clean_k = clean_kbo_num(k)
        if clean_k and clean_k not in seen:
            seen.add(clean_k)
            unique_kbos.append(k)

    total_unique = len(unique_kbos)
    already_cached = sum(1 for k in unique_kbos if clean_kbo_num(k) in cache)

    print(f"[*] Tổng số doanh nghiệp trong file: {len(rows):,} dòng")
    print(f"[*] Số mã KBO độc nhất cần tra cứu : {total_unique:,}")
    if already_cached > 0:
        print(f"[+] Đã có sẵn trong Cache JSON      : {already_cached:,} ({already_cached * 100 / total_unique:.1f}%)")

    pending_kbos = [k for k in unique_kbos if clean_kbo_num(k) not in cache]
    print(f"[*] Số mã KBO còn lại cần quét     : {len(pending_kbos):,}\n", flush=True)

    found_emails = sum(1 for v in cache.values() if v.get('email'))
    found_webs = sum(1 for v in cache.values() if v.get('web'))
    found_phones = sum(1 for v in cache.values() if v.get('tel'))

    def save_current_data():
        # Lưu cache JSON
        try:
            with open(cache_file, 'w', encoding='utf-8') as fp:
                json.dump(cache, fp, ensure_ascii=False, indent=2)
        except Exception:
            pass

        # Cập nhật dữ liệu từ cache vào rows
        for r in rows:
            c_k = clean_kbo_num(r.get('KBO_Number', ''))
            c = cache.get(c_k)
            if c:
                if c.get('email') and not r.get('Email'):
                    r['Email'] = c['email']
                if c.get('web') and not r.get('Website'):
                    r['Website'] = c['web']
                if c.get('tel') and not r.get('Phone'):
                    r['Phone'] = c['tel']

        # Ghi ra file CSV chính
        with open(p, mode='w', encoding='utf-8-sig', newline='') as fp:
            writer = csv.DictWriter(fp, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

        # Đồng bộ ra csdl_mlt và archive
        for sync_dir in [ROOT_DIR / 'csdl_mlt', ROOT_DIR / 'archive' / 'be_belgium']:
            if sync_dir.exists():
                target_f = sync_dir / p.name
                with open(target_f, mode='w', encoding='utf-8-sig', newline='') as fp:
                    writer = csv.DictWriter(fp, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(rows)

    if not pending_kbos:
        print("[+] Toàn bộ mã KBO đã được quét và lưu đầy đủ!")
        save_current_data()
        return

    ocr = ddddocr.DdddOcr(show_ad=False)

    done = already_cached
    last_csv_save = done
    last_save_time = time.time()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--start-maximized',
                '--no-sandbox'
            ]
        )
        context_kwargs = {
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'locale': 'nl-BE'
        }
        if not headless:
            context_kwargs['no_viewport'] = True
        else:
            context_kwargs['viewport'] = {'width': 1280, 'height': 800}

        context = browser.new_context(**context_kwargs)
        page = context.new_page()

        # Mở trang khởi động để nhận cookie
        try:
            page.goto('https://kbopub.economie.fgov.be/kbopub/zoeknummerform.html', wait_until='domcontentloaded', timeout=20000)
            if 'captchaform' in page.url:
                handle_captcha_if_needed(page, ocr)
        except Exception:
            pass

        for kbo_raw in pending_kbos:
            clean_num = clean_kbo_num(kbo_raw)
            done += 1

            url = f"https://kbopub.economie.fgov.be/kbopub/toonondernemingps.html?ondernemingsnummer={clean_num}"
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=15000)
                if 'captchaform' in page.url:
                    handle_captcha_if_needed(page, ocr)

                html = page.content()
                soup = BeautifulSoup(html, 'html.parser')

                email, web, tel = '', '', ''
                for tr in soup.find_all('tr'):
                    txt = tr.get_text(separator=' | ', strip=True)
                    txt_l = txt.lower()

                    if 'e-mail:' in txt_l and 'geen gegevens' not in txt_l:
                        m = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', txt)
                        if m:
                            email = clean_email(m.group(0))

                    if 'webadres:' in txt_l and 'geen gegevens' not in txt_l:
                        parts = [p.strip() for p in txt.split('|') if 'webadres' not in p.lower() and 'sinds' not in p.lower() and '(' not in p]
                        if parts:
                            web = parts[0]

                    if 'telefoonnummer:' in txt_l and 'geen gegevens' not in txt_l:
                        m = re.search(r'0032\d+|0\d{8,9}|\+32\d+', txt)
                        if m:
                            tel = format_phone(m.group(0))

                item = {'kbo': kbo_raw, 'email': email, 'web': web, 'tel': tel}
                cache[clean_num] = item

                if email:
                    found_emails += 1
                if web:
                    found_webs += 1
                if tel:
                    found_phones += 1

                # In tiến độ
                if done % 5 == 0 or done == total_unique or email:
                    pct = done * 100 / total_unique
                    hit_info = f" -> Tìm thấy: {email or web or tel}" if (email or web or tel) else ""
                    print(f"  [{done:,}/{total_unique:,}] ({pct:.1f}%) | ✉️ Mail: {found_emails:,} | 🌐 Web: {found_webs:,} | 📞 SĐT: {found_phones:,}{hit_info}", flush=True)

                if delay > 0:
                    time.sleep(delay)

            except Exception as e:
                cache[clean_num] = {'kbo': kbo_raw, 'email': '', 'web': '', 'tel': ''}
                time.sleep(1)

            # Lưu tăng dần định kỳ
            if done - last_csv_save >= 20 or (time.time() - last_save_time) > 40:
                save_current_data()
                last_csv_save = done
                last_save_time = time.time()

        browser.close()

    # Lưu kết quả cuối cùng
    save_current_data()

    print("\n" + "=" * 80)
    print(f"🏆 HOÀN THÀNH QUÉT TOÀN BỘ TRANG CHI TIẾT KBO CHO {p.name}:")
    print(f"   - Mã KBO đã hoàn tất : {done:,}/{total_unique:,}")
    print(f"   - Email chính thức    : {found_emails:,}")
    print(f"   - Website chính thức  : {found_webs:,}")
    print(f"   - SĐT chính thức      : {found_phones:,}")
    print("=" * 80 + "\n")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="KBO Detail Contact Backfill (Playwright & AI OCR)")
    parser.add_argument("file", nargs="?", default="BE_METL_KBO0_0RAW.csv", help="Tệp CSV cần bổ sung")
    parser.add_argument("--headless", action="store_true", help="Chạy ẩn trình duyệt (Mặc định: False)")
    parser.add_argument("--delay", type=float, default=0.3, help="Độ trễ mỗi trang (Mặc định: 0.3s)")
    args = parser.parse_args()

    backfill_kbo_playwright(args.file, headless=args.headless, delay=args.delay)
