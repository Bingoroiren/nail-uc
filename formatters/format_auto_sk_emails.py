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
OUTPUT_COLDMAIL_CSV = os.path.join(ROOT_DIR, "data", "formatted", "SK_AUTO_GMAP_2COL.csv")
ROOT_COLDMAIL_CSV = os.path.join(ROOT_DIR, "SK_AUTO_GMAP_2COL.csv")
ZLAT_COLDMAIL_CSV = os.path.join(ROOT_DIR, "SK_AUTO_ZLAT_2COL.csv")

COLDMAIL_FIELDNAMES = [
    "No.",
    "Công ty",
    "Chức danh",
    "Người liên hệ",
    "SĐT",
    "Liên Hệ",
    "Email",
    "Liên Hệ mail",
    "Địa chỉ",
    "Lương",
    "Ngày đăng",
    "Hạn tuyển",
    "Check gửi",
    "Last Subject",
    "Last Body HTML",
    "Trạng thái Reply",
    "Lần Follow-up",
    "Ngày Follow-up gần nhất",
    "Mailbox đã dùng",
    "Category"
]

BAD_KEYWORDS = {
    'wix', 'support', 'no-reply', 'noreply', 'test', 'example', 'domain', 'sentry'
}

CATEGORY_TRANSLATIONS = {
    "Továreň na automobily": "Nhà máy sản xuất ô tô",
    "Automobilový servis": "Dịch vụ / Sửa chữa ô tô",
    "Oprava a údržba automobilov": "Sửa chữa và bảo dưỡng ô tô",
    "Pneuservis": "Xưởng lốp xe / Pneuservis",
    "Reštaurovanie automobilov": "Phục chế và đại tu ô tô",
    "Dodávateľ hliníkových rámov": "Nhà cung cấp khung nhôm",
    "Autolakovňa": "Xưởng sơn xe ô tô",
    "Výrobca autodielov": "Nhà sản xuất phụ tùng ô tô",
    "Strojná dielňa": "Xưởng cơ khí chế tạo",
    "Kovovýroba": "Gia công kim loại",
    "Autoumyváreň": "Dịch vụ rửa và chăm sóc xe",
    "Opravovňa nákladných automobilov": "Xưởng sửa chữa xe tải",
    "Opravovňa autoskiel": "Xưởng sửa chữa & thay kính ô tô",
    "Autoelektronický servis": "Xưởng điện lạnh & điện tử ô tô",
    "Servis motocyklov": "Xưởng sửa chữa xe máy / mô tô",
    "Tuning automobilov": "Độ xe & Nâng cấp ô tô"
}

# 1. Danh mục Bán xe / Showroom / Phi ô tô không thuê lao động chân tay
BAD_CATEGORIES = {
    'Predajca automobilov',
    'Obchodník s ojazdenými vozidlami',
    'Automobilový trh',
    'Sprostredkovateľ predaja automobilov',
    'Predaj a lízing automobilov MG',
    'Predaj a lízing automobilov Dacia',
    'Predajca nákladných automobilov',
    'Opravovňa chladničiek',
    'Oprava obuvi',
    'Opravovňa televízorov',
    'Oprava hodiniek',
    'Servis mobilných telefónov',
    'Opravovňa práčok a sušičiek',
    'Výrobca nábytku',
    'Obchod s autorádiami',
    'Dodávateľ autoalarmov',
    'Obchod s autobatériami',
    'Obchod s autopríslušenstvom',
    'Obchod s príslušenstvom pre nákladné automobily',
    'Veľkoobchod s autodoplnkami'
}

DEALER_KEYWORDS = [
    'autobazar', 'autobazár', 'auto-bazar', 'auto - bazar',
    'autosalón', 'autosalon', 'auto salón', 'auto salon',
    'predaj áut', 'predaj aut', 'predaj vozidiel', 'predaj automobilov',
    'dovoz vozidiel', 'dovoz áut', 'dovoz aut',
    'požičovňa áut', 'pozicovna aut', 'autopožičovňa', 'autopozicovna',
    'car rental', 'rent a car', 'rent-a-car',
    'autoškola', 'autoskola', 'auto-škola'
]
DEALER_PATTERN = '|'.join(DEALER_KEYWORDS)

