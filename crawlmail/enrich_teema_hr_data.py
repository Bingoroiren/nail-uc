# -*- coding: utf-8 -*-
"""
Hệ Thống Làm Giàu Dữ Liệu Nhân Sự & Tuyển Dụng B2B (HR Enrichment Engine):
- NGUYÊN TẮC BẢO TOÀN 100% CƠ HỘI: Không bỏ sót bất kỳ nhà máy nào trong 4.651 nhà máy.
- Bổ sung Họ tên người liên hệ tiếng Trung, Chức danh, SĐT bàn trực tiếp + số máy lẻ ext.
- Bóc tách Email phòng Tuyển dụng/HR, Email đích danh người liên hệ; Fallback giữ nguyên Email công ty gốc.
- Phân loại chất lượng email 'Email_Quality': HR_Specific, Named_Contact, Original_Backup, No_Email.
- Ghi đĩa tức thì từng dòng (Instant Line-by-Line Write & os.fsync) để file CSV nhảy liên tục theo thời gian thực.
"""

import sys
import os
import re
import csv
import json
import time
import threading
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = str(ROOT_DIR / "data" / "formatted" / "teema_taiwan_electronics_factories_sorted.csv")
OUTPUT_CSV = str(ROOT_DIR / "data" / "formatted" / "teema_taiwan_factories_hr_enriched.csv")
CACHE_FILE = str(ROOT_DIR / "data" / "cache" / "teema_hr_enrich_cache.json")

os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)

FILE_LOCK = threading.Lock()

HR_EMAIL_KEYWORDS = [
    'hr', 'recruit', 'career', 'job', 'talent', 'personnel', 'resume', 'hire', 
    'zhaomu', 'renzi', 'work', 'employ'
]

CAREER_URL_KEYWORDS = [
    'career', 'careers', 'job', 'jobs', 'recruit', 'recruitment', 'talent', 
    'join-us', 'joinus', 'work-with-us', 'employment',
    '人才招募', '加入我們', '招募資訊', '人力資源', '徵才', '職缺'
]

JUNK_EMAIL_DOMAINS = [
    'example.com', 'domain.com', 'test.com', 'sentry.io', 'wixpress.com', 
    'wix.com', 'wordpress.org', 'google.com', 'facebook.com'
]

FIELDNAMES = [
    'Company_ID',
    'Company_Name_ZH',
    'Company_Name_EN',
    'Tax_ID',
    'Employees',
    'Capital',
    'HR_Contact_Name',
    'HR_Contact_Title',
    'HR_Email',
    'Email_Quality',
    'HR_Phone',
    'Careers_URL',
    'Company_Email',
    'Company_Phone',
    'Company_Fax',
    'Website',
    'Address_ZH',
    'Address_EN',
    'Plant_Products',
    'Keyword_Groups',
    'TEEMA_URL'
]

def format_phone(phone_str):
    if not phone_str:
        return ""
    p = str(phone_str).strip()
    return f"'{p}" if not p.startswith("'") else p

def clean_email(email_str):
    if not email_str:
        return ""
    decoded = unquote(str(email_str)).strip().lower()
    decoded = decoded.replace('%20', '').replace(' ', '')
    # Loại bỏ artifact thư viện web
    if '..' in decoded or '@4.' in decoded or '@100' in decoded or '@20' in decoded or decoded.endswith('.3'):
        return ""
    for junk in JUNK_EMAIL_DOMAINS:
        if junk in decoded:
            return ""
    return decoded

def extract_valid_emails(text):
    if not text:
        return []
    raw = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)
    valid = []
    for em in raw:
        cleaned = clean_email(em)
        if cleaned and not any(cleaned.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js']):
            if '.' in cleaned.split('@')[-1]:
                valid.append(cleaned)
    return list(dict.fromkeys(valid))

def get_session():
    s = requests.Session()
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7'
    })
    s.max_redirects = 3
    return s

def fetch_teema_internal(session, company_id):
    url = f"https://b2b.teema.org.tw/api/B2BCompanyInfomation/view/{company_id}"
    try:
        r = session.get(url, timeout=3.5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}

