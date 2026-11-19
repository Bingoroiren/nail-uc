# -*- coding: utf-8 -*-
"""
GOOGLE MAPS SCRAPER - LITHUANIAN METAL & FABRICATION FACTORIES (LT_METL_GMAP)
=============================================================================
Target:   Lithuanian Metalworking, Metal Fabrication, Welding, Foundries & Steel Plants
Output:   LT_METL_GMAP_0RAW.csv
Rules:    GEMINI.md (Rule 1, 2, 4, 5, 8, 10, 11, 12)
"""

import os
import sys
import re
import csv
import json
import random
import asyncio
import unicodedata
import urllib.parse
from pathlib import Path
from playwright.async_api import async_playwright

# Set console output encoding to UTF-8
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

# Add src to sys.path
SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Import campaign config and Lithuanian locations
import config_metal_lt as config
import locations_lt

PROGRESS_FILE = Path(config.PROGRESS_FILE)

# Rule 12: Permanent blacklist companies
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
    """Bóc tách Place ID từ URL Google Maps để khử trùng lặp chính xác"""
    if not url:
        return ""
    m = re.search(r'1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)', url)
    if m:
        return m.group(1).lower()
    return url.split('?')[0].lower()

def is_lithuania_address(address):
    """Kiểm tra địa chỉ có thuộc lãnh thổ Litva (Lithuania) hay không"""
    if not address:
        return False
    addr_lower = address.lower()
    if any(k in addr_lower for k in ["lithuania", "lietuva", "lietuvos", "lt-"]):
        return True
    
    # Các thành phố và khu vực trọng điểm của Litva
    lt_cities = [
        "vilnius", "kaunas", "klaipėda", "klaipeda", "šiauliai", "siauliai", "panevėžys", "panevezys",
        "alytus", "marijampolė", "marijampole", "mažeikiai", "mazeikiai", "jonava", "utena",
        "kėdainiai", "kedainiai", "telšiai", "telsiai", "tauragė", "taurage", "ukmergė", "ukmerge",
        "visaginas", "plungė", "plunge", "kretinga", "šilutė", "silute", "gargždai", "gargzdai",
        "radviliškis", "radviliskis", "druskininkai", "elektrėnai", "elektrenai", "rokiškis", "rokiskis",
        "kuršėnai", "kursenai", "jurbarkas", "biržai", "birzai", "vilkaviškis", "vilkaviskis",
        "raseiniai", "anykščiai", "anyksciai", "lentvaris", "grigiškės", "grigiskes", "prienai",
        "kaišiadorys", "kaisiadorys", "naujoji akmenė", "naujoji akmene", "joniškis", "joniskis"
    ]
    if any(city in addr_lower for city in lt_cities):
        return True
        
    # Mã bưu chính Litva (LT-12345 hoặc 5 chữ số)
    if re.search(r'\b(lt-)?\d{5}\b', addr_lower):
        return True
        
    return False

def clean_phone_lt(raw_phone):
    """Rule 2: Chuẩn hóa SĐT có nháy đơn (') ở đầu"""
    if not raw_phone:
        return ""
    s = str(raw_phone).strip().lstrip("'").strip()
    digits = re.sub(r'[^0-9]', '', s)
    if not digits:
        return ""
    if digits.startswith('370'):
        pass
    elif digits.startswith('8') and len(digits) == 9:
        digits = '370' + digits[1:]
    elif digits.startswith('0') and (len(digits) == 9 or len(digits) == 10):
        digits = '370' + digits[1:]
    elif len(digits) == 8:
        digits = '370' + digits

    if digits.startswith('370') and len(digits) == 11:
        return f"'+370 {digits[3:5]} {digits[5:8]} {digits[8:]}"
    return f"'+{digits}"

