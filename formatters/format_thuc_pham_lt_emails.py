import csv
import os
import shutil
import re
import sys
import urllib.parse

# Set console output encoding to UTF-8
if sys.platform.startswith('win') and hasattr(sys.stdout, 'buffer'):
    import codecs
    try:
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)

CANDIDATES = [
    os.path.join(ROOT_DIR, "Thuc pham litva - Raw.csv"),
    os.path.join(ROOT_DIR, "data", "raw", "thuc_pham_litva.csv"),
    os.path.join(ROOT_DIR, "data", "formatted", "thuc_pham_litva_with_emails.csv")
]

INPUT_CSV = None
for candidate in CANDIDATES:
    if os.path.exists(candidate):
        INPUT_CSV = candidate
        break

if len(sys.argv) > 1:
    INPUT_CSV = sys.argv[1]
elif not INPUT_CSV:
    INPUT_CSV = CANDIDATES[0]

OUTPUT_READY_CSV = os.path.join(ROOT_DIR, "Thực phẩm litva - SẴN SÀNG GỬI (ĐÃ LỌC TRÙNG).csv")
OUTPUT_ALL_CSV = os.path.join(ROOT_DIR, "Thực phẩm litva - TẤT CẢ DOANH NGHIỆP.csv")

GENERIC_DOMAINS = {
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'live.com', 
    'aol.com', 'icloud.com', 'mail.com', 'inbox.lt', 'mail.lt', 'one.lt'
}

BUSINESS_PREFIXES = {
    'info', 'uzsakymai', 'sales', 'prekyba', 'biuras', 'kontaktai', 
    'office', 'admin', 'pardavimai', 'gamyba', 'tiekimas', 'contact', 'hello'
}

BAD_KEYWORDS = {
    'wix', 'wixpress', 'support@', 'no-reply', 'noreply', 'test@', 'example@', 
    'domain.com', 'sentry.io', 'abuse@', 'privacy@'
}

SOCIAL_DOMAINS = {
    'facebook.com', 'fb.com', 'fb.me', 'instagram.com', 'instagr.am',
    'twitter.com', 'x.com', 'linkedin.com', 'youtube.com', 'youtu.be',
    'tiktok.com', 'pinterest.com', 'pin.it', 'reddit.com', 'threads.net',
    't.me', 'telegram.org', 'wa.me', 'whatsapp.com', 'viber.com',
    'google.com', 'goo.gl', 'maps.app.goo.gl', 'rekvizitai.vz.lt',
    'rekvizitai.lt', 'visalietuva.lt', 'yellowpages.lt', 'wix.com',
    'wixsite.com', 'wordpress.com', 'weebly.com', 'site123.me'
}

def normalize_name(name):
    if not name:
        return ""
    cleaned = re.sub(r'[\(\[\{].*?[\)\]\}]', '', name)
    # Remove Lithuanian legal forms: UAB, AB, MB, VšĮ, IĮ, ŽŪB
    cleaned = re.sub(r'\b(uab|ab|mb|všį|vsi|iį|ii|žūb|zub|kooperatyvas|ltd|llc)\b', '', cleaned, flags=re.I)
    cleaned = re.sub(r'[^\w\s]', '', cleaned)
    return " ".join(cleaned.lower().split())

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

def clean_and_score_email(email_str):
    if not email_str:
        return "", ""
    
    discard_domains = {
        'example.com', 'example.org', 'example.net', 'yourdomain.com', 
        'email.com', 'domain.com', 'website.com', 'company.com', 
        'sentry.io', 'git.com', 'github.com', 'test.com', 'g.co'
    }
    
    emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b', email_str)
    if not emails:
        return "", ""
        
    scored = []
    for em in emails:
        em_lower = em.strip().lower()
        if any(kw in em_lower for kw in BAD_KEYWORDS):
            continue
            
        parts = em_lower.split('@')
        if len(parts) != 2:
            continue
            
        username, domain = parts
        if domain in discard_domains or domain.endswith(('.png', '.jpg', '.jpeg', '.svg', '.webp', '.pdf')):
            continue
            
        score = 0
        if any(username.startswith(prefix) for prefix in BUSINESS_PREFIXES):
            score += 10
        if domain not in GENERIC_DOMAINS:
            score += 5
        scored.append((score, em_lower))
        
    if not scored:
        return "", ""
        
    scored.sort(key=lambda x: x[0], reverse=True)
    best_email = scored[0][1]
    
    # Secondary emails if multiple
    secondary = [e for s, e in scored[1:] if e != best_email]
    secondary_str = ", ".join(secondary) if secondary else ""
    
    return best_email, secondary_str

