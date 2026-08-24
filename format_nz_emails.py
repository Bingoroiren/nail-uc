import csv
import os
import shutil
import re

INPUT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nail_salons_nz_with_emails.csv")
BACKUP_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nail_salons_nz_with_emails_backup.csv")
FORMATTED_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nail_salons_nz_with_emails_formatted.csv")
FORMATTED_V2_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nail_salons_nz_with_emails_formatted_v2.csv")

GENERIC_DOMAINS = {
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'live.com', 
    'aol.com', 'icloud.com', 'mail.com', 'ymail.com', 'msn.com', 
    'wix.com', 'squarespace.com', 'wordpress.com', 'wixpress.com'
}

BUSINESS_PREFIXES = {
    'info', 'hello', 'contact', 'salon', 'bookings', 'appointments', 
    'enquiries', 'manager', 'office', 'sales', 'admin'
}

BAD_KEYWORDS = {
    'wix', 'support', 'no-reply', 'noreply', 'test', 'example', 'domain'
}

def clean_and_score_email(email_str):
    if not email_str:
        return ""
    
    # Split by comma or space and clean
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
            
        # 1. Prefer non-generic domain
        if domain not in GENERIC_DOMAINS:
            score += 10
            
        # 2. Prefer business prefixes
        if any(prefix in local_part for prefix in BUSINESS_PREFIXES):
            score += 5
            
        # 3. Penalize bad keywords
        if any(bad in local_part for bad in BAD_KEYWORDS) or any(bad in domain for bad in BAD_KEYWORDS):
            score -= 20
            
        # Tie breaker: favor shorter emails slightly to avoid weird long URLs
        score -= len(email) * 0.01
        
        if score > best_score:
            best_score = score
            best_email = email
            
    return best_email

def normalize_name(name):
    if not name:
        return ""
    # Lowercase, strip, remove extra spaces and common symbols to identify duplicates
    name_clean = name.lower().strip()
    name_clean = re.sub(r'[^a-z0-9\s]', '', name_clean)
    name_clean = " ".join(name_clean.split())
    return name_clean

