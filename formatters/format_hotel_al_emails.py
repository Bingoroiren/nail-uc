# -*- coding: utf-8 -*-
"""
Hệ thống Tiền xử lý & Làm giàu Email Khách sạn Albania:
1. Đọc dữ liệu từ data/raw/hotel_albania.csv.
2. Khử trùng triệt để bằng Google Place ID và Tên + SĐT.
3. Bóc tách Email chuyên sâu từ Website chính thức (Trang chủ + Trang liên hệ /kontakt, /booking...).
4. Mở rộng tiền tố email đặc thù ngành khách sạn (reservations@, booking@, reception@, info@...).
5. Lọc bỏ hoàn toàn các trang OTA (Booking, Agoda, Airbnb...) và email rác/template.
6. Chuyển đổi về đúng Template Cold Mail 20 cột chuẩn của workspace.
"""

import asyncio
import csv
import json
import os
import re
import sys
import urllib.parse
from bs4 import BeautifulSoup

try:
    from curl_cffi.requests import AsyncSession
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False
    import aiohttp

# Ensure UTF-8 console output
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)

CANDIDATE_INPUTS = [
    os.path.join(ROOT_DIR, "data", "formatted", "hotel_albania_with_emails.csv"),
    os.path.join(ROOT_DIR, "data", "raw", "hotel_albania.csv")
]

INPUT_CSV = CANDIDATE_INPUTS[0] if os.path.exists(CANDIDATE_INPUTS[0]) else CANDIDATE_INPUTS[1]
OUTPUT_FORMATTED = os.path.join(ROOT_DIR, "data", "formatted", "hotel_albania_with_emails_formatted.csv")
OUTPUT_COLDMAIL_ROOT = os.path.join(ROOT_DIR, "Khách sạn Albania - ColdMail.csv")
PROGRESS_FILE = os.path.join(ROOT_DIR, "data", "progress", "scraping_progress_hotel_al_emails.json")

# Albanian Category Translations to Vietnamese
CATEGORY_TRANSLATIONS = {
    "hotel me 5 yje": "Khách sạn 5 sao (Albania)",
    "hotel me 4 yje": "Khách sạn 4 sao (Albania)",
    "hotel me 3 yje": "Khách sạn 3 sao (Albania)",
    "hotel me 2 yje": "Khách sạn 2 sao (Albania)",
    "hotel me 1 yje": "Khách sạn 1 sao (Albania)",
    "5-star hotel": "Khách sạn 5 sao (Albania)",
    "4-star hotel": "Khách sạn 4 sao (Albania)",
    "3-star hotel": "Khách sạn 3 sao (Albania)",
    "2-star hotel": "Khách sạn 2 sao (Albania)",
    "1-star hotel": "Khách sạn 1 sao (Albania)",
    "hotel": "Khách sạn (Albania)",
    "vilë": "Biệt thự nghỉ dưỡng / Villa (Albania)",
    "vila": "Biệt thự nghỉ dưỡng / Villa (Albania)",
    "villa": "Biệt thự nghỉ dưỡng / Villa (Albania)",
    "shtrat & mëngjes": "Bed & Breakfast / B&B (Albania)",
    "shtrat dhe mëngjes": "Bed & Breakfast / B&B (Albania)",
    "bed & breakfast": "Bed & Breakfast / B&B (Albania)",
    "bed and breakfast": "Bed & Breakfast / B&B (Albania)",
    "ambient pushimi me qira": "Nhà nghỉ / Căn hộ cho thuê du lịch (Albania)",
    "shtëpi për mysafirë": "Nhà nghỉ / Guesthouse (Albania)",
    "shtëpi mysafirësh": "Nhà nghỉ / Guesthouse (Albania)",
    "guest house": "Nhà nghỉ / Guesthouse (Albania)",
    "guesthouse": "Nhà nghỉ / Guesthouse (Albania)",
    "homestay": "Homestay / Nhà dân du lịch (Albania)",
    "alloggio in famiglia": "Homestay / Nhà dân du lịch (Albania)",
    "apartament pushues": "Căn hộ dịch vụ du lịch (Albania)",
    "apartament me qira për pushime": "Căn hộ dịch vụ du lịch (Albania)",
    "holiday apartment rental": "Căn hộ dịch vụ du lịch (Albania)",
    "vacation home rental": "Nhà nghỉ cho thuê kỳ nghỉ (Albania)",
    "bujtinë": "Nhà nghỉ truyền thống / Bujtinë (Albania)",
    "bujtine": "Nhà nghỉ truyền thống / Bujtinë (Albania)",
    "bujtina": "Nhà nghỉ truyền thống / Bujtinë (Albania)",
    "resort hotel": "Khu nghỉ dưỡng / Resort (Albania)",
    "vendpushim": "Khu nghỉ dưỡng / Resort (Albania)",
    "hotel vendpushimi": "Khu nghỉ dưỡng / Resort (Albania)",
    "motel": "Nhà nghỉ ven đường / Motel (Albania)",
    "hostel": "Nhà trọ du lịch / Hostel (Albania)",
    "inn": "Quán trọ / Nhà nghỉ (Albania)",
    "lodging": "Cơ sở lưu trú du lịch (Albania)"
}