PARTS_CATEGORIES = {
    'Predajňa autodielov',
    'Trh s autodielmi',
    'Bazár náhradných dielov pre automobily',
    'Dodávateľ náhradných dielov karosérie automobilov',
    'Obchod s autodielmi pre pretekárske autá'
}
REPAIR_KEYWORDS = ['servis', 'oprav', 'dielňa', 'dielna', 'pneu', 'lako', 'montáž', 'montaz', 'vrakovisko']
REPAIR_PATTERN = '|'.join(REPAIR_KEYWORDS)

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
    name = re.sub(r'\s+', ' ', str(name)).strip()
    return name

def clean_phone(p):
    p = str(p).strip()
    if not p:
        return ""
    while p.startswith("'"):
        p = p[1:]
    return f"'{p}"

def get_phone_digits(p):
    nums = re.sub(r'[^0-9]', '', str(p))
    return nums[-9:] if len(nums) >= 9 else ''

def get_clean_name(n):
    n = str(n).lower()
    for s in ['s.r.o.', 's. r. o.', 'spol. s r.o.', 'a.s.', 'a. s.', 'v.o.s.', 'k.s.', ',', '.', '-', '"', "'"]:
        n = n.replace(s, ' ')
    return ' '.join(n.split())

def is_unwanted_for_labor(cat, name_clean):
    if cat in BAD_CATEGORIES:
        return True
    if re.search(DEALER_PATTERN, name_clean):
        return True
    if cat in PARTS_CATEGORIES:
        if not re.search(REPAIR_PATTERN, name_clean):
            return True
    return False

