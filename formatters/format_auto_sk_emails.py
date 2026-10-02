import csv
import os
import shutil
import re
import urllib.parse
import sys

# Đảm bảo UTF-8 cho Windows Console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_CSV = os.path.join(ROOT_DIR, "data", "formatted", "SK_AUTO_GMAP_1ENR.csv")
BACKUP_CSV = os.path.join(ROOT_DIR, "data", "formatted", "SK_AUTO_GMAP_1ENR_backup.csv")
FORMATTED_CSV = os.path.join(ROOT_DIR, "data", "formatted", "SK_AUTO_GMAP_2COL.csv")

GENERIC_DOMAINS = {
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'live.com', 
    'aol.com', 'icloud.com', 'mail.com', 'ymail.com', 'msn.com', 
    'wix.com', 'squarespace.com', 'wordpress.com', 'wixpress.com'
}

BUSINESS_PREFIXES = {
    'info', 'hello', 'contact', 'office', 'admin', 'sales', 
    'enquiries', 'manager', 'service', 'sk', 'slovakia', 'auto', 'servis'
}

BAD_KEYWORDS = {
    'wix', 'support', 'no-reply', 'noreply', 'test', 'example', 'domain', 'sentry'
}

SOCIAL_DOMAINS = {
    'facebook.com', 'fb.com', 'fb.me',
    'instagram.com', 'instagr.am',
    'twitter.com', 'x.com',
    'linkedin.com',
    'youtube.com', 'youtu.be',
    'tiktok.com', 'pinterest.com',
    'google.com', 'maps.app.goo.gl',
    'yelp.com', 'yellowpages.com'
}

CATEGORY_TRANSLATIONS = {
    "Továreň na automobily": "Nhà máy sản xuất ô tô",
    "Automobilový servis": "Dịch vụ / Sửa chữa ô tô",
    "Reštaurovanie automobilov": "Phục chế và đại tu ô tô",
    "Dodávateľ hliníkových rámov": "Nhà cung cấp khung nhôm",
    "Autolakovňa": "Xưởng sơn xe ô tô",
    "Výrobca autodielov": "Nhà sản xuất phụ tùng ô tô",
    "Strojná dielňa": "Xưởng cơ khí chế tạo",
    "Kovovýroba": "Gia công kim loại"
}

def clean_email(raw_email):
    if not raw_email:
        return ""
    email = urllib.parse.unquote(str(raw_email)).replace('%20', '').strip().lower().rstrip('.,;:')
    if any(bad in email for bad in BAD_KEYWORDS):
        return ""
    if re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', email):
        return email
    return ""

def format_company_name(name):
    if not name:
        return ""
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def format_data():
    if not os.path.exists(INPUT_CSV):
        print(f"[ERROR] Input file {INPUT_CSV} not found.")
        return

    print(f"[*] Reading and formatting {INPUT_CSV}...")
    shutil.copy2(INPUT_CSV, BACKUP_CSV)

    with open(INPUT_CSV, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames) if reader.fieldnames else []
        rows = list(reader)

    # Ensure necessary columns
    extra_cols = ["Category_VN", "Formatted_Name"]
    for c in extra_cols:
        if c not in fieldnames:
            fieldnames.append(c)

    cleaned_rows = []
    for r in rows:
        # 1. Format Phone with quote
        phone = r.get("Phone", "").strip()
        if phone:
            while phone.startswith("'"):
                phone = phone[1:]
            r["Phone"] = f"'{phone}"
        else:
            r["Phone"] = ""

        # 2. Clean Email
        email = r.get("Email", "").strip()
        r["Email"] = clean_email(email)

        # 3. Clean Name
        r["Formatted_Name"] = format_company_name(r.get("Name", ""))

        # 4. Translate Category
        cat = r.get("Category", "").strip()
        cat_vn = CATEGORY_TRANSLATIONS.get(cat, cat)
        r["Category_VN"] = cat_vn

        cleaned_rows.append(r)

    # Deduplicate by (Name, Address)
    seen_keys = set()
    deduped_rows = []
    for r in cleaned_rows:
        key = (r.get("Name", "").lower(), r.get("Address", "").lower())
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped_rows.append(r)

    # Quy chuẩn Workspace: Luôn đẩy toàn bộ công ty CÓ EMAIL lên đầu danh sách
    with_email = [r for r in deduped_rows if r.get("Email", "").strip()]
    without_email = [r for r in deduped_rows if not r.get("Email", "").strip()]
    final_rows = with_email + without_email

    print(f"[*] Phân loại và sắp xếp dữ liệu:")
    print(f"    - Có Email (Đẩy lên đầu): {len(with_email):,} công ty")
    print(f"    - Không có Email: {len(without_email):,} công ty")
    print(f"    - Tổng cộng: {len(final_rows):,} công ty")

    os.makedirs(os.path.dirname(FORMATTED_CSV), exist_ok=True)
    with open(FORMATTED_CSV, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(final_rows)

    print(f"[SUCCESS] Formatted {len(final_rows)} companies saved to {FORMATTED_CSV}")

    # Đồng bộ sang SK_AUTO_GMAP_2COL.csv ở thư mục gốc
    root_coldmail = os.path.join(ROOT_DIR, "SK_AUTO_GMAP_2COL.csv")
    shutil.copy2(FORMATTED_CSV, root_coldmail)
    print(f"[SUCCESS] Đã đồng bộ sang {root_coldmail}")

if __name__ == "__main__":
    format_data()
