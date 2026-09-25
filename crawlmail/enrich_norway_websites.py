# -*- coding: utf-8 -*-
"""
Hệ thống Quét sâu Website (Deep Web Email Extractor) cho dữ liệu Na Uy:
1. Đọc danh sách doanh nghiệp có Website nhưng chưa có Email.
2. Quét Trang chủ + Trang liên hệ (/kontakt, /contact, /om-oss...).
3. Bóc tách Email B2B chính thức, giải mã Cloudflare email.
4. Lưu tăng dần và cập nhật trực tiếp vào các file Cold Mail Na Uy.
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
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)

TARGET_FILES = [
    os.path.join(ROOT_DIR, "Môi giới Na Uy - ColdMail.csv"),
    os.path.join(ROOT_DIR, "NOPODATA_ColdMail.csv"),
    os.path.join(ROOT_DIR, "data", "formatted", "agency_norway_coldmail.csv")
]

CACHE_FILE = os.path.join(ROOT_DIR, "crawlmail", "cache_norway_websites_email.json")

BAD_KEYWORDS = {
    'wix', 'wixpress', 'sentry', 'no-reply', 'noreply', 'donotreply', 
    'test@', 'example@', 'domain.com', 'superio', 'placeholder',
    'eksempel@', 'esimerkki@', 'olanordmann@', 'mittnettsted.com',
    'support@theme', 'support@elementor', 'info@mysite.com'
}

DISCARD_DOMAINS = {
    'example.com', 'example.org', 'example.net', 'yourdomain.com', 
    'email.com', 'domain.com', 'website.com', 'company.com', 
    'sentry.io', 'git.com', 'github.com', 'test.com', 'g.co',
    'esimerkki.com', 'eksempel.no', 'email.no', 'mittnettsted.com'
}

CONTACT_KEYWORDS = ['kontakt', 'contact', 'om-oss', 'about', 'team', 'personell', 'oss', 'kundeservice', 'ledelse']

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
        if any(bad in f_low for bad in BAD_KEYWORDS):
            continue
        parts = f_low.split('@')
        if len(parts) != 2:
            continue
        domain = parts[1]
        if domain in DISCARD_DOMAINS or domain.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.css', '.js')):
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

def score_email(email, comp_domain=""):
    clean = clean_email(email)
    if not clean:
        return -1
    u, d = clean.split('@', 1)
    score = 10
    if comp_domain and (comp_domain in d or d in comp_domain):
        score += 30
    if u in ['post', 'postmottak', 'firmapost', 'kontakt', 'info', 'rekruttering', 'jobb', 'booking']:
        score += 20
    elif u in ['office', 'mail', 'support', 'sales', 'kundeservice']:
        score += 15
    elif '.' in u or '_' in u:
        score += 10
    return score

async def extract_emails_from_html(html, base_url=""):
    emails = set()
    if not html:
        return emails
        
    soup = BeautifulSoup(html, 'html.parser')
    
    # 1. Cloudflare protected
    for cf in soup.find_all(attrs={"data-cfemail": True}):
        dec = decode_cloudflare_email(cf['data-cfemail'])
        if dec and '@' in dec:
            emails.add(dec)
            
    # 2. mailto: links
    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        if href.lower().startswith('mailto:'):
            raw = href[7:].split('?')[0].strip()
            clean = clean_email(raw)
            if clean:
                emails.add(clean)
                
    # 3. Regex on visible text and raw html
    raw_matches = re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', html)
    for m in raw_matches:
        clean = clean_email(m)
        if clean:
            emails.add(clean)
            
    return emails

def find_subpage_links(html, base_url):
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
            if any(k in path_lower for k in CONTACT_KEYWORDS):
                clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                if clean_url not in seen and clean_url != base_url:
                    seen.add(clean_url)
                    subpages.append(clean_url)
    except Exception:
        pass
    return subpages[:3]

async def crawl_website(session, url):
    if not url.startswith('http'):
        url = f"https://{url}"
        
    comp_domain = urllib.parse.urlparse(url).netloc.lower().replace('www.', '')
    all_emails = set()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "no,nb,nn,en-US;q=0.7,en;q=0.3"
    }
    
    # Thử URL gốc, nếu lỗi thử bỏ www hoặc thêm www
    urls_to_try = [url]
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc.startswith('www.'):
        urls_to_try.append(f"{parsed.scheme}://{parsed.netloc[4:]}{parsed.path}")
    else:
        urls_to_try.append(f"{parsed.scheme}://www.{parsed.netloc}{parsed.path}")
        
    home_html = ""
    success_url = url
    for u in urls_to_try:
        try:
            resp = await session.get(u, timeout=10, headers=headers)
            if resp.status_code == 200:
                home_html = resp.text
                success_url = u
                found = await extract_emails_from_html(home_html, u)
                all_emails.update(found)
                break
        except Exception:
            continue
            
    # Nếu chưa có email, kiểm tra các trang con /kontakt
    if not all_emails and home_html:
        subpages = find_subpage_links(home_html, success_url)
        for sub in subpages:
            try:
                resp_sub = await session.get(sub, timeout=8, headers=headers)
                if resp_sub.status_code == 200:
                    found_sub = await extract_emails_from_html(resp_sub.text, sub)
                    all_emails.update(found_sub)
                    if all_emails:
                        break
            except Exception:
                pass

                
    if not all_emails:
        return ""
        
    scored = [(score_email(e, comp_domain), e) for e in all_emails]
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1] if scored and scored[0][0] > 0 else ""

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache):
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def update_all_coldmail_files(email_map):
    for f_path in TARGET_FILES:
        if not os.path.exists(f_path):
            continue
        try:
            with open(f_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                rows = list(reader)
                
            updated = False
            for r in rows:
                cname = r['Công ty'].strip()
                if cname in email_map and email_map[cname] and not r['Email']:
                    r['Email'] = email_map[cname]
                    r['Check gửi'] = 'OK'
                    updated = True
                    
            if updated:
                # Sắp xếp lại: OK lên đầu, ưu tiên có Người liên hệ
                rows.sort(key=lambda x: (
                    0 if x['Check gửi'] == 'OK' else 1,
                    0 if x['Người liên hệ'] else 1,
                    x['Công ty'].lower()
                ))
                for idx, r in enumerate(rows, 1):
                    r['No.'] = str(idx)
                    
                with open(f_path, 'w', encoding='utf-8-sig', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
                print(f"[+] Đã cập nhật file: {os.path.basename(f_path)}")
        except Exception as e:
            print(f"[-] Lỗi cập nhật file {f_path}: {e}")

async def worker(sem, session, idx, total, cname, web, cache, email_map, lock):
    async with sem:
        if cname in cache:
            em = cache[cname]
        else:
            print(f"[{idx}/{total}] Đang quét: {cname} -> {web}...")
            em = await crawl_website(session, web)
            async with lock:
                cache[cname] = em
                save_cache(cache)
                
        if em:
            print(f"  [+] TÌM THẤY EMAIL ({cname}): {em}")
            async with lock:
                email_map[cname] = em
        else:
            print(f"  [-] Không tìm thấy: {cname}")

async def main():
    print("=" * 65)
    print("   QUÉT SÂU EMAIL WEBSITE CHO DOANH NGHIỆP NA UY (COLD MAIL)")
    print("=" * 65)
    
    primary_csv = TARGET_FILES[0]
    if not os.path.exists(primary_csv):
        print(f"[-] Không tìm thấy {primary_csv}")
        return
        
    with open(primary_csv, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        
    cache = load_cache()
    print(f"[*] Đã tải {len(cache)} bản ghi từ cache.")
    
    targets = []
    for r in rows:
        cname = r['Công ty'].strip()
        web = r['Liên Hệ'].strip()
        email = r['Email'].strip()
        
        # Chỉ quét các website doanh nghiệp thật (bỏ qua proff.no)
        if web and web.startswith('http') and 'proff.no' not in web and not email:
            targets.append((cname, web))
            
    print(f"[*] Số doanh nghiệp có Website sẵn sàng bóc tách Email: {len(targets)}")
    if not targets:
        print("[+] Không có website nào cần quét!")
        return
        
    email_map = {}
    lock = asyncio.Lock()
    sem = asyncio.Semaphore(6) # 6 worker đồng thời
    
    async with AsyncSession(impersonate="chrome120", verify=False) as session:
        tasks = []
        for idx, (cname, web) in enumerate(targets, 1):
            tasks.append(worker(sem, session, idx, len(targets), cname, web, cache, email_map, lock))
            
        await asyncio.gather(*tasks)
                
    # Lưu tổng kết cuối cùng
    if email_map:
        update_all_coldmail_files(email_map)
        
    print("\n" + "=" * 65)
    print("  KẾT QUẢ QUÉT SÂU EMAIL WEBSITE NA UY:")
    print(f"  - Tổng số website đã duyệt: {len(targets)}")
    print(f"  - Số Email B2B mới tìm thấy: {len(email_map)} (Tỷ lệ thành công: {len(email_map)/len(targets)*100:.1f}%)")
    print("=" * 65)

if __name__ == '__main__':
    asyncio.run(main())

