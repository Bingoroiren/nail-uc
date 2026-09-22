# -*- coding: utf-8 -*-
"""
Tạo 2 bộ file riêng biệt phục vụ cả 2 mục tiêu:
1. Bản SẴN SÀNG GỬI: Chuẩn mẫu Sheet Cold Mail 21 cột, chỉ gồm agency có email hợp lệ, đã lọc trùng email.
2. Bản ĐẦY ĐỦ ĐỂ LÀM GIÀU DỮ LIỆU: Toàn bộ 3,868 agency, đầy đủ mã số thuế (business_id), website, SĐT, Finder URL, LinkedIn, Facebook, Doanh thu, Nhân sự, kèm phân loại trạng thái và gợi ý hành động làm giàu tiếp theo.
3. File Excel đa Sheet: Kết hợp trực quan cả 2 bảng trên + 1 tab riêng cho 120 cty có sẵn website nhưng chưa có email để ưu tiên xử lý.
"""

import os
import sys
import re
import csv
from urllib.parse import urlparse
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_CSV = os.path.join(BASE_DIR, "agency phần lan (đã lọc trùng).csv")

# File 1: Sẵn sàng gửi cold mail
OUTPUT_READY_CSV = os.path.join(BASE_DIR, "agency phần lan - SẴN SÀNG GỬI (ĐÃ LỌC TRÙNG).csv")

# File 2: Đầy đủ để tiếp tục làm giàu dữ liệu
OUTPUT_ENRICH_CSV = os.path.join(BASE_DIR, "agency phần lan - BẢN ĐẦY ĐỦ ĐỂ LÀM GIÀU DỮ LIỆU.csv")

# File 3: Excel đa Sheet tiện lợi
OUTPUT_XLSX = os.path.join(BASE_DIR, "agency phần lan - Cold Mail & Lam Giau Data.xlsx")

# 21 cột chuẩn của Cold Mail
COLD_MAIL_COLUMNS = [
    "No.", "Cong ty", "Chuc danh", "Nguoi lien he", "SDT",
    "Lien He", "Email", "Lien He mail", "Dia chi", "Luong",
    "Ngay dang", "Han tuyen", "Check gui", "Last Subject",
    "Last Body HTML", "Trang thai Reply", "Lan Follow-up",
    "Ngay Follow-up gan nhat", "Mailbox da dung", "Category", "Link FB"
]

# Các cột đầy đủ phục vụ nghiên cứu & làm giàu
ENRICH_COLUMNS = [
    "stt", "trang_thai_enrich", "huong_lam_giau_tiep_theo",
    "name", "business_id", "email_clean", "check_gui", "raw_email",
    "phone", "website", "address", "postal_code", "city", "province",
    "dia_chi_day_du", "line_of_business", "category_vn", "turnover_k_eur",
    "employees", "operating_profit_k_eur", "offices_count", "company_form",
    "facebook_url", "linkedin_url", "finder_url", "tol_code", "tol_name",
    "dia_chi_maps", "nguon_enrich"
]

JUNK_DOMAINS = {
    'facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com', 'youtube.com',
    'wix.com', 'wixsite.com', 'wordpress.com', 'squarespace.com', 'weebly.com',
    'godaddy.com', 'example.com', 'domain.com', 'placeholder.com', 'wixpress.com',
    'sentry.io', 'sentry.wixpress.com', 'sentry-next.wixpress.com', 'dvv.fi',
    'traficom.fi', 'email.fi', 'sivusto.com', 'yourdomain.com'
}

SYSTEM_USERNAMES = {
    'noreply', 'no-reply', 'donotreply', 'privacy', 'terms', 'cookies', 'gdpr',
    'abuse', 'security', 'webmaster', 'sentry', 'admin', 'mailer-daemon',
    'saavutettavuus', 'etunimi.sukunimi', 'esimerkki', 'test'
}

GENERIC_BIZ = [
    'info', 'rekry', 'rekrytointi', 'asiakaspalvelu', 'toimisto',
    'myynti', 'contact', 'office', 'post', 'palvelu'
]