def get_scraped_urls():
    """Tải danh sách các địa điểm đã cào từ file CSV để tránh cào lại"""
    scraped_urls = set()
    out_path = Path(config.OUTPUT_CSV)
    if out_path.exists():
        try:
            with open(out_path, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    url = row.get('URL', '')
                    if url:
                        scraped_urls.add(extract_place_id(url))
        except Exception as e:
            print(f"[-] Lỗi nạp dữ liệu cũ: {e}", flush=True)
    return scraped_urls

def append_to_csv(row_dict):
    """Rule 5: Ghi tăng dần từng dòng vào CSV UTF-8 with BOM"""
    out_paths = [Path(config.OUTPUT_CSV), Path(config.RAW_DATA_CSV)]
    for p in out_paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        file_exists = p.is_file()
        try:
            with open(p, mode='a', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=row_dict.keys())
                if not file_exists:
                    writer.writeheader()
                writer.writerow(row_dict)
                f.flush()
        except Exception as e:
            print(f"[-] Lỗi ghi file CSV ({p.name}): {e}", flush=True)

def load_completed_scans():
    """Tải checkpoint tiến độ quét (Location, State, Keyword)"""
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    completed = set()
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return set((item[0].lower(), item[1].lower(), item[2].lower()) for item in data.get("completed", []))
        except Exception as e:
            print(f"[-] Lỗi nạp progress file: {e}", flush=True)
            
    # Tự động đồng bộ từ file CSV nếu chưa có progress file
    out_path = Path(config.OUTPUT_CSV)
    if out_path.exists():
        try:
            print("[*] Đang khởi tạo checkpoint từ tệp CSV có sẵn...", flush=True)
            completed_list = []
            with open(out_path, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    loc_name = row.get('Location_Name')
                    state = row.get('State')
                    kw = row.get('Search_Query', '')
                    raw_kw = config.KEYWORDS[0]
                    for k in config.KEYWORDS:
                        if k in kw:
                            raw_kw = k
                            break
                    if loc_name and state:
                        pair = (loc_name.strip().lower(), state.strip().lower(), raw_kw.lower())
                        if pair not in completed:
                            completed.add(pair)
                            completed_list.append([loc_name.strip(), state.strip(), raw_kw])
            with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
                json.dump({"completed": completed_list}, f, indent=4, ensure_ascii=False)
            print(f"[+] Đã khôi phục checkpoint {len(completed)} điểm quét từ CSV.", flush=True)
        except Exception as e:
            print(f"[-] Lỗi khởi tạo progress: {e}", flush=True)
            
    return completed

def save_completed_scan(loc_name, state, keyword):
    """Lưu checkpoint tiến độ sau mỗi cặp từ khóa + vị trí hoàn tất"""
    completed_list = []
    if PROGRESS_FILE.exists():
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
    """Rule 4: Phát hiện Captcha, rung chuông cảnh báo và tạm dừng an toàn"""
    current_url = page.url.lower()
    page_content = await page.content()
    if "sorry" in current_url or "captcha" in current_url or "recaptcha" in page_content.lower() or "unusual traffic" in page_content.lower():
        print("\a" * 3)  # Chuông báo
        print("\n" + "!" * 70, flush=True)
        print("[!] PHÁT HIỆN CAPTCHA GOOGLE! Vui lòng xác thực trên trình duyệt...", flush=True)
        print("!" * 70 + "\n", flush=True)
        while True:
            await asyncio.sleep(4)
            c_url = page.url.lower()
            c_content = await page.content()
            if "sorry" not in c_url and "captcha" not in c_url and "unusual traffic" not in c_content.lower():
                print("[+] Captcha đã được xử lý xong! Tiếp tục cào dữ liệu...", flush=True)
                break

async def bypass_consent_screen(page):
    """Tự động vượt qua màn hình Cookie / Consent của Google"""
    try:
        consent_buttons = page.locator(
            'button:has-text("Priimti viską"), button:has-text("Sutinku"), '
            'button:has-text("Accept all"), button:has-text("I agree"), '
            'form:has(button) button:has-text("Priimti")'
        )
        if await consent_buttons.count() > 0:
            await consent_buttons.first.click()
            await page.wait_for_timeout(1000)
    except Exception:
        pass

async def extract_details(page, url, search_query, loc_info):
    """Trích xuất chi tiết thông tin doanh nghiệp kim loại từ panel Google Maps"""
    name = ""
    try:
        h1 = page.locator(config.SELECTORS["business_name"])
        if await h1.count() > 0:
            name = (await h1.first.inner_text()).strip()
    except Exception:
        pass

    if not name or is_blacklisted_company(name):
        return None

    # Danh mục / Ngành nghề
    category = ""
    try:
        cat_loc = page.locator(config.SELECTORS["category"])
        if await cat_loc.count() > 0:
            category = (await cat_loc.first.inner_text()).strip()
    except Exception:
        pass

    # Lọc danh mục hợp lệ
    if config.ALLOWED_CATEGORIES and category:
        match_cat = any(ac.lower() in category.lower() or category.lower() in ac.lower() for ac in config.ALLOWED_CATEGORIES)
        if not match_cat:
            # Cho phép nếu có các từ khóa kim loại / cơ khí / gia công
            metal_terms = ["metal", "plien", "suvirin", "liej", "mechanin", "gamyb", "pjaust", "kalv", "steel", "machin", "fabric"]
            if not any(t in category.lower() for t in metal_terms):
                return None

    # Địa chỉ
    address = ""
    try:
        addr_loc = page.locator(config.SELECTORS["address"])
        if await addr_loc.count() > 0:
            address = (await addr_loc.first.inner_text()).strip()
    except Exception:
        pass

    if address and not is_lithuania_address(address):
        return None

    # Số điện thoại (Rule 2: có nháy đơn)
    phone = ""
    try:
        phone_loc = page.locator(config.SELECTORS["phone"])
        if await phone_loc.count() > 0:
            raw_ph = (await phone_loc.first.inner_text()).strip()
            phone = clean_phone_lt(raw_ph)
    except Exception:
        pass

    # Website
    website = ""
    try:
        web_loc = page.locator(config.SELECTORS["website"])
        if await web_loc.count() > 0:
            website = (await web_loc.first.get_attribute("href") or "").strip()
    except Exception:
        pass

    # Đánh giá & Số lượng nhận xét
    rating = ""
    reviews_count = ""
    try:
        r_loc = page.locator(config.SELECTORS["rating"])
        if await r_loc.count() > 0:
            rating = (await r_loc.first.inner_text()).strip()
        rev_loc = page.locator(config.SELECTORS["reviews_count"])
        if await rev_loc.count() > 0:
            rev_text = (await rev_loc.first.get_attribute("aria-label") or "").strip()
            m = re.search(r'(\d+)', rev_text.replace(' ', '').replace('.', ''))
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

    # Nhận diện đóng cửa vĩnh viễn
    closed_loc = page.locator('span:has-text("Visam laikui uždaryta"), span:has-text("Permanently closed")')
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
        "URL": current_url,
        "Permanently_Closed": permanently_closed,
    }

async def process_search(page, keyword, loc_info, scraped_urls):
    """Tìm kiếm từ khóa tại một tọa độ/địa phương của Litva"""
    search_query = f"{keyword} in {loc_info['name']}, Lithuania"
    print(f"\n[+] Đang tìm: '{search_query}' ({loc_info['state']})", flush=True)
    
    query_encoded = urllib.parse.quote_plus(keyword)
    search_url = f"https://www.google.com/maps/search/{query_encoded}/@{loc_info['lat']},{loc_info['lng']},{loc_info['zoom']}z?hl=lt"
    
    try:
        await page.context.set_geolocation({"latitude": loc_info['lat'], "longitude": loc_info['lng']})
    except Exception:
        pass

    for attempt in range(1, 4):
        try:
            await page.goto(search_url, timeout=config.TIMEOUT, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            break
        except Exception as e:
            if attempt == 3:
                print(f"[-] Điều hướng thất bại: {e}", flush=True)
                return
            await asyncio.sleep(3.0)

    await handle_captcha(page)
    await bypass_consent_screen(page)
    current_url = page.url

    # Trường hợp Google Maps chuyển thẳng tới 1 địa điểm duy nhất
    if "/maps/place/" in current_url:
        pid = extract_place_id(current_url)
        if pid not in scraped_urls:
            rec = await extract_details(page, current_url, search_query, loc_info)
            if rec:
                append_to_csv(rec)
                scraped_urls.add(pid)
                print(f"    🎯 LƯU: {rec['Name']} | SĐT: {rec['Phone']} | Web: {rec['Website']}", flush=True)
        return

    # Cuộn danh sách kết quả (Results feed)
    feed_selector = config.SELECTORS["results_container"]
    link_selector = config.SELECTORS["listing_link"]

    try:
        await page.wait_for_selector(feed_selector, timeout=7000)
    except Exception:
        print("    [*] Không tìm thấy container kết quả hoặc khu vực không có dữ liệu.", flush=True)
        return

    feed = page.locator(feed_selector).first

    seen_hrefs = set()
    no_new_counter = 0

    while True:
        links = await page.locator(link_selector).all()
        current_hrefs = []
        for l in links:
            href = await l.get_attribute("href")
            if href:
                current_hrefs.append(href)

        new_found = [h for h in current_hrefs if h not in seen_hrefs]
        for h in new_found:
            seen_hrefs.add(h)

        # Kiểm tra dấu hiệu chạm cuối danh sách
        end_text = page.locator(
            'span:has-text("Pasiekėte sąrašo pabaigą"), '
            'span:has-text("You\'ve reached the end of the list"), '
            'span:has-text("Rezultatų pabaiga")'
        )
        if await end_text.count() > 0:
            break

        if not new_found:
            no_new_counter += 1
            if no_new_counter >= 5:
                break
        else:
            no_new_counter = 0

        # Cuộn thanh kết quả xuống
        try:
            await feed.evaluate('el => el.scrollBy(0, 1000)')
            await page.wait_for_timeout(1000)
        except Exception:
            break

    print(f"    [*] Tìm thấy {len(seen_hrefs)} địa điểm kim loại trong danh sách.", flush=True)

    # Duyệt chi tiết từng địa điểm
    for idx, href in enumerate(seen_hrefs):
        pid = extract_place_id(href)
        if pid in scraped_urls:
            continue

        try:
            await page.goto(href, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(1500)
            await handle_captcha(page)

            rec = await extract_details(page, href, search_query, loc_info)
            if rec:
                append_to_csv(rec)
                scraped_urls.add(pid)
                print(f"    [{idx+1}/{len(seen_hrefs)}] 🎯 LƯU: {rec['Name']} | SĐT: {rec['Phone']} | Web: {rec['Website']}", flush=True)
        except Exception:
            continue

async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Google Maps Scraper - Lithuanian Metal Factories")
    parser.add_argument("--limit-locations", type=int, default=None, help="Giới hạn số địa điểm quét (dùng khi kiểm tra)")
    parser.add_argument("--headless", action="store_true", help="Chạy ẩn trình duyệt nếu cần")
    args = parser.parse_args()

    scraped_urls = get_scraped_urls()
    completed_scans = load_completed_scans()

    target_locations = locations_lt.LOCATIONS
    if args.limit_locations:
        target_locations = target_locations[:args.limit_locations]

    is_headless = True if args.headless else config.HEADLESS

    print("=" * 80, flush=True)
    print("🌟  GOOGLE MAPS SCRAPER - NHÀ MÁY & CƠ KHÍ KIM LOẠI LITVA (LT_METL_GMAP)")
    print(f"    - File xuất thô       : {config.OUTPUT_CSV}")
    print(f"    - Điểm quét Litva     : {len(target_locations)} / {len(locations_lt.LOCATIONS)} tọa độ")
    print(f"    - Bộ từ khóa          : {len(config.KEYWORDS)} từ khóa tiếng Litva")
    print(f"    - Doanh nghiệp đã lưu : {len(scraped_urls)} địa điểm độc nhất")
    print(f"    - Điểm đã hoàn tất    : {len(completed_scans)} lượt quét")
    print("=" * 80 + "\n", flush=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=is_headless,
            slow_mo=config.SLOW_MO,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--start-maximized'
            ]
        )
        
        context = await browser.new_context(
            viewport={"width": 1366, "height": 850},
            locale="lt-LT",
            timezone_id="Europe/Vilnius",
            geolocation={"latitude": 54.6872, "longitude": 25.2800},
            permissions=["geolocation"],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        
        page = await context.new_page()

        for loc in target_locations:
            loc_name = loc["name"]
            state = loc["state"]
            
            for kw in config.KEYWORDS:
                scan_key = (loc_name.lower(), state.lower(), kw.lower())
                if scan_key in completed_scans:
                    continue
                
                await process_search(page, kw, loc, scraped_urls)
                save_completed_scan(loc_name, state, kw)
                completed_scans.add(scan_key)
                
                delay = random.uniform(config.MIN_DELAY, config.MAX_DELAY)
                await asyncio.sleep(delay)

        await browser.close()
        print("\n" + "=" * 80, flush=True)
        print("🏆 HOÀN THÀNH TIẾN TRÌNH CÀO GOOGLE MAPS KIM LOẠI LITVA!", flush=True)
        print(f"   Dữ liệu đã được lưu tăng dần vào: {config.OUTPUT_CSV}", flush=True)
        print("=" * 80 + "\n", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
