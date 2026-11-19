# -*- coding: utf-8 -*-
"""
LITORG.CC SCRAPER - LITHUANIAN AGRICULTURE, FARMING & CROPS (NACE DIVISION 01)
=============================================================================
Target  : https://litorg.cc/en/catalog/01/
Scope   : NACE 01 - Crop and animal production, hunting and related service activities
Country : Lithuania (LT) | Industry: Agriculture & Farming (FARM) | Source: Litorg (LTOR)

Strict adherence to GEMINI.md workspace rules:
1. CSV ONLY (Rule 1): UTF-8 with BOM (utf-8-sig), absolutely NO .xlsx/.xls.
2. Phone prefix (Rule 2): Lithuanian phone formatted strictly with leading single quote: phone = f"'{phone}".
3. Email cleaning & B2B Cold Mail selection (Rule 3):
   - Strict filter for junk/template/theme placeholder emails.
   - Decodes %20, \u00a0, \xa0, &nbsp;, zero-width space.
   - Exactly 1 optimal email per company.
   - 100% companies with email pushed to top of Cold Mail output.
4. Visual browser & Cloudflare management (Rule 4):
   - Native Chrome CDP connection on port 9222 (1280x800).
   - Auto-launches Chrome if not running, sounds alert bell '\a' if Cloudflare gate appears.
5. Incremental Auto-Save & Atomic Checkpoint (Rule 5):
   - Real-time append to RAW CSV with flush().
   - Atomic cache JSON (cache_scraper_litorg_farm.json) for 100% resume capability.
6. 17-Character Fixed Filenames (Rule 10):
   - LT_FARM_LTOR_0RAW.csv (Raw catalog dataset with registration codes & financials)
   - LT_FARM_LTOR_2COL.csv (Standard 20-column Cold Mail format)
   - LT_FARM_LTOR_ONLY_EMAILS_READY.csv (Filter of companies with valid email)
   - Synchronized to root, csdl_mlt/, and archive/lt_lithuania/
7. Permanent Blacklist Exclusion (Rule 12):
   - Excludes Scandi Standard Baltics, Biliarta, Daigre / Daigrė.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import urllib.parse
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# Configure UTF-8 console output for Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent
CSDL_DIR = ROOT_DIR / "csdl_mlt"
ARCHIVE_DIR = ROOT_DIR / "archive" / "lt_lithuania"
CRAWLMAIL_DIR = ROOT_DIR / "crawlmail"
CACHE_FILE = CRAWLMAIL_DIR / "cache_scraper_litorg_farm.json"
USER_DATA_DIR = ROOT_DIR / "chrome_user_data" / "native_chrome"

CATALOG_ID = "01"
CATALOG_NAME = "Crop and animal production, hunting and related service activities"
BASE_CATALOG_URL = "https://litorg.cc/en/catalog/01/"

RAW_FILENAME = "LT_FARM_LTOR_0RAW.csv"
COLDMAIL_FILENAME = "LT_FARM_LTOR_2COL.csv"
EMAILS_READY_FILENAME = "LT_FARM_LTOR_ONLY_EMAILS_READY.csv"

OUTPUT_0RAW_PATH = ROOT_DIR / RAW_FILENAME
OUTPUT_2COL_PATH = ROOT_DIR / COLDMAIL_FILENAME
OUTPUT_READY_PATH = ROOT_DIR / EMAILS_READY_FILENAME

PERMANENT_BLACKLIST_COMPANIES = (
    "scandi standard",
    "scandi-standard",
    "scandi standart",
    "biliarta",
    "daigre",
    "daigrė",
)

JUNK_EMAIL_PREFIXES = (
    "youremail",
    "your-email",
    "yourname",
    "yourcompany",
    "someone",
    "john.doe",
    "user@",
    "name@",
    "example@",
    "domain@",
    "email@email",
    "sentry",
    "wix",
    "no-reply",
    "noreply",
    "donotreply",
    "privacy@",
    "gdpr@",
)

JUNK_EMAIL_DOMAINS = (
    "yourdomain.com",
    "example.com",
    "wixpress.com",
    "wordpress.com",
    "sentry.io",
    "localservices.be",
    "bizbook.be",
    "pagesdor.be",
    "goudengids.be",
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
    """Rule 12: Permanent company blacklist exclusion with Unicode NFKD accent folding."""
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
    elif not digits.startswith("+"):
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
    if any(s.startswith(p) for p in JUNK_EMAIL_PREFIXES):
        return ""
    domain = s.split("@")[-1]
    if any(d in domain for d in JUNK_EMAIL_DOMAINS):
        return ""
    if not re.match(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$", s):
        return ""
    return s


def is_cloudflare_gate(title: str, html_text: str) -> bool:
    """Detect whether current page shows Cloudflare verification gate."""
    t_low = (title or "").lower()
    h_low = (html_text or "").lower()
    return (
        "just a moment" in t_low
        or "verify you are human" in h_low
        or "cf-turnstile" in h_low
        or "cloudflare" in t_low and "challenge" in h_low
    )


def detect_max_page(soup: BeautifulSoup) -> int:
    """Extract highest catalog page number from pagination links."""
    max_p = 1
    for a in soup.select(".pagination a, .pager a, nav a, ul.pagination li a"):
        href = a.get("href", "")
        txt = clean_text(a.get_text())
        m = re.search(r"[?&]page=(\d+)", href)
        if m:
            max_p = max(max_p, int(m.group(1)))
        elif txt.isdigit():
            max_p = max(max_p, int(txt))
    return max_p


def parse_litorg_html_page(html_text: str, page_title: str = "") -> tuple[list[dict], int, bool]:
    """
    Extract all company cards (li.fl-item) from a litorg.cc catalog page.
    Returns: (records, detected_max_page, is_gated)
    """
    soup = BeautifulSoup(html_text, "html.parser")
    items = soup.select("li.fl-item")

    if not items and is_cloudflare_gate(page_title, html_text):
        return [], 1, True

    max_p = detect_max_page(soup)
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
                "Category": category or f"NACE {CATALOG_ID} {CATALOG_NAME}",
                "Catalog_ID": CATALOG_ID,
                "Catalog_Name": CATALOG_NAME,
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

    return records, max_p, False


def record_key(rec: dict) -> str:
    """Stable deduplication key by registration code or normalized company name."""
    code = clean_text(rec.get("Company_Code"))
    if code:
        return code
    return clean_text(rec.get("Cong ty")).lower()


def load_cache() -> dict:
    """Load cached state and records from checkpoint JSON."""
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "records" in data:
                data.setdefault("completed_pages", [])
                data.setdefault("max_page", 1)
                return data
            if isinstance(data, dict):
                return {"completed_pages": [], "max_page": 1, "records": data}
        except Exception as e:
            print(f"[WARN] Error reading cache file: {e}")
    return {"completed_pages": [], "max_page": 1, "records": {}}


def save_cache(state: dict) -> None:
    """Atomically save checkpoint JSON to disk."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = CACHE_FILE.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, CACHE_FILE)


