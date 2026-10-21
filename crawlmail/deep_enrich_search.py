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
CACHE_FILE = "data/cache/deep_enrich_cache.json"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
}

DISCARD_PATTERNS = [
    r'@\d+\.', r'\.png$', r'\.jpg$', r'\.svg$', r'\.gif$', r'wixpress\.com',
    r'sentry\.io', r'example\.com', r'yourcompany', r'youremail', r'domain\.com',
    r'google-calendar', r'noto-sans', r'aos@', r'core-js', r'webpack', r'test@',
    r'contact@daangn\.com', r'admin@netfilcker\.com', r'bootstrap@', r'leaflet@',
    r'help@', r'support@naver\.com'
]

REGIONS = [
    '영암', '거제', '울산', '군산', '목포', '창원', '통영', '부산', '진해', '여수', 
    '광양', '포항', '동해', '인천', '평택', '당진', '보령', '태안', '제주'
]

def clean_company_name(name):
    return re.sub(r'\(주\)|\(유\)|\(사\)|\(재\)|주식회사|유한회사|합자회사', '', str(name)).strip()

def extract_region(addr):
    addr_str = str(addr)
    for reg in REGIONS:
        if reg in addr_str:
            return reg
    return ""

def format_phone(phone_str):
    if not phone_str or str(phone_str).strip().lower() in ['nan', 'none', '']:
        return ""
    p = str(phone_str).strip()
    return f"'{p}" if not p.startswith("'") else p

def scan_naver_blog(blog_id):
    if not blog_id:
        return None, None
    url_m = f"https://m.blog.naver.com/{blog_id}"
    url_p = f"https://m.blog.naver.com/ProfileIntro.naver?blogId={blog_id}"
    try:
        r_m = requests.get(url_m, headers=HEADERS, impersonate='chrome120', timeout=6)
        r_p = requests.get(url_p, headers=HEADERS, impersonate='chrome120', timeout=6)
        combined_text = r_m.text + " " + r_p.text
        
        raw_emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', combined_text)
        valid_emails = []
        for e in raw_emails:
            el = e.lower().strip()
            if not any(re.search(p, el) for p in DISCARD_PATTERNS):
                if len(el.split('@')[0]) >= 2 and len(el.split('@')[1]) >= 4:
                    valid_emails.append(el)
                    
        phones = re.findall(r'0\d{1,2}-\d{3,4}-\d{4}', combined_text)
        return (valid_emails[0] if valid_emails else None), (phones[0] if phones else None)
    except Exception:
        return None, None

def scan_website_deep(url):
    if not url or not url.startswith('http') or any(d in url for d in ['daangn.com', 'play.google.com']):
        return None, None
        
    if 'blog.naver.com' in url:
        parts = url.rstrip('/').split('/')
        blog_id = parts[-1] if not parts[-1].isdigit() else parts[-2]
        return scan_naver_blog(blog_id)
        
    try:
        r = requests.get(url, headers=HEADERS, impersonate='chrome120', timeout=6, verify=False)
        if r.status_code != 200:
            return None, None
            
        combined_text = r.text
        soup = BeautifulSoup(r.text, 'html.parser')
        sub_links = []
        for a in soup.find_all('a', href=True):
            href = a['href'].lower()
            if any(k in href for k in ['contact', 'intro', 'about', 'company', 'sub01', 'bbs']):
                if href.startswith('http'):
                    sub_links.append(a['href'])
                elif href.startswith('/'):
                    base_url = '/'.join(url.split('/')[:3])
                    sub_links.append(base_url + a['href'])
                    
        for sl in sub_links[:2]:
            try:
                r_sub = requests.get(sl, headers=HEADERS, impersonate='chrome120', timeout=5, verify=False)
                if r_sub.status_code == 200:
                    combined_text += " " + r_sub.text
            except Exception:
                pass
                
        raw_emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', combined_text)
        valid_emails = []
        for e in raw_emails:
            el = e.lower().strip()
            if not any(re.search(p, el) for p in DISCARD_PATTERNS):
                if len(el.split('@')[0]) >= 2 and len(el.split('@')[1]) >= 4:
                    valid_emails.append(el)
                    
        phones = re.findall(r'0\d{1,2}-\d{3,4}-\d{4}', combined_text)
        return (valid_emails[0] if valid_emails else None), (phones[0] if phones else None)
    except Exception:
        return None, None

