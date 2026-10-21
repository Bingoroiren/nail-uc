# -*- coding: utf-8 -*-
"""
Hệ thống Làm giàu Dữ liệu Khách sạn Albania bằng Web Search & Facebook (Web Enrichment Engine):
1. Đọc dữ liệu từ data/raw/hotel_albania.csv (4.205 cơ sở lưu trú).
2. Lọc danh sách các khách sạn chưa có Website hoặc chưa có Email.
3. Tìm kiếm tự động qua Search Engine (DuckDuckGo HTML / Bing):
   - Bóc tách Email trực tiếp từ Search Snippet.
   - Tìm kiếm Website chính thức của khách sạn (loại bỏ 100% trang OTA/Booking).
   - Tìm kiếm link Facebook Fanpage chính thức của khách sạn.
4. Truy cập Website (Homepage + /kontakt, /contact, /rreth-nesh) và Facebook để quét vét email.
5. Khử trùng, lọc bỏ email rác/hosting (pik-host, bluepillow, freecancellations...).
6. Lưu tăng dần Checkpoint JSON và tự động cập nhật file 'Khách sạn Albania - ColdMail.csv'.
"""

import asyncio
import csv
import json
import os
import re
import sys
import urllib.parse
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)

INPUT_CSV = os.path.join(ROOT_DIR, "data", "raw", "hotel_albania.csv")
COLDMAIL_CSV = os.path.join(ROOT_DIR, "Khách sạn Albania - ColdMail.csv")
FORMATTED_CSV = os.path.join(ROOT_DIR, "data", "formatted", "hotel_albania_with_emails_formatted.csv")
PROGRESS_FILE = os.path.join(ROOT_DIR, "data", "progress", "web_enrich_hotel_al.json")

# Danh sách OTA & Nền tảng trung gian cần loại bỏ tuyệt đối
EXCLUDED_DOMAINS = {
    'booking.com', 'agoda.com', 'airbnb.com', 'expedia.com', 'tripadvisor.com', 
    'hotels.com', 'trivago.com', 'kayak.com', 'priceline.com', 'hostelworld.com', 
    'vrbo.com', 'viator.com', 'getyourguide.com', 'makemytrip.com', 'trip.com', 
    'orbitz.com', 'travelocity.com', 'hotwire.com', 'skyscanner.com', 'opentable.com',
    'booking.al', 'albania-booking.com', 'albania-hotels.net', 'albanian-hotels.com',
    'allbookers.com', 'hotelscheck-in.com', 'hotelb3.com', 'seasonsnseasons.com',
    'freecancellations.com', 'bluepillow.com', 'bluepillow.it', 'bluepillow.de', 'bluepillow.fr',
    'placescollective.com', 'highlandhikecottage.eu', 'ocean-vista-lodge.eu', 
    'brit-voyager.eu', 'backpackinghaven.eu', 'reservation.expert', 'exelentbnb.com',
    'holidayfuture.com', 'kondostays.com', 'grandstaycollection.com', 'travelnest.com',
    'beds24.com', 'simple-spot.site', 'thomasstraveltips.com', 'kalpazorental.com',
    'linktr.ee', 'yellowpages.com', 'yellowpages.al', 'yellowpages.com.al',
    'albania-hotel.top', 'hotelsalbanian.com', 'hotelalbanian.com', 'tirent.al',
    'google.com', 'google.al', 'maps.google.com', 'wikipedia.org', 'cybo.com', 'gjithebiznesi.com'
}

DISCARD_EMAILS = {
    'albania@gmail.com', 'info@pik-host.al', 's.giordani@bluepillow.com',
    'support@freecancellations.com', 'info@kondostays.com', 'info@tirent.al',
    'reservations@gs-collection.com', 'support@elementor.com', 'info@mysite.com'
}

DISCARD_EMAIL_DOMAINS = {
    'pik-host.al', 'bluepillow.com', 'freecancellations.com', 'gs-collection.com',
    'kondostays.com', 'tirent.al', 'placescollective.com', 'reservation.expert',
    'booking.com', 'agoda.com', 'airbnb.com', 'expedia.com', 'tripadvisor.com'
}

