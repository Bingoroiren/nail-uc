# -*- coding: utf-8 -*-
"""
CHUYỂN ĐỔI & ĐỊNH DẠNG DỮ LIỆU WKO NAIL ÁO SANG 20 CỘT COLD MAIL CHUẨN
Tệp nguồn: data/AT_NAIL_WKOP_0RAW.csv
Tệp đích:  AT_NAIL_WKOP_2COL.csv & AT_NAIL_WKOP_ONLY_EMAILS_READY.csv
Đồng bộ:   csdl_mlt/ & archive/at_austria/
"""

import sys
import os
import re
import csv
import unicodedata
from pathlib import Path
import pandas as pd

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_RAW_CSV = ROOT_DIR / "data" / "AT_NAIL_WKOP_0RAW.csv"
OUTPUT_COLD_CSV = ROOT_DIR / "AT_NAIL_WKOP_2COL.csv"
OUTPUT_READY_CSV = ROOT_DIR / "AT_NAIL_WKOP_ONLY_EMAILS_READY.csv"

COLDMAIL_COLUMNS = [
    "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ", "Email",
    "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển", "Check gửi",
    "Last Subject", "Last Body HTML", "Trạng thái Reply", "Lần Follow-up",
    "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
]

PERMANENT_BLACKLIST = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta', 'daigre', 'daigrė'
]

def is_blacklisted(name):
    if not name:
        return False
    norm = unicodedata.normalize('NFKD', str(name)).lower()
    clean = ''.join(c for c in norm if not unicodedata.combining(c))
    return any(b in clean for b in PERMANENT_BLACKLIST)

def clean_phone(p):
    if not p or pd.isna(p):
        return ""
    p_str = str(p).replace('\ue0b0', '').replace('\n', '').replace('\r', '').strip().strip("'")
    p_clean = re.sub(r'[^\d+\s]', '', p_str).strip()
    p_clean = re.sub(r'\s+', ' ', p_clean)
    return f"'{p_clean}" if p_clean else ""

def clean_email(email):
    if not email or pd.isna(email) or not isinstance(email, str):
        return ""
    em = email.strip()
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\ufeff', '\u202f', '\u3000']:
        em = em.replace(bad, '')
    em = re.sub(r'^(?:mailto:|https?://)\s*', '', em, flags=re.I)
    em = re.sub(r'\s+', '', em)
    em = em.strip(" .,;:\"'<>[](){}\\/").lower()
    if re.match(r'^[a-zA-Z0-9._%+-]{1,64}@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}$', em):
        return em
    return ""

