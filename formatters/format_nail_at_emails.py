# -*- coding: utf-8 -*-
"""
CHUẨN HÓA & ĐỊNH DẠNG FILE COLD MAIL TIỆM NAIL ÁO (AT_NAIL_GMAP_2COL.csv)
=============================================================================
Quy chuẩn GEMINI.md & data-standards:
1. Định dạng 20 cột Cold Mail tiêu chuẩn.
2. 100% doanh nghiệp CÓ EMAIL ĐƯỢC ĐẨY LÊN ĐẦU (dòng 1..N).
3. SĐT luôn có dấu nháy đơn (') (+43...).
4. Làm sạch triệt để ký tự lạ (\\u00a0, %20, \\u200b), lọc sạch mail rác.
5. Dịch danh mục tiếng Đức sang tiếng Việt thân thiện.
6. Đồng bộ sang root, csdl_mlt/ và archive/at_austria/.
"""

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
INPUT_1ENR_CSV = os.path.join(ROOT_DIR, "data", "formatted", "AT_NAIL_GMAP_1ENR.csv")
CLEAN_0RAW_CSV = os.path.join(ROOT_DIR, "data", "formatted", "AT_NAIL_GMAP_0RAW_clean.csv")

OUTPUT_FORMATTED_DIR = os.path.join(ROOT_DIR, "data", "formatted")
OUTPUT_COLDMAIL_CSV = os.path.join(OUTPUT_FORMATTED_DIR, "AT_NAIL_GMAP_2COL.csv")
ROOT_COLDMAIL_CSV = os.path.join(ROOT_DIR, "AT_NAIL_GMAP_2COL.csv")
CSDL_COLDMAIL_CSV = os.path.join(ROOT_DIR, "csdl_mlt", "AT_NAIL_GMAP_2COL.csv")
ARCHIVE_COLDMAIL_CSV = os.path.join(ROOT_DIR, "archive", "at_austria", "AT_NAIL_GMAP_2COL.csv")

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

CATEGORY_TRANSLATIONS = {
    "Nagelstudio": "Tiệm nail / Chăm sóc móng (Nagelstudio)",
    "Kosmetikstudio": "Viện thẩm mỹ / Chăm sóc da (Kosmetikstudio)",
    "Schönheitssalon": "Salon làm đẹp (Schönheitssalon)",
    "Fußpflege": "Chăm sóc móng chân / Pedicure (Fußpflege)",
    "Nail salon": "Tiệm nail (Nail salon)",
    "Beauty salon": "Salon làm đẹp (Beauty salon)",
    "Permanent Make-up Studio": "Phun xăm thẩm mỹ (Permanent Make-up)",
    "Kosmetikerin": "Chuyên viên làm đẹp / Kosmetik"
}

def clean_email(email):
    if not email or not isinstance(email, str):
        return ""
    em = urllib.parse.unquote(str(email).strip())
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\u200e', '\u200f', '\ufeff', '\u202f', '\u3000']:
        em = em.replace(bad, '')
    em = re.sub(r'^(?:mailto:|https?://)\s*', '', em, flags=re.I)
    em = re.sub(r'\s+', '', em)
    em = em.strip(" .,;:\"'<>[](){}\\/")
    em = em.lower()

    # Cắt các đuôi website hoặc SĐT bị dính liền
    em = re.sub(r'(\.[a-z]{2,6})www\..*$', r'\1', em, flags=re.I)
    em = re.sub(r'(\.[a-z]{2,6})(?:tel|mob|phone|\+?\d{6,}).*$', r'\1', em, flags=re.I)

    if not re.match(r'^[a-zA-Z0-9._%+-]{1,64}@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}$', em):
        return ""
        
    bad_prefixes = ['youremail', 'your-email', 'yourname', 'someone', 'john.doe', 'example', 'name@', 'email@', 'user@', 'your@', 'yourcompany']
    bad_domains = ['example.com', 'domain.com', 'company.com', 'email.com', 'email', 'sentry.io', 'wixpress.com', 'wordpress.com']
    if any(em.startswith(b) for b in bad_prefixes) or any(em.endswith(b) for b in bad_domains):
        return ""
    return em

def clean_phone(phone):
    if not phone:
        return ""
    p = str(phone).strip()
    if not p.startswith("'"):
        p = f"'{p}"
    return p

