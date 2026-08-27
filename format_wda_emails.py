import csv
import os
import shutil
import re

INPUT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wda_hot_leads.csv")
BACKUP_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wda_hot_leads_backup.csv")
FORMATTED_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wda_employers_formatted.csv")
FORMATTED_V2_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wda_employers_formatted_v2.csv")

GENERIC_DOMAINS = {
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'live.com', 
    'aol.com', 'icloud.com', 'mail.com', 'ymail.com', 'msn.com', 
    'wix.com', 'squarespace.com', 'wordpress.com', 'wixpress.com'
}

BUSINESS_PREFIXES = {
    'info', 'hello', 'contact', 'office', 'admin', 'sales', 
    'enquiries', 'manager', 'service', 'tw', 'taiwan', 'hr'
}

BAD_KEYWORDS = {
    'wix', 'support', 'no-reply', 'noreply', 'test', 'example', 'domain'
}

# Translation dictionary from Chinese (WDA) to Vietnamese
CATEGORY_TRANSLATIONS = {
    "製造工": "Lao động sản xuất / Chế tạo",
    "營造工": "Lao động xây dựng",
    "家庭看護工": "Lao động chăm sóc gia đình / Khán hộ công",
    "海洋漁撈": "Đánh bắt hải sản / Ngư nghiệp",
    "農林牧或養殖漁業工作": "Nông lâm ngư nghiệp hoặc chăn nuôi nuôi trồng thủy sản",
    "外國技術人力農林牧或養殖漁業技術工作": "Kỹ thuật viên nông lâm ngư nghiệp hoặc nuôi trồng thủy sản",
    "廢棄物及資源物回收處理工作": "Tái chế và xử lý chất thải, tài nguyên",
    "外展農務工作": "Lao động nông nghiệp dịch vụ / Outreach nông nghiệp",
    "雙語翻譯": "Phiên dịch song ngữ",
    "外國技術人力製造技術工作": "Kỹ thuật viên sản xuất / Chế tạo",
    "家庭幫傭": "Giúp việc gia đình",
    "屠宰工": "Lao động giết mổ / Slaughterhouse worker"
}

def clean_and_score_email(email_str):
    if not email_str:
        return ""
    
    discard_domains = {
        'example.com', 'example.org', 'example.net', 'yourdomain.com', 
        'vasemail.cz', 'webonic.hu', 'tvojweb.sk', 'mojweb.sk', 'domain.com', 'mydomain.com',
        'email.com', 'mail.com', 'test.com', 'website.com', 'sentry.io', 'wixpress.com'
    }
    discard_substrings = {
        'noreply', 'no-reply', 'example', 'yourdomain', 'sentry', 'placeholder', 
        'invalid', 'null', 'undefined', 'tempmail'
    }
    discard_locals = {
        'email', 'your.email', 'yourname', 'test', 'your', 'user', 'name', 'myname'
    }

    emails = []
    for part in re.split(r'[,\s;]+', str(email_str)):
        clean_part = part.strip().lower()
        if '@' in clean_part:
            try:
                local_part, domain = clean_part.split('@', 1)
            except ValueError:
                continue
            
            if domain in discard_domains:
                continue
            if any(sub in clean_part for sub in discard_substrings):
                continue
            if local_part in discard_locals:
                continue
            try:
                if any(discard in clean_part for discard in DISCARD_KEYWORDS):
                    continue
            except NameError:
                pass
                
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
            
        try:
            if any(k in email for k in PENALTY_KEYWORDS):
                score -= 50
        except NameError:
            pass
            
        score -= len(email) * 0.01
        
        if score > best_score:
            best_score = score
            best_email = email
            
    return best_email

def normalize_name(name):
    if not name:
        return ""
    name_clean = name.strip()
    name_clean = re.sub(r'[\s\-\,\.\(\)（）]', '', name_clean)
    return name_clean.lower()

def normalize_phone(phone_str):
    if not phone_str:
        return ""
    phone_clean = re.sub(r'[^0-9]', '', phone_str)
    # If Taiwan country code is included, normalize to local representation (e.g. 886912345678 -> 0912345678)
    if phone_clean.startswith('886'):
        phone_clean = '0' + phone_clean[3:]
    return phone_clean

