import sys
import os
import re
import json
import urllib.parse
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from curl_cffi import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

MASTER_CSV = "KR_AGCY_SHIP_2COL.csv"
BACKUP_CSV = "data/formatted/KR_AGCY_SHIP_2COL.csv"
CACHE_FILE = "data/cache/naver_raw_enriched.json"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
}

DISCARD_PATTERNS = [
    r'@\d+\.', r'\.png$', r'\.jpg$', r'\.svg$', r'\.gif$', r'wixpress\.com',
    r'sentry\.io', r'example\.com', r'yourcompany', r'youremail', r'domain\.com',
    r'google-calendar', r'noto-sans', r'aos@', r'core-js', r'webpack', r'test@'
]

REGIONS = [
    '영암', '거제', '울산', '군산', '목포', '창원', '통영', '부산', '진해', '여수', 
    '광양', '포항', '동해', '인천', '평택', '당진', '보령', '태안', '제주', '강릉', '속초', '삼척'
]

def clean_company_name(name):
    cleaned = re.sub(r'\(주\)|\(유\)|\(사\)|\(재\)|주식회사|유한회사|합자회사', '', str(name)).strip()
    return cleaned

def extract_region(addr):
    addr_str = str(addr)
    for reg in REGIONS:
        if reg in addr_str:
            return reg
    return ""

def search_naver_place(query):
    url = f"https://pcmap.place.naver.com/place/list?query={urllib.parse.quote(query)}"
    try:
        r = requests.get(url, headers=HEADERS, impersonate='chrome120', timeout=8)
        if r.status_code != 200:
            return []
            
        match = re.search(r'window\.__APOLLO_STATE__\s*=\s*(\{.+?\});\s*(?:window\.|</script>)', r.text, re.DOTALL)
        if not match:
            match = re.search(r'window\.__APOLLO_STATE__\s*=\s*(\{.+?\})\s*;', r.text, re.DOTALL)
            
        if not match:
            return []
            
        state = json.loads(match.group(1))
        places = []
        for k, v in state.items():
            if k.startswith('PlaceListBusinessesItem:'):
                places.append(v)
        return places
    except Exception:
        return []

def get_naver_place_detail(place_id):
    url = f"https://pcmap.place.naver.com/place/{place_id}/home"
    try:
        r = requests.get(url, headers=HEADERS, impersonate='chrome120', timeout=8)
        if r.status_code != 200:
            return None, None, None
            
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # 1. Phone extraction
        phone = None
        m_phone = re.search(r'"phone":"([^"]+)"', r.text)
        if m_phone and m_phone.group(1):
            phone = m_phone.group(1).strip()
        if not phone:
            m_phone2 = re.search(r'"phoneInfo":\{"__typename":"PlacePhoneInfo","phone":"([^"]+)"', r.text)
            if m_phone2 and m_phone2.group(1):
                phone = m_phone2.group(1).strip()
                
        # 2. Homepage / Website / Blog extraction
        website = None
        hp_links = soup.find_all('a', attrs={'data-nlog-area': lambda x: x and 'url' in x})
        for a in hp_links:
            href = a.get('href', '').strip()
            if href.startswith('http') and not href.startswith('https://map.naver.com'):
                website = href
                break
                
        if not website:
            for a in soup.find_all('a', href=True):
                href = a.get('href', '').strip()
                if ('blog.naver.com' in href or 'modoo.at' in href) and not href.startswith('https://map.naver.com'):
                    website = href
                    break
                    
        # 3. Road address
        m_addr = re.search(r'"roadAddress":"([^"]+)"', r.text)
        road_addr = m_addr.group(1).strip() if m_addr else None
        
        return phone, website, road_addr
    except Exception:
        return None, None, None

def scan_website_email(url):
    if not url or not url.startswith('http') or 'cafe.naver.com' in url:
        return None
    try:
        r = requests.get(url, impersonate='chrome120', timeout=6, verify=False)
        if r.status_code != 200:
            return None
        raw_emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', r.text)
        valid = []
        for e in raw_emails:
            e_clean = e.lower().strip()
            if any(re.search(pat, e_clean) for pat in DISCARD_PATTERNS):
                continue
            if len(e_clean.split('@')[0]) < 2 or len(e_clean.split('@')[1]) < 4:
                continue
            valid.append(e_clean)
        if valid:
            return valid[0]
        return None
    except Exception:
        return None