HOTEL_EMAIL_PREFIXES = {
    'reservations': 40,
    'booking': 40,
    'prenotazioni': 40,
    'reception': 35,
    'frontdesk': 35,
    'stay': 30,
    'info': 25,
    'kontakt': 25,
    'contact': 25,
    'prenotazione': 25,
    'sales': 20,
    'admin': 15,
    'office': 15,
    'welcome': 15
}

BAD_KEYWORDS = {
    'wix', 'wixpress', 'sentry', 'no-reply', 'noreply', 'donotreply', 
    'test@', 'example@', 'domain.com', 'superio', 'placeholder',
    'support@theme', 'support@elementor', 'info@mysite.com'
}

DISCARD_DOMAINS = {
    'example.com', 'example.org', 'example.net', 'yourdomain.com', 
    'email.com', 'domain.com', 'website.com', 'company.com', 
    'sentry.io', 'git.com', 'github.com', 'test.com', 'g.co',
    'booking.com', 'agoda.com', 'airbnb.com', 'expedia.com', 'tripadvisor.com',
    'hotels.com', 'trivago.com', 'kayak.com', 'priceline.com', 'hostelworld.com',
    'vrbo.com', 'viator.com', 'getyourguide.com', 'freecancellations.com',
    'bluepillow.com', 'bluepillow.it', 'bluepillow.de', 'placescollective.com',
    'highlandhikecottage.eu', 'ocean-vista-lodge.eu', 'brit-voyager.eu',
    'backpackinghaven.eu', 'reservation.expert', 'exelentbnb.com',
    'pik-host.al', 'gs-collection.com', 'kondostays.com', 'tirent.al',
    'albania-hotel.top', 'hotelalbanian.com', 'albania-hotels.net'
}

DISCARD_EXACT_EMAILS = {
    'albania@gmail.com', 'info@pik-host.al', 's.giordani@bluepillow.com',
    'support@freecancellations.com', 'info@kondostays.com', 'info@tirent.al',
    'reservations@gs-collection.com', 'support@elementor.com', 'info@mysite.com'
}

def normalize_text(text):
    if not text:
        return ""
    t = text.lower().strip()
    t = re.sub(r'[\s\-_\.,\|/]+', ' ', t)
    return t.strip()