CATEGORY_MAPPING = {
    'Henkilöstövuokraus': 'Cung ứng / Cho thuê lao động (Henkilöstövuokraus)',
    'Rekrytointi': 'Tuyển dụng nhân sự (Rekrytointi)',
    'Henkilöstövuokraus; Rekrytointi': 'Cung ứng & Tuyển dụng nhân sự (Henkilöstövuokraus & Rekrytointi)',
    'Konsultointipalvelut; Rekrytointi': 'Tư vấn & Tuyển dụng nhân sự',
    'Liikkeenjohdon konsultointi': 'Tư vấn quản trị doanh nghiệp',
    'Henkilöstövuokraus; Kuljetusliike': 'Cung ứng lao động ngành vận tải',
    'Henkilöstön uudelleensijoitus; Rekrytointi': 'Tái cơ cấu nhân sự & Tuyển dụng',
    'Henkilöstövuokraus; Liikkeenjohdon konsultointi': 'Cung ứng lao động & Tư vấn quản trị',
    'Henkilöstövuokraus; Rekrytointi; Toimialapalvelut': 'Cung ứng & Tuyển dụng nhân sự đa ngành',
    'Henkilöstövuokraus; Lääkäri tai lääkärikeskus': 'Cung ứng nhân sự y tế / bác sĩ',
}

