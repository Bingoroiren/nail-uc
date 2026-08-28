import csv
import os
import shutil
import re
import sys
import openpyxl

# Set console output encoding to UTF-8
if sys.platform.startswith('win'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Determine script directory dynamically to support running on different computers
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Candidates for input file path (in order of priority)
CANDIDATES = [
    os.path.join(SCRIPT_DIR, "(chờ) khách sạn Hy Lạp - CleanData.csv"),
    os.path.join(SCRIPT_DIR, "hotel_greece_with_emails.csv"),
    os.path.join(SCRIPT_DIR, "hotel_greece.csv")
]

INPUT_CSV = None
for candidate in CANDIDATES:
    if os.path.exists(candidate):
        INPUT_CSV = candidate
        break

if len(sys.argv) > 1:
    INPUT_CSV = sys.argv[1]

# Set backup and formatted output file names
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
    'info', 'reservations', 'reception', 'contact', 'office', 'admin', 
    'hello', 'booking', 'sales', 'manager', 'service', 'enquiries'
}

BAD_KEYWORDS = {
    'wix', 'support', 'no-reply', 'noreply', 'test', 'example', 'domain'
}

# Domains and keywords belonging to chambers or GEMI registry. These are completely discarded.
DISCARD_KEYWORDS = {
    'cci', 'chamber', 'epimel', 'epime', 'eea.gr', 'gov.gr', 'evep', 
    'eves', 'eveh', 'ebed', 'icci', 'bep.gr', 'dramanet', 'arcadianet', 
    'eber.gr', 'epimevro', 'ebef', 'gemi', 'cycladescc.gr', 'larcci.gr',
    'epihal.gr', 'champier.gr', 'e-thesprotias.gr', 'fthiotidoscc.gr',
    'korinthiacc.gr', 'acci.gr', 'cci-magnesia.gr', 'eepir', 'ebear',
    'e-a.gr', 'zantecci', 'corfucci.gr', 'ebeh.gr', 'epimfok', 'epimlas'
}

# Old Greek ISP domains or low-quality domains that are penalized but NOT discarded.
PENALTY_KEYWORDS = {
    'otenet.gr', 'otenet'
}

# Category translations from Greek to Vietnamese
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
    "ξενοδοχείο 5 αστέρων": "Khách sạn 5 sao",
    "κατ' οίκον φιλοξενία": "Homestay / Nhà nghỉ gia đình",
    "ξενοδοχείο": "Khách sạn",
    "ξενοδοχείο 4 αστέρων": "Khách sạn 4 sao",
    "ξενοδοχείο 3 αστέρων": "Khách sạn 3 sao",
    "ξενοδοχείο 2 αστέρων": "Khách sạn 2 sao",
    "ξενοδοχείο 1 αστέρων": "Khách sạn 1 sao",
    "ξενοδοχείο παρατεταμένης διαμονής": "Khách sạn lưu trú dài ngày",
    "χόστελ": "Nhà nghỉ tập thể (Hostel)",
    "μοτέλ": "Nhà nghỉ ven đường (Motel)"
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
    name_clean = str(name).lower().strip()
    name_clean = re.sub(r'[^a-z0-9\sα-ωά-ώ]', '', name_clean) # Keep Latin and Greek characters
    name_clean = " ".join(name_clean.split())
    return name_clean

def normalize_phone(phone_str):
    if not phone_str:
        return ""
    phone_clean = re.sub(r'[^0-9]', '', str(phone_str))
    if phone_clean.startswith('30') and len(phone_clean) > 10:
        phone_clean = phone_clean[2:]
    elif phone_clean.startswith('0030') and len(phone_clean) > 10:
        phone_clean = phone_clean[4:]
    return phone_clean

