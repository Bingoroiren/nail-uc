# -*- coding: utf-8 -*-
"""
ENGINE CÀO GOOGLE MAPS: TIỆM NAIL & THẨM MỸ VIỆN TẠI PHÁP (FRANCE NAIL SALONS)
=============================================================================
Thị trường: Pháp (France - FR)
Từ khóa: "Institut de beauté", "Salon de manucure", "Bar à ongles", "Onglerie", "Nail salon"
Quy chuẩn GEMINI.md & skill scrape-maps:
- Playwright Chromium trực quan (headless=False) với viewport 1280x800
- Tọa độ 70 cụm đô thị tại 13 vùng nước Pháp (locations_fr.py)
- Lưu tăng dần từng dòng vào FR_NAIL_GMAP_0RAW.csv (Rule 5)
- Checkpoint tiến trình progress/progress_nail_fr.json (Resume 100%)
- Lọc địa chỉ Pháp nghiêm ngặt (Mã bưu chính 5 số, vùng/thành phố Pháp)
- SĐT luôn có dấu nháy đơn (') (Rule 2)
- Tự động vượt qua Google Consent / Cookie dialog bằng tiếng Pháp / Anh
- Bắt Captcha an toàn, hiển thị cửa sổ trực quan và rung chuông \\a (Rule 4)
- Loại trừ danh sách đen vĩnh viễn (Rule 12)
"""

import asyncio
import csv
import os
import random
import re
import sys
import json
import urllib.parse
import unicodedata
from datetime import datetime
from playwright.async_api import async_playwright

# Import cấu hình và danh sách vị trí
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config_nail_fr
import locations_fr

# Đảm bảo console UTF-8 trên Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROGRESS_FILE = os.path.join(ROOT_DIR, "progress", "progress_nail_fr.json")

# Danh sách đen cố định (Rule 12)
PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

FIELDNAMES = [
    'Name', 'Category', 'Address', 'Phone', 'Website', 'Rating',
    'Reviews_Count', 'Place_ID', 'URL', 'Search_Query', 'Location_Name',
    'Department', 'Region', 'Scraped_At'
]

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

def extract_place_id(url):
    if not url:
        return ""
    match = re.search(r'1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)', url)
    if match:
        return match.group(1).lower()
    return url.split('?')[0].lower()