def append_raw_incremental(rows: list[dict], start_no: int) -> None:
    """Incrementally append newly parsed rows to root RAW CSV with immediate disk flush."""
    if not rows:
        return
    raw_path = OUTPUT_0RAW_PATH
    file_exists = raw_path.exists() and raw_path.stat().st_size > 0
    mode = "a" if file_exists else "w"
    with open(raw_path, mode, encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RAW_COLUMNS)
        if not file_exists:
            writer.writeheader()
        for idx, rec in enumerate(rows, start=start_no):
            out = {col: rec.get(col, "") for col in RAW_COLUMNS}
            out["No."] = idx
            writer.writerow(out)
        f.flush()


def build_coldmail_rows(raw_records: list[dict]) -> tuple[list[dict], int]:
    """
    Build 20-column Cold Mail rows adhering to Rule 3:
    100% of records with valid Email are pushed to the top.
    Returns: (combined_rows, email_count)
    """
    with_email = []
    without_email = []

    for rec in raw_records:
        comp_name = clean_text(rec.get("Cong ty", ""))
        if is_blacklisted_company(comp_name):
            continue

        phone_val = clean_phone_lt(rec.get("SDT", ""))
        email_val = clean_email(rec.get("Email", ""))
        web_val = clean_text(rec.get("Website", ""))
        durl = clean_text(rec.get("Detail_URL", ""))
        city_val = clean_text(rec.get("City", ""))
        addr_val = clean_text(rec.get("Dia chi", "")) or (f"{city_val}, Lithuania" if city_val else "Lithuania")

        cat_desc = clean_text(rec.get("Category", ""))
        emp_str = clean_text(rec.get("So_Nhan_Vien", ""))
        rev_str = clean_text(rec.get("Doanh_Thu", ""))
        category_tag = f"{cat_desc} | Empl: {emp_str}" if emp_str else cat_desc

        row = {
            "No.": "",
            "Công ty": comp_name,
            "Chức danh": "Vadovas / Ūkio Vadovas",
            "Người liên hệ": "Vadovas",
            "SĐT": phone_val,
            "Liên Hệ": web_val if web_val else durl,
            "Email": email_val,
            "Liên Hệ mail": f"mailto:{email_val}" if email_val else web_val,
            "Địa chỉ": addr_val,
            "Lương": rev_str,
            "Ngày đăng": clean_text(rec.get("Nam_Thanh_Lap", "")),
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
            with_email.append(row)
        else:
            without_email.append(row)

    combined = with_email + without_email
    for idx, r in enumerate(combined, start=1):
        r["No."] = idx

    return combined, len(with_email)


def export_and_sync_all_files(records_by_key: dict[str, dict]) -> tuple[int, int]:
    """
    Export deduplicated RAW, 2COL, and READY CSVs to root, csdl_mlt/, and archive/lt_lithuania/.
    Returns: (total_companies, companies_with_email)
    """
    clean_records = []
    for rec in records_by_key.values():
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
    cold_rows, email_count = build_coldmail_rows(clean_records)
    df_col = pd.DataFrame(cold_rows, columns=COLDMAIL_COLUMNS)
    df_ready = df_col[df_col["Email"] != ""].copy()

    target_dirs = [ROOT_DIR, CSDL_DIR, ARCHIVE_DIR]
    for folder in target_dirs:
        folder.mkdir(parents=True, exist_ok=True)
        try:
            df_raw.to_csv(folder / RAW_FILENAME, index=False, encoding="utf-8-sig")
            df_col.to_csv(folder / COLDMAIL_FILENAME, index=False, encoding="utf-8-sig")
            df_ready.to_csv(folder / EMAILS_READY_FILENAME, index=False, encoding="utf-8-sig")
        except Exception as e:
            print(f"[WARN] Failed to write CSVs to {folder}: {e}")

    return len(df_raw), email_count


def find_or_open_litorg_page(browser):
    """Reuse existing litorg.cc tab or create a new tab in connected Chrome context."""
    if not browser.contexts:
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    else:
        ctx = browser.contexts[0]
    for pg in ctx.pages:
        if "litorg.cc" in (pg.url or ""):
            return pg
    return ctx.new_page()


def ensure_chrome_running(cdp_port: int = 9222) -> None:
    """Check if Chrome is running on CDP port; if not, attempt to launch native Chrome."""
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1.0)
    result = sock.connect_ex(("127.0.0.1", cdp_port))
    sock.close()
    if result == 0:
        return

    chrome_candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]

    chrome_exe = None
    for cand in chrome_candidates:
        if Path(cand).exists():
            chrome_exe = cand
            break

    if chrome_exe:
        print(f"[*] Starting native Chrome on CDP port {cdp_port}...")
        USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        cmd = [
            chrome_exe,
            f"--remote-debugging-port={cdp_port}",
            f"--user-data-dir={USER_DATA_DIR}",
            BASE_CATALOG_URL,
        ]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3.0)