def main():
    if not INPUT_CSV or not os.path.exists(INPUT_CSV):
        print("="*70)
        print("[ERROR] Không tìm thấy file dữ liệu đầu vào để định dạng!")
        print("Bạn cần thực hiện các bước cào dữ liệu trước (chạy run_hotel_gr.bat).")
        print("="*70)
        return
        
    print(f"[*] Backing up original CSV to {BACKUP_CSV}...")
    shutil.copy2(INPUT_CSV, BACKUP_CSV)
    
    rows = []
    with open(INPUT_CSV, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
            
    print(f"[+] Loaded {len(rows)} rows.")
    
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
        original_email = get_field(r, 'Email', 'Liên Hệ mail')
        r['Best_Email'] = clean_and_score_email(original_email)
        # Email guessing is disabled per user request
        # if not r['Best_Email']:
        #     website = get_field(r, 'Website', 'Liên Hệ', 'URL', 'website', 'Web')
        #     r['Best_Email'] = guess_email_from_website(website)
        
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
            
    print(f"[+] Found {len(with_email)} rows with email, {len(without_email)} rows without email (after removing duplicate emails and phone numbers).")
    
    final_sorted_rows = with_email + without_email
    
    # Step 4: Reformat to standard cold mail template columns
    fieldnames = [
        "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ", 
        "Email", "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển", 
        "Check gửi", "Last Subject", "Last Body HTML", "Trạng thái Reply", 
        "Lần Follow-up", "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
    ]
    
    output_rows = []
    for i, r in enumerate(final_sorted_rows, 1):
        phone = get_field(r, 'SĐT', 'Phone')
        if phone:
            if phone.startswith("'"):
                raw_digits = phone[1:]
            else:
                raw_digits = normalize_phone(phone)
            phone = f"'{raw_digits}"
        else:
            phone = ""
            
        raw_cat = get_field(r, 'Category', 'category').lower()
        vi_category = CATEGORY_TRANSLATIONS.get(raw_cat, get_field(r, 'Category', 'category'))
        
        # Fallback to general category name if translation not found
        if not vi_category:
            vi_category = "Khách sạn Hy Lạp"
        elif not vi_category.strip().lower().endswith("hy lạp"):
            vi_category = f"{vi_category} Hy Lạp"
            
        out_row = {
            "No.": i,
            "Công ty": get_field(r, 'Công ty', 'Name'),
            "Chức danh": get_field(r, 'Chức danh'),
            "Người liên hệ": get_field(r, 'Người liên hệ'),
            "SĐT": phone,
            "Liên Hệ": get_field(r, 'Liên Hệ', 'Website'),
            "Email": r['Best_Email'],
            "Liên Hệ mail": get_field(r, 'Liên Hệ mail'),
            "Địa chỉ": get_field(r, 'Địa chỉ', 'Address'),
            "Lương": get_field(r, 'Lương'),
            "Ngày đăng": get_field(r, 'Ngày đăng'),
            "Hạn tuyển": get_field(r, 'Hạn tuyển'),
            "Check gửi": get_field(r, 'Check gửi'),
            "Last Subject": get_field(r, 'Last Subject'),
            "Last Body HTML": get_field(r, 'Last Body HTML'),
            "Trạng thái Reply": get_field(r, 'Trạng thái Reply'),
            "Lần Follow-up": get_field(r, 'Lần Follow-up') or 0,
            "Ngày Follow-up gần nhất": get_field(r, 'Ngày Follow-up gần nhất'),
            "Mailbox đã dùng": get_field(r, 'Mailbox đã dùng'),
            "Category": vi_category
        }
        output_rows.append(out_row)
        
    # Write CSV
    target_write_file = FORMATTED_CSV
    print(f"[*] Writing to CSV: {FORMATTED_CSV}...")
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

    # Write XLSX
    target_xlsx = FORMATTED_XLSX
    print(f"[*] Writing to XLSX: {target_xlsx}...")
    
    # Helper to clean strings from XML illegal characters that cause openpyxl to fail
    illegal_xml_re = re.compile(r"[\000-\008]|[\013-\014]|[\016-\037]")
    def clean_cell_value(val):
        if isinstance(val, str):
            return illegal_xml_re.sub("", val)
        return val

    try:
        out_wb = openpyxl.Workbook()
        out_sheet = out_wb.active
        out_sheet.title = "Raw"
        out_sheet.append(fieldnames)
        for o_row in output_rows:
            row_data = [clean_cell_value(o_row[k]) for k in fieldnames]
            out_sheet.append(row_data)
        out_wb.save(target_xlsx)
    except PermissionError:
        target_xlsx = FORMATTED_V2_XLSX
        print(f"[!] {FORMATTED_XLSX} is locked by Excel. Writing to {FORMATTED_V2_XLSX} instead...")
        out_wb = openpyxl.Workbook()
        out_sheet = out_wb.active
        out_sheet.title = "Raw"
        out_sheet.append(fieldnames)
        for o_row in output_rows:
            row_data = [clean_cell_value(o_row[k]) for k in fieldnames]
            out_sheet.append(row_data)
        out_wb.save(target_xlsx)
        
    # Do not overwrite the raw INPUT_CSV to preserve raw headers for email scraper resumes
    pass

if __name__ == "__main__":
    main()