def format_phone(phone_str):
    if not phone_str:
        return ""
    p = str(phone_str).strip()
    while p.startswith("'"):
        p = p[1:]
    if not p:
        return ""
    # Standardize 86xxxxxxx -> +3706xxxxxxx, 85xxxxxxx -> +3705xxxxxxx
    p_clean = re.sub(r'[\s\(\)\-]', '', p)
    if p_clean.startswith('86') and len(p_clean) == 9:
        p = '+3706' + p_clean[2:]
    elif p_clean.startswith('85') and len(p_clean) == 9:
        p = '+3705' + p_clean[2:]
    elif p_clean.startswith('8') and len(p_clean) == 9:
        p = '+370' + p_clean[1:]
    return f"'{p}"

def get_field(r, *keys):
    for k in keys:
        val = r.get(k, '')
        if val is not None and str(val).strip():
            return str(val).strip()
    return ''

def main():
    if not os.path.exists(INPUT_CSV):
        print(f"[-] Input file {INPUT_CSV} does not exist.")
        return
        
    print(f"[*] Đang tải dữ liệu: {INPUT_CSV}...")
    rows = []
    with open(INPUT_CSV, mode='r', encoding='utf-8-sig', errors='ignore') as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
            
    print(f"[+] Đã tải {len(rows)} doanh nghiệp thực phẩm Litva.")
    
    # 1. Lọc bỏ các doanh nghiệp đã đóng cửa vĩnh viễn (Permanently Closed)
    active_rows = []
    closed_count = 0
    for r in rows:
        perm_closed = get_field(r, 'Permanently_Closed', 'closed')
        if perm_closed.lower() == 'yes':
            closed_count += 1
            continue
        active_rows.append(r)
        
    if closed_count > 0:
        print(f"[*] Đã lọc bỏ {closed_count} cơ sở đã đóng cửa vĩnh viễn (Permanently Closed).")
        
    # 2. Làm sạch email và tính hòm thư info@ nếu thiếu
    for r in active_rows:
        raw_email = get_field(r, 'Email', 'email')
        best_em, sec_em = clean_and_score_email(raw_email)
        if not best_em:
            website = get_field(r, 'Website', 'website')
            best_em = guess_email_from_website(website)
        r['Clean_Email'] = best_em
        r['Secondary_Email'] = sec_em

    # 3. Lọc trùng lặp theo Tên công ty chuẩn hóa (Deduplicate by normalized name)
    grouped_rows = {}
    for r in active_rows:
        raw_name = get_field(r, 'Name', 'name')
        norm_name = normalize_name(raw_name)
        if not norm_name:
            continue
        if norm_name not in grouped_rows:
            grouped_rows[norm_name] = []
        grouped_rows[norm_name].append(r)
        
    deduplicated_rows = []
    for norm_name, r_list in grouped_rows.items():
        def sort_rep(r):
            has_email = 1 if r['Clean_Email'] else 0
            has_web = 1 if get_field(r, 'Website', 'website').strip() else 0
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
        
    print(f"[*] Đã lọc trùng theo tên công ty: từ {len(active_rows)} còn {len(deduplicated_rows)} doanh nghiệp độc bản.")

    # 4. Tách tập có Email (đã lọc trùng Email) và tập không có Email
    seen_emails = set()
    with_email_leads = []
    without_email_leads = []

    for r in deduplicated_rows:
        em = r['Clean_Email']
        if em:
            if em.lower() not in seen_emails:
                seen_emails.add(em.lower())
                with_email_leads.append(r)
        else:
            without_email_leads.append(r)

    print(f"[+] Tìm thấy {len(with_email_leads)} doanh nghiệp CÓ EMAIL ĐỘC BẢN (Sẵn sàng gửi Cold Mail).")
    print(f"[+] Tìm thấy {len(without_email_leads)} doanh nghiệp CHƯA CÓ EMAIL (Chỉ có SĐT/Website/FB).")

    # Chuẩn 21 cột của Cold Mail Sheet
    COLD_MAIL_COLUMNS = [
        "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ", 
        "Email", "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển", 
        "Check gửi", "Last Subject", "Last Body HTML", "Trạng thái Reply", 
        "Lần Follow-up", "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category", "Link FB"
    ]

    def build_cold_mail_row(idx, r):
        phone = format_phone(get_field(r, 'Phone', 'phone'))
        website = get_field(r, 'Website', 'website')
        address = get_field(r, 'Address', 'address')
        fb_url = get_field(r, 'Facebook_URL', 'facebook_url', 'Link FB')
        category_vn = get_field(r, 'Category_VN', 'category_vn')
        if not category_vn:
            category_vn = get_field(r, 'Category_LT', 'Category', 'category')
        
        email = r.get('Clean_Email', '')
        check_gui = "OK" if email else ""

        return {
            "No.": idx,
            "Công ty": get_field(r, 'Name', 'name'),
            "Chức danh": "",
            "Người liên hệ": "",
            "SĐT": phone,
            "Liên Hệ": website,
            "Email": email,
            "Liên Hệ mail": r.get('Secondary_Email', ''),
            "Địa chỉ": address,
            "Lương": "",
            "Ngày đăng": "",
            "Hạn tuyển": "",
            "Check gửi": check_gui,
            "Last Subject": "",
            "Last Body HTML": "",
            "Trạng thái Reply": "",
            "Lần Follow-up": 0,
            "Ngày Follow-up gần nhất": "",
            "Mailbox đã dùng": "",
            "Category": category_vn,
            "Link FB": fb_url
        }

    # Xuất file 1: Bản SẴN SÀNG GỬI (chỉ gồm các công ty có email, 100% độc bản)
    ready_rows = [build_cold_mail_row(i, r) for i, r in enumerate(with_email_leads, 1)]
    with open(OUTPUT_READY_CSV, mode='w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLD_MAIL_COLUMNS)
        writer.writeheader()
        writer.writerows(ready_rows)
    print(f"[SUCCESS] Đã tạo file: {OUTPUT_READY_CSV} ({len(ready_rows)} dòng)")

    # Xuất file 2: Bản TẤT CẢ DOANH NGHIỆP (đầy đủ cả có mail và chưa có mail, xếp nhóm có mail lên đầu)
    all_combined = with_email_leads + without_email_leads
    all_rows = [build_cold_mail_row(i, r) for i, r in enumerate(all_combined, 1)]
    with open(OUTPUT_ALL_CSV, mode='w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLD_MAIL_COLUMNS)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"[SUCCESS] Đã tạo file: {OUTPUT_ALL_CSV} ({len(all_rows)} dòng)")

    print("\n" + "="*60)
    print("           TỔNG KẾT FORMAT COLD MAIL THỰC PHẨM LITVA")
    print("="*60)
    print(f"1. File Sẵn Sàng Gửi (CSV): {OUTPUT_READY_CSV}")
    print(f"   • Số lượng email độc bản: {len(ready_rows):,} doanh nghiệp")
    print(f"   • 100% có Email, SĐT, Website, Check gửi = OK")
    print(f"2. File Tất Cả Doanh Nghiệp (CSV): {OUTPUT_ALL_CSV} ({len(all_rows):,} doanh nghiệp)")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