def search_missing_web(clean_name, reg):
    # Query Naver Blog API
    q = f"{clean_name} {reg}" if reg else clean_name
    url_blog = f"https://section.blog.naver.com/ajax/SearchList.naver?countPerPage=3&currentPage=1&keyword={urllib.parse.quote(q)}&type=post"
    headers_blog = {
        'Referer': 'https://section.blog.naver.com/Search/Post.naver',
        'User-Agent': HEADERS['User-Agent']
    }
    found_url = None
    try:
        r = requests.get(url_blog, headers=headers_blog, impersonate='chrome120', timeout=6)
        raw = r.text
        j_idx = raw.find('{')
        if j_idx != -1:
            data = json.loads(raw[j_idx:])
            posts = data.get('result', {}).get('searchList', [])
            for p in posts:
                title = BeautifulSoup(p.get('title', ''), 'html.parser').get_text().strip()
                b_name = p.get('blogName', '').strip()
                post_url = p.get('postUrl', '').strip()
                # If clean_name is in title or blog_name
                if (clean_name in title or clean_name in b_name) and len(clean_name) >= 2:
                    found_url = post_url
                    break
    except Exception:
        pass
        
    # If not found via Blog API, try DuckDuckGo
    if not found_url:
        try:
            r_ddg = requests.post('https://html.duckduckgo.com/html/', data={'q': f'"{clean_name}" {reg} 인력'}, impersonate='chrome120', timeout=6)
            if r_ddg.status_code == 200:
                soup = BeautifulSoup(r_ddg.text, 'html.parser')
                for a in soup.select('a.result__url'):
                    txt = a.get_text().strip()
                    if ('blog.naver.com' in txt or 'modoo.at' in txt) and not any(d in txt for d in ['search', 'netfilcker', 'lolcalii']):
                        found_url = 'https://' + txt if not txt.startswith('http') else txt
                        break
        except Exception:
            pass
            
    return found_url

def process_company(item):
    c_name, c_addr, c_phone, c_web = item
    clean_name = clean_company_name(c_name)
    reg = extract_region(c_addr)
    
    target_web = c_web if (c_web and str(c_web).lower() != 'nan') else None
    newly_found_web = False
    
    # If no website, search for one
    if not target_web:
        found_url = search_missing_web(clean_name, reg)
        if found_url:
            target_web = found_url
            newly_found_web = True
            
    email, phone = None, None
    if target_web:
        email, phone = scan_website_deep(target_web)
        
    return {
        'clean_name': clean_name,
        'website': target_web,
        'newly_found_web': newly_found_web,
        'email': email,
        'phone': phone
    }

