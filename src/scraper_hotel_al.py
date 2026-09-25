# -*- coding: utf-8 -*-
"""
Google Maps Scraper for Albania Hotels & Accommodations:
- Đặc thù ngành Khách sạn / Lưu trú (Hotel & Lodging).
- Khử trùng bằng Google Place ID (0x...:0x...).
- Selector Category đa năng kèm vòng lặp chờ tải DOM.
- Bộ lọc ALLOWED_CATEGORIES nghiêm ngặt (tiếng Albania + Anh + Ý).
- Loại trừ triệt để các trang đại lý đặt phòng OTA (Booking, Agoda, Airbnb...).
- Nhận diện Permanently Closed ('Yes' / 'No').
- SĐT luôn có dấu nháy đơn ' ở đầu.
- Lưu tăng dần (Incremental Auto-Save) và Checkpoint JSON (Resume 100%).
"""

import asyncio
import csv
import json
import os
import random
import re
import sys
import urllib.parse
from playwright.async_api import async_playwright

# Set console output encoding to UTF-8
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

# Import local configuration and locations
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import config_hotel_al
import locations_al

def extract_place_id(url):
    """Bóc tách Google Place ID từ URL Maps để khử trùng tuyệt đối."""
    if not url:
        return ""
    match = re.search(r'1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)', url)
    if match:
        return match.group(1).lower()
    return url.split('?')[0].lower()