def deduplicate_and_merge_hotels(rows):
    merged_dict = {}
    for r in rows:
        name = normalize_text(r.get('Name', ''))
        if not name:
            continue
        phone = re.sub(r'[^0-9+]', '', r.get('Phone', ''))
        web = normalize_text(r.get('Website', ''))
        loc = normalize_text(r.get('Location_Name', ''))
        addr = normalize_text(r.get('Address', ''))[:30]
        pid = extract_place_id(r.get('URL', ''))
        
        match_id = None
        for k, v in merged_dict.items():
            if pid and v['pid'] and pid == v['pid']:
                match_id = k; break
            if name == v['norm_name']:
                if phone and v['clean_phone'] and phone == v['clean_phone']:
                    match_id = k; break
                if web and v['norm_web'] and web == v['norm_web']:
                    match_id = k; break
                if addr and v['norm_addr'] and (addr in v['norm_addr'] or v['norm_addr'] in addr):
                    match_id = k; break
                if loc and v['norm_loc'] and loc == v['norm_loc']:
                    match_id = k; break
                if not phone and not web and not addr:
                    match_id = k; break

        if match_id is not None:
            target = merged_dict[match_id]['data']
            if not target.get('Phone') and r.get('Phone'):
                target['Phone'] = r['Phone']
                merged_dict[match_id]['clean_phone'] = phone
            if not target.get('Website') and r.get('Website'):
                target['Website'] = r['Website']
                merged_dict[match_id]['norm_web'] = web
            if not target.get('Address') and r.get('Address'):
                target['Address'] = r['Address']
                merged_dict[match_id]['norm_addr'] = addr
            if r.get('Permanently_Closed', '').strip().lower() == 'yes':
                target['Permanently_Closed'] = 'Yes'
        else:
            new_id = len(merged_dict)
            merged_dict[new_id] = {
                'norm_name': name,
                'clean_phone': phone,
                'norm_web': web,
                'norm_loc': loc,
                'norm_addr': addr,
                'pid': pid,
                'data': dict(r)
            }
            
    return [v['data'] for v in merged_dict.values()]

OTA_AND_DIRECTORY_DOMAINS = {
    # Global OTAs & Booking Platforms
    'booking.com', 'agoda.com', 'airbnb.com', 'expedia.com', 'tripadvisor.com', 
    'hotels.com', 'trivago.com', 'kayak.com', 'priceline.com', 'hostelworld.com', 
    'vrbo.com', 'viator.com', 'getyourguide.com', 'makemytrip.com', 'trip.com', 
    'orbitz.com', 'travelocity.com', 'hotwire.com', 'skyscanner.com', 'opentable.com',
    'booking.al', 'albania-booking.com', 'albania-hotels.net', 'albanian-hotels.com',
    
    # Affiliates & Booking Aggregators
    'freecancellations.com', 'bluepillow.com', 'bluepillow.it', 'bluepillow.de', 'bluepillow.fr',
    'placescollective.com', 'highlandhikecottage.eu', 'ocean-vista-lodge.eu', 
    'brit-voyager.eu', 'backpackinghaven.eu', 'reservation.expert', 'exelentbnb.com',
    'linktr.ee', 'yellowpages.com', 'yellowpages.al', 'yellowpages.com.al',
    
    # Social Media & Generic platforms
    'facebook.com', 'fb.com', 'instagram.com', 'linkedin.com', 'youtube.com', 
    'twitter.com', 'x.com', 'pinterest.com', 'tiktok.com', 'google.com', 'g.co',
    'google.al', 'wikipedia.org'
}

def is_ota_or_directory_link(url):
    if not url:
        return True
    url_clean = urllib.parse.unquote(str(url)).strip().lower()
    if not url_clean.startswith(('http://', 'https://')):
        url_clean = f"https://{url_clean}"
    try:
        parsed = urllib.parse.urlparse(url_clean)
        netloc = parsed.netloc.lower()
        if netloc.startswith('www.'):
            netloc = netloc[4:]
            
        # Check direct domain or subdomains
        for d in OTA_AND_DIRECTORY_DOMAINS:
            if netloc == d or netloc.endswith(f".{d}"):
                return True
                
        # Check URL path patterns typical of affiliate/OTA search links
        path = parsed.path.lower()
        if '/search/' in path or '/search?' in url_clean:
            return True
        if any(x in netloc for x in ['pillow', 'cancellation', 'booking', 'voyager', 'haven', 'lodge', 'reservation']):
            if not any(x in netloc for x in ['hotel', 'resort', 'villa', 'bujtina', 'guest']):
                return True
    except Exception:
        pass
    return False

CONTACT_PATHS = [
    'kontakt', 'contact', 'kontakti', 'contact-us', 'kontakt-oss',
    'rreth-nesh', 'about', 'about-us', 'booking', 'reservations',
    'dhomat', 'rooms', 'prenotazioni'
]

