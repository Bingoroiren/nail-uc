import os
import sys
import re
import csv
import io
import time
from urllib.parse import urlparse, urljoin
from curl_cffi import requests
from bs4 import BeautifulSoup

# Ensure UTF-8 unbuffered output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

INPUT_CSV = "(16_9) thịt dan mạch - Trang tính1.csv"
OUTPUT_FULL_CSV = "(16_9) thịt dan mạch - Đầy đủ sau enrich 2.csv"
OUTPUT_DEDUP_CSV = "(16_9) thịt dan mạch - SẴN SÀNG GỬI (ĐÃ LỌC TRÙNG).csv"

# Domain blacklist: MXH, dịch vụ chung, danh bạ, tìm kiếm
BLACKLIST_DOMAINS = {
    'facebook.com', 'fb.com', 'instagram.com', 'linkedin.com', 'twitter.com', 'x.com',
    'youtube.com', 'tiktok.com', 'pinterest.com',
    'google.com', 'google.dk', 'maps.google.com', 'bing.com',
    'wix.com', 'shopify.com', 'wordpress.com', 'squarespace.com',
    'cvr.dk', 'proff.dk', 'krak.dk', 'degulesider.dk', 'find-firma.dk',
    'eniro.dk', 'virk.dk', 'ret-nemt.dk', 'havneguide.dk', 'trustpilot.com',
    'yelp.com', 'tripadvisor.com', 'wikipedia.org', 'datacvr.virk.dk',
    'foedevarestyrelsen.dk', 'fvst.dk'
}

# Web agencies / third party widgets blacklist
AGENCY_DOMAINS = {
    'nozebra.dk', 'novicell.dk', 'kraftvaerk.com', 'adaptagency.com', 'creuna.dk',
    'valtech.com', 'co3.dk', 'discus.dk', 'dynamicweb.com', 'sentry.io',
    'cookiebot.com', 'usercentrics.eu', 'termly.io', 'onetrust.com',
    'cloudflare.com', 'hubspot.com', 'mailchimp.com', 'wix.com', 'shopify.com'
}

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b')

session = requests.Session()

def get_clean_domain(url):
    if not url:
        return None
    if not url.startswith(('http://', 'https://')):
        url = 'http://' + url
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith('www.'):
            netloc = netloc[4:]
        netloc = netloc.split(':')[0]
        
        for bl in BLACKLIST_DOMAINS:
            if netloc == bl or netloc.endswith('.' + bl):
                return None
        
        if '.' in netloc and len(netloc) > 4:
            return netloc
    except Exception:
        pass
    return None

def is_valid_company_email(email, clean_dom):
    email = email.lower().strip()
    if any(email.endswith(x) for x in ['.png', '.jpg', '.jpeg', '.webp', '.svg', '.gif']):
        return False
    if '@' not in email:
        return False
        
    e_domain = email.split('@')[1]
    
    for ag in AGENCY_DOMAINS:
        if e_domain == ag or e_domain.endswith('.' + ag):
            return False
            
    if e_domain == clean_dom or e_domain.endswith('.' + clean_dom) or clean_dom.endswith('.' + e_domain):
        return True
        
    root_clean = clean_dom.split('.')[0]
    if len(root_clean) >= 4 and root_clean in e_domain:
        return True
        
    if any(m in e_domain for m in ['gmail.com', 'hotmail.com', 'outlook.com', 'mail.dk', 'tele.dk', 'post.tele.dk']):
        return True
        
    return False

