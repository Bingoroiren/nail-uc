"""
Scrape Lithuanian Warehousing, Storage and Support Activities for Transportation (NACE 52)
Source: https://litorg.cc/en/catalog/52/

Outputs (CSV UTF-8 with BOM - utf-8-sig):
- LT_WARE_LTOR_0RAW.csv (raw catalog records synced to root, csdl_mlt/, archive/lt_lithuania/)
- LT_WARE_LTOR_2COL.csv (Cold Mail 20-column format synced to root, csdl_mlt/, archive/lt_lithuania/)
"""

import argparse
import csv
import json
import os
import random
import re
import sys
import time
import unicodedata
import urllib.parse
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
CSDL_DIR = ROOT_DIR / "csdl_mlt"
ARCHIVE_DIR = ROOT_DIR / "archive" / "lt_lithuania"
CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_scraper_litorg_ware.json"

CATALOG_ID = "52"
CATALOG_NAME = "Warehousing, storage and support activities for transportation"
BASE_CATALOG_URL = "https://litorg.cc/en/catalog/52/"

RAW_FILENAME = "LT_WARE_LTOR_0RAW.csv"
COLDMAIL_FILENAME = "LT_WARE_LTOR_2COL.csv"

PERMANENT_BLACKLIST_COMPANIES = [
    "scandi standard",
    "scandi-standard",
    "scandi standart",
    "biliarta",
    "daigre",
]

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
    """Normalize invisible spaces and trim text safely."""
    if val is None:
        return ""
    text = str(val)
    for bad in ("\u00a0", "\xa0", "\u200b", "\ufeff"):
        text = text.replace(bad, " ")
    return re.sub(r"\s+", " ", text).strip()


def is_blacklisted_company(name: str) -> bool:
    """Enforce permanent company blacklist with Unicode NFKD accent folding."""
    if not name:
        return False
    norm = unicodedata.normalize("NFKD", str(name)).lower()
    clean = "".join(c for c in norm if not unicodedata.combining(c))
    return any(b in clean for b in PERMANENT_BLACKLIST_COMPANIES)