def extract_place_id(url):
    if not url:
        return ""
    match = re.search(r'1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)', url)
    if match:
        return match.group(1).lower()
    return url.split('?')[0].lower()

def translate_category(cat_raw):
    if not cat_raw:
        return "Khách sạn / Lưu trú (Albania)"
    c_low = cat_raw.strip().lower()
    for k, v in CATEGORY_TRANSLATIONS.items():
        if k in c_low or c_low in k:
            return v
    return f"{cat_raw.strip()} (Albania)"

def clean_email(em_raw):
    if not em_raw:
        return ""
    em = urllib.parse.unquote(str(em_raw)).strip()
    em = re.sub(r'&quot;.*$', '', em)
    em = re.sub(r'\\+$', '', em)
    em = re.sub(r'\.\s+([a-z]{2,})', r'.\1', em, flags=re.I)
    em = re.sub(r'\s+', '', em)
    
    found = re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', em)
    valid = []
    for f in found:
        f_low = f.lower()
        if f_low in DISCARD_EXACT_EMAILS:
            continue
        if any(bad in f_low for bad in BAD_KEYWORDS):
            continue
        parts = f_low.split('@')
        if len(parts) != 2:
            continue
        domain = parts[1]
        if any(domain == d or domain.endswith(f".{d}") for d in DISCARD_DOMAINS):
            continue
        if domain.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.css', '.js')):
            continue
        valid.append(f_low)
    
    return valid[0] if valid else ""

def decode_cloudflare_email(hex_str):
    try:
        hex_data = bytes.fromhex(hex_str)
        key = hex_data[0]
        return ''.join(chr(b ^ key) for b in hex_data[1:])
    except Exception:
        return ""

def score_hotel_email(email, comp_domain=""):
    clean = clean_email(email)
    if not clean:
        return -1
    u, d = clean.split('@', 1)
    score = 10
    if comp_domain and (comp_domain in d or d in comp_domain):
        score += 30
    for pref, pts in HOTEL_EMAIL_PREFIXES.items():
        if u.startswith(pref):
            score += pts
            break
    return score

async def extract_emails_from_html(html, base_url=""):
    emails = set()
    if not html:
        return emails
        
    soup = BeautifulSoup(html, 'html.parser')
    
    # Cloudflare protected emails
    for cf in soup.find_all(attrs={"data-cfemail": True}):
        dec = decode_cloudflare_email(cf['data-cfemail'])
        if dec and '@' in dec:
            clean = clean_email(dec)
            if clean:
                emails.add(clean)
                
    # mailto: links
    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        if href.lower().startswith('mailto:'):
            raw = href[7:].split('?')[0].strip()
            clean = clean_email(raw)
            if clean:
                emails.add(clean)
                
    # Regex search in full body
    raw_matches = re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', html)
    for m in raw_matches:
        clean = clean_email(m)
        if clean:
            emails.add(clean)
            
    return emails

def find_contact_subpages(html, base_url):
    subpages = []
    if not html:
        return subpages
    try:
        soup = BeautifulSoup(html, 'html.parser')
        base_domain = urllib.parse.urlparse(base_url).netloc.lower().replace('www.', '')
        seen = set()
        
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            if not href or href.startswith('#') or href.startswith('javascript:') or href.startswith('tel:'):
                continue
            full_url = urllib.parse.urljoin(base_url, href)
            parsed = urllib.parse.urlparse(full_url)
            curr_domain = parsed.netloc.lower().replace('www.', '')
            
            if curr_domain != base_domain:
                continue
                
            path_lower = parsed.path.lower()
            if any(k in path_lower for k in CONTACT_PATHS):
                clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                if clean_url not in seen and clean_url != base_url:
                    seen.add(clean_url)
                    subpages.append(clean_url)
    except Exception:
        pass
    return subpages[:3]