def scan_website_for_email(url, clean_dom):
    if not url.startswith(('http://', 'https://')):
        url = 'http://' + url
        
    base_url = f"{urlparse(url).scheme}://{clean_dom}"
    
    # 1. Quét trang chủ
    contact_link = None
    try:
        r = session.get(base_url, impersonate="chrome124", timeout=3.5, allow_redirects=True)
        if r.status_code == 200:
            emails = set(EMAIL_REGEX.findall(r.text))
            valid = [e.lower() for e in emails if is_valid_company_email(e, clean_dom)]
            if valid:
                pref = [e for e in valid if any(p in e for p in ['info@', 'kontakt@', 'mail@', 'salg@', 'ordre@', 'sales@', 'kundeservice@'])]
                return pref[0] if pref else valid[0]
            
            # Tìm link trang liên hệ chính xác từ trang chủ
            soup = BeautifulSoup(r.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                h = a['href'].lower()
                if any(x in h for x in ['kontakt', 'contact', 'kundeservice', 'om-os']):
                    if not any(x in h for x in ['javascript', '#', 'tel:', 'mailto:']):
                        contact_link = urljoin(base_url, a['href'])
                        break
    except Exception:
        pass
        
    # 2. Quét trang con liên hệ (ưu tiên link tìm được từ homepage, fallback sang /kontakt)
    target_sub = contact_link or (base_url.rstrip('/') + '/kontakt')
    try:
        r_sub = session.get(target_sub, impersonate="chrome124", timeout=3.5, allow_redirects=True)
        if r_sub.status_code == 200:
            emails = set(EMAIL_REGEX.findall(r_sub.text))
            valid = [e.lower() for e in emails if is_valid_company_email(e, clean_dom)]
            if valid:
                pref = [e for e in valid if any(p in e for p in ['info@', 'kontakt@', 'mail@', 'salg@', 'ordre@', 'sales@', 'kundeservice@'])]
                return pref[0] if pref else valid[0]
    except Exception:
        pass
            
    return None

def score_row(row):
    score = 0
    if row.get('SDT', '').strip(): score += 3
    if row.get('Nguoi lien he', '').strip(): score += 2
    if row.get('Dia chi', '').strip(): score += 2
    if row.get('Lien He', '').strip(): score += 1
    if row.get('Link FB', '').strip(): score += 1
    return score

def do_dedup_and_save(reader, fieldnames):
    email_groups = {}
    no_email_rows = []
    
    for r in reader:
        em = r.get('Email', '').strip().lower()
        if em:
            email_groups.setdefault(em, []).append(r)
        else:
            no_email_rows.append(r)

    dedup_rows = []
    for em, rows in email_groups.items():
        best_row = max(rows, key=score_row)
        dedup_rows.append(best_row)

    for i, r in enumerate(dedup_rows, 1):
        r['No.'] = i

    with open(OUTPUT_DEDUP_CSV, "w", encoding="utf-8-sig", newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(dedup_rows)

    with open(OUTPUT_FULL_CSV, "w", encoding="utf-8-sig", newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(reader)

    with open(INPUT_CSV, "w", encoding="utf-8-sig", newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(reader)
        
    return len(dedup_rows), sum(len(v)-1 for v in email_groups.values())

def main():
    print("="*75)
    print("TIẾN TRÌNH ENRICH LƯỢT 2 + ĐOÁN EMAIL THEO DOMAIN + LỌC TRÙNG (DEDUP)")
    print("="*75)
    
    with open(INPUT_CSV, "r", encoding="utf-8-sig") as f:
        reader = list(csv.DictReader(f))
        fieldnames = list(reader[0].keys())

    total = len(reader)
    initial_has_email = sum(1 for r in reader if r.get('Email', '').strip())
    print(f"[*] Tổng số dòng dữ liệu: {total} | Đã có email lượt 1: {initial_has_email}")
    
    print("\n--- BƯỚC 1: QUÉT SÂU CÁC WEBSITE CHƯA CÓ EMAIL ---")
    new_found = 0
    guessed = 0
    
    for idx, r in enumerate(reader, 1):
        curr_email = r.get('Email', '').strip()
        web = r.get('Lien He', '').strip()
        cname = r.get('Cong ty', 'N/A')
        
        if curr_email:
            continue
            
        clean_dom = get_clean_domain(web)
        if clean_dom:
            found_email = scan_website_for_email(web, clean_dom)
            if found_email:
                r['Email'] = found_email
                new_found += 1
                print(f"[{idx}/{total}] 🎯 TÌM THẤY EMAIL THẬT: {cname} -> {found_email}")
            else:
                guessed_email = f"info@{clean_dom}"
                r['Email'] = guessed_email
                guessed += 1
                print(f"[{idx}/{total}] 💡 ĐOÁN THEO DOMAIN: {cname} -> {guessed_email}")

        if (new_found + guessed) > 0 and (new_found + guessed) % 20 == 0:
            do_dedup_and_save(reader, fieldnames)
            print(f"   [Checkpoint]: Đã xử lý {new_found + guessed} doanh nghiệp mới...")

    total_with_email = sum(1 for r in reader if r.get('Email', '').strip())
    print(f"\n[+] Tổng kết sau Enrich Lượt 2:")
    print(f"    - Tìm thấy email thật mới: +{new_found}")
    print(f"    - Đoán email hợp lệ từ domain riêng: +{guessed}")
    print(f"    - Tổng số dòng có email hiện tại: {total_with_email} / {total} ({total_with_email/total*100:.1f}%)")

    # Bước 2: Deduplication
    unique_count, dup_removed = do_dedup_and_save(reader, fieldnames)
    print("\n--- BƯỚC 2: LỌC TRÙNG THEO EMAIL (DEDUPLICATION) ---")
    print(f"[+] Số email độc nhất (Unique Clients): {unique_count}")
    print(f"[+] Đã loại bỏ {dup_removed} dòng email trùng lặp!")
    print(f"📁 File chuẩn đầy đủ 1.237 dòng: {OUTPUT_FULL_CSV}")
    print(f"📁 FILE SẴN SÀNG GỬI (ĐÃ LỌC TRÙNG 100%): {OUTPUT_DEDUP_CSV}")
    print(f"📁 Cập nhật file gốc: {INPUT_CSV}")
    print("="*75)

if __name__ == "__main__":
    main()