def main():
    # If wda_hot_leads.csv doesn't exist, try wda_employers.csv
    input_file = INPUT_CSV
    if not os.path.exists(input_file):
        input_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wda_employers.csv")
        
    if not os.path.exists(input_file):
        print(f"Error: Neither {INPUT_CSV} nor wda_employers.csv exist.")
        return
        
    print(f"[*] Reading data from {input_file}...")
    print(f"[*] Backing up to {BACKUP_CSV}...")
    shutil.copy2(input_file, BACKUP_CSV)
    
    # Read existing rows
    rows = []
    with open(input_file, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
            
    print(f"[+] Loaded {len(rows)} rows.")
    
    # Step 1: Normalize emails and score them
    for r in rows:
        original_email = r.get('Email liên hệ', '')
        r['Best_Email'] = clean_and_score_email(original_email)
        
    # Step 2: Deduplicate by normalized name
    grouped_rows = {}
    for r in rows:
        norm_name = normalize_name(r.get('Tên chủ sử dụng', ''))
        if not norm_name:
            continue
            
        if norm_name not in grouped_rows:
            grouped_rows[norm_name] = []
        grouped_rows[norm_name].append(r)
        
    deduplicated_rows = []
    for norm_name, r_list in grouped_rows.items():
        def sort_rep(r):
            has_email = 1 if r['Best_Email'] else 0
            has_web = 1 if r.get('Link chi tiết', '').strip() else 0
            try:
                quota = float(r.get('Số lượng tuyển (Quota)') or 0)
            except ValueError:
                quota = 0.0
            return (-has_email, -has_web, -quota)
            
        r_list.sort(key=sort_rep)
        deduplicated_rows.append(r_list[0])
        
    print(f"[+] Deduplicated from {len(rows)} to {len(deduplicated_rows)} unique company names.")
    
    # Step 3: Separate and deduplicate by email and phone number
    seen_emails = set()
    seen_phones = set()
    
    with_email = []
    without_email = []
    
    # Process rows with emails first (to prioritize keeping them)
    for r in deduplicated_rows:
        email = r['Best_Email']
        if not email:
            continue
            
        clean_email = email.strip().lower()
        
        phone_chu = r.get('SĐT chủ', '').strip()
        clean_phone_chu = normalize_phone(phone_chu) if phone_chu != "不顯示" else ""
        phone_mg = r.get('SĐT môi giới', '').strip()
        clean_phone_mg = normalize_phone(phone_mg) if phone_mg != "不顯示" else ""
        
        clean_phone = clean_phone_chu if clean_phone_chu else clean_phone_mg
        
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
            
        phone_chu = r.get('SĐT chủ', '').strip()
        clean_phone_chu = normalize_phone(phone_chu) if phone_chu != "不顯示" else ""
        phone_mg = r.get('SĐT môi giới', '').strip()
        clean_phone_mg = normalize_phone(phone_mg) if phone_mg != "不顯示" else ""
        
        clean_phone = clean_phone_chu if clean_phone_chu else clean_phone_mg
        
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
        "Lần Follow-up", "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category",
        "SĐT môi giới"
    ]
    
    output_rows = []
    for i, r in enumerate(final_sorted_rows, 1):
        # SĐT (5th column) contains SĐT chủ (employer phone)
        phone_chu = r.get('SĐT chủ', '').strip()
        if phone_chu and phone_chu != "不顯示" and 'E+' not in phone_chu and 'e+' not in phone_chu:
            raw_digits_chu = normalize_phone(phone_chu)
            phone_val = f"'{raw_digits_chu}" if raw_digits_chu else ""
        else:
            phone_val = ""
            
        # SĐT môi giới (last column) contains SĐT môi giới (broker phone)
        phone_mg = r.get('SĐT môi giới', '').strip()
        if phone_mg and phone_mg != "不顯示" and 'E+' not in phone_mg and 'e+' not in phone_mg:
            raw_digits_mg = normalize_phone(phone_mg)
            phone_mg_val = f"'{raw_digits_mg}" if raw_digits_mg else ""
        else:
            phone_mg_val = ""
            
        # Translate category (job name)
        raw_job = r.get('Ngành nghề', '').strip()
        vi_job = CATEGORY_TRANSLATIONS.get(raw_job, r.get('Ngành nghề', ''))
        
        # Lead level rating
        lead_type = r.get('Xếp loại Lead', 'COLD LEAD ❄️').strip()
            
        out_row = {
            "No.": i,
            "Công ty": r.get('Tên chủ sử dụng', ''),
            "Chức danh": vi_job,
            "Người liên hệ": "",
            "SĐT": phone_val,
            "Liên Hệ": r.get('Link chi tiết', ''),
            "Email": r['Best_Email'],
            "Liên Hệ mail": "",
            "Địa chỉ": r.get('Địa điểm làm việc', ''),
            "Lương": r.get('Điều kiện lao động (Lương/Ăn ở)', ''),
            "Ngày đăng": "",
            "Hạn tuyển": r.get('Ngày hết hạn', ''),
            "Check gửi": "",
            "Last Subject": "",
            "Last Body HTML": "",
            "Trạng thái Reply": "",
            "Lần Follow-up": 0,
            "Ngày Follow-up gần nhất": "",
            "Mailbox đã dùng": "",
            "Category": lead_type,
            "SĐT môi giới": phone_mg_val
        }
        output_rows.append(out_row)
        
    target_write_file = FORMATTED_CSV
    print(f"[*] Trying to write to {FORMATTED_CSV}...")
    try:
        with open(FORMATTED_CSV, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(output_rows)
        print("[SUCCESS] Formatting complete!")
    except PermissionError:
        target_write_file = FORMATTED_V2_CSV
        print(f"[!] {FORMATTED_CSV} is locked. Writing to {FORMATTED_V2_CSV} instead...")
        with open(FORMATTED_V2_CSV, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(output_rows)
        print("[SUCCESS] Formatting complete (v2)!")
        
if __name__ == "__main__":
    main()
