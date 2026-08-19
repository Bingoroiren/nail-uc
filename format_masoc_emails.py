import csv
import os
import shutil
import re
import sys

INPUT_CSV = r"d:\glc\nail uc\masoc_members.csv"
if len(sys.argv) > 1:
    INPUT_CSV = sys.argv[1]

BACKUP_CSV = INPUT_CSV.replace(".csv", "_backup.csv")
FORMATTED_CSV = INPUT_CSV.replace(".csv", "_formatted.csv")
FORMATTED_V2_CSV = INPUT_CSV.replace(".csv", "_formatted_v2.csv")

GENERIC_DOMAINS = {
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'live.com',
    'aol.com', 'icloud.com', 'mail.com', 'ymail.com', 'msn.com',
    'wix.com', 'squarespace.com', 'wordpress.com', 'wixpress.com'
}

BUSINESS_PREFIXES = {
    'info', 'hello', 'contact', 'office', 'admin',
    'sales', 'manager', 'support', 'mail', 'enquiries'
}

BAD_KEYWORDS = {
    'wix', 'no-reply', 'noreply', 'test', 'example', 'domain'
}

# Category: Latvia metalworking / mechanical engineering
CATEGORY_DEFAULT = "Hiệp hội Cơ khí - Gia công kim loại Latvia (MASOC)"


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


def main():
    if not os.path.exists(INPUT_CSV):
        print(f"Error: Input file {INPUT_CSV} does not exist.")
        return

    print(f"[*] Backing up original CSV to {BACKUP_CSV}...")
    shutil.copy2(INPUT_CSV, BACKUP_CSV)

    rows = []
    with open(INPUT_CSV, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    print(f"[+] Loaded {len(rows)} rows.")

    def get_field(r, *keys):
        for k in keys:
            val = r.get(k, '')
            if val is not None and str(val).strip():
                return str(val).strip()
        return ''

    # Step 1: Score emails
    for r in rows:
        original_email = get_field(r, 'email', 'Email')
        r['Best_Email'] = clean_and_score_email(original_email)

    # Step 2: Deduplicate by normalized name
    grouped_rows = {}
    for r in rows:
        raw_name = get_field(r, 'name', 'Name', 'Công ty')
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
            has_web = 1 if get_field(r, 'website', 'Website').strip() else 0
            return (-has_email, -has_web)

        r_list.sort(key=sort_rep)
        deduplicated_rows.append(r_list[0])

    print(f"[+] Deduplicated from {len(rows)} to {len(deduplicated_rows)} unique company names.")

    # Step 3: Deduplicate by email and phone
    seen_emails = set()
    seen_phones = set()

    def normalize_phone(phone_str):
        if not phone_str:
            return ""
        phone_clean = re.sub(r'[^0-9]', '', phone_str)
        if phone_clean.startswith('371'):
            phone_clean = phone_clean[3:]
        return phone_clean

    with_email = []
    without_email = []

    for r in deduplicated_rows:
        email = r['Best_Email']
        if not email:
            continue

        clean_email = email.strip().lower()
        phone = get_field(r, 'phone', 'Phone', 'SĐT')
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

        phone = get_field(r, 'phone', 'Phone', 'SĐT')
        clean_phone = normalize_phone(phone)

        if clean_phone and clean_phone in seen_phones:
            continue

        if clean_phone:
            seen_phones.add(clean_phone)
        without_email.append(r)

    print(f"[+] Found {len(with_email)} rows with email, {len(without_email)} rows without email.")

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
        phone = get_field(r, 'phone', 'Phone', 'SĐT')
        if phone:
            raw_digits = re.sub(r'[^0-9]', '', phone)
            if raw_digits.startswith('371'):
                raw_digits = raw_digits[3:]
            phone = f"'{raw_digits}"
        else:
            phone = ""

        out_row = {
            "No.": i,
            "Công ty": get_field(r, 'name', 'Name', 'Công ty'),
            "Chức danh": "",
            "Người liên hệ": "",
            "SĐT": phone,
            "Liên Hệ": get_field(r, 'website', 'Website', 'Liên Hệ'),
            "Email": r['Best_Email'],
            "Liên Hệ mail": "",
            "Địa chỉ": get_field(r, 'address', 'Address', 'Địa chỉ'),
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
            "Category": CATEGORY_DEFAULT
        }
        output_rows.append(out_row)

    target_write_file = FORMATTED_CSV
    print(f"[*] Writing to {FORMATTED_CSV}...")
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

    print(f"[*] Updating original {INPUT_CSV}...")
    try:
        shutil.copy2(target_write_file, INPUT_CSV)
        print("[SUCCESS] Successfully updated original file!")
    except PermissionError:
        print(f"\n[WARNING] Permission denied updating {INPUT_CSV}. File is open in Excel.")


if __name__ == "__main__":
    main()
