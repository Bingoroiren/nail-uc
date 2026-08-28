"""
format_metal_lv_emails.py
=========================
Formats metal_latvia_with_emails.csv into the standard cold-mail template.

Output columns match all other formatted files in the project:
  No. | Cong ty | Chuc danh | Nguoi lien he | SDT | Lien He | Email |
  Lien He mail | Dia chi | Luong | Ngay dang | Han tuyen |
  Check gui | Last Subject | Last Body HTML | Trang thai Reply |
  Lan Follow-up | Ngay Follow-up gan nhat | Mailbox da dung | Category

Data designed to be merged/appended into masoc_members_formatted.csv.
"""
import csv
import os
import shutil
import re
import sys

INPUT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metal_latvia_with_emails.csv")
if len(sys.argv) > 1:
    INPUT_CSV = sys.argv[1]

BACKUP_CSV      = INPUT_CSV.replace(".csv", "_backup.csv")
FORMATTED_CSV   = INPUT_CSV.replace(".csv", "_formatted.csv")
FORMATTED_V2_CSV = INPUT_CSV.replace(".csv", "_formatted_v2.csv")

# ---- Category translations (Latvian -> Vietnamese) ----
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
    "metāla darbnīca":               "Xưởng gia công kim loại",
    "metālapstrāde":                 "Gia công kim loại",
    "metāla konstrukcijas":          "Kết cấu kim loại",
    "metāla izstrādājumu ražotājs":  "Nhà sản xuất sản phẩm kim loại",
    "metāllūžņu sniedzējs":          "Nhà cung cấp phế liệu kim loại",
    "metālapstrādes uzņēmums":       "Công ty gia công kim loại",
    "metālizstrādājumu ražotājs":    "Nhà sản xuất đồ kim loại",
    "metāla ražotājs":               "Nhà sản xuất kim loại",
    "nerūsejošā tērauda piegādātājs":"Nhà cung cấp thép không gỉ",
    "tērauda piegādātājs":           "Nhà cung cấp thép",
    "metāla jumts":                  "Mái kim loại",
    "metāla detaļu ražotājs":        "Nhà sản xuất phụ tùng kim loại",
    "metālapstrādes pakalpojumi":    "Dịch vụ gia công kim loại",
}
CATEGORY_DEFAULT = "Gia công kim loại Latvia"

GENERIC_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "live.com",
    "aol.com", "icloud.com", "mail.com", "ymail.com", "msn.com",
    "wix.com", "squarespace.com", "wordpress.com", "wixpress.com"
}
BUSINESS_PREFIXES = {
    "info", "hello", "contact", "office", "admin",
    "sales", "manager", "support", "mail", "enquiries"
}
BAD_KEYWORDS = {"wix", "no-reply", "noreply", "test", "example", "domain"}


def clean_and_score_email(email_str):
    if not email_str:
        return ""
    emails = []
    for part in re.split(r"[,\s]+", email_str):
        clean = part.strip().lower()
        if "@" in clean:
            emails.append(clean)
    if not emails:
        return ""
    best, best_score = emails[0], -9999
    for email in emails:
        score = 0
        try:
            local, domain = email.split("@", 1)
        except ValueError:
            continue
        if domain not in GENERIC_DOMAINS:
            score += 10
        if any(p in local for p in BUSINESS_PREFIXES):
            score += 5
        if any(b in local for b in BAD_KEYWORDS) or any(b in domain for b in BAD_KEYWORDS):
            score -= 20
        score -= len(email) * 0.01
        if score > best_score:
            best_score, best = score, email
    return best


def normalize_name(name):
    if not name:
        return ""
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\s]", "", name)
    return " ".join(name.split())


def normalize_phone(phone_str):
    if not phone_str:
        return ""
    clean = re.sub(r"[^0-9]", "", phone_str)
    if clean.startswith("371"):
        clean = clean[3:]
    return clean


def get_field(r, *keys):
    for k in keys:
        v = r.get(k, "")
        if v and str(v).strip():
            return str(v).strip()
    return ""


