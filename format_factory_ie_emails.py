import csv
import os
import shutil
import re
import sys
import openpyxl

# Set console output encoding to UTF-8
if sys.platform.startswith('win') and hasattr(sys.stdout, 'buffer'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

CANDIDATES = [
    os.path.join(SCRIPT_DIR, "factory_ireland_with_emails.csv"),
    os.path.join(SCRIPT_DIR, "factory_ireland.csv")
]

INPUT_CSV = None
for candidate in CANDIDATES:
    if os.path.exists(candidate):
        INPUT_CSV = candidate
        break

if len(sys.argv) > 1:
    INPUT_CSV = sys.argv[1]

if INPUT_CSV:
    ext = os.path.splitext(INPUT_CSV)[1]
    BACKUP_CSV = INPUT_CSV.replace(ext, f"_backup{ext}")
    FORMATTED_CSV = INPUT_CSV.replace(ext, f"_formatted{ext}")
    FORMATTED_XLSX = INPUT_CSV.replace(ext, f"_formatted.xlsx")
    FORMATTED_V2_CSV = INPUT_CSV.replace(ext, f"_formatted_v2{ext}")
    FORMATTED_V2_XLSX = INPUT_CSV.replace(ext, f"_formatted_v2.xlsx")
else:
    BACKUP_CSV = None
    FORMATTED_CSV = None
    FORMATTED_XLSX = None
    FORMATTED_V2_CSV = None
    FORMATTED_V2_XLSX = None

GENERIC_DOMAINS = {
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'live.com', 
    'aol.com', 'icloud.com', 'mail.com', 'ymail.com', 'msn.com', 
    'wix.com', 'squarespace.com', 'wordpress.com', 'wixpress.com'
}

BUSINESS_PREFIXES = {
    'info', 'sales', 'contact', 'general', 'orders', 
    'admin', 'office', 'hello', 'enquiries', 'factory', 'manufacturing'
}

BAD_KEYWORDS = {
    'wix', 'support', 'no-reply', 'noreply', 'test', 'example', 'domain', 'sentry'
}

DISCARD_KEYWORDS = {
    'gov.ie', 'enterprise-ireland.com', 'gemi'
}

# Category translations from English to Vietnamese for Factories & Manufacturing
CATEGORY_TRANSLATIONS = {
    "manufacturer": "Nhà sản xuất / Nhà máy sản xuất",
    "medical equipment manufacturer": "Nhà sản xuất thiết bị y tế",
    "semi conductor supplier": "Nhà cung cấp / Sản xuất bán dẫn",
    "semiconductor supplier": "Nhà cung cấp / Sản xuất bán dẫn",
    "electronics manufacturer": "Nhà sản xuất thiết bị điện tử",
    "corporate office": "Văn phòng doanh nghiệp / Trụ sở chính",
    "industrial equipment supplier": "Nhà cung cấp thiết bị công nghiệp",
    "electronics factory": "Nhà máy sản xuất thiết bị điện tử",
    "biomedical equipment manufacturer": "Nhà sản xuất thiết bị y sinh"
}

def translate_category(raw_cat):
    if not raw_cat:
        return "Nhà máy Điện tử & Bán dẫn Ireland"
    raw_lower = raw_cat.strip().lower()
    for key, vi_val in CATEGORY_TRANSLATIONS.items():
        if key in raw_lower:
            return vi_val
    return raw_cat.title()

def clean_and_score_email(email_str):
    if not email_str:
        return ""
    
    emails = []
    for part in re.split(r'[,\s]+', email_str):
        clean_part = part.strip().lower()
        if '@' in clean_part:
            emails.append(clean_part)
            
    if not emails:
        return ""
        
    best_email = emails[0]
    best_score = -9999
    
    for email in emails:
        score = 0
        try:
            local_part, domain = email.split('@', 1)
        except ValueError:
            continue
            
        if domain not in GENERIC_DOMAINS:
            score += 10
            
        if any(prefix in local_part for prefix in BUSINESS_PREFIXES):
            score += 5
            
        if any(bad in local_part for bad in BAD_KEYWORDS) or any(bad in domain for bad in BAD_KEYWORDS):
            score -= 20
            
        if any(discard in email for discard in DISCARD_KEYWORDS):
            score -= 50
            
        score -= len(email) * 0.01
        
        if score > best_score:
            best_score = score
            best_email = email
            
    return best_email

def normalize_name(name):
    if not name:
        return ""
    name_clean = name.lower().strip()
    name_clean = re.sub(r'[^a-z0-9\s]', '', name_clean)
    name_clean = " ".join(name_clean.split())
    return name_clean

def normalize_phone(phone_str):
    if not phone_str:
        return ""
    phone_clean = re.sub(r'[^0-9]', '', phone_str)
    if phone_clean.startswith('353'):
        phone_clean = phone_clean[3:]
    return phone_clean

def main():
    if not INPUT_CSV or not os.path.exists(INPUT_CSV):
        print(f"Error: No valid input CSV found.")
        return
        
    print(f"[*] Backing up original CSV to {BACKUP_CSV}...")
    shutil.copy2(INPUT_CSV, BACKUP_CSV)
    
    rows = []
    with open(INPUT_CSV, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
            
    print(f"[+] Loaded {len(rows)} rows from {INPUT_CSV}.")
    
    # Filter out permanently closed businesses safely
    active_rows = []
    closed_count = 0
    for r in rows:
        perm_closed = r.get('Permanently_Closed') or ''
        if str(perm_closed).strip().lower() == 'yes':
            closed_count += 1
            continue
        active_rows.append(r)
    rows = active_rows
    if closed_count > 0:
        print(f"[*] Filtered out {closed_count} permanently closed businesses.")

    def get_field(r, *keys):
        for k in keys:
            val = r.get(k, '')
            if val is not None and str(val).strip():
                return str(val).strip()
        return ''

    # Step 1: Normalize emails and score them
    for r in rows:
        original_email = get_field(r, 'Email', 'Category', 'Liên Hệ mail')
        r['Best_Email'] = clean_and_score_email(original_email)
        
    # Step 2: Deduplicate by normalized name
    grouped_rows = {}
    for r in rows:
        raw_name = get_field(r, 'Name', 'Công ty', 'name')
        norm_name = normalize_name(raw_name)
        if not norm_name:
            continue
            
        if norm_name not in grouped_rows:
            grouped_rows[norm_name] = []
        grouped_rows[norm_name].append(r)
        
    deduplicated_rows = []
    for norm_name, r_list in grouped_rows.items():
        def sort_rep(r):
            has_email = 1 if r['Best_Email'] else 0
            has_web = 1 if get_field(r, 'Website', 'Công ty', 'Liên Hệ').strip() else 0
            try:
                reviews = float(get_field(r, 'Reviews_Count') or 0)
            except ValueError:
                reviews = 0.0
            try:
                rating = float(get_field(r, 'Rating') or 0)
            except ValueError:
                rating = 0.0
            return (-has_email, -has_web, -reviews, -rating)
            
        r_list.sort(key=sort_rep)
        deduplicated_rows.append(r_list[0])
        
    print(f"[+] Deduplicated from {len(rows)} to {len(deduplicated_rows)} unique company names.")
    
    # Step 3: Separate and deduplicate by email and phone number
    seen_emails = set()
    seen_phones = set()

    with_email = []
    without_email = []
    
    for r in deduplicated_rows:
        email = r['Best_Email']
        if not email:
            continue
            
        clean_email = email.strip().lower()
        phone = get_field(r, 'Phone', 'SĐT')
        clean_phone = normalize_phone(phone)
        
        if clean_email in seen_emails:
            continue
        if clean_phone and clean_phone in seen_phones:
            continue
            
        seen_emails.add(clean_email)
        if clean_phone:
            seen_phones.add(clean_phone)
        with_email.append(r)
        
    for r in deduplicated_rows:
        email = r['Best_Email']
        if email:
            continue
            
        phone = get_field(r, 'Phone', 'SĐT')
        clean_phone = normalize_phone(phone)
        
        if clean_phone and clean_phone in seen_phones:
            continue
            
        if clean_phone:
            seen_phones.add(clean_phone)
        without_email.append(r)
            
    print(f"[+] Found {len(with_email)} rows with email, {len(without_email)} rows without email.")
    
    final_sorted_rows = with_email + without_email
    
    # Step 4: Reformat to standard cold mail template columns (20 columns)
    fieldnames = [
        "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ", 
        "Email", "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển", 
        "Check gửi", "Last Subject", "Last Body HTML", "Trạng thái Reply", 
        "Lần Follow-up", "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
    ]
    
    output_rows = []
    for i, r in enumerate(final_sorted_rows, 1):
        phone = get_field(r, 'Phone', 'SĐT')
        if phone:
            while phone.startswith("'"):
                phone = phone[1:]
            phone = f"'{phone}"
        else:
            phone = ""
            
        raw_cat = get_field(r, 'Category', 'category')
        vi_category = translate_category(raw_cat)
            
        out_row = {
            "No.": i,
            "Công ty": get_field(r, 'Name', 'Công ty'),
            "Chức danh": "",
            "Người liên hệ": "",
            "SĐT": phone,
            "Liên Hệ": get_field(r, 'Website', 'Liên Hệ'),
            "Email": r['Best_Email'],
            "Liên Hệ mail": "",
            "Địa chỉ": get_field(r, 'Address', 'Địa chỉ'),
            "Lương": "",
            "Ngày đăng": "",
            "Hạn tuyển": "",
            "Check gửi": "",
            "Last Subject": "",
            "Last Body HTML": "",
            "Trạng thái Reply": "",
            "Lần Follow-up": 0,
            "Ngày Follow-up gần nhất": "",
            "Mailbox đã dùng": "",
            "Category": vi_category
        }
        output_rows.append(out_row)
        
    target_write_file = FORMATTED_CSV
    print(f"[*] Writing formatted CSV to {FORMATTED_CSV}...")
    try:
        with open(FORMATTED_CSV, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(output_rows)
    except PermissionError:
        target_write_file = FORMATTED_V2_CSV
        print(f"[!] {FORMATTED_CSV} is locked by Excel. Writing to {FORMATTED_V2_CSV} instead...")
        with open(FORMATTED_V2_CSV, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(output_rows)
            
    # Also save Excel XLSX file
    print(f"[*] Writing formatted Excel to {FORMATTED_XLSX}...")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "CleanData"
    ws.append(fieldnames)
    for row_dict in output_rows:
        ws.append([row_dict[col] for col in fieldnames])
    wb.save(FORMATTED_XLSX)
        
    print(f"[*] Updating original {INPUT_CSV}...")
    try:
        shutil.copy2(target_write_file, INPUT_CSV)
        print("[SUCCESS] Successfully updated original file!")
    except PermissionError:
        print(f"\n[WARNING] Permission denied updating {INPUT_CSV}. File is open in Excel.")

if __name__ == "__main__":
    main()