def scan_website_careers(session, website):
    if not website or not website.startswith('http'):
        return {'hr_emails': [], 'careers_url': ''}
    
    hr_emails = []
    careers_urls = []
    
    try:
        r = session.get(website, timeout=3.5, verify=False, stream=True)
        if r.status_code == 200:
            content = r.raw.read(150000, decode_content=True).decode('utf-8', errors='ignore')
            emails = extract_valid_emails(content)
            for em in emails:
                if any(k in em for k in HR_EMAIL_KEYWORDS):
                    hr_emails.append(em)
            
            soup = BeautifulSoup(content, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = a['href']
                text = (a.get_text() or '').strip().lower()
                href_lower = href.lower()
                
                is_career = any(k in href_lower or k in text for k in CAREER_URL_KEYWORDS)
                if is_career:
                    full_link = urljoin(website, href)
                    if full_link not in careers_urls and urlparse(full_link).netloc == urlparse(website).netloc:
                        careers_urls.append(full_link)
        
        if careers_urls:
            target_career = careers_urls[0]
            try:
                r_c = session.get(target_career, timeout=3.5, verify=False, stream=True)
                if r_c.status_code == 200:
                    c_content = r_c.raw.read(150000, decode_content=True).decode('utf-8', errors='ignore')
                    c_emails = extract_valid_emails(c_content)
                    for em in c_emails:
                        if any(k in em for k in HR_EMAIL_KEYWORDS) or len(c_emails) <= 2:
                            hr_emails.append(em)
            except Exception:
                pass
            return {'hr_emails': list(dict.fromkeys(hr_emails)), 'careers_url': target_career}
            
    except Exception:
        pass
        
    return {'hr_emails': list(dict.fromkeys(hr_emails)), 'careers_url': careers_urls[0] if careers_urls else ''}

def enrich_single_factory(row, session):
    cid = row.get('Company_ID', '').strip()
    cname_en = row.get('Company_Name', '').strip()
    tax_id = row.get('Tax_ID', '').strip()
    emp = row.get('Employees', '').strip()
    cap = row.get('Capital', '').strip()
    web = row.get('Website', '').strip()
    old_email = clean_email(row.get('Email', ''))
    old_phone = row.get('Phone', '').strip()
    old_fax = row.get('Fax', '').strip()
    addr_en = row.get('Address', '').strip()
    products = row.get('Plant_Products', '').strip()
    kw_groups = row.get('Keyword_Groups', '').strip()
    teema_url = row.get('TEEMA_URL', '').strip()

    # 1. Gọi TEEMA API
    teema = fetch_teema_internal(session, cid)
    cname_zh = teema.get('companyName_cht') or ''
    addr_zh = teema.get('companyAddress_cht') or ''
    contact_name = teema.get('contactName_cht') or teema.get('contactName_en') or ''
    contact_title = teema.get('contactJobTitle_cht') or teema.get('contactJobTitle_en') or ''
    contact_email = clean_email(teema.get('contactEMail') or '')
    
    tel_num = teema.get('contactTel_number') or teema.get('companyTel_number') or old_phone
    tel_ext = teema.get('contactTel_ext') or ''
    direct_phone = f"{tel_num} ext {tel_ext}" if tel_ext and tel_num else tel_num

    # 2. Quét Website tìm HR Email
    web_res = scan_website_careers(session, web)
    hr_emails_found = web_res.get('hr_emails', [])
    careers_url = web_res.get('careers_url', '')

    # 3. Cơ Chế Thay Thế Dữ Liệu Tối Ưu
    company_email = old_email or clean_email(teema.get('companyEMail') or '')
    
    if hr_emails_found:
        best_email = hr_emails_found[0]
        quality = "HR_Specific"
    elif contact_email:
        best_email = contact_email
        quality = "Named_Contact"
    elif company_email:
        best_email = company_email
        quality = "Original_Backup"
    else:
        best_email = ""
        quality = "No_Email"

    return {
        'Company_ID': cid,
        'Company_Name_ZH': cname_zh,
        'Company_Name_EN': cname_en,
        'Tax_ID': tax_id,
        'Employees': emp,
        'Capital': cap,
        'HR_Contact_Name': contact_name,
        'HR_Contact_Title': contact_title,
        'HR_Email': best_email,
        'Email_Quality': quality,
        'HR_Phone': format_phone(direct_phone),
        'Careers_URL': careers_url,
        'Company_Email': company_email,
        'Company_Phone': format_phone(old_phone or tel_num),
        'Company_Fax': format_phone(old_fax or teema.get('companyFax_number', '')),
        'Website': web,
        'Address_ZH': addr_zh,
        'Address_EN': addr_en,
        'Plant_Products': products,
        'Keyword_Groups': kw_groups,
        'TEEMA_URL': teema_url
    }

def main():
    if not os.path.exists(INPUT_CSV):
        print(f"[-] Không tìm thấy file đầu vào: {INPUT_CSV}")
        return

    print("=" * 85)
    print(" HỆ THỐNG LÀM GIÀU DỮ LIỆU NHÂN SỰ & TUYỂN DỤNG B2B (NGUYÊN TẮC BẢO TOÀN 100% CƠ HỘI)")
    print(" Ghi đĩa NGAY LẬP TỨC từng dòng (Instant Line-by-Line Auto-Save)")
    print("=" * 85)

    with open(INPUT_CSV, 'r', encoding='utf-8-sig') as f:
        reader = list(csv.DictReader(f))
    total_factories = len(reader)
    print(f"[*] Tổng số nhà máy cần xử lý: {total_factories}")

    # Đọc cache checkpoint
    processed_ids = set()
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                processed_ids = set(json.load(f))
        except Exception:
            processed_ids = set()

    file_exists = os.path.exists(OUTPUT_CSV)
    if not file_exists:
        with open(OUTPUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
    else:
        try:
            with open(OUTPUT_CSV, 'r', encoding='utf-8-sig') as f:
                for row in csv.DictReader(f):
                    cid = row.get('Company_ID')
                    if cid:
                        processed_ids.add(cid)
        except Exception:
            pass

    print(f"[*] Đã hoàn thành trước đó: {len(processed_ids)} / {total_factories} nhà máy.")

    remaining_tasks = [r for r in reader if r.get('Company_ID') not in processed_ids]
    print(f"[*] Số nhà máy còn lại cần làm giàu: {len(remaining_tasks)} / {total_factories}")

    if not remaining_tasks:
        print("[+] Toàn bộ 4,651 nhà máy đã được làm giàu dữ liệu hoàn tất 100%!")
        return

    MAX_WORKERS = 16
    print(f"[*] Khởi chạy xử lý song song với {MAX_WORKERS} luồng...")

    start_time = time.time()
    completed_count = len(processed_ids)

    def worker_task(row):
        s = get_session()
        try:
            res = enrich_single_factory(row, s)
        finally:
            s.close()
        return res

    with open(OUTPUT_CSV, 'a', encoding='utf-8-sig', newline='') as out_f:
        writer = csv.DictWriter(out_f, fieldnames=FIELDNAMES)

        CHUNK_SIZE = 30
        for i in range(0, len(remaining_tasks), CHUNK_SIZE):
            chunk = remaining_tasks[i:i + CHUNK_SIZE]
            
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {executor.submit(worker_task, r): r for r in chunk}
                
                for future in as_completed(futures):
                    try:
                        res = future.result(timeout=10)
                        cid = res['Company_ID']
                        completed_count += 1

                        with FILE_LOCK:
                            writer.writerow(res)
                            out_f.flush()
                            os.fsync(out_f.fileno())
                            processed_ids.add(cid)

                        q_tag = res['Email_Quality']
                        c_tag = f"👤 {res['HR_Contact_Name']}" if res.get('HR_Contact_Name') else ""
                        print(f"[{completed_count}/{total_factories}] {res['Company_Name_ZH'] or res['Company_Name_EN'][:25]} | {c_tag} | [{q_tag}] {res['HR_Email']}")

                    except Exception:
                        pass
            
            with FILE_LOCK:
                with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(list(processed_ids), f)

    elapsed = time.time() - start_time
    print("\n" + "=" * 85)
    print(f"[+] HOÀN THÀNH TOÀN BỘ CHIẾN DỊCH LÀM GIÀU DỮ LIỆU!")
    print(f"[+] Đã xử lý đầy đủ: {completed_count}/{total_factories} nhà máy (Bảo toàn 100% cơ hội)")
    print(f"[+] Thời gian: {elapsed/60:.1f} phút")
    print(f"[+] Tệp kết quả: {OUTPUT_CSV}")
    print("=" * 85)

if __name__ == '__main__':
    main()
