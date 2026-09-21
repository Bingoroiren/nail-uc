# -*- coding: utf-8 -*-
"""
Crawl Email cho các công ty Chế biến thực phẩm Litva từ danh sách Website đã làm giàu
Sử dụng curl_cffi AsyncSession (impersonate chrome) để quét Homepage + Contact pages
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
import openpyxl

if sys.platform == 'win32':
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_CSV = os.path.join(BASE_DIR, "chế biến thực phẩm litva - đã làm giàu rekvizitai.csv")
OUTPUT_CSV = os.path.join(BASE_DIR, "chế biến thực phẩm litva - đã làm giàu rekvizitai.csv")
OUTPUT_XLSX = os.path.join(BASE_DIR, "chế biến thực phẩm litva - đã làm giàu rekvizitai.xlsx")
OUTPUT_HAS_EMAIL_CSV = os.path.join(BASE_DIR, "chế biến thực phẩm litva - có email.csv")
CACHE_FILE = os.path.join(BASE_DIR, "crawlmail", "cache_emails_thuc_pham_litva.json")

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,7}\b')
INVALID_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf', '.css', '.js', '.ico', '.woff', '.woff2', '.mp4', '.mp3', '.ttf')
IGNORE_DOMAINS = {
    'sentry.io', 'wixpress.com', 'example.com', 'domain.com', 'schema.org', 
    'wordpress.org', 'cloudflare.com', 'google.com', 'facebook.com', 'w3.org', 
    'jsdelivr.net', 'bootstrapcdn.com', 'website.com', 'yourdomain.com'
}
DUMMY_EMAILS = {'user@website.com', 'name@domain.com', 'email@domain.com', 'info@domain.com'}

def decode_cloudflare_email(hex_str):
    try:
        hex_data = bytes.fromhex(hex_str)
        key = hex_data[0]
        return ''.join(chr(b ^ key) for b in hex_data[1:])
    except Exception:
        return ""

def clean_email(email_str):
    if not email_str:
        return ""
    email = email_str.strip().lower()
    email = email.rstrip('.,;:')
    if any(email.endswith(ext) for ext in INVALID_EXTENSIONS):
        return ""
    if email in DUMMY_EMAILS:
        return ""
    domain = email.split('@')[-1]
    if domain in IGNORE_DOMAINS or domain.endswith('.invalid'):
        return ""
    if len(email) < 6 or '@' not in email:
        return ""
    return email

def extract_emails_from_html(html):
    if not html:
        return set()
    found = set()
    
    # 1. Cloudflare protected emails
    for cf in re.findall(r'data-cfemail="([0-9a-fA-F]+)"', html):
        dec = decode_cloudflare_email(cf)
        em = clean_email(dec)
        if em:
            found.add(em)
            
    # 2. mailto: links
    for mailto in re.findall(r'mailto:([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7})', html, re.IGNORECASE):
        em = clean_email(mailto)
        if em:
            found.add(em)
            
    # 3. Plain text regex
    for match in EMAIL_REGEX.findall(html):
        em = clean_email(match)
        if em:
            found.add(em)
            
    return found

def find_contact_links(html, base_url):
    contact_urls = []
    if not html:
        return contact_urls
    try:
        soup = BeautifulSoup(html, 'html.parser')
        base_domain = urllib.parse.urlparse(base_url).netloc.lower()
        
        keywords = ['kontakt', 'contact', 'apie', 'about', 'rekvizit', 'susisiek', 'kontakty']
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            text = a.get_text(strip=True).lower()
            href_lower = href.lower()
            
            matched = any(kw in href_lower for kw in keywords) or any(kw in text for kw in keywords)
            if matched:
                full_url = urllib.parse.urljoin(base_url, href)
                parsed = urllib.parse.urlparse(full_url)
                if parsed.scheme in ('http', 'https') and (base_domain in parsed.netloc.lower() or not parsed.netloc):
                    if not parsed.path.endswith(('.jpg', '.png', '.pdf', '.zip')):
                        if full_url not in contact_urls and full_url != base_url:
                            contact_urls.append(full_url)
                            if len(contact_urls) >= 3:
                                break
    except Exception:
        pass
    return contact_urls

def score_email(email, domain):
    score = 0
    clean_domain = domain.lower().replace('www.', '')
    if clean_domain in email:
        score += 50
    pfx = email.split('@')[0].lower()
    if pfx in ['info', 'office', 'pardavimai', 'uzsakymai', 'kokybe', 'direktorius', 'buhalterija', 'administracija', 'kontaktai', 'sales']:
        score += 30
    elif any(pfx.startswith(x) for x in ['info', 'sales', 'order', 'contact', 'uzsakym', 'export']):
        score += 20
    return score

def prioritize_emails(emails_set, domain):
    if not emails_set:
        return ""
    sorted_emails = sorted(list(emails_set), key=lambda e: score_email(e, domain), reverse=True)
    return "; ".join(sorted_emails)

async def scrape_single_website(session, raw_url):
    url = raw_url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
        
    parsed_orig = urllib.parse.urlparse(url)
    domain = parsed_orig.netloc.lower().replace('www.', '')
    
    collected_emails = set()
    homepage_html = ""
    
    # Step 1: Fetch Homepage
    try:
        res = await session.get(url, timeout=7, allow_redirects=True)
        if res.status_code == 200:
            homepage_html = res.text
            collected_emails.update(extract_emails_from_html(homepage_html))
    except Exception:
        if url.startswith('https://'):
            http_url = 'http://' + url[8:]
            try:
                res = await session.get(http_url, timeout=7, allow_redirects=True)
                if res.status_code == 200:
                    homepage_html = res.text
                    collected_emails.update(extract_emails_from_html(homepage_html))
            except Exception:
                pass

    # Step 2: Contact pages
    contact_links = find_contact_links(homepage_html, url)
    if not contact_links:
        contact_links = [
            urllib.parse.urljoin(url, '/kontaktai'),
            urllib.parse.urljoin(url, '/contacts'),
            urllib.parse.urljoin(url, '/lt/kontaktai')
        ]
        
    for c_url in contact_links[:2]:
        try:
            c_res = await session.get(c_url, timeout=6, allow_redirects=True)
            if c_res.status_code == 200:
                collected_emails.update(extract_emails_from_html(c_res.text))
        except Exception:
            continue

    return prioritize_emails(collected_emails, domain)

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def save_output_files(rows, fieldnames):
    # Save CSV
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        
    # Save Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Chế biến thực phẩm Litva"
    ws.append(fieldnames)
    for r in rows:
        ws.append([r.get(f, '') for f in fieldnames])
    wb.save(OUTPUT_XLSX)
    
    # Save Has-Email CSV
    has_email_rows = [r for r in rows if r.get('email', '').strip()]
    with open(OUTPUT_HAS_EMAIL_CSV, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(has_email_rows)

async def worker(queue, session, cache, progress):
    while True:
        url = await queue.get()
        if url is None:
            queue.task_done()
            break
        try:
            emails = await asyncio.wait_for(scrape_single_website(session, url), timeout=15.0)
            cache[url] = emails
            progress['done'] += 1
            if emails:
                print(f"[{progress['done']}/{progress['total']}] {url} -> [EMAIL]: {emails[:60]}...", flush=True)
            else:
                print(f"[{progress['done']}/{progress['total']}] {url} -> Không có email", flush=True)
        except asyncio.TimeoutError:
            cache[url] = ""
            progress['done'] += 1
            print(f"[{progress['done']}/{progress['total']}] {url} -> Timeout (15s)", flush=True)
        except Exception as e:
            cache[url] = ""
            progress['done'] += 1
            print(f"[{progress['done']}/{progress['total']}] {url} -> Lỗi: {e}", flush=True)
            
        if progress['done'] % 10 == 0:
            save_cache(cache)
        queue.task_done()

async def main():
    print("=" * 70, flush=True)
    print(" CÀO EMAIL DOANH NGHIỆP CHẾ BIẾN THỰC PHẨM LITVA TỪ WEBSITE ", flush=True)
    print("=" * 70, flush=True)
    
    if not os.path.exists(INPUT_CSV):
        print(f"[-] Không tìm thấy file: {INPUT_CSV}", flush=True)
        return
        
    rows = []
    fieldnames = []
    with open(INPUT_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
        
    website_rows = [r for r in rows if r.get('website', '').strip()]
    unique_websites = sorted(list(set(r['website'].strip() for r in website_rows)))
    print(f"[+] Tổng số công ty trong danh sách: {len(rows)}", flush=True)
    print(f"[+] Số công ty có Website: {len(website_rows)} (Duy nhất: {len(unique_websites)} website)", flush=True)
    
    cache = load_cache()
    print(f"[+] Cache hiện tại: {len(cache)} website đã quét trước đó", flush=True)
    
    to_scrape = [w for w in unique_websites if w not in cache]
    print(f"[+] Cần quét mới: {len(to_scrape)} website", flush=True)
    
    if to_scrape:
        queue = asyncio.Queue()
        for w in to_scrape:
            queue.put_nowait(w)
            
        progress = {'done': 0, 'total': len(to_scrape)}
        num_workers = 15
        
        async with AsyncSession(impersonate='chrome124', verify=False) as session:
            tasks = []
            for _ in range(num_workers):
                tasks.append(asyncio.create_task(worker(queue, session, cache, progress)))
                
            await queue.join()
            
            for _ in range(num_workers):
                await queue.put(None)
            await asyncio.gather(*tasks)
            
    save_cache(cache)
    
    # Update rows with emails from cache
    email_found_count = 0
    for r in rows:
        w = r.get('website', '').strip()
        if w in cache and cache[w]:
            r['email'] = cache[w]
            email_found_count += 1
        elif not r.get('email', '').strip():
            r['email'] = ""
            
    save_output_files(rows, fieldnames)
    
    print("\n" + "=" * 70, flush=True)
    print("                     HOÀN TẤT CÀO EMAIL!", flush=True)
    print("=" * 70, flush=True)
    print(f"- Tổng số công ty có email sau khi quét   : {email_found_count} / {len(website_rows)} công ty có web", flush=True)
    print(f"- Tỷ lệ tìm thấy email trên website       : {round(email_found_count / len(website_rows) * 100, 1)}%", flush=True)
    print(f"- File CSV cập nhật                       : {OUTPUT_CSV}", flush=True)
    print(f"- File Excel cập nhật                     : {OUTPUT_XLSX}", flush=True)
    print(f"- File CSV lọc riêng công ty CÓ EMAIL     : {OUTPUT_HAS_EMAIL_CSV}", flush=True)
    print("=" * 70, flush=True)

if __name__ == '__main__':
    asyncio.run(main())
