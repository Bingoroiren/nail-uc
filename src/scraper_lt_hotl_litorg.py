# -*- coding: utf-8 -*-
"""
LITORG.CC SCRAPER - LITHUANIAN HOTELS & ACCOMMODATION (NACE 55)
=============================================================================
Target  : https://litorg.cc/en/catalog/55/
Scope   : NACE 55 (Accommodation - Hotels, Short-stay, Camping, Lodging)
Country : Lithuania (LT) | Industry: Hotels & Accommodation (HOTL) | Source: Litorg (LTOR)

Catalog Details:
  - Base URL : https://litorg.cc/en/catalog/55/
  - Total    : 1,292 companies across 26 pages (50 per page, 42 on page 26)
  - Subcategories included:
      * 55.1 / 55.10 Hotels and similar accommodation
      * 55.2 / 55.20 Holiday and other short-stay accommodation
      * 55.3 / 55.30 Camping grounds and recreational vehicle parks
      * 55.4 / 55.40 Intermediation service activities for accommodation
      * 55.9 / 55.90 Other accommodation

Outputs (UTF-8 with BOM - utf-8-sig):
  - LT_HOTL_LTOR_0RAW.csv (Raw catalog dataset with registration codes & financials)
  - LT_HOTL_LTOR_2COL.csv (Standard 20-column Cold Mail format)
  - Synced to root, csdl_mlt/, and archive/lt_lithuania/
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import shutil
import sys
import time
import unicodedata
import urllib.parse
from pathlib import Path

import curl_cffi.requests as requests
import pandas as pd
from bs4 import BeautifulSoup

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent
CSDL_DIR = ROOT_DIR / "csdl_mlt"
ARCHIVE_DIR = ROOT_DIR / "archive" / "lt_lithuania"
CRAWLMAIL_DIR = ROOT_DIR / "crawlmail"
CACHE_FILE = CRAWLMAIL_DIR / "cache_scraper_litorg_hotel.json"

RAW_FILENAME = "LT_HOTL_LTOR_0RAW.csv"
COLDMAIL_FILENAME = "LT_HOTL_LTOR_2COL.csv"

OUTPUT_0RAW_PATH = ROOT_DIR / RAW_FILENAME
OUTPUT_2COL_PATH = ROOT_DIR / COLDMAIL_FILENAME

BASE_CATALOG_URL = "https://litorg.cc/en/catalog/55/"
TOTAL_CATALOG_PAGES = 26

PERMANENT_BLACKLIST_COMPANIES = (
    "scandi standard",
    "scandi-standard",
    "scandi standart",
    "biliarta",
    "daigre",
    "daigrė",
)

RAW_COLUMNS = [
    "No.",
    "Company_Code",
    "Cong ty",
    "City",
    "Nam_Thanh_Lap",
    "Category",
    "Catalog_ID",
    "Catalog_Name",
    "Doanh_Thu",
    "Loi_Nhuan",
    "Bien_Loi_Nhuan",
    "So_Nhan_Vien",
    "Detail_URL",
    "SDT",
    "Website",
    "Email",
    "Dia chi",
]

COLDMAIL_COLUMNS = [
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
    "Category",
]


def clean_text(val) -> str:
    """Normalize text, replace non-breaking spaces and strip excess whitespace."""
    if val is None or pd.isna(val):
        return ""
    text = str(val)
    for bad in ("\u00a0", "\xa0", "&nbsp;", "\u200b", "\ufeff"):
        text = text.replace(bad, " ")
    return re.sub(r"\s+", " ", text).strip()


def is_blacklisted_company(name: str) -> bool:
    """Rule 12: Permanent company blacklist with Unicode NFKD accent folding."""
    if not name:
        return False
    norm = unicodedata.normalize("NFKD", str(name)).lower()
    clean = "".join(c for c in norm if not unicodedata.combining(c))
    return any(b in clean for b in PERMANENT_BLACKLIST_COMPANIES)


def clean_phone_lt(phone_str: str) -> str:
    """Normalize Lithuanian phone numbers and prefix with apostrophe (Rule 2)."""
    if not phone_str or str(phone_str).lower() == "nan":
        return ""
    raw = str(phone_str).strip().lstrip("'")
    digits = re.sub(r"[^\d+]", "", raw)
    if not digits:
        return ""
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    elif digits.startswith("8") and len(digits) == 9:
        digits = "+370" + digits[1:]
    elif digits.startswith("6") and len(digits) == 8:
        digits = "+370" + digits
    elif digits.startswith("370") and not digits.startswith("+"):
        digits = "+" + digits
    return f"'{digits}"


def clean_email(email_str: str) -> str:
    """Clean email string, decoding URL encoding and removing non-breaking spaces (Rule 3)."""
    if not email_str or str(email_str).lower() == "nan":
        return ""
    s = urllib.parse.unquote(str(email_str)).strip().lower()
    for bad in ("\u00a0", "\xa0", "&nbsp;", "%20", "\u200b", "\ufeff", " "):
        s = s.replace(bad, "")
    if s.startswith("20") and "@" in s and not s.startswith("202"):
        s = s[2:]
    s = s.strip(".,;:'\"<>[]()")
    if "@" not in s or "." not in s.split("@")[-1]:
        return ""
    return s


def parse_litorg_html_page(html_text: str) -> list[dict]:
    """Extract all company cards (li.fl-item) from a litorg.cc catalog page."""
    soup = BeautifulSoup(html_text, "html.parser")
    items = soup.select("li.fl-item")
    records = []

    for item in items:
        h3_a = item.select_one("h3 a")
        if not h3_a:
            continue

        name = clean_text(h3_a.get_text())
        if not name or is_blacklisted_company(name):
            continue

        href = (h3_a.get("href") or "").strip()
        detail_url = f"https://litorg.cc{href}" if href and not href.startswith("http") else href

        metas = item.select("div.fl-meta")
        company_code = ""
        city = ""
        year = ""
        category = ""

        if len(metas) >= 1:
            parts = [clean_text(p) for p in metas[0].get_text().split("·")]
            if len(parts) >= 1 and parts[0].isdigit():
                company_code = parts[0]
            if len(parts) >= 2:
                city = parts[1]
            if len(parts) >= 3:
                m_yr = re.search(r"(?:since|nuo)\s+(\d{4})", parts[2], re.IGNORECASE)
                if m_yr:
                    year = m_yr.group(1)

        if not company_code and href:
            m_code = re.search(r"/company/(\d+)/", href)
            if m_code:
                company_code = m_code.group(1)

        if len(metas) >= 2:
            category = clean_text(metas[1].get_text())

        rev_el = item.select_one("div.c-rev b")
        prof_el = item.select_one("div.c-profit b")
        marg_el = item.select_one("div.c-margin b")
        emp_el = item.select_one("div.c-emp b")

        records.append(
            {
                "Company_Code": company_code,
                "Cong ty": name,
                "City": city,
                "Nam_Thanh_Lap": year,
                "Category": category or "NACE 55 Accommodation",
                "Catalog_ID": "55",
                "Catalog_Name": "Accommodation",
                "Doanh_Thu": clean_text(rev_el.get_text()) if rev_el else "",
                "Loi_Nhuan": clean_text(prof_el.get_text()) if prof_el else "",
                "Bien_Loi_Nhuan": clean_text(marg_el.get_text()) if marg_el else "",
                "So_Nhan_Vien": clean_text(emp_el.get_text()) if emp_el else "",
                "Detail_URL": detail_url,
                "SDT": "",
                "Website": "",
                "Email": "",
                "Dia chi": f"{city}, Lithuania" if city else "Lithuania",
            }
        )

    return records


def record_key(rec: dict) -> str:
    """Unique key by registration code or normalized company name."""
    code = clean_text(rec.get("Company_Code"))
    if code:
        return code
    return clean_text(rec.get("Cong ty")).lower()


def load_cache() -> dict[str, dict]:
    """Load cached companies from checkpoint JSON."""
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception as e:
            print(f"[WARN] Error loading cache: {e}")
    return {}


def save_cache(all_companies: dict[str, dict]) -> None:
    """Save checkpoint JSON atomically."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = CACHE_FILE.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(all_companies, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, CACHE_FILE)