def translate_category(cat_str):
    if not cat_str:
        return "Tiệm nail / Chăm sóc móng (Nagelstudio)"
    for de_k, vn_k in CATEGORY_TRANSLATIONS.items():
        if de_k.lower() in cat_str.lower():
            return vn_k
    return cat_str

def format_dataset():
    input_file = INPUT_1ENR_CSV
    if not os.path.exists(input_file):
        if os.path.exists(CLEAN_0RAW_CSV):
            print(f"[*] Chưa có file 1ENR, sử dụng file sạch: {CLEAN_0RAW_CSV}")
            input_file = CLEAN_0RAW_CSV
        else:
            print(f"[ERROR] Không tìm thấy file dữ liệu đầu vào tại {INPUT_1ENR_CSV}!")
            return

    print("=" * 75)
    print("  CHUẨN HÓA DỮ LIỆU TIỆM NAIL ÁO (AT_NAIL) THÀNH FILE COLD MAIL 20 CỘT")
    print(f"  Tệp nguồn: {input_file}")
    print("=" * 75)

    with open(input_file, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"[*] Đã tải {len(rows):,} bản ghi từ file nguồn.")

    formatted_rows = []
    for r in rows:
        name = r.get("Name", "").strip()
        raw_email = r.get("Email", "") or r.get("Emails", "")
        # Nếu có nhiều email phân tách bởi dấu phẩy/chấm phẩy, lấy email đầu tiên hợp lệ
        em = ""
        if raw_email:
            for potential_em in re.split(r'[,;\s]+', str(raw_email)):
                c_em = clean_email(potential_em)
                if c_em:
                    em = c_em
                    break

        phone = clean_phone(r.get("Phone", ""))
        website = r.get("Website", "").strip()
        address = r.get("Address", "").strip()
        cat = translate_category(r.get("Category", ""))

        formatted_rows.append({
            "No.": "",
            "Công ty": name,
            "Chức danh": "",
            "Người liên hệ": "",
            "SĐT": phone,
            "Liên Hệ": website,
            "Email": em,
            "Liên Hệ mail": f"mailto:{em}" if em else "",
            "Địa chỉ": address,
            "Lương": "",
            "Ngày đăng": "",
            "Hạn tuyển": "",
            "Check gửi": "Chưa gửi" if em else "",
            "Last Subject": "",
            "Last Body HTML": "",
            "Trạng thái Reply": "",
            "Lần Follow-up": "",
            "Ngày Follow-up gần nhất": "",
            "Mailbox đã dùng": "",
            "Category": cat
        })

    # PHÂN LOẠI & ĐẨY 100% CÔNG TY CÓ EMAIL LÊN ĐẦU (Rule 3)
    rows_with_email = [r for r in formatted_rows if r["Email"]]
    rows_without_email = [r for r in formatted_rows if not r["Email"]]

    sorted_rows = rows_with_email + rows_without_email

    for idx, r in enumerate(sorted_rows, 1):
        r["No."] = idx

    # Xuất ra các đích đồng bộ
    destinations = [OUTPUT_COLDMAIL_CSV, ROOT_COLDMAIL_CSV, CSDL_COLDMAIL_CSV, ARCHIVE_COLDMAIL_CSV]
    for dest in destinations:
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        with open(dest, mode="w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=COLDMAIL_FIELDNAMES)
            writer.writeheader()
            writer.writerows(sorted_rows)

    print(f"\n[+] TỔNG KẾT BẢN GHI:")
    print(f"  - Tổng số tiệm nail: {len(sorted_rows):,}")
    print(f"  - Số tiệm CÓ EMAIL B2B (đã đẩy lên dòng 1..{len(rows_with_email)}): {len(rows_with_email):,} ({len(rows_with_email)/len(sorted_rows)*100:.1f}%)" if sorted_rows else "  - Không có dữ liệu")
    print(f"  - Số tiệm chưa có email: {len(rows_without_email):,}")
    print(f"  - Xuất thành công tệp Cold Mail 20 cột: {OUTPUT_COLDMAIL_CSV}")
    print(f"  - Đồng bộ tự động sang csdl_mlt/ và archive/at_austria/: HOÀN TẤT!")
    print("=" * 75 + "\n")

if __name__ == "__main__":
    format_dataset()