def format_phone(phone_str):
    if not phone_str or str(phone_str).strip().lower() in ['nan', 'none', '']:
        return ""
    p = str(phone_str).strip()
    return f"'{p}" if not p.startswith("'") else p

def process_single_company(row_info):
    c_name, c_addr = row_info
    clean_name = clean_company_name(c_name)
    reg = extract_region(c_addr)
    
    q = f"{clean_name} {reg}" if reg else clean_name
    places = search_naver_place(q)
    if not places and reg:
        places = search_naver_place(clean_name)
        
    matched = None
    if places:
        for p in places:
            p_name = p.get('name', '')
            p_addr = p.get('roadAddress', '') or p.get('address', '')
            if (clean_name in p_name or p_name in clean_name) and len(clean_name) >= 2:
                if not reg or (reg in p_addr or reg in c_addr):
                    matched = p
                    break
                    
    res_phone, res_web, res_addr, res_email = None, None, None, None
    if matched:
        pid = matched.get('id')
        res_phone, res_web, res_addr = get_naver_place_detail(pid)
        if res_web:
            res_email = scan_website_email(res_web)
            
    return {
        'matched_name': matched.get('name') if matched else None,
        'matched_id': matched.get('id') if matched else None,
        'naver_phone': res_phone,
        'naver_web': res_web,
        'naver_addr': res_addr,
        'discovered_email': res_email
    }