def get_scraped_place_ids():
    scraped = set()
    for csv_file in [config_nail_fr.OUTPUT_CSV, config_nail_fr.ROOT_OUTPUT_CSV]:
        if os.path.exists(csv_file):
            try:
                with open(csv_file, mode='r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        pid = row.get('Place_ID') or extract_place_id(row.get('URL', ''))
                        if pid:
                            scraped.add(pid.lower())
            except Exception as e:
                print(f"[-] Lỗi đọc file CSV hiện tại ({csv_file}): {e}", flush=True)
    return scraped

def is_france_address(address):
    """Xác thực địa chỉ nằm trên lãnh thổ nước Pháp (France)."""
    if not address:
        return False
    addr_lower = address.lower()
    
    # 1. Tên quốc gia
    if any(k in addr_lower for k in ["france", ", fr", " fra"]):
        return True
    
    # 2. Mã bưu chính Pháp (5 chữ số chuẩn vd: 75001, 69001, 13001, 31000...)
    if re.search(r'\b(?:0[1-9]|[1-8][0-9]|9[0-8]|2[abAB])[0-9]{3}\b', address):
        return True
    
    # 3. Các vùng / thành phố lớn của Pháp
    fr_regions = [
        "paris", "lyon", "marseille", "toulouse", "nice", "nantes", "strasbourg",
        "montpellier", "bordeaux", "lille", "rennes", "reims", "toulon", "saint-étienne",
        "le havre", "grenoble", "dijon", "angers", "nîmes", "villeurbanne", "clermont-ferrand",
        "le mans", "aix-en-provence", "brest", "tours", "amiens", "limoges", "annecy", "perpignan",
        "boulogne-billancourt", "nanterre", "saint-denis", "créteil", "versailles", "courbevoie",
        "îles-de-france", "île-de-france", "auvergne", "rhône", "occitanie", "aquitaine",
        "bretagne", "normandie", "alsace", "grand est", "paca", "provence", "côte d'azur"
    ]
    if any(r in addr_lower for r in fr_regions):
        return True
        
    return False

def clean_phone_fr(raw_phone):
    """Chuẩn hóa số điện thoại Pháp, bắt buộc nháy đơn (') theo Rule 2."""
    if not raw_phone:
        return ""
    p = str(raw_phone).strip()
    p = re.sub(r'^tel:\s*', '', p, flags=re.I)
    return f"'{p}" if not p.startswith("'") else p

def init_csv():
    """Khởi tạo các file CSV nếu chưa tồn tại (Rule 1: utf-8-sig, CSV only)."""
    for out_path in [config_nail_fr.OUTPUT_CSV, config_nail_fr.ROOT_OUTPUT_CSV]:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
            with open(out_path, mode='w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
                writer.writeheader()

def save_single_row(row_data):
    """Ghi tăng dần trực tiếp từng dòng vào CSV (Rule 5: Incremental Auto-Save)."""
    for out_path in [config_nail_fr.OUTPUT_CSV, config_nail_fr.ROOT_OUTPUT_CSV]:
        try:
            with open(out_path, mode='a', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
                writer.writerow(row_data)
                f.flush()
        except Exception as e:
            print(f"[-] Lỗi ghi file CSV ({out_path}): {e}", flush=True)

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[-] Lỗi đọc progress file: {e}", flush=True)
    return {"completed_queries": [], "total_scraped": 0}

def save_progress(progress_data):
    os.makedirs(os.path.dirname(os.path.abspath(PROGRESS_FILE)), exist_ok=True)
    try:
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[-] Lỗi lưu checkpoint: {e}", flush=True)

async def handle_captcha(page):
    current_url = page.url.lower()
    page_content = await page.content()
    if "sorry" in current_url or "captcha" in current_url or "recaptcha" in page_content.lower() or "unusual traffic" in page_content.lower():
        print("\a" * 3)  # Rung chuông cảnh báo
        print("\n" + "=" * 70, flush=True)
        print("[!] PHÁT HIỆN CAPTCHA! Vui lòng thao tác giải Captcha trên cửa sổ trình duyệt...", flush=True)
        print("=" * 70 + "\n", flush=True)
        while True:
            await asyncio.sleep(5)
            c_url = page.url.lower()
            c_content = await page.content()
            if "sorry" not in c_url and "captcha" not in c_url and "unusual traffic" not in c_content.lower():
                print("[+] Captcha đã được giải quyết! Đang tiếp tục cào...", flush=True)
                break

async def bypass_consent_screen(page):
    """Vượt qua màn hình Consent / Cookie của Google (tiếng Pháp và tiếng Anh)."""
    try:
        consent_buttons = page.locator(
            'button:has-text("Tout accepter"), button:has-text("J\'accepte"), '
            'button:has-text("Accepter tout"), button:has-text("Accept all"), '
            'button:has-text("I agree"), form:has(button) button:has-text("Accepter")'
        )
        if await consent_buttons.count() > 0:
            await consent_buttons.first.click()
            await page.wait_for_timeout(1000)
    except Exception:
        pass

async def extract_details(page, url, search_query, loc_info):
    name = ""
    try:
        h1 = page.locator(config_nail_fr.SELECTORS["business_name"])
        if await h1.count() > 0:
            name = (await h1.first.inner_text()).strip()
    except Exception:
        pass

    if not name or is_blacklisted_company(name):
        return None

    # Danh mục Google Maps
    category = ""
    try:
        cat_loc = page.locator(config_nail_fr.SELECTORS["category"])
        if await cat_loc.count() > 0:
            category = (await cat_loc.first.inner_text()).strip()
    except Exception:
        pass

    # Bộ lọc danh mục tiệm nail / làm đẹp
    if config_nail_fr.ALLOWED_CATEGORIES and category:
        match_cat = any(ac.lower() in category.lower() or category.lower() in ac.lower() for ac in config_nail_fr.ALLOWED_CATEGORIES)
        if not match_cat:
            nail_terms = ["ongle", "manucure", "beauté", "beaute", "esthétique", "esthetique", "nail", "spa", "cosmétique", "cosmetique", "pédicure", "pedicure", "coiffure"]
            if not any(t in category.lower() for t in nail_terms):
                return None

    # Địa chỉ
    address = ""
    try:
        addr_loc = page.locator(config_nail_fr.SELECTORS["address"])
        if await addr_loc.count() > 0:
            address = (await addr_loc.first.inner_text()).strip()
    except Exception:
        pass

    if address and not is_france_address(address):
        return None

    # SĐT: Bắt buộc nháy đơn (') theo Rule 2
    phone = ""
    try:
        phone_loc = page.locator(config_nail_fr.SELECTORS["phone"])
        if await phone_loc.count() > 0:
            phone_raw = (await phone_loc.first.inner_text()).strip()
            phone = clean_phone_fr(phone_raw)
    except Exception:
        pass

    # Website
    website = ""
    try:
        web_loc = page.locator(config_nail_fr.SELECTORS["website"])
        if await web_loc.count() > 0:
            website = (await web_loc.first.get_attribute("href") or "").strip()
    except Exception:
        pass

    # Đánh giá & Số lượng reviews
    rating = ""
    reviews_count = ""
    try:
        r_loc = page.locator(config_nail_fr.SELECTORS["rating"])
        if await r_loc.count() > 0:
            rating = (await r_loc.first.inner_text()).strip()
        rev_loc = page.locator(config_nail_fr.SELECTORS["reviews_count"])
        if await rev_loc.count() > 0:
            rev_txt = (await rev_loc.first.inner_text()).strip()
            m = re.search(r'\d[\d\s.,]*', rev_txt)
            if m:
                reviews_count = re.sub(r'\D', '', m.group(0))
    except Exception:
        pass

    place_id = extract_place_id(url)

    return {
        'Name': name,
        'Category': category,
        'Address': address,
        'Phone': phone,
        'Website': website,
        'Rating': rating,
        'Reviews_Count': reviews_count,
        'Place_ID': place_id,
        'URL': url,
        'Search_Query': search_query,
        'Location_Name': loc_info.get('name', ''),
        'Department': loc_info.get('department', ''),
        'Region': loc_info.get('region', ''),
        'Scraped_At': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

async def scrape_location_keyword(page, keyword, loc, scraped_pids, progress_data):
    query_key = f"{keyword} | {loc['name']}"
    if query_key in progress_data["completed_queries"]:
        return 0

    print(f"\n[+] Bắt đầu quét: [{keyword}] tại {loc['name']} ({loc.get('region', 'France')})", flush=True)

    lat = loc['lat']
    lng = loc['lng']
    zoom = loc.get('zoom', 14)
    search_url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(keyword)}/@{lat},{lng},{zoom}z?hl=fr"

    try:
        await page.goto(search_url, wait_until='domcontentloaded', timeout=config_nail_fr.TIMEOUT)
        await page.wait_for_timeout(1500)
        await bypass_consent_screen(page)
        await handle_captcha(page)

        feed_selector = config_nail_fr.SELECTORS["results_container"]
        try:
            await page.wait_for_selector(feed_selector, timeout=10000)
        except Exception:
            # Có thể chỉ có 1 kết quả duy nhất (direct detail view)
            detail_title = page.locator(config_nail_fr.SELECTORS["business_name"])
            if await detail_title.count() > 0:
                row = await extract_details(page, page.url, keyword, loc)
                if row and row['Place_ID'] not in scraped_pids:
                    save_single_row(row)
                    scraped_pids.add(row['Place_ID'])
                    progress_data["total_scraped"] += 1
                    print(f"  [+] 1 Địa điểm trực tiếp: {row['Name']} | SĐT: {row['Phone']} | Web: {row['Website']}", flush=True)
            progress_data["completed_queries"].append(query_key)
            save_progress(progress_data)
            return 1

        feed = page.locator(feed_selector)
        count_found = 0
        no_new_count = 0
        max_scroll_tries = 35

        for scroll_i in range(max_scroll_tries):
            # Cuộn thanh feed
            await feed.evaluate('el => el.scrollTop += 1200')
            await page.wait_for_timeout(random.uniform(700, 1200))

            items = page.locator(config_nail_fr.SELECTORS["listing_link"])
            item_count = await items.count()

            end_text = page.locator('text="Vous êtes arrivé à la fin de la liste"')
            if await end_text.count() > 0:
                break

            if scroll_i > 5 and item_count == count_found:
                no_new_count += 1
                if no_new_count >= 3:
                    break
            else:
                no_new_count = 0
            count_found = item_count

        items = page.locator(config_nail_fr.SELECTORS["listing_link"])
        total_items = await items.count()
        print(f"  [*] Tìm thấy {total_items} địa điểm trong danh sách. Đang trích xuất chi tiết...", flush=True)

        new_scraped = 0
        for i in range(total_items):
            try:
                item = items.nth(i)
                item_url = await item.get_attribute("href") or ""
                place_id = extract_place_id(item_url)

                if place_id and place_id in scraped_pids:
                    continue

                await item.scroll_into_view_if_needed()
                await item.click()
                await page.wait_for_timeout(random.uniform(900, 1400))
                await handle_captcha(page)

                row = await extract_details(page, item_url or page.url, keyword, loc)
                if row:
                    p_id = row['Place_ID']
                    if p_id not in scraped_pids:
                        save_single_row(row)
                        scraped_pids.add(p_id)
                        new_scraped += 1
                        progress_data["total_scraped"] += 1
                        web_str = row['Website'][:25] + '..' if len(row['Website']) > 27 else (row['Website'] or 'Khong web')
                        print(f"  [{progress_data['total_scraped']:04d}] {row['Name'][:28]:<28} | {row['Phone']:<16} | {web_str:<27} | {row['Category'][:20]}", flush=True)
            except Exception:
                continue

        progress_data["completed_queries"].append(query_key)
        save_progress(progress_data)
        return new_scraped

    except Exception as e:
        print(f"[-] Lỗi trong quá trình quét '{query_key}': {e}", flush=True)
        return 0

async def main():
    print("=" * 80)
    print("  HỆ THỐNG CÀO GOOGLE MAPS: TIỆM NAIL & LÀM ĐẸP TẠI PHÁP (FRANCE NAIL SALONS)")
    print("  Tuân thủ: GEMINI.md - Rule 1, 2, 4, 5, 8, 9, 10, 11, 12")
    print("=" * 80)
    print(f"[*] Từ khóa tìm kiếm  : {', '.join(config_nail_fr.KEYWORDS)}")
    print(f"[*] Số cụm đô thị quét: {len(locations_fr.LOCATIONS)} vị trí (Paris 20 quận + các thành phố lớn)")
    print(f"[*] Tệp xuất thô      : {config_nail_fr.ROOT_OUTPUT_CSV}")
    print(f"[*] Chế độ trình duyệt: {'Headless=True (Ẩn)' if config_nail_fr.HEADLESS else 'Headless=False (Trực quan 1280x800)'}")
    print("=" * 80 + "\n")

    init_csv()
    progress_data = load_progress()
    scraped_pids = get_scraped_place_ids()

    print(f"[*] Đã thu thập trước đó: {len(scraped_pids)} địa điểm duy nhất", flush=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=config_nail_fr.HEADLESS,
            slow_mo=config_nail_fr.SLOW_MO,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox"
            ]
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            locale="fr-FR",
            timezone_id="Europe/Paris"
        )
        # Bỏ qua Cookie consent banner của Google bằng cookie SOCS
        await context.add_cookies([
            {'name': 'SOCS', 'value': 'CAESEwgDEgk2OTQ0NTgyODQaAmVuIAEaBgiA_LyaBg', 'domain': '.google.com', 'path': '/'},
            {'name': 'SOCS', 'value': 'CAESEwgDEgk2OTQ0NTgyODQaAmVuIAEaBgiA_LyaBg', 'domain': '.google.fr', 'path': '/'}
        ])
        page = await context.new_page()

        total_new = 0
        for kw in config_nail_fr.KEYWORDS:
            for loc in locations_fr.LOCATIONS:
                new_cnt = await scrape_location_keyword(page, kw, loc, scraped_pids, progress_data)
                total_new += new_cnt

        await browser.close()

    print("\n" + "=" * 80)
    print("  HOÀN TẤT CHIẾN DỊCH CÀO GOOGLE MAPS PHÁP!")
    print(f"[*] Số địa điểm mới thu thập : {total_new}")
    print(f"[*] Tổng số địa điểm trong CSV: {len(scraped_pids)}")
    print(f"[*] File CSV đầu ra          : {config_nail_fr.ROOT_OUTPUT_CSV}")
    print("=" * 80 + "\n")

if __name__ == '__main__':
    asyncio.run(main())