def main():
    os.makedirs("data/cache", exist_ok=True)
    os.makedirs("data/formatted", exist_ok=True)
    
    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f"Loaded existing deep search cache: {len(cache)} entries.")
        except Exception:
            cache = {}
            
    df = pd.read_csv(MASTER_CSV, encoding='utf-8-sig')
    print(f"Master CSV total rows: {len(df)}")
    
    has_email_mask = df['Email'].notna() & (df['Email'].astype(str).str.strip() != '') & (df['Email'].astype(str).str.lower() != 'nan')
    proven_df = df[has_email_mask].copy()
    raw_df = df[~has_email_mask].copy()
    
    print(f"Rows with Email (Top tier): {len(proven_df)}")
    print(f"Rows to deep-enrich: {len(raw_df)}")
    
    to_query = []
    for idx, row in raw_df.iterrows():
        c_name = str(row['Công ty']).strip()
        c_addr = str(row['Địa chỉ']).strip() if pd.notna(row['Địa chỉ']) else ""
        c_phone = str(row['SĐT']).strip() if pd.notna(row['SĐT']) else ""
        c_web = str(row['Liên Hệ']).strip() if pd.notna(row['Liên Hệ']) else ""
        cache_key = f"{c_name}___{c_addr}"
        if cache_key not in cache:
            to_query.append((cache_key, c_name, c_addr, c_phone, c_web))
            
    print(f"Already in cache: {len(cache)}. Remaining to process: {len(to_query)}")
    
    lock = threading.Lock()
    processed_count = 0
    total_to_query = len(to_query)
    
    if total_to_query > 0:
        print(f"Starting parallel deep enrichment with 6 workers...")
        with ThreadPoolExecutor(max_workers=6) as executor:
            future_to_key = {
                executor.submit(process_company, (c_name, c_addr, c_phone, c_web)): cache_key
                for cache_key, c_name, c_addr, c_phone, c_web in to_query
            }
            for future in as_completed(future_to_key):
                cache_key = future_to_key[future]
                try:
                    res = future.result()
                except Exception as e:
                    res = {'clean_name': '', 'website': None, 'newly_found_web': False, 'email': None, 'phone': None}
                    
                with lock:
                    cache[cache_key] = res
                    processed_count += 1
                    if processed_count % 15 == 0 or processed_count == total_to_query:
                        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                            json.dump(cache, f, ensure_ascii=False, indent=2)
                        print(f"[{processed_count}/{total_to_query}] processed. Total in cache: {len(cache)}")
                        
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
        
    print(f"\nAll entries processed. Assembling updated master file...")
    
    new_emails_found = 0
    new_webs_found = 0
    new_phones_found = 0
    
    updated_raw_rows = []
    promoted_rows = []
    
    for idx, row in raw_df.iterrows():
        c_name = str(row['Công ty']).strip()
        c_addr = str(row['Địa chỉ']).strip() if pd.notna(row['Địa chỉ']) else ""
        c_phone = str(row['SĐT']).strip() if pd.notna(row['SĐT']) else ""
        c_web = str(row['Liên Hệ']).strip() if pd.notna(row['Liên Hệ']) else ""
        cache_key = f"{c_name}___{c_addr}"
        entry = cache.get(cache_key, {})
        
        final_web = c_web if (c_web and str(c_web).lower() != 'nan') else ""
        if entry.get('website'):
            final_web = entry['website']
            if entry.get('newly_found_web'):
                new_webs_found += 1
                
        final_phone = c_phone
        if entry.get('phone'):
            final_phone = format_phone(entry['phone'])
            new_phones_found += 1
        elif c_phone and c_phone.lower() != 'nan':
            final_phone = format_phone(c_phone)
            
        final_email = ""
        if entry.get('email'):
            final_email = entry['email']
            new_emails_found += 1
            
        new_row = row.copy()
        new_row['SĐT'] = final_phone
        new_row['Liên Hệ'] = final_web
        
        if final_email:
            new_row['Email'] = final_email
            new_row['Liên Hệ mail'] = final_email
            new_row['Check gửi'] = 'Đang rà soát'
            promoted_rows.append(new_row)
        else:
            updated_raw_rows.append(new_row)
            
    promoted_df = pd.DataFrame(promoted_rows) if promoted_rows else pd.DataFrame(columns=df.columns)
    remaining_raw_df = pd.DataFrame(updated_raw_rows) if updated_raw_rows else pd.DataFrame(columns=df.columns)
    
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
    
    print("\n=== HOÀN TẤT LÀM GIÀU SÂU ===")
    print(f"Tổng số dòng: {len(final_master_df)}")
    total_with_email = len(proven_df) + len(promoted_df)
    print(f"Công ty có Email (Top tier): {total_with_email} (Gốc: {len(proven_df)}, Mới phát hiện: {len(promoted_df)})")
    print(f"Công ty thô còn lại: {len(remaining_raw_df)}")
    print(f"Email mới tìm thấy: {new_emails_found}")
    print(f"Website mới tìm thấy: {new_webs_found}")
    print(f"SĐT mới tìm thấy: {new_phones_found}")
    print(f"Đã cập nhật: {MASTER_CSV} và {BACKUP_CSV}")

if __name__ == "__main__":
    main()