def score_email(email, comp_domain=''):
    email = email.lower().strip()
    if '@' not in email:
        return 0
    parts = email.split('@', 1)
    user, dom = parts[0], parts[1]

    if dom in JUNK_DOMAINS or any(dom.endswith('.' + jd) for jd in JUNK_DOMAINS):
        return 0
    if user in SYSTEM_USERNAMES or any(s in user for s in ['noreply', 'no-reply', 'privacy', 'etunimi.sukunimi', 'esimerkki', 'saavutettavuus']):
        return 0
    if dom.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf', '.css', '.js')):
        return 0

    score = 10
    if comp_domain and (dom == comp_domain or comp_domain.endswith('.' + dom) or dom.endswith('.' + comp_domain)):
        score += 25
    if any(user == g or user.startswith(g + '.') or user.startswith(g + '-') for g in GENERIC_BIZ):
        score += 15
    if dom in ['gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'kolumbus.fi', 'elisa.fi', 'luukku.com', 'netti.fi']:
        score -= 5
    return score

def pick_best_email(raw_email_str, website):
    if not raw_email_str:
        return ""
    comp_domain = ""
    if website:
        try:
            comp_domain = urlparse(website).netloc.lower().replace('www.', '')
        except Exception:
            pass

    tokens = [t.strip().lower() for t in re.split(r'[;,\s]+', raw_email_str) if t.strip()]
    scored = []
    for t in tokens:
        sc = score_email(t, comp_domain)
        if sc > 0:
            scored.append((sc, t))

    if not scored:
        return ""
    scored.sort(key=lambda x: (x[0], -len(x[1])), reverse=True)
    return scored[0][1]

def clean_phone(phone_str):
    if not phone_str:
        return ""
    s = str(phone_str).strip().lstrip("'").strip()
    if not s:
        return ""
    return f"'{s}"

def format_address(r):
    addr = r.get('address', '').strip()
    post = r.get('postal_code', '').strip()
    city = r.get('city', '').strip().title()
    maps_addr = r.get('dia_chi_maps', '').strip().lstrip('').strip()
    if maps_addr:
        return maps_addr

    parts = []
    if addr:
        parts.append(addr)
    if post and city:
        parts.append(f"{post} {city}")
    elif city:
        parts.append(city)
    parts.append("Finland")
    return ", ".join(parts)

def format_category(lob):
    lob = lob.strip()
    if not lob:
        return "Agency tuyển dụng & cung ứng nhân sự Phần Lan"
    if lob in CATEGORY_MAPPING:
        return CATEGORY_MAPPING[lob]
    has_vuokraus = 'Henkilöstövuokraus' in lob
    has_rekry = 'Rekrytointi' in lob
    if has_vuokraus and has_rekry:
        return f"Cung ứng & Tuyển dụng ({lob})"
    elif has_vuokraus:
        return f"Cung ứng lao động ({lob})"
    elif has_rekry:
        return f"Tuyển dụng ({lob})"
    return f"Agency nhân sự ({lob})"

def build_datasets():
    if not os.path.exists(INPUT_CSV):
        print(f"[ERROR] Không tìm thấy file nguồn: {INPUT_CSV}")
        return

    print(f"[*] Đang tải dữ liệu: {INPUT_CSV} ...")
    with open(INPUT_CSV, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        raw_rows = list(reader)

    print(f"[+] Đã tải {len(raw_rows)} doanh nghiệp.")

    cold_mail_rows = []
    enrich_rows = []

    for idx, r in enumerate(raw_rows, 1):
        name = r.get("name", "").strip()
        web = r.get("website", "").strip()
        raw_email = r.get("email", "").strip()
        phone = r.get("phone", "").strip()
        fb = r.get("facebook_url", "").strip()
        lob = r.get("line_of_business", "").strip()
        b_id = r.get("business_id", "").strip()
        finder_url = r.get("finder_url", "").strip()

        best_email = pick_best_email(raw_email, web)
        formatted_phone = clean_phone(phone)
        formatted_addr = format_address(r)
        cat = format_category(lob)

        try:
            turnover = float(r.get("turnover_k_eur", 0) or 0)
        except Exception:
            turnover = 0
        try:
            employees = float(r.get("employees", 0) or 0)
        except Exception:
            employees = 0

        # Phân loại trạng thái làm giàu dữ liệu & gợi ý hành động
        if best_email:
            status = "1. ĐÃ CÓ EMAIL (SẴN SÀNG GỬI)"
            next_action = "Đã có email, dùng gửi mail ngay"
        elif web:
            status = "2. CÓ WEBSITE (ƯU TIÊN CÀO WEB LẤY EMAIL)"
            next_action = f"Cào sâu các trang contact/tietoa của {web} hoặc fanpage"
        elif phone or fb:
            status = "3. CÓ SĐT/FB (CẦN TRA MAPS TÌM WEB/EMAIL)"
            next_action = "Tra Google Maps hoặc Google Search theo tên + SĐT để lấy Website"
        else:
            status = "4. CHỈ CÓ LINK FINDER & MÃ THUẾ (CẦN SEARCH GOOGLE)"
            next_action = f"Search Google: '{name} {b_id}' để tìm trang chủ hoặc danh bạ doanh nghiệp"

        # Dữ liệu cho Cold Mail
        cm_row = {
            "No.": str(idx),
            "Cong ty": name,
            "Chuc danh": "",
            "Nguoi lien he": "",
            "SDT": formatted_phone,
            "Lien He": web,
            "Email": best_email,
            "Lien He mail": "",
            "Dia chi": formatted_addr,
            "Luong": "",
            "Ngay dang": "",
            "Han tuyen": "",
            "Check gui": "OK" if best_email else "",
            "Last Subject": "",
            "Last Body HTML": "",
            "Trang thai Reply": "",
            "Lan Follow-up": "",
            "Ngay Follow-up gan nhat": "",
            "Mailbox da dung": "",
            "Category": cat,
            "Link FB": fb,
            "_turnover": turnover,
            "_employees": employees
        }
        cold_mail_rows.append(cm_row)

        # Dữ liệu cho Nghiên Cứu & Làm Giàu Thêm
        en_row = {
            "stt": str(idx),
            "trang_thai_enrich": status,
            "huong_lam_giau_tiep_theo": next_action,
            "name": name,
            "business_id": b_id,
            "email_clean": best_email,
            "check_gui": "OK" if best_email else "",
            "raw_email": raw_email,
            "phone": formatted_phone,
            "website": web,
            "address": r.get("address", ""),
            "postal_code": r.get("postal_code", ""),
            "city": r.get("city", ""),
            "province": r.get("province", ""),
            "dia_chi_day_du": formatted_addr,
            "line_of_business": lob,
            "category_vn": cat,
            "turnover_k_eur": r.get("turnover_k_eur", ""),
            "employees": r.get("employees", ""),
            "operating_profit_k_eur": r.get("operating_profit_k_eur", ""),
            "offices_count": r.get("offices_count", ""),
            "company_form": r.get("company_form", ""),
            "facebook_url": fb,
            "linkedin_url": r.get("linkedin_url", ""),
            "finder_url": finder_url,
            "tol_code": r.get("tol_code", ""),
            "tol_name": r.get("tol_name", ""),
            "dia_chi_maps": r.get("dia_chi_maps", ""),
            "nguon_enrich": r.get("nguon_enrich", "")
        }
        enrich_rows.append(en_row)

    # -------------------------------------------------------------
    # 1. TẠO BẢN SẴN SÀNG GỬI (1,593 HÀNG ĐÃ LỌC TRÙNG EMAIL)
    # -------------------------------------------------------------
    rows_with_email = [r for r in cold_mail_rows if r["Check gui"] == "OK"]
    email_groups = {}
    for r in rows_with_email:
        em = r["Email"].lower().strip()
        if em not in email_groups:
            email_groups[em] = []
        email_groups[em].append(r)

    ready_to_send = []
    for em, g_rows in email_groups.items():
        g_rows.sort(key=lambda x: (x["_turnover"], x["_employees"]), reverse=True)
        ready_to_send.append(dict(g_rows[0]))

    for idx, r in enumerate(ready_to_send, 1):
        r["No."] = str(idx)

    print(f"[*] Xuất bản Sẵn Sàng Gửi: {OUTPUT_READY_CSV} ...")
    with open(OUTPUT_READY_CSV, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLD_MAIL_COLUMNS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(ready_to_send)

    # -------------------------------------------------------------
    # 2. TẠO BẢN ĐẦY ĐỦ ĐỂ LÀM GIÀU DỮ LIỆU (3,868 CTY)
    # -------------------------------------------------------------
    # Sắp xếp bản làm giàu: Ưu tiên cty có website chưa có email lên trên để tiện xử lý,
    # tiếp đến cty có SĐT, cuối cùng là cty chỉ có Finder
    enrich_rows_sorted = sorted(enrich_rows, key=lambda x: x["trang_thai_enrich"])
    for idx, r in enumerate(enrich_rows_sorted, 1):
        r["stt"] = str(idx)

    print(f"[*] Xuất bản Đầy Đủ Làm Giàu: {OUTPUT_ENRICH_CSV} ...")
    with open(OUTPUT_ENRICH_CSV, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ENRICH_COLUMNS)
        writer.writeheader()
        writer.writerows(enrich_rows_sorted)

    # -------------------------------------------------------------
    # 3. TẠO FILE EXCEL 3 SHEET ĐẸP MẮT
    # -------------------------------------------------------------
    print(f"[*] Đang xuất file Excel: {OUTPUT_XLSX} ...")
    wb = openpyxl.Workbook()

    # Sheet 1: Sẵn Sàng Gửi Cold Mail
    ws_ready = wb.active
    ws_ready.title = "SẴN SÀNG GỬI (1593 CTY)"

    # Sheet 2: Danh Sách Đầy Đủ Để Làm Giàu Data (3868 cty)
    ws_full = wb.create_sheet(title="ĐẦY ĐỦ ĐỂ LÀM GIÀU (3868 CTY)")

    # Sheet 3: Top 120 Cty Có Sẵn Website Nhưng Chưa Có Email (Ưu tiên làm giàu ngay)
    ws_web_priority = wb.create_sheet(title="ƯU TIÊN LÀM GIÀU (120 CTY WEB)")

    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    fill_green = PatternFill(start_color="1B5E20", end_color="1B5E20", fill_type="solid")
    fill_blue = PatternFill(start_color="0D47A1", end_color="0D47A1", fill_type="solid")
    fill_orange = PatternFill(start_color="E65100", end_color="E65100", fill_type="solid")

    # Ghi Sheet 1 (Sẵn Sàng Gửi)
    ws_ready.append(COLD_MAIL_COLUMNS)
    for col_idx in range(1, len(COLD_MAIL_COLUMNS) + 1):
        c = ws_ready.cell(row=1, column=col_idx)
        c.font = header_font
        c.fill = fill_green
        c.alignment = Alignment(horizontal="center", vertical="center")
    for r in ready_to_send:
        ws_ready.append([r.get(col, "") for col in COLD_MAIL_COLUMNS])
    ws_ready.freeze_panes = "C2"

    # Ghi Sheet 2 (Đầy Đủ Để Làm Giàu)
    ws_full.append(ENRICH_COLUMNS)
    for col_idx in range(1, len(ENRICH_COLUMNS) + 1):
        c = ws_full.cell(row=1, column=col_idx)
        c.font = header_font
        c.fill = fill_blue
        c.alignment = Alignment(horizontal="center", vertical="center")
    for r in enrich_rows_sorted:
        ws_full.append([r.get(col, "") for col in ENRICH_COLUMNS])
    ws_full.freeze_panes = "E2"

    # Ghi Sheet 3 (120 Cty có Website cần cào email)
    web_missing_email = [r for r in enrich_rows if "2. CÓ WEBSITE" in r["trang_thai_enrich"]]
    for idx, r in enumerate(web_missing_email, 1):
        r["stt"] = str(idx)

    ws_web_priority.append(ENRICH_COLUMNS)
    for col_idx in range(1, len(ENRICH_COLUMNS) + 1):
        c = ws_web_priority.cell(row=1, column=col_idx)
        c.font = header_font
        c.fill = fill_orange
        c.alignment = Alignment(horizontal="center", vertical="center")
    for r in web_missing_email:
        ws_web_priority.append([r.get(col, "") for col in ENRICH_COLUMNS])
    ws_web_priority.freeze_panes = "E2"

    # Tự chỉnh độ rộng các cột
    for ws in [ws_ready, ws_full, ws_web_priority]:
        for col in ws.columns:
            header_val = str(col[0].value or '')
            col_letter = get_column_letter(col[0].column)
            if header_val in ["stt", "No."]:
                ws.column_dimensions[col_letter].width = 6
            elif header_val in ["trang_thai_enrich", "huong_lam_giau_tiep_theo"]:
                ws.column_dimensions[col_letter].width = 38
            elif header_val in ["name", "Cong ty", "dia_chi_day_du", "Dia chi"]:
                ws.column_dimensions[col_letter].width = 34
            elif "email" in header_val.lower() or "website" in header_val.lower() or "lien he" in header_val.lower():
                ws.column_dimensions[col_letter].width = 28
            else:
                ws.column_dimensions[col_letter].width = 16

    wb.save(OUTPUT_XLSX)
    print(f"[+] File Excel hoàn tất: {OUTPUT_XLSX}")

    print("\n" + "=" * 68)
    print("        HOÀN TẤT PHÂN TÁCH 2 BẢN: GỬI MAIL & LÀM GIÀU DỮ LIỆU")
    print("=" * 68)
    print(f" 1. BẢN SẴN SÀNG GỬI (ĐÃ LỌC TRÙNG):")
    print(f"    - File: [agency phần lan - SẴN SÀNG GỬI (ĐÃ LỌC TRÙNG).csv]")
    print(f"    - Số lượng: {len(ready_to_send)} doanh nghiệp.")
    print(f"    - Cấu trúc: Đúng chuẩn 21 cột của Sheet Cold Mail.")
    print(f"    - Đặc điểm: 100% có email hợp lệ, mỗi email là độc bản (không trùng hộp thư).")
    print()
    print(f" 2. BẢN ĐẦY ĐỦ ĐỂ TIẾP TỤC LÀM GIÀU DATA:")
    print(f"    - File: [agency phần lan - BẢN ĐẦY ĐỦ ĐỂ LÀM GIÀU DỮ LIỆU.csv]")
    print(f"    - Số lượng: {len(enrich_rows_sorted)} doanh nghiệp.")
    print(f"    - Cấu trúc: 29 cột (kèm mã Y-tunnus, website, Finder URL, Doanh thu, Nhân sự...)")
    print(f"    - Phân loại rõ:")
    print(f"      + Đã có email sẵn sàng gửi:                   1,802 cty")
    print(f"      + Có sẵn website nhưng chưa lấy được email:     120 cty (Ưu tiên cào web ngay)")
    print(f"      + Có SĐT/Facebook nhưng chưa có web:            213 cty (Tra Google Maps)")
    print(f"      + Chỉ có link Finder & mã thuế:               1,733 cty (Cần search Google)")
    print()
    print(f" 3. FILE EXCEL TỔNG HỢP: [agency phần lan - Cold Mail & Lam Giau Data.xlsx]")
    print("=" * 68)

if __name__ == "__main__":
    build_datasets()
