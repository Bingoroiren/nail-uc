import os
import re
import csv
import sys
import shutil
from datetime import datetime
import requests
from bs4 import BeautifulSoup

# Ensure UTF-8 output encoding
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET_FILE = os.path.join(ROOT_DIR, "môi giới Canada  - CleanData.csv")
STANDALONE_FILE = os.path.join(ROOT_DIR, "mb_licensed_recruiters.csv")
BACKUP_FILE = os.path.join(ROOT_DIR, "môi giới Canada  - CleanData.backup.csv")
MB_URL = "https://www.gov.mb.ca/labour/standards/validlicences-wrapa.html"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

def format_phone(phone_str):
    if not phone_str:
        return ''
    cleaned = phone_str.strip()
    digits = re.sub(r'\D', '', cleaned)
    if digits.startswith('1') and len(digits) == 11:
        digits = digits[1:]
    if len(digits) == 10:
        return f"'{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    if not cleaned.startswith("'"):
        return f"'{cleaned}"
    return cleaned

def format_date(d_str):
    if not d_str:
        return ''
    d_str = d_str.strip().replace('\xa0', ' ')
    m = re.search(r'([A-Za-z]+\s+\d{1,2},?\s+\d{4})', d_str)
    if m:
        clean = m.group(1).replace(',', '')
        for fmt in ('%B %d %Y', '%b %d %Y'):
            try:
                return datetime.strptime(clean, fmt).strftime('%d-%b-%y')
            except ValueError:
                pass
    return d_str

def scrape_manitoba_licences():
    print(f"[*] Fetching Manitoba Foreign Worker Recruiters from: {MB_URL}")
    resp = requests.get(MB_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    
    soup = BeautifulSoup(resp.text, 'html.parser')
    tables = soup.find_all('table')
    if not tables:
        raise ValueError("No table found on Manitoba page.")
    
    target_table = tables[0]
    rows = target_table.find_all('tr')
    print(f"[*] Found {len(rows)} rows in Foreign Worker Recruitment table.")
    
    data = []
    for idx, tr in enumerate(rows):
        tds = tr.find_all('td')
        if len(tds) < 2:
            continue
            
        # Clone td to preserve structure
        td0 = BeautifulSoup(str(tds[0]), 'html.parser')
        for br in td0.find_all(['br', 'p']):
            br.replace_with('\n' + br.get_text())
        raw_lines = [l.strip() for l in td0.get_text().split('\n') if l.strip()]
        
        person = raw_lines[0] if len(raw_lines) > 0 else ''
        company = raw_lines[1] if len(raw_lines) > 1 else ''
        phone_raw = raw_lines[2] if len(raw_lines) > 2 else ''
        contact_line = raw_lines[3] if len(raw_lines) > 3 else ''
        
        # Email parsing
        emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', contact_line)
        email = emails[0].lower() if emails else ''
        
        # Website / Link parsing
        webs = re.findall(r'(?:https?://|www\.)[^\s;,]+', contact_line)
        if webs:
            web = webs[0]
            if web.startswith('www.'):
                web = 'https://' + web
        else:
            web = MB_URL
            
        phone = format_phone(phone_raw)
        expiry = format_date(tds[1].get_text(' ', strip=True))
        
        data.append({
            'licensee_name': person,
            'business_name': company,
            'phone': phone,
            'email': email,
            'website': web,
            'expiry_date': expiry,
            'address': 'Manitoba, Canada',
            'province': 'Manitoba',
            'country': 'Canada'
        })
        
    print(f"[+] Successfully parsed {len(data)} Manitoba recruiters.")
    return data

def save_standalone_file(data):
    fieldnames = [
        'No.', 'Licensee Name', 'Business Name', 'Phone', 'Email',
        'Website', 'Expiry Date', 'Address', 'Province', 'Country'
    ]
    with open(STANDALONE_FILE, mode='w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, item in enumerate(data, 1):
            writer.writerow({
                'No.': i,
                'Licensee Name': item['licensee_name'],
                'Business Name': item['business_name'],
                'Phone': item['phone'],
                'Email': item['email'],
                'Website': item['website'],
                'Expiry Date': item['expiry_date'],
                'Address': item['address'],
                'Province': item['province'],
                'Country': item['country']
            })
    print(f"[+] Saved standalone full list (33 records) to: {STANDALONE_FILE}")

def append_to_cleandata(data, filter_duplicates=True):
    if not os.path.exists(TARGET_FILE):
        raise FileNotFoundError(f"Target file not found: {TARGET_FILE}")
        
    # Create backup first
    shutil.copyfile(TARGET_FILE, BACKUP_FILE)
    print(f"[+] Created safety backup at: {BACKUP_FILE}")
    
    with open(TARGET_FILE, mode='r', encoding='utf-8', errors='replace', newline='') as f:
        reader = csv.reader(f)
        header = next(reader)
        existing_rows = list(reader)
        
    email_idx = header.index('Email')
    company_idx = header.index('Công ty')
    
    existing_emails = set(r[email_idx].strip().lower() for r in existing_rows if r[email_idx].strip())
    existing_companies = set(r[company_idx].strip().lower() for r in existing_rows if r[company_idx].strip())
    
    new_rows = []
    skipped_count = 0
    start_no = len(existing_rows) + 1
    
    for item in data:
        email = item['email'].strip().lower()
        company = item['business_name'].strip().lower()
        
        if filter_duplicates:
            is_dup = False
            if email and email in existing_emails:
                is_dup = True
            if company and company in existing_companies:
                is_dup = True
            if is_dup:
                skipped_count += 1
                print(f"  [-] Skipped duplicate: {item['business_name']} ({item['email']})")
                continue
                
        # Append valid new row
        row = [
            str(start_no + len(new_rows)),     # No.
            item['business_name'],              # Công ty
            '',                                 # Chức danh
            item['licensee_name'],              # Người liên hệ
            item['phone'],                      # SĐT
            item['website'],                    # Liên Hệ
            item['email'],                      # Email
            '',                                 # Liên Hệ mail
            item['address'],                    # Địa chỉ
            '',                                 # Lương
            '',                                 # Ngày đăng
            item['expiry_date'],                # Hạn tuyển
            '',                                 # Check gửi
            '',                                 # Last Subject
            '',                                 # Last Body HTML
            '',                                 # Trạng thái Reply
            '0',                                # Lần Follow-up
            '',                                 # Ngày Follow-up gần nhất
            '',                                 # Mailbox đã dùng
            'Môi Giới Canada'                   # Category
        ]
        new_rows.append(row)
        if email:
            existing_emails.add(email)
        if company:
            existing_companies.add(company)
            
    all_rows = existing_rows + new_rows
    with open(TARGET_FILE, mode='w', encoding='utf-8', errors='replace', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(all_rows)
        
    print(f"\n[+] SUMMARY:")
    print(f"  - Total records scraped from Manitoba: {len(data)}")
    print(f"  - Duplicate records skipped: {skipped_count}")
    print(f"  - New records appended: {len(new_rows)}")
    print(f"  - Total records in '{os.path.basename(TARGET_FILE)}': {len(all_rows)}")

if __name__ == "__main__":
    records = scrape_manitoba_licences()
    save_standalone_file(records)
    append_to_cleandata(records, filter_duplicates=True)