def main():
    if not os.path.exists(INPUT_CSV):
        print(f"Error: Input file {INPUT_CSV} does not exist.")
        return
        
    print(f"[*] Backing up original CSV to {BACKUP_CSV}...")
    shutil.copy2(INPUT_CSV, BACKUP_CSV)
    
    # Read existing rows
    rows = []
    with open(INPUT_CSV, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
            
    print(f"[+] Loaded {len(rows)} rows.")
    
    # Filter out permanently closed businesses
    active_rows = []
    closed_count = 0
    for r in rows:
        if r.get('Permanently_Closed', '').strip().lower() == 'yes':
            closed_count += 1
            continue
        active_rows.append(r)
    rows = active_rows
    if closed_count > 0:
        print(f"[*] Filtered out {closed_count} permanently closed businesses.")

    # Step 1: Normalize emails and score them
    for r in rows:
        original_email = r.get('Email', '')
        r['Best_Email'] = clean_and_score_email(original_email)
        
    # Step 2: Deduplicate by normalized name
    # We group by normalized name and select the best representative
    grouped_rows = {}
    for r in rows:
        norm_name = normalize_name(r.get('Name', ''))
        if not norm_name:
            continue
            
        if norm_name not in grouped_rows:
            grouped_rows[norm_name] = []
        grouped_rows[norm_name].append(r)
        
    deduplicated_rows = []
    for norm_name, r_list in grouped_rows.items():
        # Sort key to find the best representative:
        # 1. Has email (True first, so -1)
        # 2. Has website (True first, so -1)
        # 3. Reviews count (higher first, so -count)
        # 4. Rating (higher first, so -rating)
        def sort_rep(r):
            has_email = 1 if r['Best_Email'] else 0
            has_web = 1 if r.get('Website', '').strip() else 0
            try:
                reviews = float(r.get('Reviews_Count') or 0)
            except ValueError:
                reviews = 0.0
            try:
                rating = float(r.get('Rating') or 0)
            except ValueError:
                rating = 0.0
            return (-has_email, -has_web, -reviews, -rating)
            
        r_list.sort(key=sort_rep)
        deduplicated_rows.append(r_list[0])
        
    print(f"[+] Deduplicated from {len(rows)} to {len(deduplicated_rows)} unique company names.")
    
    # Step 3: Separate and deduplicate by email and phone number
    seen_emails = set()
    seen_phones = set()
    
    def normalize_phone(phone_str):
        if not phone_str:
            return ""
        phone_clean = re.sub(r'[^0-9]', '', phone_str)
        if phone_clean.startswith('64'):
            phone_clean = '0' + phone_clean[2:]
        return phone_clean

    with_email = []
    without_email = []
    
    # Process rows with emails first (to prioritize keeping them)
    for r in deduplicated_rows:
        email = r['Best_Email']
        if not email:
            continue
            
        clean_email = email.strip().lower()
        phone = r.get('Phone', '')
        clean_phone = normalize_phone(phone)
        
        if clean_email in seen_emails:
            continue
        if clean_phone and clean_phone in seen_phones:
            continue
            
        seen_emails.add(clean_email)
        if clean_phone:
            seen_phones.add(clean_phone)
        with_email.append(r)
        
    # Process rows without emails second
    for r in deduplicated_rows:
        email = r['Best_Email']
        if email:
            continue
            
        phone = r.get('Phone', '')
        clean_phone = normalize_phone(phone)
        
        if clean_phone and clean_phone in seen_phones:
            continue
            
        if clean_phone:
            seen_phones.add(clean_phone)
        without_email.append(r)
            
    print(f"[+] Found {len(with_email)} rows with email, {len(without_email)} rows without email (after removing duplicate emails and phone numbers).")
    
    # Combine (with email first, then without)
    final_sorted_rows = with_email + without_email
    
    # Step 4: Reformat to the requested cold mail template columns
    fieldnames = [
        "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ", 
        "Email", "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển", 
        "Check gửi", "Last Subject", "Last Body HTML", "Trạng thái Reply", 
        "Lần Follow-up", "Ngày Follow-up gần nhất", "Mailbox đã dùng"
    ]
    
    output_rows = []
    for i, r in enumerate(final_sorted_rows, 1):
        # Format phone number correctly (keep single quote prefix if exists)
        phone = r.get('Phone', '').strip()
        if phone:
            if not phone.startswith("'"):
                phone = f"'{phone}"
        else:
            phone = ""
            
        out_row = {
            "No.": i,
            "Công ty": r.get('Name', ''),
            "Chức danh": "",
            "Người liên hệ": "",
            "SĐT": phone,
            "Liên Hệ": r.get('Website', ''),
            "Email": r['Best_Email'],
            "Liên Hệ mail": "",
            "Địa chỉ": r.get('Address', ''),
            "Lương": "",
            "Ngày đăng": "",
            "Hạn tuyển": "",
            "Check gửi": "",
            "Last Subject": "",
            "Last Body HTML": "",
            "Trạng thái Reply": "",
            "Lần Follow-up": 0,
            "Ngày Follow-up gần nhất": "",
            "Mailbox đã dùng": ""
        }
        output_rows.append(out_row)
        
    # Determine which target file to write to
    target_write_file = FORMATTED_CSV
    print(f"[*] Trying to write to {FORMATTED_CSV}...")
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
        
    # Try to copy/overwrite the original INPUT_CSV
    print(f"[*] Attempting to update original {INPUT_CSV}...")
    try:
        shutil.copy2(target_write_file, INPUT_CSV)
        print("[SUCCESS] Successfully updated original file!")
    except PermissionError:
        print("\n[WARNING] Permission denied! The original file is locked by Excel.")
        print(f"[!] Please close Excel and run: python format_nz_emails.py")
        print(f"[i] The formatted copy is available at: {target_write_file}")

if __name__ == "__main__":
    main()