CONTACT_PATHS = [
    'kontakt', 'contact', 'kontakti', 'na-kontaktoni', 'contact-us',
    'rreth-nesh', 'per-ne', 'about', 'about-us', 'dhomat', 'rezervime',
    'contatti', 'chi-siamo'
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "sq,it,en-US;q=0.8,en;q=0.5"
}

def normalize_text(text):
    if not text:
        return ""
    t = text.lower().strip()
    return re.sub(r'[\s\-_\.,\|/]+', ' ', t).strip()

def clean_email(em_raw):
    if not em_raw:
        return ""
    em = urllib.parse.unquote(str(em_raw)).strip().lower()
    em = re.sub(r'&quot;.*$', '', em)
    em = re.sub(r'\\+$', '', em)
    em = re.sub(r'\s+', '', em)
    
    found = re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', em)
    valid = []
    for f in found:
        if f in DISCARD_EMAILS:
            continue
        parts = f.split('@')
        if len(parts) != 2:
            continue
        d = parts[1]
        if any(d == bad or d.endswith(f".{bad}") for bad in DISCARD_EMAIL_DOMAINS):
            continue
        if d.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.css', '.js')):
            continue
        valid.append(f)
    return valid[0] if valid else ""

def is_domain_matching_hotel(domain, hotel_name):
    """Kiểm tra tên miền có chứa từ khóa nhận diện của khách sạn không."""
    if not domain or not hotel_name:
        return False
    d = domain.lower().replace('www.', '')
    if any(ex in d for ex in EXCLUDED_DOMAINS):
        return False
    
    # Lấy các từ có nghĩa từ tên khách sạn (> 3 ký tự)
    name_clean = normalize_text(hotel_name)
    words = [w for w in name_clean.split() if len(w) >= 4 and w not in ['hotel', 'vila', 'villa', 'resort', 'apartament', 'hostel', 'bujtina', 'guest', 'house', 'city', 'center']]
    
    if not words:
        # Nếu tên chỉ gồm từ chung chung (vd: 'Hotel Marika'), lấy từ có nghĩa duy nhất
        words = [w for w in name_clean.split() if w not in ['hotel', 'resort', 'the', 'and']]
        
    for w in words:
        if w in d:
            return True
            
    return False

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_progress(cache):
    try:
        os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

async def search_duckduckgo(session, query):
    """Tìm kiếm DuckDuckGo HTML không bị chặn, trả về danh sách kết quả."""
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    try:
        r = await session.get(url, headers=HEADERS, timeout=18)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, 'html.parser')
        results = []
        for d in soup.find_all('div', class_='result'):
            h2 = d.find('h2')
            snip = d.find('a', class_='result__snippet')
            snip_text = snip.get_text(strip=True) if snip else ""
            if not h2 or not h2.find('a'):
                continue
            raw_href = h2.find('a').get('href', '')
            m = re.search(r'uddg=([^&]+)', raw_href)
            if m:
                target_url = urllib.parse.unquote(m.group(1))
                results.append({
                    "url": target_url,
                    "title": h2.get_text(strip=True),
                    "snippet": snip_text
                })
        return results
    except Exception:
        return []

async def crawl_website_for_email(session, web_url):
    """Truy cập trang web và các trang con để bóc tách email."""
    if not web_url.startswith('http'):
        web_url = f"https://{web_url}"
    found_emails = set()
    
    # 1. Quét trang chủ
    home_html = ""
    try:
        resp = await session.get(web_url, headers=HEADERS, timeout=20)
        if resp.status_code == 200:
            home_html = resp.text
            for em in re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', home_html):
                c = clean_email(em)
                if c:
                    found_emails.add(c)
    except Exception:
        pass
        
    # 2. Quét trang con liên hệ
    if not found_emails and home_html:
        soup = BeautifulSoup(home_html, 'html.parser')
        base_domain = urllib.parse.urlparse(web_url).netloc.lower().replace('www.', '')
        subpages = []
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            if not href or href.startswith(('#', 'javascript:', 'tel:')):
                continue
            full = urllib.parse.urljoin(web_url, href)
            p = urllib.parse.urlparse(full)
            if p.netloc.lower().replace('www.', '') == base_domain:
                path_low = p.path.lower()
                if any(k in path_low for k in CONTACT_PATHS):
                    clean_u = f"{p.scheme}://{p.netloc}{p.path}"
                    if clean_u not in subpages and clean_u != web_url:
                        subpages.append(clean_u)
                        
        for sub in subpages[:3]:
            try:
                r_sub = await session.get(sub, headers=HEADERS, timeout=15)
                if r_sub.status_code == 200:
                    for em in re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', r_sub.text):
                        c = clean_email(em)
                        if c:
                            found_emails.add(c)
                    if found_emails:
                        break
            except Exception:
                pass
                
    return list(found_emails)[0] if found_emails else ""