def export_and_sync_all_files(all_records: list[dict]) -> tuple[int, int]:
    """
    Export 0RAW and 2COL CSVs and sync to csdl_mlt/ and archive/lt_lithuania/.
    Sorts companies with email first according to Rule 3.
    """
    clean_records = []
    for rec in all_records:
        if is_blacklisted_company(rec.get("Cong ty", "")):
            continue
        item = dict(rec)
        item["SDT"] = clean_phone_lt(item.get("SDT", ""))
        item["Email"] = clean_email(item.get("Email", ""))
        clean_records.append(item)

    raw_rows = []
    for idx, rec in enumerate(clean_records, start=1):
        row = {col: rec.get(col, "") for col in RAW_COLUMNS}
        row["No."] = idx
        raw_rows.append(row)

    df_raw = pd.DataFrame(raw_rows, columns=RAW_COLUMNS)

    # Build Cold Mail 20-column rows
    with_email = []
    without_email = []

    for r in clean_records:
        comp_name = clean_text(r.get("Cong ty", ""))
        phone_val = clean_phone_lt(r.get("SDT", ""))
        email_val = clean_email(r.get("Email", ""))
        web_val = clean_text(r.get("Website", ""))
        durl = clean_text(r.get("Detail_URL", ""))
        city_val = clean_text(r.get("City", ""))
        addr_val = clean_text(r.get("Dia chi", "")) or (f"{city_val}, Lithuania" if city_val else "Lithuania")

        cat_desc = clean_text(r.get("Category", ""))
        emp_str = clean_text(r.get("So_Nhan_Vien", ""))
        rev_str = clean_text(r.get("Doanh_Thu", ""))

        category_tag = f"{cat_desc} | Empl: {emp_str}" if emp_str else cat_desc

        row_2c = {
            "No.": "",
            "Công ty": comp_name,
            "Chức danh": "Vadovas / Viešbučio Vadovas",
            "Người liên hệ": "Vadovas",
            "SĐT": phone_val,
            "Liên Hệ": web_val if web_val else durl,
            "Email": email_val,
            "Liên Hệ mail": f"mailto:{email_val}" if email_val else web_val,
            "Địa chỉ": addr_val,
            "Lương": rev_str,
            "Ngày đăng": clean_text(r.get("Nam_Thanh_Lap", "")),
            "Hạn tuyển": f"Darbuotojai: {emp_str}" if emp_str else "",
            "Check gửi": "Chưa gửi",
            "Last Subject": "",
            "Last Body HTML": "",
            "Trạng thái Reply": "",
            "Lần Follow-up": "",
            "Ngày Follow-up gần nhất": "",
            "Mailbox đã dùng": "",
            "Category": category_tag,
        }

        if email_val:
            with_email.append(row_2c)
        else:
            without_email.append(row_2c)

    combined = with_email + without_email
    for idx, row in enumerate(combined, start=1):
        row["No."] = idx

    df_2col = pd.DataFrame(combined, columns=COLDMAIL_COLUMNS)

    # Save to root, csdl_mlt, archive/lt_lithuania
    target_dirs = [ROOT_DIR, CSDL_DIR, ARCHIVE_DIR]
    for folder in target_dirs:
        folder.mkdir(parents=True, exist_ok=True)
        try:
            df_raw.to_csv(folder / RAW_FILENAME, index=False, encoding="utf-8-sig")
            df_2col.to_csv(folder / COLDMAIL_FILENAME, index=False, encoding="utf-8-sig")
        except Exception as e:
            print(f"[WARN] Failed to write to {folder}: {e}")

    return len(df_raw), len(with_email)