def clean_phone_lt(phone_str: str) -> str:
    """Normalize Lithuanian phone numbers and prefix with apostrophe for CSV safety."""
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
    """Decode URL/unicode escapes, strip junk placeholders, and validate email format."""
    if not email_str or str(email_str).lower() == "nan":
        return ""
    s = urllib.parse.unquote(str(email_str)).strip().lower()
    s = s.replace("&nbsp;", "").replace("\u00a0", "").replace("\xa0", "")
    s = s.replace("\u200b", "").replace("\ufeff", "").replace(" ", "")
    s = re.sub(r"^(?:\\?u00[0-9a-f]{2})+", "", s)
    s = re.sub(r"^20(?=[a-z0-9])", "", s) if "@" in s else s
    s = s.strip(".,;:'\"<>[]()")
    if not s or "@" not in s:
        return ""
    if any(s.startswith(prefix) for prefix in JUNK_EMAIL_PREFIXES):
        return ""
    domain = s.split("@")[-1]
    if any(d in domain for d in JUNK_EMAIL_DOMAINS):
        return ""
    if not re.match(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$", s):
        return ""
    return s


def is_cloudflare_gate(title: str, html_text: str) -> bool:
    """Detect whether the current page shows a Cloudflare human-verification gate."""
    t_low = (title or "").lower()
    h_low = (html_text or "").lower()
    return (
        "just a moment" in t_low
        or "verify you are human" in h_low
        or "cf-turnstile" in h_low
    )


def detect_max_page(soup: BeautifulSoup) -> int:
    """Extract highest catalog page number from pagination links."""
    max_p = 1
    for a in soup.select(".pagination a, .pager a, nav a"):
        href = a.get("href", "")
        txt = clean_text(a.get_text())
        m = re.search(r"[?&]page=(\d+)", href)
        if m:
            max_p = max(max_p, int(m.group(1)))
        elif txt.isdigit():
            max_p = max(max_p, int(txt))
    return max_p


def parse_litorg_html_page(html_text: str, page_title: str = "") -> tuple[list[dict], int, bool]:
    """Parse all company cards (li.fl-item) from a litorg.cc catalog page."""
    soup = BeautifulSoup(html_text, "html.parser")
    items = soup.select("li.fl-item")
    if not items and is_cloudflare_gate(page_title, html_text):
        return [], 1, True

    max_page = detect_max_page(soup)
    records = []

    for item in items:
        h3_a = item.select_one("h3 a")
        if not h3_a:
            continue

        name = clean_text(h3_a.get_text())
        if is_blacklisted_company(name):
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
                m_yr = re.search(r"since\s+(\d{4})", parts[2], re.IGNORECASE)
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
                "Category": category,
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

    return records, max_page, False


def record_key(rec: dict) -> str:
    """Return stable deduplication key by registration code or normalized company name."""
    code = clean_text(rec.get("Company_Code"))
    if code:
        return code
    return clean_text(rec.get("Cong ty")).lower()


def load_cache() -> dict:
    """Load checkpoint JSON state if present."""
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
            print(f"[WARN] Could not read cache file cleanly: {e}")
    return {"completed_pages": [], "max_page": 1, "records": {}}


def save_cache(state: dict) -> None:
    """Persist checkpoint JSON state atomically."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = CACHE_FILE.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, CACHE_FILE)


def append_raw_incremental(rows: list[dict], start_no: int) -> None:
    """Incrementally append newly scraped page rows to root RAW CSV with immediate flush."""
    if not rows:
        return
    raw_path = ROOT_DIR / RAW_FILENAME
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


def build_coldmail_rows(raw_records: list[dict]) -> list[dict]:
    """Convert raw records to 20-column Cold Mail format, keeping email rows first."""
    with_email = []
    without_email = []

    for rec in raw_records:
        if is_blacklisted_company(rec.get("Cong ty", "")):
            continue
        email = clean_email(rec.get("Email", ""))
        phone = clean_phone_lt(rec.get("SDT", ""))
        city = clean_text(rec.get("City", ""))
        row = {
            "No.": "",
            "Công ty": clean_text(rec.get("Cong ty", "")),
            "Chức danh": "Vadovas",
            "Người liên hệ": "",
            "SĐT": phone,
            "Liên Hệ": clean_text(rec.get("Detail_URL", "")),
            "Email": email,
            "Liên Hệ mail": "",
            "Địa chỉ": f"{city}, Lithuania" if city else "Lithuania",
            "Lương": clean_text(rec.get("Doanh_Thu", "")),
            "Ngày đăng": clean_text(rec.get("Nam_Thanh_Lap", "")),
            "Hạn tuyển": "",
            "Check gửi": "Chưa gửi",
            "Last Subject": "",
            "Last Body HTML": "",
            "Trạng thái Reply": "",
            "Lần Follow-up": "",
            "Ngày Follow-up gần nhất": "",
            "Mailbox đã dùng": "",
            "Category": clean_text(rec.get("Category", "")),
        }
        if email:
            with_email.append(row)
        else:
            without_email.append(row)

    combined = with_email + without_email
    for idx, row in enumerate(combined, start=1):
        row["No."] = idx
    return combined


def export_and_sync_all_files(records_by_key: dict[str, dict]) -> tuple[int, int]:
    """Write deduplicated RAW and 2COL CSVs to root, csdl_mlt/, and archive/lt_lithuania/."""
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
    cold_rows = build_coldmail_rows(clean_records)
    df_col = pd.DataFrame(cold_rows, columns=COLDMAIL_COLUMNS)

    target_dirs = [ROOT_DIR, CSDL_DIR, ARCHIVE_DIR]
    for folder in target_dirs:
        folder.mkdir(parents=True, exist_ok=True)
        df_raw.to_csv(folder / RAW_FILENAME, index=False, encoding="utf-8-sig")
        df_col.to_csv(folder / COLDMAIL_FILENAME, index=False, encoding="utf-8-sig")

    email_count = sum(1 for r in cold_rows if r["Email"])
    return len(cold_rows), email_count


def find_or_open_litorg_page(browser):
    """Reuse an already open litorg.cc tab in Chrome CDP or open a new tab."""
    if not browser.contexts:
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    else:
        ctx = browser.contexts[0]
    for pg in ctx.pages:
        if "litorg.cc" in (pg.url or ""):
            return pg
    return ctx.new_page()


def merge_page_records(
    state: dict, completed: set[int], records_by_key: dict[str, dict], page_num: int, recs: list[dict]
) -> int:
    """Merge newly parsed records into state, append incremental RAW CSV, and save checkpoint."""
    new_rows = []
    for rec in recs:
        k = record_key(rec)
        if k not in records_by_key:
            new_rows.append(rec)
        records_by_key[k] = rec

    append_raw_incremental(new_rows, len(records_by_key) - len(new_rows) + 1)
    completed.add(page_num)
    state["completed_pages"] = sorted(completed)
    state["records"] = records_by_key
    save_cache(state)
    return len(new_rows)


def fetch_and_parse_page(page, page_url: str) -> tuple[list[dict], int, bool, int]:
    """Load one catalog page over CDP and return (records, max_page, gated, http_status)."""
    backoff_delays = (12, 25, 45)
    for attempt in range(4):
        resp = page.goto(page_url, wait_until="load", timeout=30000)
        status = resp.status if resp else 200
        headers = resp.headers if resp else {}
        html = page.content()
        title = page.title()
        recs, page_max, gated = parse_litorg_html_page(html, title)
        if gated or status == 403:
            return [], page_max, True, status
        if recs:
            return recs, page_max, False, status
        if attempt < len(backoff_delays):
            if status == 429:
                retry_after = headers.get("retry-after", "")
                wait_sec = int(retry_after) + 1 if retry_after.isdigit() else backoff_delays[attempt]
                wait_sec = min(max(wait_sec, 5), 60)
                print(f"  [HTTP 429] Rate-limited; backing off {wait_sec}s before retry {attempt + 1}/3...")
                time.sleep(wait_sec)
                continue
            if status in (500, 502, 503, 504):
                time.sleep(backoff_delays[attempt])
                continue
        return [], page_max, False, status
    return [], 1, False, 200


def scrape_catalog_over_cdp(cdp_port: int, start_page: int, max_pages_arg: int | None, reset_cache: bool) -> None:
    """Scrape all pages of litorg.cc/en/catalog/52/ via connected native Chrome CDP."""
    state = {"completed_pages": [], "max_page": 1, "records": {}} if reset_cache else load_cache()
    completed = set(state.get("completed_pages", []))
    records_by_key: dict[str, dict] = state.get("records", {})
    detected_max_page = int(state.get("max_page") or 1)

    if reset_cache:
        raw_root = ROOT_DIR / RAW_FILENAME
        if raw_root.exists():
            raw_root.unlink()

    print("=" * 72)
    print(f"LITORG.CC SCRAPER - NACE {CATALOG_ID}: {CATALOG_NAME}")
    print(f"Connecting to Chrome CDP on http://127.0.0.1:{cdp_port} ...")
    print(f"Loaded cache: {len(records_by_key)} records, {len(completed)} pages completed.")
    print("=" * 72)

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
        except Exception as e:
            print(f"\n[ERROR] Cannot connect to Chrome CDP port {cdp_port}: {e}")
            print("Please start Chrome with --remote-debugging-port=9222 and verify Cloudflare first.")
            sys.exit(1)

        page = find_or_open_litorg_page(browser)
        try:
            page.set_viewport_size({"width": 1280, "height": 800})
        except Exception:
            pass

        if detected_max_page <= 1 or (1 not in completed and start_page <= 1):
            current_url = page.url or ""
            if current_url.rstrip("/") != BASE_CATALOG_URL.rstrip("/"):
                recs_p1, p1_max, gated, st = fetch_and_parse_page(page, BASE_CATALOG_URL)
            else:
                recs_p1, p1_max, gated = parse_litorg_html_page(page.content(), page.title())
                st = 403 if gated else 200
            if gated:
                print("\a")
                print(f"[BLOCKED] Cloudflare verification gate detected on page 1 (HTTP {st}).")
                print("Please complete the human verification directly in the Chrome window, then re-run.")
                return
            detected_max_page = max(detected_max_page, p1_max)
            state["max_page"] = detected_max_page
            if recs_p1 and 1 not in completed and start_page <= 1:
                merge_page_records(state, completed, records_by_key, 1, recs_p1)
                print(f"[Page 1/{detected_max_page}] +{len(recs_p1)} items (total unique: {len(records_by_key)})")
            else:
                save_cache(state)
                print(f"Detected total catalog pages: {detected_max_page}")

        end_page = min(detected_max_page, max_pages_arg) if max_pages_arg else detected_max_page

        for page_num in range(max(1, start_page), end_page + 1):
            if page_num in completed:
                continue

            page_url = f"{BASE_CATALOG_URL}?page={page_num}" if page_num > 1 else BASE_CATALOG_URL
            try:
                recs, page_max, gated, status = fetch_and_parse_page(page, page_url)
            except Exception as nav_err:
                print(f"[WARN] Page {page_num} navigation error: {nav_err}")
                save_cache(state)
                break

            if gated:
                print("\a")
                print(f"[BLOCKED] Cloudflare gate appeared at page {page_num} (HTTP {status}).")
                print("Checkpoint saved. Complete verification in Chrome, then re-run to resume.")
                save_cache(state)
                export_and_sync_all_files(records_by_key)
                return

            if page_max > detected_max_page and not max_pages_arg:
                detected_max_page = page_max
                state["max_page"] = detected_max_page

            if not recs:
                print(f"[Page {page_num}/{end_page}] 0 cards found (HTTP {status}). Stopping pagination.")
                break

            new_cnt = merge_page_records(state, completed, records_by_key, page_num, recs)
            print(
                f"[Page {page_num}/{end_page}] parsed={len(recs)} | new={new_cnt} | total_unique={len(records_by_key)}"
            )
            time.sleep(random.uniform(1.8, 2.8))

    total_rows, with_email = export_and_sync_all_files(records_by_key)
    print("=" * 72)
    print(f"DONE! Exported {total_rows} unique companies (with email: {with_email}).")
    print(f"- {ROOT_DIR / RAW_FILENAME}")
    print(f"- {ROOT_DIR / COLDMAIL_FILENAME}")
    print(f"- {CSDL_DIR / COLDMAIL_FILENAME}")
    print(f"- {ARCHIVE_DIR / COLDMAIL_FILENAME}")
    print("=" * 72)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape Lithuanian Warehousing & Transport Support companies from litorg.cc/en/catalog/52/ via Chrome CDP"
    )
    parser.add_argument("--cdp-port", type=int, default=9222, help="Chrome remote debugging port (default: 9222)")
    parser.add_argument("--start-page", type=int, default=1, help="Start catalog page number (default: 1)")
    parser.add_argument("--max-page", type=int, default=None, help="Optional max page override for partial runs")
    parser.add_argument("--reset-cache", action="store_true", help="Clear cached progress before scraping")
    args = parser.parse_args()

    scrape_catalog_over_cdp(
        cdp_port=args.cdp_port,
        start_page=args.start_page,
        max_pages_arg=args.max_page,
        reset_cache=args.reset_cache,
    )


if __name__ == "__main__":
    main()