def fetch_page_with_cdp(page, page_url: str) -> tuple[list[dict], int, bool, int]:
    """
    Navigate to page_url using CDP, with retry backoff.
    Returns: (records, detected_max_page, is_gated, status_code)
    """
    backoff_delays = (10, 20, 35)
    for attempt in range(4):
        try:
            resp = page.goto(page_url, wait_until="load", timeout=35000)
            status = resp.status if resp else 200
            html = page.content()
            title = page.title()
            recs, max_p, gated = parse_litorg_html_page(html, title)

            if gated or status == 403:
                return [], max_p, True, status
            if recs:
                return recs, max_p, False, status

            if attempt < len(backoff_delays):
                if status == 429:
                    wait_sec = backoff_delays[attempt]
                    print(f"  [HTTP 429 Rate-limited] Waiting {wait_sec}s before retry {attempt + 1}/3...")
                    time.sleep(wait_sec)
                    continue
                if status in (500, 502, 503, 504):
                    time.sleep(backoff_delays[attempt])
                    continue
            return [], max_p, False, status
        except Exception as e:
            if attempt == 3:
                print(f"  [Navigation Error] {e}")
            time.sleep(2.0)
    return [], 1, False, 200


def run_scraper(
    cdp_port: int = 9222,
    start_page: int = 1,
    max_pages_arg: int | None = None,
    limit: int | None = None,
    reset_cache: bool = False,
) -> None:
    """Main scraping loop for NACE Division 01."""
    print("=" * 80)
    print("🌾  LITORG.CC SCRAPER - LITHUANIAN AGRICULTURE & FARMING (NACE 01)")
    print("    Crop and animal production, hunting and related service activities")
    print(f"    - Target URL      : {BASE_CATALOG_URL}")
    print(f"    - Raw output      : {OUTPUT_0RAW_PATH.name}")
    print(f"    - Cold Mail (2COL): {OUTPUT_2COL_PATH.name}")
    print(f"    - Emails Ready    : {OUTPUT_READY_PATH.name}")
    print(f"    - Checkpoint Cache: {CACHE_FILE.name}")
    print(f"    - Chrome CDP Port : {cdp_port}")
    if limit:
        print(f"    - Limit           : {limit} companies")
    print("=" * 80 + "\n")

    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state = {"completed_pages": [], "max_page": 1, "records": {}} if reset_cache else load_cache()
    completed = set(state.get("completed_pages", []))
    records_by_key: dict[str, dict] = state.get("records", {})
    detected_max_page = int(state.get("max_page") or 1)

    if records_by_key:
        print(f"[*] Loaded {len(records_by_key):,} companies from checkpoint cache ({len(completed)} pages completed).")

    ensure_chrome_running(cdp_port)

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
            print(f"[+] Successfully connected to Chrome CDP on port {cdp_port}!")
        except Exception as e:
            print(f"\n[ERROR] Cannot connect to Chrome CDP on port {cdp_port}: {e}")
            print("Please ensure Google Chrome is launched with --remote-debugging-port=9222.")
            print(f"Alternative: runners\\run_lt_farm_litorg.bat launches Chrome automatically.")
            return

        page = find_or_open_litorg_page(browser)
        try:
            page.set_viewport_size({"width": 1280, "height": 800})
        except Exception:
            pass

        # Page 1 check to establish total page count
        if detected_max_page <= 1 or (1 not in completed and start_page <= 1):
            curr_url = page.url or ""
            if curr_url.rstrip("/") != BASE_CATALOG_URL.rstrip("/"):
                recs_p1, p1_max, gated, st = fetch_page_with_cdp(page, BASE_CATALOG_URL)
            else:
                recs_p1, p1_max, gated = parse_litorg_html_page(page.content(), page.title())
                st = 403 if gated else 200

            if gated:
                print("\a")
                print(f"[BLOCKED] Cloudflare verification gate detected on Page 1 (HTTP {st}).")
                print(">>> Please complete the human verification directly in the Chrome window! <<<")
                # Wait up to 60 seconds for manual user verification
                for w in range(20):
                    time.sleep(3.0)
                    recs_retry, p1_max, gated_retry = parse_litorg_html_page(page.content(), page.title())
                    if not gated_retry and recs_retry:
                        print("[+] Verification passed! Resuming scraping...")
                        recs_p1 = recs_retry
                        gated = False
                        break

                if gated:
                    print("[!] Gate still active. Checkpoint saved. Re-run after completing verification.")
                    return

            detected_max_page = max(detected_max_page, p1_max)
            state["max_page"] = detected_max_page

            if recs_p1 and 1 not in completed and start_page <= 1:
                new_added = 0
                for r in recs_p1:
                    k = record_key(r)
                    if k not in records_by_key:
                        records_by_key[k] = r
                        new_added += 1
                completed.add(1)
                state["completed_pages"] = sorted(completed)
                state["records"] = records_by_key
                save_cache(state)
                append_raw_incremental(list(records_by_key.values())[-new_added:] if new_added > 0 else [], 1)
                print(f"[Page 01/{detected_max_page}] +{new_added} new companies (Total: {len(records_by_key):,})")
            else:
                save_cache(state)
                print(f"[*] Detected total catalog pages: {detected_max_page}")

        end_page = min(detected_max_page, max_pages_arg) if max_pages_arg else detected_max_page

        for page_num in range(max(1, start_page), end_page + 1):
            if page_num in completed:
                continue

            if limit and len(records_by_key) >= limit:
                print(f"\n[*] Reached limit of {limit} companies. Stopping pagination.")
                break

            page_url = f"{BASE_CATALOG_URL}?page={page_num}" if page_num > 1 else BASE_CATALOG_URL
            print(f"[Page {page_num:2d}/{end_page:2d}] Scraping: {page_url} ...", end=" ", flush=True)

            try:
                recs, page_max, gated, status = fetch_page_with_cdp(page, page_url)
            except Exception as nav_err:
                print(f"❌ Error: {nav_err}")
                save_cache(state)
                break

            if gated:
                print("\a")
                print(f"\n[BLOCKED] Cloudflare gate appeared at page {page_num} (HTTP {status}).")
                print(">>> Please complete the human verification directly in the Chrome window! <<<")
                unblocked = False
                for _ in range(20):
                    time.sleep(3.0)
                    recs_r, _, gated_r = parse_litorg_html_page(page.content(), page.title())
                    if not gated_r and recs_r:
                        recs = recs_r
                        unblocked = True
                        print("[+] Gate resolved! Continuing...")
                        break

                if not unblocked:
                    print("Checkpoint saved. Re-run to resume.")
                    save_cache(state)
                    export_and_sync_all_files(records_by_key)
                    return

            if page_max > detected_max_page and not max_pages_arg:
                detected_max_page = page_max
                state["max_page"] = detected_max_page
                end_page = detected_max_page

            if not recs:
                print(f"⚠ 0 cards found (HTTP {status}). Stopping pagination.")
                break

            new_added = 0
            new_rows = []
            for r in recs:
                k = record_key(r)
                if k not in records_by_key:
                    records_by_key[k] = r
                    new_rows.append(r)
                    new_added += 1
                else:
                    curr_cat = records_by_key[k].get("Category", "")
                    new_cat = r.get("Category", "")
                    if new_cat and new_cat not in curr_cat:
                        records_by_key[k]["Category"] = f"{curr_cat}; {new_cat}"

            completed.add(page_num)
            state["completed_pages"] = sorted(completed)
            state["records"] = records_by_key

            append_raw_incremental(new_rows, len(records_by_key) - len(new_rows) + 1)
            save_cache(state)

            print(f"✅ {len(recs):2d} cards (+{new_added:2d} new | Total: {len(records_by_key):,})")

            # Periodic full export every 5 pages
            if page_num % 5 == 0:
                export_and_sync_all_files(records_by_key)

            time.sleep(random.uniform(1.2, 2.2))

        # Final save and export
        save_cache(state)
        tot, em = export_and_sync_all_files(records_by_key)

        print("\n" + "=" * 80)
        print("🏆 SCRAPING COMPLETED SUCCESSFULLY!")
        print(f"  Total companies collected    : {tot:,}")
        print(f"  Companies with Email ready   : {em:,}")
        print(f"  Raw catalog CSV (0RAW)       : {OUTPUT_0RAW_PATH.name}")
        print(f"  Cold Mail 20-col CSV (2COL)  : {OUTPUT_2COL_PATH.name}")
        print(f"  Ready emails subset (READY)  : {OUTPUT_READY_PATH.name}")
        print(f"  Synced automatically to      : csdl_mlt/ & archive/lt_lithuania/")
        print("=" * 80 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape Lithuanian Agriculture & Farming Enterprises (NACE 01) from litorg.cc"
    )
    parser.add_argument("--cdp-port", type=int, default=9222, help="Chrome CDP port (default: 9222)")
    parser.add_argument("--start-page", type=int, default=1, help="Start catalog page number (default: 1)")
    parser.add_argument("--max-pages", type=int, default=None, help="Optional max pages override")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of companies to scrape")
    parser.add_argument("--reset-cache", action="store_true", help="Reset checkpoint cache before scraping")
    parser.add_argument("--export-only", action="store_true", help="Re-export files from cache without scraping")
    args = parser.parse_args()

    if args.export_only:
        state = load_cache()
        records = state.get("records", {})
        if records:
            tot, em = export_and_sync_all_files(records)
            print(f"[+] Re-exported {tot:,} companies ({em:,} with email) from checkpoint cache.")
        else:
            print("[!] Cache is empty. Nothing to export.")
        return

    run_scraper(
        cdp_port=args.cdp_port,
        start_page=args.start_page,
        max_pages_arg=args.max_pages,
        limit=args.limit,
        reset_cache=args.reset_cache,
    )


if __name__ == "__main__":
    main()
