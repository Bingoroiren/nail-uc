# -*- coding: utf-8 -*-
"""
ENGINE CÀO GOOGLE MAPS: TIỆM NAIL ÁO (AUSTRIA NAIL SALONS - NAGELSTUDIO)
=============================================================================
Thị trường: Áo (Austria - AT)
Từ khóa: Nagelstudio
Quy chuẩn:
- Playwright Chromium trực quan (headless=False)
- Tọa độ 53 cụm đô thị tại Áo (locations_at.py)
- Lưu tăng dần từng dòng vào AT_NAIL_GMAP_0RAW.csv
- Checkpoint tiến trình progress/progress_nail_at.json (Resume 100%)
- Lọc địa chỉ Áo nghiêm ngặt
- SĐT luôn có dấu nháy đơn (')
- Tự động vượt qua Google Consent / Cookie dialog
- Bắt Captcha rung chuông \a
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
from playwright.async_api import async_playwright

# Import cấu hình và danh sách vị trí
import config_nail_at
import locations_at

# Đảm bảo console UTF-8 trên Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

PROGRESS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "progress",
    "progress_nail_at.json"
)

# Danh sách đen cố định (Rule 12)
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

def extract_place_id(url):
    if not url:
        return ""
    match = re.search(r'1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)', url)
    if match:
        return match.group(1).lower()
    return url.split('?')[0].lower()

def get_scraped_urls():
    scraped_urls = set()
    for csv_file in [config_nail_at.OUTPUT_CSV, config_nail_at.ROOT_OUTPUT_CSV]:
        if os.path.exists(csv_file):
            try:
                with open(csv_file, mode='r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if 'URL' in row and row['URL']:
                            scraped_urls.add(extract_place_id(row['URL']))
            except Exception as e:
                print(f"[-] Lỗi đọc file CSV hiện tại ({csv_file}): {e}", flush=True)
    return scraped_urls

def is_austria_address(address):
    """Xác thực địa chỉ nằm trên lãnh thổ nước Áo (Austria)."""
    if not address:
        return False
    addr_lower = address.lower()
    
    # 1. Tên quốc gia
    if any(k in addr_lower for k in ["österreich", "oesterreich", "austria", ", at", " aut"]):
        return True
    
    # 2. 9 bang (Bundesländer) của Áo
    at_states = [
        "wien", "vienna", "niederösterreich", "niederoesterreich", 
        "oberösterreich", "oberoesterreich", "steiermark", "tirol", 
        "kärnten", "kaernten", "salzburg", "vorarlberg", "burgenland"
    ]
    if any(s in addr_lower for s in at_states):
        return True
        
    # 3. Các thành phố lớn & thị trấn trọng điểm của Áo
    at_cities = [
        "wien", "graz", "linz", "salzburg", "innsbruck", "klagenfurt", "villach", 
        "wels", "sankt pölten", "st. pölten", "dornbirn", "wiener neustadt", 
        "steyr", "feldkirch", "bregenz", "leonding", "klosterneuburg", "baden", 
        "wolfsberg", "leoben", "krems", "traun", "amstetten", "lustenau", 
        "kapfenberg", "mödling", "hallein", "kufstein", "traiskirchen", "schwechat", 
        "braunau", "saalfelden", "ansfelden", "spittal", "hohenems", "telfs", 
        "ternitz", "perchtoldsdorf", "feldkirchen", "tulln", "bludenz", "bad ischl", 
        "eisenstadt", "bruck an der mur", "schwaz", "hall in tirol", "wörgl", 
        "hard", "korneuburg", "neunkirchen", "marchtrenk", "voitsberg", "enns", 
        "gmunden", "leibnitz", "knittelfeld", "ried im innkreis", "weiz", "zwettl"
    ]
    if any(city in addr_lower for city in at_cities):
        return True
        
    # 4. Mã bưu chính Áo: 4 chữ số (ví dụ: 1010, 8010, 4020...)
    if re.search(r'\b[1-9]\d{3}\b', address):
        return True
        
    return False

def append_to_csv(row_dict):
    """Ghi tăng dần vào cả data/raw/AT_NAIL_GMAP_0RAW.csv và root AT_NAIL_GMAP_0RAW.csv"""
    targets = [config_nail_at.OUTPUT_CSV, config_nail_at.ROOT_OUTPUT_CSV]
    for target in targets:
        os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
        file_exists = os.path.isfile(target)
        try:
            with open(target, mode='a', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=row_dict.keys())
                if not file_exists:
                    writer.writeheader()
                writer.writerow(row_dict)
                f.flush()
        except Exception as e:
            print(f"[-] Không thể ghi dòng vào CSV ({target}): {e}", flush=True)

def load_completed_scans():
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    completed = set()
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return set((item[0].lower(), item[1].lower(), item[2].lower()) for item in data.get("completed", []))
        except Exception as e:
            print(f"[-] Lỗi đọc progress file: {e}", flush=True)
            
    if os.path.exists(config_nail_at.OUTPUT_CSV):
        try:
            print("[*] Nạp tiến trình từ dữ liệu CSV hiện có...", flush=True)
            completed_list = []
            with open(config_nail_at.OUTPUT_CSV, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    loc_name = row.get('Location_Name')
                    state = row.get('State')
                    kw = row.get('Search_Query', '')
                    raw_kw = ""
                    if kw:
                        for original_kw in config_nail_at.KEYWORDS:
                            if original_kw in kw:
                                raw_kw = original_kw
                                break
                    if not raw_kw:
                        raw_kw = config_nail_at.KEYWORDS[0]
                    if loc_name and state:
                        pair = (loc_name.strip().lower(), state.strip().lower(), raw_kw.lower())
                        if pair not in completed:
                            completed.add(pair)
                            completed_list.append([loc_name.strip(), state.strip(), raw_kw])
            with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
                json.dump({"completed": completed_list}, f, indent=4, ensure_ascii=False)
            print(f"[+] Đã khôi phục {len(completed)} điểm quét đã hoàn tất.", flush=True)
        except Exception as e:
            print(f"[-] Lỗi khôi phục tiến trình: {e}", flush=True)
            
    return completed

def save_completed_scan(loc_name, state, keyword):
    completed_list = []
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                completed_list = data.get("completed", [])
        except Exception:
            pass
            
    pair = [loc_name, state, keyword]
    if pair not in completed_list:
        completed_list.append(pair)
        try:
            with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
                json.dump({"completed": completed_list}, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[-] Lỗi lưu checkpoint: {e}", flush=True)

async def handle_captcha(page):
    current_url = page.url.lower()
    page_content = await page.content()
    if "sorry" in current_url or "captcha" in current_url or "recaptcha" in page_content.lower() or "unusual traffic" in page_content.lower():
        print("\a" * 3)  # Rung chuông cảnh báo
        print("[!] PHÁT HIỆN CAPTCHA! Vui lòng thao tác giải Captcha trên cửa sổ trình duyệt...", flush=True)
        while True:
            await asyncio.sleep(5)
            c_url = page.url.lower()
            c_content = await page.content()
            if "sorry" not in c_url and "captcha" not in c_url and "unusual traffic" not in c_content.lower():
                print("[+] Captcha đã được giải quyết! Đang tiếp tục cào...", flush=True)
                break

async def bypass_consent_screen(page):
    """Vượt qua màn hình Consent / Cookie của Google (tiếng Đức và tiếng Anh)"""
    try:
        consent_buttons = page.locator(
            'button:has-text("Alle akzeptieren"), button:has-text("Zustimmen"), '
            'button:has-text("Ich stimme zu"), button:has-text("Accept all"), '
            'button:has-text("I agree"), form:has(button) button:has-text("Akzeptieren")'
        )
        if await consent_buttons.count() > 0:
            await consent_buttons.first.click()
            await page.wait_for_timeout(1000)
    except Exception:
        pass

async def extract_details(page, url, search_query, loc_info):
    name = ""
    try:
        h1 = page.locator(config_nail_at.SELECTORS["business_name"])
        if await h1.count() > 0:
            name = (await h1.first.inner_text()).strip()
    except Exception:
        pass

    if not name or is_blacklisted_company(name):
        return None

    # Danh mục Google Maps
    category = ""
    try:
        cat_loc = page.locator(config_nail_at.SELECTORS["category"])
        if await cat_loc.count() > 0:
            category = (await cat_loc.first.inner_text()).strip()
    except Exception:
        pass

    # Bộ lọc danh mục tiệm nail / làm đẹp
    if config_nail_at.ALLOWED_CATEGORIES and category:
        match_cat = any(ac.lower() in category.lower() or category.lower() in ac.lower() for ac in config_nail_at.ALLOWED_CATEGORIES)
        if not match_cat:
            nail_terms = ["nagel", "nail", "kosmetik", "schönheit", "fußpflege", "beauty", "permanent", "pediküre", "maniküre"]
            if not any(t in category.lower() for t in nail_terms):
                print(f"    [-] Bỏ qua danh mục không khớp: {category} ({name})", flush=True)
                return None

    # Địa chỉ
    address = ""
    try:
        addr_loc = page.locator(config_nail_at.SELECTORS["address"])
        if await addr_loc.count() > 0:
            address = (await addr_loc.first.inner_text()).strip()
    except Exception:
        pass

    if address and not is_austria_address(address):
        print(f"    [-] Bỏ qua địa chỉ ngoài nước Áo: {address} ({name})", flush=True)
        return None

    # SĐT: Bắt buộc thêm dấu nháy đơn (') theo Rule 2
    phone = ""
    try:
        phone_loc = page.locator(config_nail_at.SELECTORS["phone"])
        if await phone_loc.count() > 0:
            phone_raw = (await phone_loc.first.inner_text()).strip()
            phone = f"'{phone_raw}" if phone_raw and not phone_raw.startswith("'") else phone_raw
    except Exception:
        pass

    # Website
    website = ""
    try:
        web_loc = page.locator(config_nail_at.SELECTORS["website"])
        if await web_loc.count() > 0:
            website = (await web_loc.first.get_attribute("href") or "").strip()
    except Exception:
        pass

    # Đánh giá & Số lượng reviews
    rating = ""
    reviews_count = ""
    try:
        r_loc = page.locator(config_nail_at.SELECTORS["rating"])
        if await r_loc.count() > 0:
            rating = (await r_loc.first.inner_text()).strip()
        rev_loc = page.locator(config_nail_at.SELECTORS["reviews_count"])
        if await rev_loc.count() > 0:
            rev_text = (await rev_loc.first.get_attribute("aria-label") or "").strip()
            m = re.search(r'(\d+)', rev_text.replace(',', '').replace('.', ''))
            if m:
                reviews_count = m.group(1)
    except Exception:
        pass

    # Tọa độ thực tế từ URL
    actual_lat, actual_lng = "", ""
    current_url = page.url
    coord_match = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', current_url)
    if coord_match:
        actual_lat, actual_lng = coord_match.group(1), coord_match.group(2)
    else:
        m2 = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', current_url)
        if m2:
            actual_lat, actual_lng = m2.group(1), m2.group(2)

    # Nhận diện cơ sở đã đóng cửa vĩnh viễn
    closed_loc = page.locator('span:has-text("Dauerhaft geschlossen"), span:has-text("Permanently closed")')
    permanently_closed = "Yes" if await closed_loc.count() > 0 else "No"

    return {
        "Name": name,
        "Category": category,
        "Phone": phone,
        "Website": website,
        "Address": address,
        "Rating": rating,
        "Reviews_Count": reviews_count,
        "State": loc_info.get("state", ""),
        "Location_Name": loc_info.get("name", ""),
        "Latitude": actual_lat,
        "Longitude": actual_lng,
        "Search_Query": search_query,
        "URL": url,
        "Permanently_Closed": permanently_closed
    }

async def scrape_feed(page, search_query, loc_info, scraped_urls):
    feed_selector = config_nail_at.SELECTORS["results_container"]
    try:
        await page.wait_for_selector(feed_selector, timeout=12000)
    except Exception:
        # Kiểm tra nếu Google Maps nhảy thẳng vào 1 kết quả duy nhất
        single_h1 = page.locator(config_nail_at.SELECTORS["business_name"])
        if await single_h1.count() > 0:
            place_id = extract_place_id(page.url)
            if place_id not in scraped_urls:
                details = await extract_details(page, page.url, search_query, loc_info)
                if details:
                    append_to_csv(details)
                    scraped_urls.add(place_id)
                    print(f"  [+] Tìm thấy 1 kết quả duy nhất: {details['Name']} | {details['Phone']}", flush=True)
            return
        print(f"  [-] Không tìm thấy danh sách kết quả cho '{search_query}'.", flush=True)
        return

    feed = page.locator(feed_selector)
    seen_in_feed = set()
    no_new_results_count = 0
    max_no_new_results = 5
    
    # Cuộn danh sách
    while no_new_results_count < max_no_new_results:
        await handle_captcha(page)
        
        cards = page.locator(f'{feed_selector} {config_nail_at.SELECTORS["listing_link"]}')
        card_count = await cards.count()
        new_items_found = False

        for i in range(card_count):
            card = cards.nth(i)
            href = await card.get_attribute("href")
            if not href:
                continue

            place_id = extract_place_id(href)
            if place_id in seen_in_feed or place_id in scraped_urls:
                continue

            seen_in_feed.add(place_id)
            new_items_found = True

            try:
                await card.click()
                await page.wait_for_timeout(random.randint(600, 1100))
                
                details = await extract_details(page, href, search_query, loc_info)
                if details:
                    append_to_csv(details)
                    scraped_urls.add(place_id)
                    phone_disp = details['Phone'] or "Chưa có SĐT"
                    web_disp = details['Website'][:30] if details['Website'] else "Chưa có Web"
                    print(f"  [+] Đã cào: {details['Name'][:28]:<28} | {phone_disp:<18} | {web_disp}", flush=True)
            except Exception as e:
                print(f"    [-] Lỗi bóc tách chi tiết: {e}", flush=True)

        if not new_items_found:
            no_new_results_count += 1
        else:
            no_new_results_count = 0

        # Cuộn thanh danh sách xuống
        try:
            await feed.evaluate("node => node.scrollBy(0, 1500)")
            await page.wait_for_timeout(random.randint(800, 1400))
        except Exception:
            break

        # Kiểm tra chạm cuối danh sách
        end_indicators = page.locator('span:has-text("Sie haben das Ende der Liste erreicht"), span:has-text("You\'ve reached the end of the list")')
        if await end_indicators.count() > 0 and await end_indicators.first.is_visible():
            print("  [*] Đã chạm cuối danh sách kết quả của khu vực này.", flush=True)
            break

async def main():
    print("=" * 75)
    print("  KHỞI ĐỘNG HỆ THỐNG CÀO GOOGLE MAPS: TIỆM NAIL ÁO (NAGELSTUDIO)")
    print("  Quy chuẩn: GEMINI.md | UTF-8 with BOM | SĐT nháy đơn (') | Headless=False")
    print(f"  Đích xuất: {config_nail_at.OUTPUT_CSV}")
    print("=" * 75)

    scraped_urls = get_scraped_urls()
    print(f"[*] Đã tải {len(scraped_urls)} địa điểm đã cào từ trước.", flush=True)

    completed_scans = load_completed_scans()
    print(f"[*] Đã tải {len(completed_scans)} lượt quét đã hoàn thành.", flush=True)

    async with async_playwright() as p:
        # Khởi chạy trình duyệt trực quan theo Rule 4 (1280x800)
        browser = await p.chromium.launch(
            headless=config_nail_at.HEADLESS,
            slow_mo=config_nail_at.SLOW_MO,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized"
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1366, "height": 850},
            locale="de-AT",
            timezone_id="Europe/Vienna",
            geolocation={"latitude": 47.5162, "longitude": 14.5501},
            permissions=["geolocation"]
        )
        page = await context.new_page()

        # Mở trang chủ Google Maps & xử lý Consent
        try:
            await page.goto("https://www.google.com/maps?hl=de", timeout=config_nail_at.TIMEOUT)
            await page.wait_for_timeout(2000)
            await bypass_consent_screen(page)
        except Exception as e:
            print(f"[-] Lỗi tải trang chủ Google Maps: {e}", flush=True)

        total_locations = len(locations_at.LOCATIONS)
        print(f"[*] Tổng số vị trí khảo sát tại Áo: {total_locations} cụm đô thị.", flush=True)

        for kw_idx, keyword in enumerate(config_nail_at.KEYWORDS, 1):
            print(f"\n=======================================================")
            print(f" CHIẾN DỊCH TỪ KHÓA [{kw_idx}/{len(config_nail_at.KEYWORDS)}]: '{keyword}'")
            print(f"=======================================================", flush=True)

            for idx, loc in enumerate(locations_at.LOCATIONS, 1):
                loc_name = loc["name"]
                state = loc["state"]
                lat = loc["lat"]
                lng = loc["lng"]
                # Tiệm nail trong đô thị nên dùng zoom 12-13 để gom trọn vẹn
                zoom = max(12, loc.get("zoom", 12))

                scan_key = (loc_name.lower(), state.lower(), keyword.lower())
                if scan_key in completed_scans:
                    print(f"[{idx:02d}/{total_locations:02d}] {loc_name} ({state}) - Đã cào trước đó (Bỏ qua).", flush=True)
                    continue

                search_query = f"{keyword} {loc_name} {state} Austria"
                encoded_kw = urllib.parse.quote(keyword)
                search_url = f"https://www.google.com/maps/search/{encoded_kw}/@{lat},{lng},{zoom}z?hl=de"

                print(f"\n[{idx:02d}/{total_locations:02d}] Đang quét: '{keyword}' tại {loc_name}, {state}...", flush=True)
                
                try:
                    await page.goto(search_url, timeout=config_nail_at.TIMEOUT)
                    await page.wait_for_timeout(1500)
                    await bypass_consent_screen(page)
                    await handle_captcha(page)

                    await scrape_feed(page, search_query, loc, scraped_urls)
                    save_completed_scan(loc_name, state, keyword)
                    completed_scans.add(scan_key)
                except Exception as e:
                    print(f"  [-] Lỗi trong lượt quét '{loc_name}': {e}", flush=True)

                await page.wait_for_timeout(random.randint(1000, 2000))

        await browser.close()

    print("\n" + "=" * 75)
    print("  HOÀN THÀNH TOÀN BỘ CHIẾN DỊCH CÀO TIỆM NAIL ÁO TRÊN GOOGLE MAPS!")
    print(f"  Tệp thô đã lưu tại: {config_nail_at.OUTPUT_CSV}")
    print("=" * 75 + "\n")

if __name__ == "__main__":
    asyncio.run(main())