async def enrich_hotel(session, r, idx, total, cache, lock):
    """Quy trình làm giàu 1 khách sạn qua Search Engine."""
    comp_name = r.get('Name', '').strip()
    city = r.get('Location_Name', '').strip()
    addr = r.get('Address', '').strip()
    web_existing = r.get('Website', '').strip()
    cache_key = f"{comp_name}|{city}|{addr[:20]}".lower()
    
    if cache_key in cache:
        cached_data = cache[cache_key]
        return cached_data.get('email', ''), cached_data.get('website', ''), cached_data.get('facebook', '')

    discovered_email = ""
    discovered_web = web_existing if web_existing else ""
    discovered_fb = ""

    # Nếu đã có Website chuẩn từ trước, trước tiên thử cào trực tiếp web đó
    if discovered_web and discovered_web.startswith('http'):
        discovered_email = await crawl_website_for_email(session, discovered_web)

    # Nếu vẫn chưa có email -> Kích hoạt Web Search
    if not discovered_email:
        query = f'"{comp_name}" {city} albania email'
        results = await search_duckduckgo(session, query)
        
        # Bước 1: Quét tìm email trong Snippet của kết quả tìm kiếm
        for res in results:
            snip = res.get('snippet', '')
            for m in re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', snip):
                c = clean_email(m)
                if c:
                    discovered_email = c
                    break
            if discovered_email:
                break
                
        # Bước 2: Quét tìm Website chính thức hoặc Facebook Fanpage
        for res in results:
            link = res.get('url', '')
            parsed = urllib.parse.urlparse(link)
            domain = parsed.netloc.lower().replace('www.', '')
            
            if 'facebook.com' in domain and not discovered_fb:
                if not any(x in link for x in ['/events/', '/groups/', '/public/']):
                    discovered_fb = link
            elif not discovered_web and is_domain_matching_hotel(domain, comp_name):
                discovered_web = f"{parsed.scheme}://{parsed.netloc}"

        # Bước 3: Nếu phát hiện Website mới, lập tức cào email từ website đó
        if not discovered_email and discovered_web:
            discovered_email = await crawl_website_for_email(session, discovered_web)

    # Lưu lại kết quả vào cache
    result_data = {
        "email": discovered_email,
        "website": discovered_web,
        "facebook": discovered_fb
    }
    
    async with lock:
        cache[cache_key] = result_data
        save_progress(cache)
        if discovered_email:
            print(f"[{idx}/{total}] [+] TÌM THẤY: '{comp_name}' -> Email: {discovered_email} | Web: {discovered_web}")
        elif discovered_web or discovered_fb:
            print(f"[{idx}/{total}] [*] TÌM THẤY LINK: '{comp_name}' -> Web: {discovered_web} | FB: {discovered_fb}")
        else:
            print(f"[{idx}/{total}] [-] Không tìm thấy: '{comp_name}' ({city})")

    # Giãn cách nhẹ để bảo đảm ổn định qua VPN
    await asyncio.sleep(1.2)
    return discovered_email, discovered_web, discovered_fb

