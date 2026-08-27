import csv
import os
import shutil
import re

INPUT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "taiwan_factories_with_emails.csv")
BACKUP_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "taiwan_factories_with_emails_backup.csv")
FORMATTED_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "taiwan_factories_with_emails_formatted.csv")
FORMATTED_V2_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "taiwan_factories_with_emails_formatted_v2.csv")

GENERIC_DOMAINS = {
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'live.com', 
    'aol.com', 'icloud.com', 'mail.com', 'ymail.com', 'msn.com', 
    'wix.com', 'squarespace.com', 'wordpress.com', 'wixpress.com'
}

BUSINESS_PREFIXES = {
    'info', 'hello', 'contact', 'office', 'admin', 'sales', 
    'enquiries', 'manager', 'service', 'tw', 'taiwan', 'factory', 'mfg'
}

BAD_KEYWORDS = {
    'wix', 'support', 'no-reply', 'noreply', 'test', 'example', 'domain'
}

# Translation dictionary from Traditional Chinese to Vietnamese
import urllib.parse

SOCIAL_DOMAINS = {
    # Social networks & Media
    'facebook.com', 'fb.com', 'fb.me',
    'instagram.com', 'instagr.am',
    'twitter.com', 'x.com',
    'linkedin.com',
    'youtube.com', 'youtu.be',
    'tiktok.com',
    'pinterest.com', 'pin.it',
    'reddit.com',
    'threads.net',
    'tumblr.com',
    'flickr.com',
    'snapchat.com',
    # Messaging
    't.me', 'telegram.org', 'telegram.me',
    'wa.me', 'whatsapp.com',
    'line.me',
    'viber.com',
    'zalo.me',
    'wechat.com',
    # Search & Maps
    'google.com', 'goo.gl', 'google.co.uk', 'google.ie', 'google.com.au',
    'google.com.tw', 'google.gr', 'google.pt', 'google.sk', 'google.lv',
    'google.co.nz', 'google.com.hk', 'google.de', 'google.fr',
    'maps.app.goo.gl', 'waze.com', 'bing.com', 'yahoo.com', 'duckduckgo.com',
    # Directories & Reviews & Platforms
    'yelp.com', 'yelp.com.au', 'yelp.ie', 'yelp.co.uk',
    'tripadvisor.com', 'tripadvisor.ie', 'tripadvisor.co.uk', 'tripadvisor.com.tw', 'tripadvisor.com.gr',
    'yellowpages.com', 'yellowpages.com.au', 'whitepages.com', 'whitepages.com.au',
    'foursquare.com', 'trustpilot.com', 'wikipedia.org', 'wikidata.org',
    # Website builders default / generic hosting
    'apple.com', 'apps.apple.com', 'play.google.com',
    'wix.com', 'wixsite.com', 'wixpress.com', 'squarespace.com', 
    'wordpress.com', 'weebly.com', 'site123.me', 'jimdosite.com', 
    'godaddysites.com', 'myshopify.com', 'canva.site', 'linktr.ee', 'carrd.co'
}

def get_field(r, *keys):
    for k in keys:
        val = r.get(k, '')
        if val is not None and str(val).strip():
            return str(val).strip()
    return ''

def guess_email_from_website(website_url):
    if not website_url or not isinstance(website_url, str):
        return ""
    url = website_url.strip()
    if not url:
        return ""
    if not url.startswith(('http://', 'https://')):
        url = 'http://' + url
    try:
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.strip().lower()
        if not netloc:
            return ""
        if ':' in netloc:
            netloc = netloc.split(':')[0]
        netloc = re.sub(r'^www\d*\.', '', netloc)
        if not netloc or '.' not in netloc:
            return ""
        for social in SOCIAL_DOMAINS:
            if netloc == social or netloc.endswith('.' + social):
                return ""
        if re.match(r'^[a-z0-9][a-z0-9\.\-]*\.[a-z]{2,}$', netloc):
            if netloc.endswith('.') or re.match(r'^\d+\.\d+\.\d+\.\d+$', netloc):
                return ""
            return f"info@{netloc}"
        return ""
    except Exception:
        return ""

