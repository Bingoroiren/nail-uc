# -*- coding: utf-8 -*-
"""
Script Chuẩn Hóa AutoSlovakia.csv Sang Mẫu Cold Mail Tiêu Chuẩn Workspace:
Header chuẩn 20 cột:
['No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ', 
 'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển', 
 'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply', 
 'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category']
"""

import sys
import os
import re
import csv
import shutil
import urllib.parse
from pathlib import Path

# Đảm bảo UTF-8 cho Windows Console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = ROOT_DIR / "AutoSlovakia.csv"
BACKUP_CSV = ROOT_DIR / "AutoSlovakia_backup.csv"
OUTPUT_COLDMAIL_CSV = ROOT_DIR / "AutoSlovakia_ColdMail.csv"

FIELDNAMES = [
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

CATEGORY_MAP = {
    "Kovovýroba": "Gia công kim loại / Cơ khí chế tạo",
    "Automobily - náhradné dielce": "Phụ tùng & Linh kiện ô tô",
    "Nákladné automobily, autobusy - náhradné dielce": "Phụ tùng xe tải & Xe buýt",
    "Automobily - výroba, úpravy": "Sản xuất & Lắp ráp ô tô",
    "Zámočníctvo, zámočníci": "Cơ khí khóa / Hàn gá kim loại",
    "Strojárenstvo": "Cơ khí chế tạo máy công nghiệp",
    "Reklama - agentúry": "Đại lý quảng cáo & Truyền thông",
    "Automobily - servisy": "Dịch vụ & Sửa chữa ô tô",
    "Hutnícke materiály - predaj": "Kinh doanh vật liệu luyện kim",
    "Klimatizačná technika": "Kỹ thuật điều hòa / Nhiệt lạnh",
    "Reklama - tlač": "In ấn quảng cáo",
    "Plastické hmoty": "Sản xuất & Gia công đồ nhựa",
    "Zvárači": "Dịch vụ thợ hàn kim loại",
    "Prívesy, návesy": "Sản xuất rơ-moóc & Sơ-mi rơ-moóc",
    "Kovy, obrábanie": "Gia công & Tiện phay cắt kim loại",
    "Plachty, autoplachty": "Bạt che xe tải & Công nghiệp",
    "Hydraulika": "Hệ thống thủy lực",
    "Ploty a ohrady": "Sản xuất hàng rào & Cổng kim loại",
    "Kovový tovar": "Hàng kim khí & Phụ kiện kim loại",
    "Drevo - spracovanie": "Chế biến & Sản xuất gỗ",
    "Pneuservisy": "Dịch vụ lốp xe ô tô",
    "Nákladné automobily - doprava a preprava": "Vận tải hàng hóa bằng xe tải",
    "Rúrky, rúry, potrubia": "Sản xuất ống kim loại & Đường ống",
    "Motoristické služby": "Dịch vụ kỹ thuật xe cơ giới",
    "Oceľ, oceľové výrobky": "Thép & Sản phẩm kết cấu thép",
    "Automobily - služby": "Dịch vụ ô tô",
    "Výškové práce": "Thi công xây lắp trên cao",
    "Obchody - zariadenia": "Thiết bị nội thất cửa hàng",
    "Nábytok, čalúnený": "Sản xuất đồ nội thất bọc nệm",
    "Betónové ploty": "Sản xuất hàng rào bê tông",
    "Poľnohospodárska výroba": "Sản xuất nông nghiệp & Cơ khí nông cụ",
    "Reklama - vonkajšia (outdoor)": "Quảng cáo ngoài trời",
    "Autobazáre": "Kinh doanh xe ô tô",
    "Reklama - nápisy, tabule, stojany": "Bảng hiệu & Biển bảng quảng cáo",
    "Kované výrobky": "Sản phẩm sắt mỹ thuật / Rèn đúc kim loại",
    "Rezanie vysokotlakým vodným lúčom": "Cắt kim loại bằng tia nước áp lực cao",
    "Dvere, brány a vráta": "Sản xuất cửa & Cổng tự động",
    "Rolety, markízy": "Sản xuất rèm cuốn & Mái hiên",
    "Drevoobrábacie stroje a zariadenia": "Máy móc & Thiết bị chế biến gỗ",
    "Pečiatky": "Khắc dấu & Tem mác",
    "Úrady krajské, okresné, mestské a obecné": "Cơ quan hành chính địa phương",
    "Zdravotnícka technika a zariadenie": "Thiết bị & Kỹ thuật y tế",
    "Vysokozdvižné a prepravné vozíky, plošiny": "Xe nâng & Thang nâng công nghiệp",
    "Automobily - príslušenstvo a doplnky": "Phụ kiện & Đồ chơi ô tô",
    "Stolári": "Thợ mộc & Gia công gỗ",
    "Stavebné firmy, spoločnosti": "Công ty xây dựng & Thi công",
    "Zimné záhrady": "Thi công nhà kính & Khung nhôm kính",
    "Hasiace prístroje a zariadenia": "Thiết bị phòng cháy chữa cháy",
    "Nábytok": "Sản xuất & Gia công nội thất",
    "Svietidlá, osvetlenie": "Thiết bị chiếu sáng công nghiệp",
    "Export a import": "Xuất nhập khẩu & Thương mại",
    "Etikety, štítky": "In nhãn mác & Tem kim loại",
    "Studniarske práce, studniari": "Thi công khoan giếng & Công trình ngầm",
    "Odťahovacia služba": "Dịch vụ cứu hộ & Kéo xe ô tô",
    "Stavebniny, stavebný materiál": "Vật liệu xây dựng",
    "Piesky, drviny, štrky": "Khai thác cát đá sỏi",
    "Letecké potreby": "Vật tư & Thiết bị hàng không",
    "Obaly": "Sản xuất bao bì & Đóng gói",
    "Kontajnery": "Sản xuất container & Thùng chứa kim loại",
    "Protipožiarna ochrana - zariadenia, služby": "Thiết bị & Dịch vụ PCCC",
    "Školy, súkromné": "Trường đào tạo tư nhân",
    "Modelárstvo, modely": "Gia công mô hình & Khuôn mẫu",
    "Prívesy - opravy": "Sửa chữa rơ-moóc",
    "Automobily - lakovanie": "Sơn xe ô tô",
    "Kozuby": "Sản xuất lò sưởi & Lò đốt kim loại",
    "Stožiare": "Sản xuất cột tháp thép & Cột đèn",
    "Cesty, diaľnice - stavba a údržba": "Xây dựng cầu đường & Hạ tầng giao thông",
    "Okná a okenice": "Sản xuất cửa sổ sổ nhôm kính",
    "Upratovacie služby": "Dịch vụ vệ sinh công nghiệp",
    "Železiarstvo": "Kinh doanh kim khí sắt thép",
    "Hutníctvo": "Luyện kim & Đúc kim loại"
}

BAD_EMAIL_PATTERNS = {
    'wix', 'support', 'no-reply', 'noreply', 'donotreply', 'privacy', 'terms', 'gdpr',
    'test', 'example', 'sentry', 'yourdomain', 'placeholder', 'invalid', 'undefined',
    'tempmail', 'youremail', 'your-email', 'your_email', 'yourname', 'your-name',
    'yourcompany', 'myemail', 'myname', 'sample', 'someone', 'john.doe', 'johndoe',
    'templatemonster', 'themeforest', 'bootstrapmade', 'colorlib', 'nicepage'
}

def score_email_b2b(email, website_domain=""):
    if not email or not isinstance(email, str):
        return -1
    e = email.replace('%20', '').strip().lower().rstrip('.,;:')
    if not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', e):
        return -1
    u, d = e.split('@', 1)

    if any(bad in d for bad in BAD_EMAIL_PATTERNS) or any(bad in u for bad in BAD_EMAIL_PATTERNS):
        return -1
    if u.startswith(('your', 'my')) and any(k in u for k in ['email', 'mail', 'name', 'company', 'domain']):
        return -1
    if u in ['email', 'mail'] and d in ['email.com', 'mail.com', 'domain.com', 'company.com']:
        return -1

    score = 10
    clean_domain = website_domain.lower().replace('www.', '').split('/')[0] if website_domain else ""
    if clean_domain and (clean_domain in d or d in clean_domain):
        score += 50

    # 3. ƯU TIÊN SỐ 1: Nhân sự / Tuyển dụng / Việc làm (+50đ - B2B Agency)
    if u in ['praca', 'kariera', 'hr', 'personalne', 'jobs', 'recruitment', 'nabor', 'zamestnanie', 'career', 'careers', 'talent', 'people', 'rekrutacja']:
        score += 50
    # 4. ƯU TIÊN SỐ 2: Ban Giám đốc / Lãnh đạo điều hành (+45đ)
    elif u in ['vedenie', 'riaditel', 'konatel', 'ceo', 'director', 'manager', 'obchod', 'sales', 'management', 'owner']:
        score += 45
    # 5. ƯU TIÊN SỐ 3: Cổng liên hệ chính thức / Bộ phận thông tin (+40đ)
    elif u in ['info', 'kontakt', 'contact', 'office', 'biuro', 'sekretariat', 'recepcia', 'kancelaria', 'mail']:
        score += 40
    # 6. Email đích danh cá nhân theo domain riêng (+25đ)
    elif '.' in u and score >= 60:
        score += 25
    # 7. Webmail miễn phí (+10đ - chỉ nhận nếu không có mail domain riêng)
    elif d in ['gmail.com', 'seznam.cz', 'zoznam.sk', 'post.sk', 'azet.sk']:
        score += 10
    # 8. Email kỹ thuật / hỗ trợ chung (+5đ)
    elif u in ['support', 'admin', 'help', 'webmaster']:
        score += 5

    return score

def clean_email(email_str, website=""):
    if not email_str:
        return ""
    clean = urllib.parse.unquote(str(email_str)).replace('%20', '').strip().lower()
    clean = clean.rstrip('.,;:/-_')
    domain = urllib.parse.urlparse(website).netloc.lower().replace('www.', '') if website else ""

    parts = [p.strip() for p in re.split(r'[,;\s]+', clean) if p.strip()]
    valid_candidates = [p for p in parts if score_email_b2b(p, domain) > 0]
    if not valid_candidates:
        return ""
    return max(valid_candidates, key=lambda p: score_email_b2b(p, domain))


def format_phone(phone_str):
    if not phone_str:
        return ""
    p = str(phone_str).strip()
    # Bỏ các nháy đơn ở đầu để chuẩn hóa
    while p.startswith("'"):
        p = p[1:].strip()
    if p:
        return f"'{p}"
    return ""

def translate_category(cat_str):
    if not cat_str:
        return "Sản xuất & Dịch vụ kỹ thuật Ô tô / Cơ khí"
    cat_str = cat_str.strip()
    if cat_str in CATEGORY_MAP:
        return CATEGORY_MAP[cat_str]
    
    # Tìm kiếm một phần nếu có nhiều danh mục ghép nhau
    translated_parts = []
    for part in cat_str.split(','):
        part = part.strip()
        translated_parts.append(CATEGORY_MAP.get(part, part))
    return " / ".join(translated_parts)

def main():
    if not INPUT_CSV.exists():
        print(f"[-] Không tìm thấy tệp: {INPUT_CSV}")
        return

    # Backup file gốc trước khi xử lý
    if not BACKUP_CSV.exists():
        shutil.copy2(INPUT_CSV, BACKUP_CSV)
        print(f"[*] Đã tạo bản sao lưu an toàn tại: {BACKUP_CSV.name}")

    with open(INPUT_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        raw_rows = list(reader)

    print(f"[*] Đọc thành công {len(raw_rows)} dòng dữ liệu từ {INPUT_CSV.name}.")

    cleaned_rows = []
    seen_dedup = set()

    for r in raw_rows:
        company = (r.get("Company_Name") or "").strip()
        company = re.sub(r'\s+', ' ', company)
        if not company:
            continue

        website = (r.get("Website") or "").strip()
        email = clean_email(r.get("Email"), website)
        phone = format_phone(r.get("Phone"))
        facebook = (r.get("Facebook_URL") or "").strip()
        detail_url = (r.get("Detail_URL") or "").strip()
        address = (r.get("Full_Address") or "").strip()

        # Xác định Liên hệ và Liên hệ mail
        lien_he = website if website else (facebook if facebook else detail_url)
        lien_he_mail = detail_url if (website or facebook) else ""

        # Khử trùng lặp theo cặp (Company, Address) hoặc (Company, Phone)
        dedup_key = (company.lower(), address.lower(), phone)
        if dedup_key in seen_dedup:
            continue
        seen_dedup.add(dedup_key)

        category_vn = translate_category(r.get("Category"))

        cleaned_rows.append({
            "company": company,
            "phone": phone,
            "lien_he": lien_he,
            "email": email,
            "lien_he_mail": lien_he_mail,
            "address": address,
            "category": category_vn,
            "ico": (r.get("ICO") or "").strip()
        })

    # Tách nhóm có Email lên trước, nhóm không có Email ra sau
    with_email = [r for r in cleaned_rows if r["email"]]
    without_email = [r for r in cleaned_rows if not r["email"]]

    sorted_total = with_email + without_email
    print(f"[*] Phân loại dữ liệu:")
    print(f"    - Có Email (Ưu tiên gửi Cold Mail): {len(with_email):,} công ty")
    print(f"    - Không có Email (Dự phòng gọi điện / thư): {len(without_email):,} công ty")
    print(f"    - Tổng cộng sau khử trùng: {len(sorted_total):,} công ty")

    # Đưa vào cấu trúc 20 cột chuẩn
    output_rows = []
    for idx, r in enumerate(sorted_total, 1):
        output_rows.append({
            "No.": idx,
            "Công ty": r["company"],
            "Chức danh": "",
            "Người liên hệ": "",
            "SĐT": r["phone"],
            "Liên Hệ": r["lien_he"],
            "Email": r["email"],
            "Liên Hệ mail": r["lien_he_mail"],
            "Địa chỉ": r["address"],
            "Lương": "",
            "Ngày đăng": f"Mã DN: {r['ico']}" if r["ico"] else "",
            "Hạn tuyển": "",
            "Check gửi": "",
            "Last Subject": "",
            "Last Body HTML": "",
            "Trạng thái Reply": "",
            "Lần Follow-up": 0,
            "Ngày Follow-up gần nhất": "",
            "Mailbox đã dùng": "",
            "Category": r["category"]
        })

    # Ghi ra file AutoSlovakia_ColdMail.csv
    with open(OUTPUT_COLDMAIL_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"\n[+] XUẤT THÀNH CÔNG: {OUTPUT_COLDMAIL_CSV.name}")
    print(f"[+] Đường dẫn đầy đủ: {OUTPUT_COLDMAIL_CSV}")
    print(f"[+] Tổng số dòng chuẩn Cold Mail: {len(output_rows)}")

if __name__ == '__main__':
    main()