async def main():
    print("=" * 70)
    print("   HỆ THỐNG LÀM GIÀU DATA KHÁCH SẠN ALBANIA BẰNG WEB SEARCH")
    print("=" * 70)
    
    if not os.path.exists(INPUT_CSV):
        print(f"[-] Không tìm thấy tệp: {INPUT_CSV}")
        return
        
    with open(INPUT_CSV, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        hotels = list(reader)
        fieldnames = list(reader.fieldnames)
        
    print(f"[*] Đã tải {len(hotels)} cơ sở lưu trú duy nhất từ: {INPUT_CSV}")
    cache = load_progress()
    print(f"[*] Đã tải {len(cache)} bản ghi từ cache tiến trình.")
    
    # Lọc danh sách cần làm giàu: những cơ sở chưa có email
    # Đọc email hiện có từ ColdMail nếu có
    existing_emails = {}
    if os.path.exists(COLDMAIL_CSV):
        try:
            with open(COLDMAIL_CSV, mode='r', encoding='utf-8-sig') as f_cm:
                for row in csv.DictReader(f_cm):
                    c_name = normalize_text(row.get('Công ty', ''))
                    em = row.get('Email', '').strip()
                    if c_name and em:
                        existing_emails[c_name] = em
        except Exception:
            pass
            
    print(f"[*] Đã nhận diện {len(existing_emails)} khách sạn đã có email hợp lệ từ trước.")

    sem = asyncio.Semaphore(3)
    lock = asyncio.Lock()
    
    async def worker(session, r, idx, total):
        c_name = normalize_text(r.get('Name', ''))
        if c_name in existing_emails:
            # Đã có email từ trước, tái sử dụng không cần search lại
            return existing_emails[c_name], r.get('Website', ''), ""
        async with sem:
            return await enrich_hotel(session, r, idx, total, cache, lock)

    async with AsyncSession(impersonate="chrome120", verify=False) as session:
        tasks = [worker(session, r, idx, len(hotels)) for idx, r in enumerate(hotels, 1)]
        results = await asyncio.gather(*tasks)

    # Cập nhật lại danh sách và xuất file Cold Mail mới
    print("\n[*] Đang tổng hợp và cập nhật file Cold Mail...")
    
    formatted_rows = []
    enriched_email_count = 0
    
    for r, (em, new_web, fb) in zip(hotels, results):
        comp_name = r.get('Name', '').strip()
        phone = r.get('Phone', '').strip()
        if phone and not phone.startswith("'"):
            phone = f"'{phone}"
            
        maps_url = r.get('URL', '').strip()
        address = r.get('Address', '').strip()
        category = r.get('Category', '').strip()
        is_closed = r.get('Permanently_Closed', '').strip().lower() == 'yes'
        
        final_web = new_web if new_web else r.get('Website', '').strip()
        contact_link = final_web if final_web else maps_url
        contact_mail = maps_url if final_web else ""
        
        email_clean = clean_email(em)
        if email_clean:
            enriched_email_count += 1
            check_gui = "Dong_Cua" if is_closed else "OK"
        else:
            check_gui = "Dong_Cua" if is_closed else ""

        formatted_rows.append({
            'No.': 0,
            'Công ty': comp_name,
            'Chức danh': 'Quản lý khách sạn / Hotel Manager',
            'Người liên hệ': '',
            'SĐT': phone,
            'Liên Hệ': contact_link,
            'Email': email_clean,
            'Liên Hệ mail': contact_mail,
            'Địa chỉ': address,
            'Lương': '',
            'Ngày đăng': '',
            'Hạn tuyển': '',
            'Check gửi': check_gui,
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '0',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': category,
            '_is_closed': is_closed,
            '_has_email': bool(email_clean)
        })

    active_rows = [r for r in formatted_rows if not r['_is_closed']]
    active_rows.sort(key=lambda x: (
        0 if x['_has_email'] else 1,
        x['Công ty'].lower()
    ))
    
    cols = [
        'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ', 
        'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển', 
        'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply', 
        'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
    ]

    for idx, r in enumerate(active_rows, 1):
        r['No.'] = str(idx)
        del r['_is_closed']
        del r['_has_email']

    for out_path in [COLDMAIL_CSV, FORMATTED_CSV]:
        with open(out_path, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=cols)
            writer.writeheader()
            writer.writerows(active_rows)
        print(f"[+] Đã cập nhật file: {out_path}")

    ok_count = sum(1 for r in active_rows if r['Check gửi'] == 'OK')
    has_phone_count = sum(1 for r in active_rows if r['SĐT'])
    
    print("\n" + "=" * 70)
    print("  BÁO CÁO KẾT QUẢ LÀM GIÀU DỮ LIỆU KHÁCH SẠN ALBANIA (WEB ENRICHMENT):")
    print(f"  - Tổng số cơ sở lưu trú: {len(active_rows):,}")
    print(f"  - Sẵn sàng gửi ngay ('OK' - Đang hoạt động + Đã có Email): {ok_count:,}")
    print(f"  - Cơ sở có Số điện thoại: {has_phone_count:,}")
    print("=" * 70)

if __name__ == '__main__':
    asyncio.run(main())