def format_data():
    if not os.path.exists(INPUT_CSV):
        print(f"[ERROR] Input file {INPUT_CSV} not found.")
        return

    print(f"[*] Reading {INPUT_CSV}...")
    shutil.copy2(INPUT_CSV, BACKUP_CSV)

    with open(INPUT_CSV, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        raw_rows = list(reader)

    # 1. Đọc dữ liệu ZLAT để loại trừ trùng lặp
    zlat_emails = set()
    zlat_phones = set()
    zlat_names = set()
    if os.path.exists(ZLAT_COLDMAIL_CSV):
        with open(ZLAT_COLDMAIL_CSV, mode="r", encoding="utf-8-sig") as f:
            zlat_reader = csv.DictReader(f)
            for zr in zlat_reader:
                em = clean_email(zr.get("Email", ""))
                ph = get_phone_digits(zr.get("SĐT", ""))
                nm = get_clean_name(zr.get("Công ty", ""))
                if em:
                    zlat_emails.add(em)
                if ph:
                    zlat_phones.add(ph)
                if nm and len(nm) > 6:
                    zlat_names.add(nm)

    # 2. Khử trùng lặp nội bộ, loại bỏ bán xe / phụ tùng, và loại trừ trùng với ZLAT
    seen_internal = set()
    seen_emails = set()
    cleaned_coldmail_rows = []
    dup_zlat_count = 0
    non_labor_count = 0
    no_contact_count = 0

    for r in raw_rows:
        name = format_company_name(r.get("Name", ""))
        phone = clean_phone(r.get("Phone", ""))
        email = clean_email(r.get("Email", ""))
        website = str(r.get("Website", "")).strip()
        map_url = str(r.get("URL", "")).strip()
        address = str(r.get("Address", "")).strip()
        cat = str(r.get("Category", "")).strip()
        cat_vn = CATEGORY_TRANSLATIONS.get(cat, cat)
        name_clean = name.lower()

        # A. Lọc bỏ các doanh nghiệp không thuê lao động chân tay (Bán xe, showroom, cửa hàng bán lẻ phụ tùng)
        if is_unwanted_for_labor(cat, name_clean):
            non_labor_count += 1
            continue

        # B. Lọc bỏ hoàn toàn các cơ sở KHÔNG CÓ THÔNG TIN LIÊN LẠC (Không có Email và Không có SĐT)
        if not email and not phone:
            no_contact_count += 1
            continue

        # C. Khử trùng nội bộ theo (Name, Address)
        int_key = (name_clean, address.lower())
        if int_key in seen_internal:
            continue
        seen_internal.add(int_key)

        # D. Loại trừ nếu trùng ZLAT
        ph_digits = get_phone_digits(phone)
        cl_name = get_clean_name(name)
        if (email and email in zlat_emails) or (ph_digits and ph_digits in zlat_phones) or (cl_name and cl_name in zlat_names and len(cl_name) > 6):
            dup_zlat_count += 1
            continue

        # E. Khử trùng email nội bộ (mỗi email chỉ giữ 1 doanh nghiệp duy nhất)
        if email:
            if email in seen_emails:
                email = "" # Xóa email ở chi nhánh phụ để tránh gửi spam, vẫn giữ lại SĐT
            else:
                seen_emails.add(email)

        # Map vào 20 cột chuẩn Cold Mail
        lien_he = website if website else map_url
        lien_he_mail = map_url if website else ""

        cleaned_coldmail_rows.append({
            "No.": "",
            "Công ty": name,
            "Chức danh": "",
            "Người liên hệ": "",
            "SĐT": phone,
            "Liên Hệ": lien_he,
            "Email": email,
            "Liên Hệ mail": lien_he_mail,
            "Địa chỉ": address,
            "Lương": "",
            "Ngày đăng": "",
            "Hạn tuyển": "",
            "Check gửi": "",
            "Last Subject": "",
            "Last Body HTML": "",
            "Trạng thái Reply": "",
            "Lần Follow-up": "",
            "Ngày Follow-up gần nhất": "",
            "Mailbox đã dùng": "",
            "Category": cat_vn
        })

    print(f"[*] Báo cáo lọc dữ liệu:")
    print(f"    - Đã loại trừ {non_labor_count} cửa hàng bán xe, showroom, phụ tùng bán lẻ.")
    print(f"    - Đã loại trừ {no_contact_count} cơ sở không có thông tin liên lạc.")
    print(f"    - Đã loại trừ {dup_zlat_count} công ty trùng lặp với danh sách Zlaté Stránky.")

    # 3. Sắp xếp: Đẩy 100% công ty CÓ EMAIL lên đầu
    with_email = [r for r in cleaned_coldmail_rows if r["Email"]]
    without_email = [r for r in cleaned_coldmail_rows if not r["Email"]]
    sorted_coldmail_rows = with_email + without_email

    # 4. Đánh số No. từ 1 đến N
    for i, r in enumerate(sorted_coldmail_rows, start=1):
        r["No."] = str(i)

    print(f"[*] Dữ liệu Cold Mail 20 cột hoàn thiện:")
    print(f"    - Có Email độc bản (Xếp đầu dòng 1 đến {len(with_email)}): {len(with_email):,} công ty")
    print(f"    - Có SĐT để gọi (Xếp sau): {len(without_email):,} công ty")
    print(f"    - Tổng cộng: {len(sorted_coldmail_rows):,} công ty")

    # 5. Ghi file Cold Mail 20 cột
    os.makedirs(os.path.dirname(OUTPUT_COLDMAIL_CSV), exist_ok=True)
    with open(OUTPUT_COLDMAIL_CSV, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLDMAIL_FIELDNAMES)
        writer.writeheader()
        writer.writerows(sorted_coldmail_rows)

    print(f"[SUCCESS] Đã lưu file chuẩn 20 cột: {OUTPUT_COLDMAIL_CSV}")

    # Đồng bộ sang SK_AUTO_GMAP_2COL.csv ở thư mục gốc
    shutil.copy2(OUTPUT_COLDMAIL_CSV, ROOT_COLDMAIL_CSV)
    print(f"[SUCCESS] Đã đồng bộ sang: {ROOT_COLDMAIL_CSV}")

if __name__ == "__main__":
    format_data()
