import os
import re
import csv
import sys
import time
import json
import shutil
from datetime import datetime
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Ensure UTF-8 console output
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET_FILE = os.path.join(ROOT_DIR, "môi giới Canada  - CleanData.csv")
BACKUP_FILE = os.path.join(ROOT_DIR, "môi giới Canada  - CleanData.backup.csv")
STANDALONE_FILE = os.path.join(ROOT_DIR, "on_licensed_recruiters.csv")
CACHE_FILE = os.path.join(ROOT_DIR, "crawlmail", "cache_on_recruiters.json")

PORTAL_URL = "https://www.tha.labour.gov.on.ca/portal/s/public-facing-status-page?language=en_US"
AURA_URL = "https://www.tha.labour.gov.on.ca/portal/s/sfsites/aura?r=1&aura.ApexAction.execute=1"

# Salesforce Aura context parameters
FWUID = "WUdfaXlIZDNDQ0lZLWNFZDMtVGZ3d2tVMjdnTGFERUU2S3FfSVdrcU92bkExNC4xOTIuODM4ODYwOA"
APP = "siteforce:communityApp"
APP_ID = "1712_xZHiuQoc1HHcvGz4vs6mGA"

CONTEXT = {
    "mode": "PROD",
    "fwuid": FWUID,
    "app": APP,
    "loaded": {f"APPLICATION@markup://{APP}": APP_ID},
    "dn": [],
    "globals": {},
    "uad": True
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Accept": "*/*",
    "Origin": "https://www.tha.labour.gov.on.ca",
    "Referer": PORTAL_URL,
}

def format_phone(phone_str):
    if not phone_str:
        return ''
    cleaned = str(phone_str).strip()
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
    d_str = str(d_str).strip()
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%B %d, %Y', '%b %d, %Y'):
        try:
            return datetime.strptime(d_str, fmt).strftime('%d-%b-%y')
        except ValueError:
            pass
    return d_str

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache):
    temp_file = CACHE_FILE + ".tmp"
    with open(temp_file, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False)
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
    os.rename(temp_file, CACHE_FILE)

def fetch_all_accounts():
    print("[*] Fetching all accounts list from Ontario MLITSD portal...")
    filter_message = {
        "actions": [
            {
                "id": "1;a",
                "descriptor": "aura://ApexActionController/ACTION$execute",
                "callingDescriptor": "UNKNOWN",
                "params": {
                    "namespace": "",
                    "classname": "MLITSD_PublicRegistryController",
                    "method": "filterAccounts",
                    "params": {"filterKey": "All"},
                    "cacheable": False,
                    "isContinuation": False
                }
            }
        ]
    }
    resp = requests.post(
        AURA_URL,
        data={
            "message": json.dumps(filter_message),
            "aura.context": json.dumps(CONTEXT),
            "aura.pageURI": "/portal/s/public-facing-status-page?language=en_US",
            "aura.token": "null"
        },
        headers=HEADERS,
        verify=False,
        timeout=45
    )
    resp.raise_for_status()
    text = resp.text
    if text.startswith("*/"):
        text = text[2:]
    data = json.loads(text)
    accounts = data['actions'][0]['returnValue']['returnValue']
    print(f"[+] Successfully retrieved {len(accounts)} total accounts from Ontario registry.")
    return accounts

def fetch_details_batch(account_batch, max_retries=3):
    actions = [
        {
            "id": f"{i};a",
            "descriptor": "aura://ApexActionController/ACTION$execute",
            "callingDescriptor": "UNKNOWN",
            "params": {
                "namespace": "",
                "classname": "MLITSD_PublicRegistryController",
                "method": "getRelatedInfoByAccountId",
                "params": {"accountId": acc["Id"]},
                "cacheable": False,
                "isContinuation": False
            }
        }
        for i, acc in enumerate(account_batch)
    ]
    
    payload = {
        "message": json.dumps({"actions": actions}),
        "aura.context": json.dumps(CONTEXT),
        "aura.pageURI": "/portal/s/public-facing-status-page?language=en_US",
        "aura.token": "null"
    }
    
    for attempt in range(max_retries):
        try:
            resp = requests.post(AURA_URL, data=payload, headers=HEADERS, verify=False, timeout=30)
            if resp.status_code == 200:
                text = resp.text
                if text.startswith("*/"):
                    text = text[2:]
                res_data = json.loads(text)
                return res_data.get('actions', [])
        except Exception as e:
            time.sleep(1.5 * (attempt + 1))
            if attempt == max_retries - 1:
                print(f"  [!] Batch request error: {e}")
    return []

def extract_record_details(acc, detail_action_val):
    val = detail_action_val.get('returnValue', {}).get('returnValue', {})
    contacts = val.get('Contacts', [])
    account_info = val.get('Account', [])
    apps = val.get('BusinessLicenseApplications', [])
    
    contact_name = ''
    contact_phone = ''
    contact_email = ''
    
    if contacts:
        c0 = contacts[0]
        contact_name = c0.get('Name', '').strip()
        contact_phone = c0.get('Phone', '').strip()
        contact_email = c0.get('Email', '').strip()
        
    if account_info:
        a0 = account_info[0]
        if not contact_phone and a0.get('Phone'):
            contact_phone = a0.get('Phone', '').strip()
        if not contact_email and a0.get('Email_Address__c'):
            contact_email = a0.get('Email_Address__c', '').strip()
            
    # Licence types and statuses
    licence_types = set()
    statuses = set()
    expiry_dates = []
    
    for app_item in apps:
        rt = app_item.get('RecordType', {}).get('Name')
        if rt:
            licence_types.add(rt)
        st = app_item.get('Public_Status__c') or app_item.get('Status')
        if st:
            statuses.add(st)
        lic_r = app_item.get('Licence__r') or {}
        exp = lic_r.get('MLITSD_Expiry_Date__c')
        if exp:
            expiry_dates.append(exp)
            
    lic_type_str = ' & '.join(sorted(licence_types)) if licence_types else 'Temporary help agency / Recruiter'
    status_str = '; '.join(sorted(statuses)) if statuses else 'Under review'
    expiry_str = format_date(expiry_dates[0]) if expiry_dates else ''
    
    legal_name = acc.get('Name', '').strip()
    operating_name = acc.get('Operating_Name_s_Business_Name_s__c', '').strip()
    company_name = operating_name if operating_name else legal_name
    
    city = acc.get('BillingCity', '').strip()
    state = acc.get('BillingState', 'ON').strip()
    country = acc.get('BillingCountry', 'Canada').strip()
    
    addr_parts = [p for p in [city, state, country] if p]
    address = ', '.join(addr_parts)
    
    return {
        'id': acc['Id'],
        'legal_name': legal_name,
        'operating_name': operating_name,
        'company_name': company_name,
        'contact_name': contact_name,
        'phone': format_phone(contact_phone),
        'email': contact_email.lower(),
        'address': address,
        'city': city,
        'province': state,
        'country': country,
        'licence_type': lic_type_str,
        'status': status_str,
        'expiry_date': expiry_str,
        'link': PORTAL_URL
    }

def run_scraper():
    accounts = fetch_all_accounts()
    cache = load_cache()
    print(f"[*] Cache contains {len(cache)} previously crawled records.")
    
    # Filter pending accounts
    pending = [acc for acc in accounts if acc['Id'] not in cache]
    print(f"[*] Pending accounts to fetch: {len(pending)}")
    
    batch_size = 25
    total_batches = (len(pending) + batch_size - 1) // batch_size
    
    start_time = time.time()
    for b_idx in range(total_batches):
        batch = pending[b_idx * batch_size : (b_idx + 1) * batch_size]
        actions = fetch_details_batch(batch)
        
        # Map actions to accounts
        for i, acc in enumerate(batch):
            if i < len(actions):
                rec = extract_record_details(acc, actions[i])
            else:
                rec = {
                    'id': acc['Id'],
                    'legal_name': acc.get('Name', '').strip(),
                    'operating_name': acc.get('Operating_Name_s_Business_Name_s__c', '').strip(),
                    'company_name': acc.get('Operating_Name_s_Business_Name_s__c', '').strip() or acc.get('Name', '').strip(),
                    'contact_name': '',
                    'phone': '',
                    'email': '',
                    'address': f"{acc.get('BillingCity', '')}, {acc.get('BillingState', 'ON')}, Canada",
                    'city': acc.get('BillingCity', ''),
                    'province': acc.get('BillingState', 'ON'),
                    'country': 'Canada',
                    'licence_type': 'Temporary help agency / Recruiter',
                    'status': 'Unknown',
                    'expiry_date': '',
                    'link': PORTAL_URL
                }
            cache[acc['Id']] = rec
            
        if (b_idx + 1) % 10 == 0 or b_idx == total_batches - 1:
            save_cache(cache)
            elapsed = time.time() - start_time
            fetched = (b_idx + 1) * batch_size
            if fetched > len(pending):
                fetched = len(pending)
            pct = (fetched / len(pending)) * 100 if pending else 100
            speed = fetched / elapsed if elapsed > 0 else 0
            eta = (len(pending) - fetched) / speed if speed > 0 else 0
            print(f"[*] Progress: {fetched}/{len(pending)} ({pct:.1f}%) | Speed: {speed:.1f} rec/s | ETA: {eta/60:.1f} min | Cached: {len(cache)}")
            
    save_cache(cache)
    print(f"\n[+] All {len(cache)} Ontario accounts fetched and cached.")
    
    # Save standalone CSV
    print(f"[*] Saving standalone CSV to: {STANDALONE_FILE}")
    standalone_fields = [
        'No.', 'Legal Name', 'Operating Name', 'Company Name', 'Contact Name',
        'Phone', 'Email', 'Address', 'City', 'Province', 'Country',
        'Licence Type', 'Status', 'Expiry Date', 'Portal Link'
    ]
    all_cached_records = [cache[acc['Id']] for acc in accounts if acc['Id'] in cache]
    
    with open(STANDALONE_FILE, mode='w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=standalone_fields)
        writer.writeheader()
        for idx, item in enumerate(all_cached_records, 1):
            writer.writerow({
                'No.': idx,
                'Legal Name': item['legal_name'],
                'Operating Name': item['operating_name'],
                'Company Name': item['company_name'],
                'Contact Name': item['contact_name'],
                'Phone': item['phone'],
                'Email': item['email'],
                'Address': item['address'],
                'City': item['city'],
                'Province': item['province'],
                'Country': item['country'],
                'Licence Type': item['licence_type'],
                'Status': item['status'],
                'Expiry Date': item['expiry_date'],
                'Portal Link': item['link']
            })
    print(f"[+] Saved standalone list ({len(all_cached_records)} records) to: {STANDALONE_FILE}")
    
    # Append deduplicated leads to CleanData
    append_to_cleandata(all_cached_records)

def append_to_cleandata(records):
    print(f"\n[*] Preparing to merge Ontario records into: {TARGET_FILE}")
    if not os.path.exists(TARGET_FILE):
        raise FileNotFoundError(f"Target file not found: {TARGET_FILE}")
        
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
    
    for item in records:
        email = item['email'].strip().lower()
        company = item['company_name'].strip().lower()
        legal = item['legal_name'].strip().lower()
        
        # Only append if valid email exists
        if not email:
            continue
            
        # Deduplication check
        if email in existing_emails:
            skipped_count += 1
            continue
        if company and company in existing_companies:
            skipped_count += 1
            continue
        if legal and legal in existing_companies:
            skipped_count += 1
            continue
            
        # Valid new row
        row = [
            str(start_no + len(new_rows)),     # No.
            item['company_name'],               # Công ty
            item['licence_type'],               # Chức danh
            item['contact_name'],               # Người liên hệ
            item['phone'],                      # SĐT
            item['link'],                       # Liên Hệ
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
        existing_emails.add(email)
        if company:
            existing_companies.add(company)
        if legal:
            existing_companies.add(legal)
            
    all_rows = existing_rows + new_rows
    with open(TARGET_FILE, mode='w', encoding='utf-8', errors='replace', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(all_rows)
        
    print(f"\n==========================================")
    print(f"  [+] ONTARIO RECRUITERS MERGE COMPLETE:")
    print(f"  - Total Ontario records crawled: {len(records)}")
    print(f"  - Duplicate / existing records skipped: {skipped_count}")
    print(f"  - Fresh new leads added: {len(new_rows)}")
    print(f"  - Total rows in '{os.path.basename(TARGET_FILE)}': {len(all_rows)}")
    print(f"==========================================")

if __name__ == '__main__':
    run_scraper()