async def crawl_hotel_website(session, url):
    if not url.startswith('http'):
        url = f"https://{url}"
        
    comp_domain = urllib.parse.urlparse(url).netloc.lower().replace('www.', '')
    all_emails = set()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "sq,it,en-US;q=0.8,en;q=0.5"
    }
    
    # 1. Fetch homepage
    home_html = ""
    try:
        resp = await session.get(url, timeout=25, headers=headers)
        if resp.status_code == 200:
            home_html = resp.text
            found = await extract_emails_from_html(home_html, url)
            all_emails.update(found)
    except Exception:
        pass
        
    # 2. Check contact subpages if no email found
    if not all_emails and home_html:
        subpages = find_contact_subpages(home_html, url)
        for sub in subpages:
            try:
                resp_sub = await session.get(sub, timeout=20, headers=headers)
                if resp_sub.status_code == 200:
                    found_sub = await extract_emails_from_html(resp_sub.text, sub)
                    all_emails.update(found_sub)
                    if all_emails:
                        break
            except Exception:
                pass
                
    if not all_emails:
        return ""
        
    scored = [(score_hotel_email(e, comp_domain), e) for e in all_emails]
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1] if scored and scored[0][0] > 0 else ""

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

async def main():
    print("=" * 70)
    print("   TIỀN XỬ LÝ & BÓC TÁCH EMAIL KHÁCH SẠN ALBANIA (COLD MAIL)")
    print("=" * 70)
    
    if not os.path.exists(INPUT_CSV):
        print(f"[-] Không tìm thấy tệp đầu vào: {INPUT_CSV}")
        print("    Vui lòng chạy bộ cào raw trước: runners/run_hotel_al.bat")
        return
        
    with open(INPUT_CSV, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        raw_rows = list(reader)
        
    print(f"[*] Đã tải {len(raw_rows)} bản ghi khách sạn thô từ: {INPUT_CSV}")
    
    # 1. Khử trùng nâng cao theo Tên, SĐT, Website, Địa chỉ và hợp nhất đa thuộc tính
    dedup_rows = deduplicate_and_merge_hotels(raw_rows)
    print(f"[*] Sau khử trùng và hợp nhất đa thuộc tính: {len(dedup_rows)} cơ sở lưu trú duy nhất thực tế (loại bỏ hoàn toàn {len(raw_rows) - len(dedup_rows)} bản ghi trùng lặp ảo).")
    
    # 2. Quét Email từ Website với Cache Checkpoint
    raw_cache = load_progress()
    # Làm sạch cache khỏi các email rác/hosting đã biết
    cache = {}
    for k, v in raw_cache.items():
        if not v:
            continue
        v_clean = clean_email(v)
        if v_clean:
            cache[k] = v_clean
    save_progress(cache)
    print(f"[*] Đã tải {len(cache)} kết quả email sạch từ cache.")
    
    sem = asyncio.Semaphore(6)
    lock = asyncio.Lock()
    
    async def process_hotel(session, r, idx, total):
        comp_name = r.get('Name', '').strip()
        web = r.get('Website', '').strip()
        pid = extract_place_id(r.get('URL', ''))
        
        if not web or not web.startswith('http'):
            return ""
            
        if is_ota_or_directory_link(web):
            print(f"[{idx}/{total}] [BỎ QUA NỀN TẢNG BOOKING/OTA] '{comp_name}' -> {web}")
            return ""
            
        if pid in cache:
            return cache[pid]
            
        async with sem:
            print(f"[{idx}/{total}] Đang quét email khách sạn: '{comp_name}' -> {web}...")
            em = await crawl_hotel_website(session, web)
            async with lock:
                cache[pid] = em
                save_progress(cache)
                if em:
                    print(f"  [+] TÌM THẤY EMAIL: {em}")
                else:
                    print(f"  [-] Không tìm thấy")
            return em

    if HAS_CURL_CFFI:
        async with AsyncSession(impersonate="chrome120", verify=False) as session:
            tasks = [process_hotel(session, r, idx, len(dedup_rows)) for idx, r in enumerate(dedup_rows, 1)]
            emails = await asyncio.gather(*tasks)
    else:
        # Fallback aiohttp
        async with aiohttp.ClientSession() as session:
            tasks = [process_hotel(session, r, idx, len(dedup_rows)) for idx, r in enumerate(dedup_rows, 1)]
            emails = await asyncio.gather(*tasks)

    # 3. Hậu kiểm tần suất email toàn bộ dataset:
    # Nếu 1 email xuất hiện ở >= 3 khách sạn và domain email không match tên/website của khách sạn -> Đánh dấu email rác/agency/hosting và loại bỏ!
    emails = list(emails)
    from collections import Counter
    email_counts = Counter(e.lower() for e in emails if e)
    
    for idx, em in enumerate(emails):
        if not em:
            continue
        em_low = em.lower()
        if em_low in DISCARD_EXACT_EMAILS:
            emails[idx] = ""
            continue
        d = em_low.split('@')[-1]
        if any(d == bad or d.endswith(f".{bad}") for bad in DISCARD_DOMAINS):
            emails[idx] = ""
            continue
        if email_counts[em_low] >= 3:
            comp_name = normalize_text(dedup_rows[idx].get('Name', ''))
            comp_web = normalize_text(dedup_rows[idx].get('Website', ''))
            em_user = em_low.split('@')[0]
            words = [w for w in comp_name.split() if len(w) > 3]
            match_name = any(w in em_user or w in d for w in words) if words else False
            match_web = (comp_web and (d in comp_web or comp_web in d))
            if not match_name and not match_web:
                emails[idx] = ""

    # 3. Chuẩn hóa sang Template Cold Mail 20 cột chuẩn
    formatted_rows = []
    for r, em in zip(dedup_rows, emails):
        comp_name = r.get('Name', '').strip()
        phone = r.get('Phone', '').strip()
        if phone and not phone.startswith("'"):
            phone = f"'{phone}"
            
        raw_website = r.get('Website', '').strip()
        official_website = "" if is_ota_or_directory_link(raw_website) else raw_website
        maps_url = r.get('URL', '').strip()
        address = r.get('Address', '').strip()
        category = translate_category(r.get('Category', ''))
        is_closed = r.get('Permanently_Closed', '').strip().lower() == 'yes'
        
        email_clean = clean_email(em)
        
        if is_closed:
            check_gui = "Dong_Cua"
        elif email_clean:
            check_gui = "OK"
        else:
            check_gui = ""
            
        contact_link = official_website if official_website else maps_url
        contact_mail = maps_url if official_website else ""
        
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

    # Lọc bỏ công ty đóng cửa
    active_rows = [r for r in formatted_rows if not r['_is_closed']]
    
    # Sắp xếp: OK lên đầu, tên A-Z
    active_rows.sort(key=lambda x: (
        0 if x['_has_email'] else 1,
        x['Công ty'].lower()
    ))
    
    fieldnames = [
        'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ', 
        'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển', 
        'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply', 
        'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
    ]

    for idx, r in enumerate(active_rows, 1):
        r['No.'] = str(idx)
        del r['_is_closed']
        del r['_has_email']

    # Xuất các file đầu ra
    outputs = [OUTPUT_FORMATTED, OUTPUT_COLDMAIL_ROOT]
    for out_path in outputs:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, mode='w', encoding='utf-8-sig', newline='') as f_out:
            writer = csv.DictWriter(f_out, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(active_rows)
        print(f"[+] Đã xuất file chuẩn Cold Mail: {out_path}")

    ok_count = sum(1 for r in active_rows if r['Check gửi'] == 'OK')
    has_phone_count = sum(1 for r in active_rows if r['SĐT'])
    
    print("\n" + "=" * 70)
    print("  BÁO CÁO KẾT QUẢ XỬ LÝ DỮ LIỆU KHÁCH SẠN ALBANIA:")
    print(f"  - Tổng số khách sạn / cơ sở lưu trú: {len(active_rows):,}")
    print(f"  - Sẵn sàng gửi ngay ('OK' - Đang hoạt động + Có Email): {ok_count:,}")
    print(f"  - Doanh nghiệp có Số điện thoại (chuẩn hóa nháy đơn): {has_phone_count:,}")
    print("=" * 70)

if __name__ == '__main__':
    asyncio.run(main())