def get_scraped_urls():
    """Tải danh sách Place ID đã cào từ file CSV thô để không cào trùng."""
    scraped_urls = set()
    if os.path.exists(config_hotel_al.OUTPUT_CSV):
        try:
            with open(config_hotel_al.OUTPUT_CSV, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if 'URL' in row and row['URL']:
                        scraped_urls.add(extract_place_id(row['URL']))
        except Exception as e:
            print(f"[-] Lỗi đọc tệp CSV hiện có: {e}")
    return scraped_urls

def is_albania_address(address):
    """Kiểm tra địa chỉ có thuộc lãnh thổ Albania hay không."""
    if not address:
        return False
    addr_lower = address.lower()
    if "albania" in addr_lower or "shqipëri" in addr_lower or "shqiperi" in addr_lower or ", al" in addr_lower:
        return True
    
    al_cities = [
        "tiranë", "tirana", "durrës", "durres", "vlorë", "vlore", "shkodër", "shkoder", 
        "elbasan", "fier", "korçë", "korce", "berat", "sarandë", "sarande", "lushnjë", 
        "lushnje", "pogradec", "kavajë", "kavaje", "gjirokastër", "gjirokaster", "lezhë", 
        "lezhe", "krujë", "kruje", "ksamil", "himarë", "himare", "dhermi", "dhërmi", 
        "tepelenë", "tepelene", "kukës", "kukes", "përmet", "permet", "tropojë", "tropoje", 
        "valbonë", "valbone", "theth", "velipojë", "velipoje", "divjakë", "divjake", 
        "shëngjin", "shengjin", "orikum", "qeparo", "borsh", "lukovë", "lukove"
    ]
    if any(city in addr_lower for city in al_cities):
        return True
        
    # Mã bưu điện 4 chữ số Albania (1001, 9401...)
    if re.search(r'\b\d{4}\b', addr_lower):
        return True
        
    return False

def append_to_csv(row_dict):
    """Lưu tăng dần từng bản ghi vào CSV với UTF-8 with BOM."""
    os.makedirs(os.path.dirname(config_hotel_al.OUTPUT_CSV), exist_ok=True)
    file_exists = os.path.isfile(config_hotel_al.OUTPUT_CSV)
    try:
        with open(config_hotel_al.OUTPUT_CSV, mode='a', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=row_dict.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(row_dict)
            f.flush()
    except Exception as e:
        print(f"[-] Lỗi ghi dòng vào CSV: {e}")

PROGRESS_FILE = config_hotel_al.PROGRESS_FILE

def load_completed_scans():
    """Tải tiến độ quét từ checkpoint JSON để hỗ trợ Resume 100%."""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return set((item[0].lower(), item[1].lower(), item[2].lower()) for item in data.get("completed", []))
        except Exception as e:
            print(f"[-] Lỗi đọc tệp tiến trình: {e}")
            
    if os.path.exists(config_hotel_al.OUTPUT_CSV):
        try:
            print("[*] Đang khởi tạo tiến trình từ dữ liệu CSV hiện có...")
            completed_list = []
            with open(config_hotel_al.OUTPUT_CSV, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    loc_name = row.get('Location_Name')
                    state = row.get('State')
                    search_query = row.get('Search_Query', '')
                    if loc_name and state:
                        found_kw = ""
                        if search_query:
                            for kw in config_hotel_al.KEYWORDS:
                                if kw.lower() in search_query.lower():
                                    found_kw = kw
                                    break
                        if not found_kw:
                            found_kw = config_hotel_al.KEYWORDS[0]
                            
                        pair = [loc_name.strip(), state.strip(), found_kw]
                        pair_lower = (loc_name.strip().lower(), state.strip().lower(), found_kw.lower())
                        if pair_lower not in [(x[0].lower(), x[1].lower(), x[2].lower()) for x in completed_list]:
                            completed_list.append(pair)
            
            os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
            with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
                json.dump({"completed": completed_list}, f, indent=2, ensure_ascii=False)
            return set((x[0].lower(), x[1].lower(), x[2].lower()) for x in completed_list)
        except Exception as e:
            print(f"[-] Lỗi đồng bộ CSV sang tiến trình: {e}")
            
    return set()

def save_completed_scan(loc_name, state, keyword):
    """Lưu tiến độ điểm quét vừa hoàn thành."""
    completed = []
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                completed = data.get("completed", [])
        except Exception:
            completed = []
            
    item = [loc_name, state, keyword]
    if item not in completed:
        completed.append(item)
        try:
            os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
            with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
                json.dump({"completed": completed}, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[-] Lỗi lưu tiến trình: {e}")

async def handle_captcha(page):
    """Phát hiện Captcha của Google, rung chuông cảnh báo và chờ người dùng xử lý."""
    is_captcha = False
    try:
        title = await page.title()
        if "sorry" in title.lower() or "recaptcha" in title.lower() or "captcha" in title.lower():
            is_captcha = True
        elif await page.locator('iframe[src*="recaptcha"]').count() > 0 or await page.locator('div#recaptcha').count() > 0:
            is_captcha = True
    except Exception:
        pass
        
    if is_captcha:
        print("\a" * 3) # Chuông báo động
        print("\n" + "!" * 70)
        print("[!] PHÁT HIỆN GOOGLE CAPTCHA / BOT DETECTION!")
        print("[!] Vui lòng giải Captcha trực tiếp trên cửa sổ trình duyệt Chrome...")
        print("!" * 70)
        
        while True:
            await asyncio.sleep(3.0)
            try:
                title = await page.title()
                if "sorry" not in title.lower() and "recaptcha" not in title.lower() and "captcha" not in title.lower():
                    if await page.locator('iframe[src*="recaptcha"]').count() == 0 and await page.locator('div#recaptcha').count() == 0:
                        print("[+] Captcha đã được giải thành công! Tiếp tục tiến trình...")
                        await asyncio.sleep(2.0)
                        break
            except Exception:
                pass

async def bypass_consent_screen(page):
    """Tự động đóng popup đồng ý Cookie / Consent của Google."""
    try:
        consent_btn = page.locator('button[aria-label*="Pranoji të gjitha"], button[aria-label*="Accept all"], button[aria-label*="Agree"], form[action*="consent"] button')
        if await consent_btn.count() > 0:
            await consent_btn.first.click()
            await asyncio.sleep(1.0)
    except Exception:
        pass

async def extract_details(page, url, search_query, loc_info):
    """Trích xuất chi tiết khách sạn theo chuẩn đặc thù Hotel & Lodging."""
    actual_suburb = loc_info['name']
    actual_state = loc_info['state']
    actual_lat = ""
    actual_lng = ""
    
    coord_match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if coord_match:
        actual_lat = coord_match.group(1)
        actual_lng = coord_match.group(2)
        
    # 1. Tên doanh nghiệp
    name = ""
    name_loc = page.locator(config_hotel_al.SELECTORS["business_name"])
    if await name_loc.count() > 0:
        name = (await name_loc.first.inner_text()).strip()
        
    # 2. Website (Loại bỏ triệt để các trang OTA theo Skill scrape-hotel)
    website = ""
    web_loc = page.locator(config_hotel_al.SELECTORS["website"])
    if await web_loc.count() > 0:
        raw_web = await web_loc.first.get_attribute("href")
        if raw_web:
            raw_web = raw_web.strip()
            # Kiểm tra xem có phải link OTA không
            is_ota = any(ota in raw_web.lower() for ota in config_hotel_al.EXCLUDED_OTA_DOMAINS)
            if not is_ota:
                website = raw_web
            else:
                website = "" # Bỏ qua trang OTA để đảm bảo bóc tách email chính chủ
                
    # 3. Số điện thoại (Bắt buộc thêm dấu nháy đơn ' ở đầu theo quy chuẩn)
    phone = ""
    phone_loc = page.locator(config_hotel_al.SELECTORS["phone"])
    if await phone_loc.count() > 0:
        raw_ph = await phone_loc.first.get_attribute("data-item-id")
        if raw_ph:
            p_clean = raw_ph.replace("phone:tel:", "").strip()
            p_clean = re.sub(r'[^\d+]', '', p_clean)
            if p_clean:
                phone = f"'{p_clean}" if not p_clean.startswith("'") else p_clean
                
    # 4. Địa chỉ
    address = ""
    addr_loc = page.locator(config_hotel_al.SELECTORS["address"])
    if await addr_loc.count() > 0:
        addr_label = await addr_loc.first.get_attribute("aria-label")
        if addr_label:
            address = addr_label.replace("Address:", "").replace("Adresa:", "").strip()
        else:
            address = (await addr_loc.first.inner_text()).strip()
            
    # 5. Rating & Reviews
    rating = ""
    rating_loc = page.locator(config_hotel_al.SELECTORS["rating"])
    if await rating_loc.count() > 0:
        rating = (await rating_loc.first.inner_text()).strip()
        
    reviews_count = ""
    rev_loc = page.locator(config_hotel_al.SELECTORS["reviews_count"])
    if await rev_loc.count() > 0:
        raw_rev = await rev_loc.first.get_attribute("aria-label") or await rev_loc.first.inner_text()
        rev_match = re.search(r'([\d\.,]+)', raw_rev)
        if rev_match:
            reviews_count = rev_match.group(1).replace(".", "").replace(",", "")
            
    # 6. Kiểm tra Permanently Closed (Đóng cửa vĩnh viễn)
    permanently_closed = "No"
    try:
        closed_loc = page.locator('span:has-text("Mbyllur përfundimisht"), span:has-text("Permanently closed"), span:has-text("Chiuso definitivamente")')
        if await closed_loc.count() > 0:
            permanently_closed = "Yes"
    except Exception:
        pass
        
    # 7. Bóc tách Category đa năng với vòng lặp chờ tải DOM (Rule 2 của Skill)
    category = ""
    cat_loc = page.locator(config_hotel_al.SELECTORS["category"])
    for _ in range(15):
        if await cat_loc.count() > 0:
            for c_idx in range(await cat_loc.count()):
                c_text = (await cat_loc.nth(c_idx).inner_text()).strip()
                if c_text and not c_text.replace(".", "").isdigit():
                    category = c_text
                    break
            if category:
                break
        await asyncio.sleep(0.2)
        
    # 8. Lọc Category nghiêm ngặt (Rule 3 của Skill)
    if category:
        cat_lower = category.lower().strip()
        is_allowed = any(ac in cat_lower or cat_lower in ac for ac in config_hotel_al.ALLOWED_CATEGORIES)
        if not is_allowed:
            return None # Bỏ qua nếu là nhà hàng, quán bar, trạm xăng... không phải cơ sở lưu trú
            
    if not name:
        return None

    record = {
        "Name": name,
        "Website": website,
        "Phone": phone,
        "Address": address,
        "Rating": rating,
        "Reviews_Count": reviews_count,
        "State": actual_state,
        "Location_Name": actual_suburb,
        "Latitude": actual_lat,
        "Longitude": actual_lng,
        "Search_Query": search_query,
        "URL": url,
        "Permanently_Closed": permanently_closed,
        "Category": category,
    }
    return record

async def scroll_feed(page):
    """Cuộn danh sách kết quả để Google Maps tải toàn bộ các khách sạn."""
    feed_loc = page.locator(config_hotel_al.SELECTORS["results_container"])
    if await feed_loc.count() == 0:
        return
        
    no_change_count = 0
    prev_count = 0
    max_scrolls = 35
    
    for _ in range(max_scrolls):
        await feed_loc.evaluate("node => node.scrollTop = node.scrollHeight")
        await asyncio.sleep(1.2)
        
        cards = page.locator(config_hotel_al.SELECTORS["listing_link"])
        curr_count = await cards.count()
        
        # Kiểm tra thông báo chạm đáy
        end_text = page.locator('text="You\'ve reached the end of the list", text="Keni arritur në fund të listës", text="Hai raggiunto la fine dell\'elenco"')
        if await end_text.count() > 0:
            break
            
        if curr_count == prev_count:
            no_change_count += 1
            if no_change_count >= 3:
                break
        else:
            no_change_count = 0
            prev_count = curr_count

async def process_search(page, keyword, loc_info, scraped_urls):
    """Thực thi tìm kiếm từ khóa tại một tọa độ cụ thể."""
    search_query = f"{keyword} in {loc_info['name']}, Albania"
    print(f"\n[+] Đang tìm kiếm: '{search_query}'")
    
    query_encoded = urllib.parse.quote_plus(keyword)
    zoom = loc_info.get("zoom", 12)
    search_url = f"https://www.google.com/maps/search/{query_encoded}/@{loc_info['lat']},{loc_info['lng']},{zoom}z?hl=sq"
    
    try:
        await page.context.set_geolocation({"latitude": loc_info['lat'], "longitude": loc_info['lng']})
    except Exception:
        pass

    for attempt in range(1, 4):
        try:
            await page.goto(search_url, timeout=config_hotel_al.TIMEOUT, wait_until="domcontentloaded")
            await asyncio.sleep(2.0)
            break
        except Exception as e:
            if attempt == 3:
                print(f"[-] Lỗi nạp trang tìm kiếm: {e}")
                return False
            await asyncio.sleep(3.0)
            
    await handle_captcha(page)
    await bypass_consent_screen(page)
    current_url = page.url
    
    # Trường hợp Google Maps mở trực tiếp 1 địa điểm
    if "/maps/place/" in current_url:
        pid = extract_place_id(current_url)
        if pid not in scraped_urls:
            record = await extract_details(page, current_url, search_query, loc_info)
            if record:
                append_to_csv(record)
                scraped_urls.add(pid)
                print(f"    -> ĐÃ LƯU: {record['Name']} | Hạng mục: {record['Category']} | SĐT: {record['Phone']} | Web: {record['Website']}")
        return True

    # Cuộn danh sách
    await scroll_feed(page)
    
    link_selector = config_hotel_al.SELECTORS["listing_link"]
    listings_count = await page.locator(link_selector).count()
    print(f"[*] Tìm thấy {listings_count} địa điểm trên danh sách.")
    
    for i in range(listings_count):
        item = page.locator(link_selector).nth(i)
        try:
            place_url = await item.get_attribute("href")
            if not place_url:
                continue
                
            pid = extract_place_id(place_url)
            if pid in scraped_urls:
                continue
                
            await item.scroll_into_view_if_needed()
            await item.click()
            
            # Chờ panel chi tiết mở ra
            try:
                await page.wait_for_selector(config_hotel_al.SELECTORS["business_name"], timeout=7000)
            except Exception:
                await asyncio.sleep(1.0)
                
            await handle_captcha(page)
            record = await extract_details(page, place_url, search_query, loc_info)
            if record:
                # Kiểm tra geofence địa chỉ Albania
                if record["Address"] and not is_albania_address(record["Address"]):
                    continue
                    
                append_to_csv(record)
                scraped_urls.add(pid)
                print(f"    -> ĐÃ LƯU: {record['Name']} | Hạng mục: {record['Category']} | SĐT: {record['Phone']} | Web: {record['Website']}")
                
            await asyncio.sleep(random.uniform(config_hotel_al.MIN_DELAY, config_hotel_al.MAX_DELAY))
        except Exception as e:
            continue
            
    return True

async def main():
    print("=" * 70)
    print("   HỆ THỐNG CÀO DỮ LIỆU KHÁCH SẠN ALBANIA (GOOGLE MAPS PLAYWRIGHT)")
    print("=" * 70)
    
    scraped_urls = get_scraped_urls()
    completed_scans = load_completed_scans()
    
    print(f"[*] Đã tải {len(scraped_urls)} khách sạn / cơ sở lưu trú đã cào từ trước.")
    print(f"[*] Đã tải {len(completed_scans)} điểm quét đã hoàn thành.")
    print(f"[*] Tổng số từ khóa: {len(config_hotel_al.KEYWORDS)}")
    print(f"[*] Tổng số địa điểm: {len(locations_al.LOCATIONS)}")
    
    # Khởi tạo Playwright với headless=False để USER quan sát trực quan
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=config_hotel_al.HEADLESS,
            slow_mo=config_hotel_al.SLOW_MO
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="sq-AL",
            permissions=["geolocation"]
        )
        page = await context.new_page()
        
        total_scans = len(config_hotel_al.KEYWORDS) * len(locations_al.LOCATIONS)
        curr_scan = 0
        
        for loc in locations_al.LOCATIONS:
            for kw in config_hotel_al.KEYWORDS:
                curr_scan += 1
                scan_key = (loc['name'].lower(), loc['state'].lower(), kw.lower())
                
                if scan_key in completed_scans:
                    continue
                    
                print(f"\n[{curr_scan}/{total_scans}] Tiến trình: '{kw}' tại {loc['name']} ({loc['state']})...")
                success = await process_search(page, kw, loc, scraped_urls)
                if success:
                    save_completed_scan(loc['name'], loc['state'], kw)
                    completed_scans.add(scan_key)
                    
                await asyncio.sleep(random.uniform(0.5, 1.2))
                
        await browser.close()
        
    print("\n" + "=" * 70)
    print("   HOÀN TẤT CHIẾN DỊCH CÀO KHÁCH SẠN ALBANIA THÀNH CÔNG!")
    print(f"   Dữ liệu đã được lưu tăng dần tại: {config_hotel_al.OUTPUT_CSV}")
    print("=" * 70)

if __name__ == '__main__':
    asyncio.run(main())