CATEGORY_TRANSLATIONS = {
    "工廠設備供應商": "Nhà cung cấp thiết bị nhà máy",
    "家具製造商": "Nhà sản xuất đồ nội thất",
    "電子產品製造商": "Nhà sản xuất sản phẩm điện tử",
    "電子零件供應商": "Nhà cung cấp linh kiện điện tử",
    "玩具製造商": "Nhà sản xuất đồ chơi",
    "食品製造商": "Nhà sản xuất thực phẩm",
    "食品調味料製造商": "Nhà sản xuất gia vị thực phẩm",
    "冷凍食品製造商": "Nhà sản xuất thực phẩm đông lạnh",
    "化學工廠": "Nhà máy hóa chất",
    "化學品製造商": "Nhà sản xuất hóa chất",
    "機械製造商": "Nhà sản xuất máy móc",
    "機械廠": "Nhà máy cơ khí",
    "機械零件製造商": "Nhà sản xuất phụ tùng máy móc",
    "汽車零件製造商": "Nhà sản xuất phụ tùng ô tô",
    "塑料製造公司": "Công ty sản xuất nhựa",
    "塑膠製品供應商": "Nhà cung cấp sản phẩm nhựa",
    "紡織廠": "Nhà máy dệt",
    "紗廠": "Nhà máy kéo sợi",
    "服裝與布料製造商": "Nhà sản xuất quần áo và vải",
    "布產品製造商": "Nhà sản xuất sản phẩm vải",
    "電池製造商": "Nhà sản xuất pin",
    "玻璃製造商": "Nhà sản xuất thủy tinh",
    "玻璃纖維供應商": "Nhà cung cấp sợi thủy tinh",
    "鞋廠": "Nhà máy giày",
    "汽車工廠": "Nhà máy sản xuất ô tô",
    "造紙廠": "Nhà máy sản xuất giấy",
    "半導體供應商": "Nhà cung cấp bán dẫn",
    "橡膠製品供應商": "Nhà cung cấp sản phẩm cao su",
    "扣件供應商": "Nhà cung cấp chốt đai ốc (bu lông đai ốc)",
    "製造商": "Nhà sản xuất",
    "電子公司": "Công ty điện tử",
    "公司辦公室": "Văn phòng công ty"
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
    # For Chinese names, we remove spaces and punctuation
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
        original_email = get_field(r, 'Email', 'Category', 'Liên Hệ mail', 'email', 'Email liên hệ')
        r['Best_Email'] = clean_and_score_email(original_email)
        if not r['Best_Email']:
            website = r.get('Website') or r.get('Liên Hệ') or r.get('URL') or r.get('website') or ''
            r['Best_Email'] = guess_email_from_website(website)
        
    # Step 2: Deduplicate by normalized name
    grouped_rows = {}
    for r in rows:
        norm_name = normalize_name(get_field(r, 'Name', 'Công ty', 'name', 'Tên công ty', 'Tên tiếng Anh', 'Tên chủ sử dụng'))
        if not norm_name:
            continue
            
        if norm_name not in grouped_rows:
            grouped_rows[norm_name] = []
        grouped_rows[norm_name].append(r)
        
    deduplicated_rows = []
    for norm_name, r_list in grouped_rows.items():
        # Sort key:
        # 1. Has email (True first, so -1)
        # 2. Has website (True first, so -1)
        # 3. Reviews count (higher first, so -count)
        # 4. Rating (higher first, so -rating)
        def sort_rep(r):
            has_email = 1 if r['Best_Email'] else 0
            has_web = 1 if get_field(r, 'Website', 'Liên Hệ', 'URL', 'website', 'Web').strip() else 0
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
    
    with_email = []
    without_email = []
    
    # Process rows with emails first (to prioritize keeping them)
    for r in deduplicated_rows:
        email = r['Best_Email']
        if not email:
            continue
            
        clean_email = email.strip().lower()
        phone = get_field(r, 'Phone', 'SĐT', 'phone', 'Điện thoại', 'SĐT chủ')
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
            
        phone = get_field(r, 'Phone', 'SĐT', 'phone', 'Điện thoại', 'SĐT chủ')
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
        "Lần Follow-up", "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
    ]
    
    output_rows = []
    for i, r in enumerate(final_sorted_rows, 1):
        phone = get_field(r, 'Phone', 'SĐT', 'phone', 'Điện thoại', 'SĐT chủ').strip()
        if phone:
            raw_digits = normalize_phone(phone)
            phone = f"'{raw_digits}"
        else:
            phone = ""
            
        # Translate category to Vietnamese if translation exists
        raw_category = get_field(r, 'Category', 'category', 'Ngành nghề').strip()
        vi_category = CATEGORY_TRANSLATIONS.get(raw_category, get_field(r, 'Category', 'category', 'Ngành nghề'))
            
        out_row = {
            "No.": i,
            "Công ty": get_field(r, 'Name', 'Công ty', 'name', 'Tên công ty', 'Tên tiếng Anh', 'Tên chủ sử dụng'),
            "Chức danh": "",
            "Người liên hệ": "",
            "SĐT": phone,
            "Liên Hệ": get_field(r, 'Website', 'Liên Hệ', 'URL', 'website', 'Web'),
            "Email": r['Best_Email'],
            "Liên Hệ mail": "",
            "Địa chỉ": get_field(r, 'Address', 'Địa chỉ', 'address'),
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
        print(f"[!] Please close Excel and run: python format_tw_factories_emails.py")
        print(f"[i] The formatted copy is available at: {target_write_file}")

if __name__ == "__main__":
    main()