def fetch_page_fast(session: requests.Session, url: str, retries: int = 4) -> str | None:
    """Fetch HTML using curl_cffi with impersonated Chrome headers and exponential backoff."""
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, timeout=15)
            if r.status_code == 200:
                return r.text
            elif r.status_code == 429:
                wait_sec = min(5 * attempt, 30)
                print(f" [Rate-limit 429: wait {wait_sec}s] ", end="", flush=True)
                time.sleep(wait_sec)
            elif r.status_code in (500, 502, 503, 504):
                time.sleep(2 * attempt)
            elif r.status_code == 404:
                return None
        except Exception as e:
            if attempt == retries:
                print(f" [Network err: {e}] ", end="", flush=True)
            time.sleep(1.5 * attempt)
    return None


def run_scraper(start_page: int = 1, max_pages_arg: int | None = None, reset_cache: bool = False) -> None:
    """Execute scraping of NACE 55 across all catalog pages."""
    print("=" * 80)
    print("LITORG.CC SCRAPER - LITHUANIAN HOTELS & ACCOMMODATION (NACE 55)")
    print("Mục tiêu: Khách sạn, resort, căn hộ du lịch & dịch vụ lưu trú tại Litva")
    print(f"Nguồn cào: {BASE_CATALOG_URL} (Tổng cộng {TOTAL_CATALOG_PAGES} trang, ~1,292 công ty)")
    print(f"Đầu ra   : {OUTPUT_0RAW_PATH.name} & {OUTPUT_2COL_PATH.name}")
    print("=" * 80 + "\n")

    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    all_companies = {} if reset_cache else load_cache()

    if all_companies:
        print(f"[*] Đã nạp sẵn {len(all_companies):,} công ty từ checkpoint cache.")

    session = requests.Session(impersonate="chrome120")

    effective_max_pages = min(TOTAL_CATALOG_PAGES, max_pages_arg) if max_pages_arg else TOTAL_CATALOG_PAGES

    for p in range(max(1, start_page), effective_max_pages + 1):
        page_url = f"{BASE_CATALOG_URL}?page={p}" if p > 1 else BASE_CATALOG_URL
        print(f"[{p:2d}/{effective_max_pages:2d}] Trang {p:2d}/{effective_max_pages:2d}: {page_url} ...", end=" ", flush=True)

        html = fetch_page_fast(session, page_url)
        if not html:
            print("❌ LỖI TẢI TRANG!")
            continue

        records = parse_litorg_html_page(html)
        if not records:
            print("⚠ 0 cards (Có thể đã hết danh sách hoặc bị chặn)")
            continue

        new_added = 0
        for r in records:
            k = record_key(r)
            if k not in all_companies:
                all_companies[k] = r
                new_added += 1
            else:
                curr_cat = all_companies[k].get("Category", "")
                new_cat = r.get("Category", "")
                if new_cat and new_cat not in curr_cat:
                    all_companies[k]["Category"] = f"{curr_cat}; {new_cat}"

        print(f"✅ {len(records):2d} cty (+{new_added:2d} mới | Tổng: {len(all_companies):,})")

        # Checkpoint save on every page
        if new_added > 0:
            save_cache(all_companies)
            export_and_sync_all_files(list(all_companies.values()))

        # Gentle human-like delay
        time.sleep(random.uniform(0.35, 0.75))

    # Final save and export
    save_cache(all_companies)
    total_cnt, has_em = export_and_sync_all_files(list(all_companies.values()))

    print("\n" + "=" * 80)
    print("🏆 HOÀN THÀNH TIẾN TRÌNH CÀO KHÁCH SẠN & LƯU TRÚ LITVA (NACE 55)!")
    print(f"  Tổng số doanh nghiệp thu thập : {total_cnt:,}")
    print(f"  Tệp dữ liệu thô (0RAW)        : {OUTPUT_0RAW_PATH.name}")
    print(f"  Tệp Cold Mail (2COL)          : {OUTPUT_2COL_PATH.name}")
    print(f"  Đã đồng bộ sang               : csdl_mlt/ & archive/lt_lithuania/")
    print("=" * 80 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Lithuanian Hotels & Accommodation (NACE 55) from litorg.cc")
    parser.add_argument("--start-page", type=int, default=1, help="Start catalog page number (default: 1)")
    parser.add_argument("--max-pages", type=int, default=None, help="Optional max pages override")
    parser.add_argument("--reset-cache", action="store_true", help="Reset cache and scrape fresh")
    args = parser.parse_args()

    run_scraper(
        start_page=args.start_page,
        max_pages_arg=args.max_pages,
        reset_cache=args.reset_cache,
    )


if __name__ == "__main__":
    main()