def format_wko_nail():
    print("=" * 75)
    print("  CHUẨN HÓA DỮ LIỆU WKO NAIL ÁO SANG 20 CỘT COLD MAIL (AT_NAIL_WKOP)")
    print("=" * 75)

    if not INPUT_RAW_CSV.exists():
        alt_input = ROOT_DIR / "AT_NAIL_WKOP_0RAW.csv"
        if alt_input.exists():
            input_path = alt_input
        else:
            print(f"[!] Không tìm thấy file nguồn: {INPUT_RAW_CSV}")
            return
    else:
        input_path = INPUT_RAW_CSV

    df_raw = pd.read_csv(input_path, encoding="utf-8-sig")
    print(f"[*] Đã nạp {len(df_raw):,} bản ghi từ {input_path.name}")

    # Lọc blacklist (Rule 12)
    df_raw = df_raw[~df_raw["name"].apply(is_blacklisted)].copy()

    records = []
    for _, r in df_raw.iterrows():
        comp_name = str(r.get("name", "")).strip()
        street = str(r.get("street", "")).strip() if pd.notna(r.get("street")) else ""
        postal_code = str(r.get("postal_code", "")).strip() if pd.notna(r.get("postal_code")) else ""
        city = str(r.get("city", "")).strip() if pd.notna(r.get("city")) else ""
        state = str(r.get("state", "")).strip() if pd.notna(r.get("state")) else ""

        addr_parts = [p for p in [street, f"{postal_code} {city}".strip(), state, "Austria"] if p]
        full_addr = ", ".join(addr_parts)

        phone = clean_phone(r.get("phone", ""))
        email = clean_email(r.get("email", ""))
        website = str(r.get("website", "")).strip() if pd.notna(r.get("website")) else ""
        detail_url = str(r.get("detail_url", "")).strip() if pd.notna(r.get("detail_url")) else ""
        web_link = website or detail_url

        records.append({
            "No.": 0,
            "Công ty": comp_name,
            "Chức danh": "",
            "Người liên hệ": "",
            "SĐT": phone,
            "Liên Hệ": web_link,
            "Email": email,
            "Liên Hệ mail": f"mailto:{email}" if email else "",
            "Địa chỉ": full_addr,
            "Lương": "",
            "Ngày đăng": "",
            "Hạn tuyển": "",
            "Check gửi": "Chưa gửi" if email else "",
            "Last Subject": "",
            "Last Body HTML": "",
            "Trạng thái Reply": "",
            "Lần Follow-up": "",
            "Ngày Follow-up gần nhất": "",
            "Mailbox đã dùng": "",
            "Category": "Tiệm làm móng (Nagelstudio)"
        })

    df = pd.DataFrame(records)

    # Khử trùng lặp theo tên + thành phố
    df["dedup_key"] = df["Công ty"].str.lower().str.strip() + "_" + df["Địa chỉ"].str.lower().str.strip()
    df = df.drop_duplicates(subset=["dedup_key"], keep="first").copy()
    df.drop(columns=["dedup_key"], inplace=True)

    # Phân loại có email và không có email (Rule 3: 100% email lên đầu dòng 1..N)
    has_em = df[df["Email"] != ""].copy()
    no_em = df[df["Email"] == ""].copy()

    # Khử trùng email
    has_em["clean_em"] = has_em["Email"].str.lower().str.strip()
    has_em = has_em.drop_duplicates(subset=["clean_em"], keep="first").copy()
    has_em.drop(columns=["clean_em"], inplace=True)

    # Ghép lại với email ở đầu
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted["No."] = range(1, len(df_sorted) + 1)

    # Bản chỉ có email
    df_ready = has_em.copy()
    df_ready["No."] = range(1, len(df_ready) + 1)
    df_ready["Check gửi"] = "Chưa gửi"

    def safe_export(dframe, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            dframe.to_csv(path, index=False, encoding="utf-8-sig")
            print(f"  [+] Đã lưu: {path}")
        except PermissionError:
            tmp = path.with_name(f"{path.stem}_updated{path.suffix}")
            dframe.to_csv(tmp, index=False, encoding="utf-8-sig")
            print(f"  [!] File {path.name} đang mở, đã lưu vào: {tmp.name}")

    print("\n[*] Xuất file 2COL (toàn bộ danh mục):")
    for p in [
        OUTPUT_COLD_CSV,
        ROOT_DIR / "data" / "formatted" / "AT_NAIL_WKOP_2COL.csv",
        ROOT_DIR / "csdl_mlt" / "AT_NAIL_WKOP_2COL.csv",
        ROOT_DIR / "archive" / "at_austria" / "AT_NAIL_WKOP_2COL.csv"
    ]:
        safe_export(df_sorted, p)

    print("\n[*] Xuất file ONLY_EMAILS_READY (sẵn sàng Cold Mail):")
    for p in [
        OUTPUT_READY_CSV,
        ROOT_DIR / "csdl_mlt" / "AT_NAIL_WKOP_ONLY_EMAILS_READY.csv",
        ROOT_DIR / "archive" / "at_austria" / "AT_NAIL_WKOP_ONLY_EMAILS_READY.csv"
    ]:
        safe_export(df_ready, p)

    print("\n" + "=" * 75)
    print("  KẾT QUẢ ĐỊNH DẠNG WKO NAIL ÁO:")
    print(f"  - Tổng số tiệm nail WKO hợp lệ : {len(df_sorted):,} tiệm")
    print(f"  - Số tiệm CÓ EMAIL SẴN SÀNG   : {len(df_ready):,} tiệm (dòng 1 đến {len(df_ready)})")
    print(f"  - Tỷ lệ có email trực tiếp    : {len(df_ready)/len(df_sorted)*100:.1f}%")
    print("=" * 75 + "\n")

if __name__ == "__main__":
    format_wko_nail()

