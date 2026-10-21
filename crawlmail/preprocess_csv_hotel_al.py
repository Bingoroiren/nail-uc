# -*- coding: utf-8 -*-
"""
Tiền xử lý dữ liệu Khách sạn Albania trước khi cào Email:
1. Đọc dữ liệu từ data/raw/hotel_albania.csv
2. Khử trùng triệt để bằng Tên chuẩn hóa, SĐT, Website, Địa chỉ, Khu vực và Place ID (loại bỏ hoàn toàn bản ghi ảo).
3. Hợp nhất thông tin (Smart Merge).
4. Tiền xử lý & làm sạch link Website: loại bỏ hoàn toàn các trang OTA, đặt phòng trung gian (Booking, Agoda, Bluepillow, Freecancellations, v.v.).
5. Lưu dữ liệu đã làm sạch vào data/raw/hotel_albania.csv để sẵn sàng cho crawlmail/email_scraper.py.
"""

import csv
import os
import re
import shutil
import urllib.parse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
INPUT_CSV = os.path.join(BASE_DIR, "data", "raw", "hotel_albania.csv")
BACKUP_CSV = os.path.join(BASE_DIR, "data", "raw", "hotel_albania_pre_dedup.csv")

OTA_AND_DIRECTORY_DOMAINS = {
    # Global OTAs & Booking Platforms
    'booking.com', 'agoda.com', 'airbnb.com', 'expedia.com', 'tripadvisor.com', 
    'hotels.com', 'trivago.com', 'kayak.com', 'priceline.com', 'hostelworld.com', 
    'vrbo.com', 'viator.com', 'getyourguide.com', 'makemytrip.com', 'trip.com', 
    'orbitz.com', 'travelocity.com', 'hotwire.com', 'skyscanner.com', 'opentable.com',
    'booking.al', 'albania-booking.com', 'albania-hotels.net', 'albanian-hotels.com',
    'allbookers.com', 'hotelscheck-in.com', 'hotelb3.com', 'seasonsnseasons.com',
    
    # Affiliates & Booking Aggregators
    'freecancellations.com', 'bluepillow.com', 'bluepillow.it', 'bluepillow.de', 'bluepillow.fr',
    'placescollective.com', 'highlandhikecottage.eu', 'ocean-vista-lodge.eu', 
    'brit-voyager.eu', 'backpackinghaven.eu', 'reservation.expert', 'exelentbnb.com',
    'holidayfuture.com', 'kondostays.com', 'grandstaycollection.com', 'travelnest.com',
    'beds24.com', 'simple-spot.site', 'thomasstraveltips.com', 'kalpazorental.com',
    'linktr.ee', 'yellowpages.com', 'yellowpages.al', 'yellowpages.com.al',
    'albania-hotel.top', 'hotelsalbanian.com', 'hotelalbanian.com',
    
    # Social Media & Generic platforms
    'facebook.com', 'fb.com', 'instagram.com', 'linkedin.com', 'youtube.com', 
    'twitter.com', 'x.com', 'pinterest.com', 'tiktok.com', 'google.com', 'g.co',
    'google.al', 'wikipedia.org', 'tirent.al'
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
            
        for d in OTA_AND_DIRECTORY_DOMAINS:
            if netloc == d or netloc.endswith(f".{d}"):
                return True
                
        path = parsed.path.lower()
        if '/search/' in path or '/search?' in url_clean or 'googleVR=1' in url_clean:
            return True
        if any(x in netloc for x in ['pillow', 'cancellation', 'booking', 'voyager', 'haven', 'lodge', 'reservation']):
            if not any(x in netloc for x in ['hotel', 'resort', 'villa', 'bujtina', 'guest']):
                return True
    except Exception:
        pass
    return False

def normalize_text(text):
    if not text:
        return ""
    t = text.lower().strip()
    t = re.sub(r'[\s\-_\.,\|/]+', ' ', t)
    return t.strip()

def extract_place_id(url):
    if not url:
        return ""
    match = re.search(r'1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)', url)
    if match:
        return match.group(1).lower()
    return url.split('?')[0].lower()

def preprocess():
    if not os.path.exists(INPUT_CSV):
        print(f"[-] Không tìm thấy file {INPUT_CSV}")
        return False

    print(f"[*] Sao lưu file gốc sang {BACKUP_CSV}...")
    shutil.copy2(INPUT_CSV, BACKUP_CSV)

    with open(INPUT_CSV, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        raw_rows = list(reader)
        fieldnames = list(reader.fieldnames) if reader.fieldnames else []

    print(f"[*] Đang xử lý khử trùng & lọc OTA cho {len(raw_rows)} bản ghi...")

    merged_dict = {}
    for r in raw_rows:
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

    dedup_list = [v['data'] for v in merged_dict.values()]

    # Làm sạch cột Website: loại bỏ link OTA trước khi cào mail
    clean_web_count = 0
    ota_dropped_count = 0
    for r in dedup_list:
        w = r.get('Website', '').strip()
        if w:
            if is_ota_or_directory_link(w):
                r['Website'] = ""
                ota_dropped_count += 1
            else:
                clean_web_count += 1

    with open(INPUT_CSV, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(dedup_list)

    print("\n" + "=" * 60)
    print("  KẾT QUẢ TIỀN XỬ LÝ DỮ LIỆU KHÁCH SẠN ALBANIA (CRAWLMAIL):")
    print(f"  - Số bản ghi thô ban đầu: {len(raw_rows):,}")
    print(f"  - Khách sạn / cơ sở lưu trú thực tế duy nhất: {len(dedup_list):,}")
    print(f"  - Số bản ghi trùng lặp ảo đã loại bỏ: {len(raw_rows) - len(dedup_list):,}")
    print(f"  - Link OTA / Booking / Thư bạ đã làm sạch: {ota_dropped_count:,}")
    print(f"  - Website chính chủ hợp lệ sẵn sàng cào mail: {clean_web_count:,}")
    print("=" * 60 + "\n")
    return True

if __name__ == '__main__':
    preprocess()