def main():
    if not os.path.exists(INPUT_CSV):
        print(f"Error: Input file {INPUT_CSV} does not exist.")
        return

    print(f"[*] Backing up original CSV to {BACKUP_CSV}...")
    shutil.copy2(INPUT_CSV, BACKUP_CSV)

    rows = []
    with open(INPUT_CSV, mode="r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(f"[+] Loaded {len(rows)} rows.")

    # Filter permanently closed
    active_rows, closed_count = [], 0
    for r in rows:
        if str(r.get("Permanently_Closed", "")).strip().lower() == "yes":
            closed_count += 1
            continue
        active_rows.append(r)
    rows = active_rows
    if closed_count:
        print(f"[*] Filtered out {closed_count} permanently closed businesses.")

    # Score best email
    for r in rows:
        r["Best_Email"] = clean_and_score_email(
            get_field(r, "Email", "Category", "Liên Hệ mail")
        )
        if not r["Best_Email"]:
            website = get_field(r, "Website", "Liên Hệ", "URL", "website")
            r["Best_Email"] = guess_email_from_website(website)

    # Deduplicate by normalized name
    grouped = {}
    for r in rows:
        raw_name = get_field(r, "Name", "Công ty", "name")
        norm = normalize_name(raw_name)
        if not norm:
            continue
        grouped.setdefault(norm, []).append(r)

    deduped = []
    for norm, rlist in grouped.items():
        rlist.sort(key=lambda r: (
            -1 if r["Best_Email"] else 0,
            -1 if get_field(r, "Website").strip() else 0,
            -(float(get_field(r, "Reviews_Count") or 0) if get_field(r, "Reviews_Count") else 0)
        ))
        deduped.append(rlist[0])
    print(f"[+] Deduplicated from {len(rows)} to {len(deduped)} unique companies.")

    # Deduplicate by email / phone
    seen_emails, seen_phones = set(), set()
    with_email, without_email = [], []

    for r in deduped:
        email = r["Best_Email"]
        if not email:
            continue
        ce = email.strip().lower()
        phone = get_field(r, "Phone", "SĐT")
        cp = normalize_phone(phone)
        if ce in seen_emails:
            continue
        if cp and cp in seen_phones:
            continue
        seen_emails.add(ce)
        if cp:
            seen_phones.add(cp)
        with_email.append(r)

    for r in deduped:
        if r["Best_Email"]:
            continue
        phone = get_field(r, "Phone", "SĐT")
        cp = normalize_phone(phone)
        if cp and cp in seen_phones:
            continue
        if cp:
            seen_phones.add(cp)
        without_email.append(r)

    print(f"[+] Found {len(with_email)} rows with email, {len(without_email)} without email.")
    final_rows = with_email + without_email

    # Build output rows with standard cold-mail columns
    fieldnames = [
        "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ",
        "Email", "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển",
        "Check gửi", "Last Subject", "Last Body HTML", "Trạng thái Reply",
        "Lần Follow-up", "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
    ]

    # Load existing MASOC members to append/merge
    masoc_formatted_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "masoc_members_formatted.csv")
    masoc_rows = []
    seen_masoc_names = set()
    seen_masoc_emails = set()
    seen_masoc_phones = set()

    if os.path.exists(masoc_formatted_path):
        print(f"[*] Loading existing MASOC members from {masoc_formatted_path} for merging...")
        try:
            with open(masoc_formatted_path, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    masoc_rows.append(dict(r))
                    
                    name = r.get("Công ty", "").strip()
                    norm_n = normalize_name(name)
                    if norm_n:
                        seen_masoc_names.add(norm_n)
                        
                    email = r.get("Email", "").strip().lower()
                    if email:
                        seen_masoc_emails.add(email)
                        
                    phone = r.get("SĐT", "").replace("'", "").strip()
                    norm_p = normalize_phone(phone)
                    if norm_p:
                        seen_masoc_phones.add(norm_p)
            print(f"[+] Loaded {len(masoc_rows)} existing MASOC records.")
        except Exception as e:
            print(f"[-] Error loading MASOC file: {e}")

    metal_only_formatted = []
    merged_count = 0
    updated_count = 0

    # Build a lookup dictionary for masoc rows by normalized name
    masoc_by_name = {}
    for row in masoc_rows:
        n_name = normalize_name(row.get("Công ty", ""))
        if n_name:
            masoc_by_name[n_name] = row

    for r in final_rows:
        name_val = get_field(r, "Name", "Công ty")
        norm_name = normalize_name(name_val)
        
        email_val = r["Best_Email"].strip()
        phone_val = get_field(r, "Phone", "SĐT")
        
        if phone_val:
            digits = re.sub(r"[^0-9]", "", phone_val)
            if digits.startswith("371"):
                digits = digits[3:]
            phone_fmt = f"'{digits}"
            norm_phone = digits
        else:
            phone_fmt = ""
            norm_phone = ""

        raw_cat = get_field(r, "Category", "category").lower().strip()
        vi_cat = CATEGORY_DEFAULT
        for lv_key, vi_val in CATEGORY_TRANSLATIONS.items():
            if lv_key in raw_cat:
                vi_cat = vi_val
                break

        # If it already exists in MASOC, check if we can fill missing email/phone
        if norm_name in masoc_by_name:
            existing_row = masoc_by_name[norm_name]
            updated = False
            
            # Fill missing email
            if email_val and not existing_row.get("Email", "").strip():
                existing_row["Email"] = email_val
                updated = True
                
            # Fill missing phone
            if phone_fmt and not existing_row.get("SĐT", "").strip():
                existing_row["SĐT"] = phone_fmt
                updated = True
                
            if updated:
                updated_count += 1
            continue

        # Check duplicates against MASOC by email/phone
        if email_val.lower() and email_val.lower() in seen_masoc_emails:
            continue
        if norm_phone and norm_phone in seen_masoc_phones:
            continue

        new_row = {
            "No.":                       0,  # Will be re-indexed
            "Công ty":                   name_val,
            "Chức danh":                 "",
            "Người liên hệ":             "",
            "SĐT":                       phone_fmt,
            "Liên Hệ":                   get_field(r, "Website", "Liên Hệ"),
            "Email":                     email_val,
            "Liên Hệ mail":              "",
            "Địa chỉ":                   get_field(r, "Address", "Địa chỉ"),
            "Lương":                     "",
            "Ngày đăng":                 "",
            "Hạn tuyển":                 "",
            "Check gửi":                 "",
            "Last Subject":              "",
            "Last Body HTML":            "",
            "Trạng thái Reply":          "",
            "Lần Follow-up":             0,
            "Ngày Follow-up gần nhất":   "",
            "Mailbox đã dùng":           "",
            "Category":                  vi_cat,
        }
        
        metal_only_formatted.append(new_row.copy())
        masoc_rows.append(new_row.copy())
        merged_count += 1

    # Re-index all lists
    for idx, row in enumerate(metal_only_formatted, 1):
        row["No."] = idx
    for idx, row in enumerate(masoc_rows, 1):
        row["No."] = idx

    # Write standalone metal formatted CSV
    print(f"[*] Writing to {FORMATTED_CSV}...")
    try:
        with open(FORMATTED_CSV, mode="w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(metal_only_formatted)
    except PermissionError:
        print(f"[!] {FORMATTED_CSV} is locked. Writing to {FORMATTED_V2_CSV} instead...")
        with open(FORMATTED_V2_CSV, mode="w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(metal_only_formatted)

    # Write merged MASOC CSV
    print(f"[*] Writing to {masoc_formatted_path}...")
    try:
        with open(masoc_formatted_path, mode="w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(masoc_rows)
    except PermissionError:
        masoc_v2 = masoc_formatted_path.replace(".csv", "_v2.csv")
        print(f"[!] {masoc_formatted_path} is locked. Writing to {masoc_v2} instead...")
        with open(masoc_v2, mode="w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(masoc_rows)

    # Do not overwrite the raw INPUT_CSV so it preserves the original headers for scraper resumes
    pass

    print(f"\n--- Summary ---")
    print(f"Total unique metal rows: {len(metal_only_formatted)}")
    print(f"Updated in existing MASOC file: {updated_count} rows")
    print(f"Merged new into MASOC file:  {merged_count} rows")
    print(f"Total combined MASOC:    {len(masoc_rows)} rows")
    print(f"MASOC output file:       {masoc_formatted_path}")


if __name__ == "__main__":
    main()