def main():
    os.makedirs("data/cache", exist_ok=True)
    os.makedirs("data/formatted", exist_ok=True)
    
    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"Loaded existing cache: {len(cache)} entries.")
        except Exception as e:
            print(f"Error loading cache: {e}")
            cache = {}
            
    if not os.path.exists(MASTER_CSV):
        print(f"Master file {MASTER_CSV} not found!")
        return
        
    df = pd.read_csv(MASTER_CSV, encoding='utf-8-sig')
    print(f"Master CSV total rows: {len(df)}")
    
    has_email_mask = df['Email'].notna() & (df['Email'].astype(str).str.strip() != '') & (df['Email'].astype(str).str.lower() != 'nan')
    proven_df = df[has_email_mask].copy()
    raw_df = df[~has_email_mask].copy()
    
    print(f"Proven rows (top tier with email): {len(proven_df)}")
    print(f"Raw rows to enrich: {len(raw_df)}")
    
    # Identify items to query
    to_query = []
    for idx, row in raw_df.iterrows():
        c_name = str(row['Công ty']).strip()
        c_addr = str(row['Địa chỉ']).strip() if pd.notna(row['Địa chỉ']) else ""
        cache_key = f"{c_name}___{c_addr}"
        if cache_key not in cache:
            to_query.append((cache_key, c_name, c_addr))
            
    print(f"Items already cached: {len(cache)}. Items remaining to query: {len(to_query)}")
    
    lock = threading.Lock()
    processed_count = 0
    total_to_query = len(to_query)
    
    if total_to_query > 0:
        print(f"Starting parallel enrichment with 6 workers for {total_to_query} companies...")
        with ThreadPoolExecutor(max_workers=6) as executor:
            future_to_key = {
                executor.submit(process_single_company, (c_name, c_addr)): cache_key
                for cache_key, c_name, c_addr in to_query
            }
            for future in as_completed(future_to_key):
                cache_key = future_to_key[future]
                try:
                    res = future.result()
                except Exception as e:
                    res = {'matched_name': None, 'matched_id': None, 'naver_phone': None, 'naver_web': None, 'naver_addr': None, 'discovered_email': None}
                
                with lock:
                    cache[cache_key] = res
                    processed_count += 1
                    if processed_count % 10 == 0 or processed_count == total_to_query:
                        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                            json.dump(cache, f, ensure_ascii=False, indent=2)
                        print(f"[{processed_count}/{total_to_query}] enriched. Total in cache: {len(cache)}")
                        
    # Final cache save
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
        
    print(f"\nAll {len(cache)} entries processed and cached. Building updated CSV...")
    
    new_phone_count = 0
    new_web_count = 0
    new_email_count = 0
    
    updated_raw_rows = []
    newly_promoted_rows = []
    
    for idx, row in raw_df.iterrows():
        c_name = str(row['Công ty']).strip()
        c_addr = str(row['Địa chỉ']).strip() if pd.notna(row['Địa chỉ']) else ""
        c_phone = str(row['SĐT']).strip() if pd.notna(row['SĐT']) else ""
        c_web = str(row['Liên Hệ']).strip() if pd.notna(row['Liên Hệ']) else ""
        cache_key = f"{c_name}___{c_addr}"
        entry = cache.get(cache_key, {})
        
        final_phone = c_phone
        if entry.get('naver_phone'):
            final_phone = format_phone(entry['naver_phone'])
            new_phone_count += 1
        elif c_phone and c_phone.lower() != 'nan':
            final_phone = format_phone(c_phone)
            
        final_web = c_web if (c_web and c_web.lower() != 'nan') else ""
        if entry.get('naver_web'):
            final_web = entry['naver_web']
            new_web_count += 1
            
        final_email = ""
        if entry.get('discovered_email'):
            final_email = entry['discovered_email']
            new_email_count += 1
            
        final_addr = c_addr
        if entry.get('naver_addr') and (not c_addr or len(entry['naver_addr']) > len(c_addr)):
            final_addr = entry['naver_addr']
            
        new_row = row.copy()
        new_row['SĐT'] = final_phone
        new_row['Liên Hệ'] = final_web
        new_row['Địa chỉ'] = final_addr
        
        if final_email:
            new_row['Email'] = final_email
            new_row['Liên Hệ mail'] = final_email
            new_row['Check gửi'] = 'Đang rà soát'
            newly_promoted_rows.append(new_row)
        else:
            updated_raw_rows.append(new_row)
            
    promoted_df = pd.DataFrame(newly_promoted_rows) if newly_promoted_rows else pd.DataFrame(columns=df.columns)
    remaining_raw_df = pd.DataFrame(updated_raw_rows) if updated_raw_rows else pd.DataFrame(columns=df.columns)
    
    # Combine: Proven 68 -> Newly Promoted -> Remaining raw
    final_dfs = [proven_df]
    if not promoted_df.empty:
        final_dfs.append(promoted_df)
    if not remaining_raw_df.empty:
        final_dfs.append(remaining_raw_df)
        
    final_master_df = pd.concat(final_dfs, ignore_index=True)
    final_master_df['SĐT'] = final_master_df['SĐT'].apply(format_phone)
    final_master_df['No.'] = range(1, len(final_master_df) + 1)
    
    expected_cols = [
        'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ', 
        'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển', 
        'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply', 
        'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
    ]
    for col in expected_cols:
        if col not in final_master_df.columns:
            final_master_df[col] = ""
    final_master_df = final_master_df[expected_cols]
    
    final_master_df.to_csv(MASTER_CSV, index=False, encoding='utf-8-sig')
    final_master_df.to_csv(BACKUP_CSV, index=False, encoding='utf-8-sig')
    
    print("\n=== HOÀN TẤT LÀM GIÀU DỮ LIỆU NAVER MAP ===")
    print(f"Tổng số dòng: {len(final_master_df)}")
    total_with_email = len(proven_df) + len(promoted_df)
    print(f"Công ty có Email (Ưu tiên đầu file): {total_with_email} (68 đối tác sạch + {len(promoted_df)} mới phát hiện)")
    print(f"Công ty thô còn lại đã làm giàu SĐT/Web: {len(remaining_raw_df)}")
    print(f"SĐT văn phòng mới bổ sung: {new_phone_count}")
    print(f"Website / Blog mới tìm thấy: {new_web_count}")
    print(f"Đã lưu thành công vào: {MASTER_CSV} và {BACKUP_CSV}")

if __name__ == "__main__":
    main()
