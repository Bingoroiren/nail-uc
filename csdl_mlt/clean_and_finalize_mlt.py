# -*- coding: utf-8 -*-
"""
CSDL MLT - Solution 1: Consolidate, Clean, Deduplicate & Format Lithuania Food Industry Data:
Nguồn dữ liệu:
1. visalietuva_database.csv (473 cty)
2. infolt_database.csv (641 cty)
3. imoneslt_database.csv (277 cty)
4. b2lithuania_database.csv (300 cty)

Quy chuẩn & Tiêu chuẩn xuất tệp 17 ký tự (Rule 10):
- LT_FOOD_WEBD_0RAW.csv (Tổng hợp thô sau lọc trùng)
- LT_FOOD_WEBD_1ENR.csv (Làm giàu email B2B, chuẩn hóa SĐT nháy đơn, 100% email lên đầu)
- LT_FOOD_WEBD_2COL.csv (Chuẩn Cold Mail 20 cột, sẵn sàng gửi chiến dịch)
"""

import sys
import os
import re
import csv
import time
import unicodedata
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from curl_cffi import requests
from bs4 import BeautifulSoup

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent

F_RAW = "LT_FOOD_WEBD_0RAW.csv"
F_ENR = "LT_FOOD_WEBD_1ENR.csv"
F_COL = "LT_FOOD_WEBD_2COL.csv"

LEGAL_FORMS = [
    "uždaroji akcinė bendrovė", "akcinė bendrovė", "mažoji bendrija",
    "individuali įmonė", "viešoji įstaiga", "tikroji ūkinė bendrija",
    "komanditinė ūkinė bendrija", "žemės ūkio bendrovė", "kooperatinė bendrovė",
    "kooperatyvas", "uab", "ab", "mb", "iį", "všį", "tūb", "kūb", "žūb", "koop.", "ii"
]

EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b")
INVALID_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js", ".pdf", ".woff", ".woff2", ".ico")

SUBPATHS = [
    "", "/kontaktai", "/apie-mus", "/karjera", "/darbas", "/rekvizitai", "/contact", "/contacts"
]

HEADERS_1ENR = [
    "No.",
    "Công ty",
    "IČO",  # Įmonės kodas
    "SĐT",
    "Web",
    "Email",
    "Địa chỉ",
    "Thành phố",
    "Direktorius",
    "Nhân sự",
    "Doanh thu (EUR)",
    "Category",
    "Source",
    "Source_URL",
]

HEADERS_2COL = [
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


def remove_accents(s):
    if not s:
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn")


def normalize_company_name(name):
    if not name:
        return ""
    s = remove_accents(str(name)).lower()
    s = re.sub(r'["\'„“”«»]', "", s)
    for lf in LEGAL_FORMS:
        lf_norm = remove_accents(lf)
        s = re.sub(rf"\b{re.escape(lf_norm)}\b", "", s)
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


def clean_phone(phone):
    """Normalize phone numbers to international standard with single quote '"""
    if not phone or str(phone).strip() in ["", "nan", "None"]:
        return ""
    p = re.sub(r"[^\d+]", "", str(phone).strip())
    if p.startswith("8") and len(p) == 9:
        p = "+370" + p[1:]
    elif p.startswith("0") and len(p) == 10:
        p = "+370" + p[1:]
    elif not p.startswith("+") and len(p) == 8:
        p = "+370" + p
    return f"'{p}" if not p.startswith("'") else p


def decode_cf(cf_hex):
    try:
        r = int(cf_hex[:2], 16)
        return "".join([chr(int(cf_hex[i:i + 2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
    except Exception:
        return ""


def score_email_b2b(email, domain=""):
    """B2B Heuristic scoring per Workspace Rule 3"""
    if not email or not isinstance(email, str):
        return -1
    e = email.strip().lower()
    if not EMAIL_REGEX.match(e) or any(e.endswith(ext) for ext in INVALID_EXTS):
        return -1
    u, d = e.split("@", 1)

    # Filter spam / placeholders
    if any(bad in d for bad in ["sentry", "wixpress", "wix.com", "example.com", "domain.com", "email.com", "address.com", "mail.lt"]):
        return -1
    if any(bad in u for bad in ["sentry", "youremail", "your-email", "yourname", "sample", "no-reply", "donotreply", "es-module"]):
        return -1

    score = 10
    clean_d = domain.lower().replace("www.", "").split("/")[0] if domain else ""
    if clean_d and (clean_d in d or d in clean_d):
        score += 50
    elif d.endswith(".lt"):
        score += 25

    # HR & Recruitment (Highest Priority)
    if u in ["karjera", "darbas", "personalas", "hr", "praca", "jobs", "recruitment", "nabor", "career"]:
        score += 50
    # Executives & Management
    elif u in ["direktorius", "vadovas", "generalinis", "ceo", "director", "manager", "prekyba", "pardavimai", "sales"]:
        score += 45
    # Official portal
    elif u in ["info", "kontaktai", "kontakt", "contact", "office", "biuras", "sekretoriatas"]:
        score += 40
    elif "." in u and score >= 60:
        score += 25

    return score


def select_best_email(emails, domain=""):
    valid = [e for e in set(emails) if score_email_b2b(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b(e, domain))


def crawl_site_for_emails(web_url):
    """Fast DOM-First Email Extractor with fail-fast for dead domains"""
    if not web_url or not str(web_url).startswith("http"):
        return ""
    if any(bad in web_url.lower() for bad in ["facebook", "linkedin", "instagram", "youtube", "twitter"]):
        return ""

    root = web_url.rstrip("/")
    found = set()

    # Step 1: Check root domain first. If offline/timeout, fail-fast immediately!
    try:
        r = requests.get(root, impersonate="chrome120", timeout=4, verify=False)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select('a[href^="mailto:"]'):
                em = a["href"].replace("mailto:", "").split("?")[0].strip()
                if score_email_b2b(em, web_url) > 0:
                    found.add(em)
            for cf in soup.select("[data-cfemail]"):
                em = decode_cf(cf["data-cfemail"])
                if score_email_b2b(em, web_url) > 0:
                    found.add(em)
            for em in EMAIL_REGEX.findall(r.text):
                if score_email_b2b(em, web_url) > 0:
                    found.add(em)

            # If high-quality email already found on root page, stop here!
            if any(score_email_b2b(e, web_url) >= 80 for e in found):
                return select_best_email(list(found), web_url)
        else:
            return ""
    except Exception:
        return ""

    # Step 2: Check common contact subpages only if root is alive
    for sub in ["/kontaktai", "/apie-mus", "/karjera", "/contact"]:
        target = f"{root}{sub}"
        try:
            r = requests.get(target, impersonate="chrome120", timeout=3, verify=False)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.select('a[href^="mailto:"]'):
                    em = a["href"].replace("mailto:", "").split("?")[0].strip()
                    if score_email_b2b(em, web_url) > 0:
                        found.add(em)
                for cf in soup.select("[data-cfemail]"):
                    em = decode_cf(cf["data-cfemail"])
                    if score_email_b2b(em, web_url) > 0:
                        found.add(em)
                for em in EMAIL_REGEX.findall(r.text):
                    if score_email_b2b(em, web_url) > 0:
                        found.add(em)
                if any(score_email_b2b(e, web_url) >= 80 for e in found):
                    break
        except Exception:
            pass

    return select_best_email(list(found), web_url)


def run_pipeline():
    print("=" * 75)
    print(" CSDL MLT - GIAI PHAP 1: CONSOLIDATE, CLEAN & FORMAT LITHUANIA FOOD DATA")
    print("=" * 75)

    input_files = [
        BASE_DIR / "visalietuva_database.csv",
        BASE_DIR / "infolt_database.csv",
        BASE_DIR / "imoneslt_database.csv",
        BASE_DIR / "b2lithuania_database.csv",
    ]

    records_by_ico = {}
    records_by_name = {}
    total_raw = 0

    # 1. Load and Deduplicate across all 4 databases
    for fpath in input_files:
        if not fpath.exists():
            print(f"[-] Bo qua: Khong tim thay {fpath.name}")
            continue

        print(f"[+] Doc va doi chieu: {fpath.name}")
        with open(fpath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                total_raw += 1
                count += 1
                comp_name = (row.get("Công ty") or "").strip()
                ico = str(row.get("IČO") or "").strip()
                norm_name = normalize_company_name(comp_name)

                # Match priority: IČO first, then normalized name
                matched = None
                if ico and ico in records_by_ico:
                    matched = records_by_ico[ico]
                elif norm_name and norm_name in records_by_name:
                    matched = records_by_name[norm_name]

                if matched:
                    # Merge missing fields
                    for col in ["SĐT", "Web", "Email", "Địa chỉ", "Thành phố", "Direktorius", "Nhân sự", "Doanh thu (EUR)"]:
                        if not matched.get(col) and row.get(col):
                            matched[col] = str(row.get(col)).strip()
                    if not matched.get("IČO") and ico:
                        matched["IČO"] = ico
                        records_by_ico[ico] = matched
                    # Merge Category
                    old_cat = matched.get("Category", "")
                    new_cat = row.get("Category", "")
                    if new_cat and new_cat not in old_cat:
                        matched["Category"] = f"{old_cat}; {new_cat}".strip("; ")
                    # Merge Source
                    old_src = matched.get("Source", "")
                    new_src = row.get("Source", "")
                    if new_src and new_src not in old_src:
                        matched["Source"] = f"{old_src}, {new_src}".strip(", ")
                else:
                    new_rec = {
                        "Công ty": comp_name,
                        "IČO": ico,
                        "SĐT": clean_phone(row.get("SĐT")),
                        "Web": (row.get("Web") or "").strip(),
                        "Email": (row.get("Email") or "").strip(),
                        "Địa chỉ": (row.get("Địa chỉ") or "").strip(),
                        "Thành phố": (row.get("Thành phố") or "").strip(),
                        "Direktorius": (row.get("Direktorius") or "").strip(),
                        "Nhân sự": (row.get("Nhân sự") or "").strip(),
                        "Doanh thu (EUR)": (row.get("Doanh thu (EUR)") or "").strip(),
                        "Category": (row.get("Category") or "").strip(),
                        "Source": (row.get("Source") or "").strip(),
                        "Source_URL": (row.get("Source_URL") or "").strip(),
                    }
                    if ico:
                        records_by_ico[ico] = new_rec
                    if norm_name:
                        records_by_name[norm_name] = new_rec

            print(f"    Da nap {count:,} ban ghi.")

    unique_records = list({id(v): v for v in list(records_by_ico.values()) + list(records_by_name.values())}.values())
    print(f"\n[*] Tong ban ghi tho: {total_raw:,}")
    print(f"[*] Tong doanh nghiep duy nhat sau loc trung (IČO + Ten): {len(unique_records):,}")

    # Clean addresses and extract city if missing
    for r in unique_records:
        r["SĐT"] = clean_phone(r.get("SĐT"))
        if not r.get("Thành phố") and r.get("Địa chỉ"):
            parts = [p.strip() for p in r["Địa chỉ"].split(",") if p.strip()]
            for p in parts:
                if any(k in p.upper() for k in [" M.", " R.", " K.", "SAV.", "SEN."]):
                    r["Thành phố"] = p
                    break

    # Save 0RAW file
    raw_path_csdl = BASE_DIR / F_RAW
    raw_path_root = ROOT_DIR / F_RAW
    for p in [raw_path_csdl, raw_path_root]:
        with open(p, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=HEADERS_1ENR)
            writer.writeheader()
            for idx, r in enumerate(unique_records, 1):
                writer.writerow({"No.": idx, **r})
    print(f"[V] Da xuat tệp tho tong hop: {F_RAW} ({len(unique_records):,} cty)")

    # 2. Fast Multi-Threaded Website Email Enrichment for companies with Web but no Email
    need_scan = [r for r in unique_records if r.get("Web") and not r.get("Email")]
    print(f"\n[*] Tien hanh quet Website da luong (Multi-Threading) tim Email cho {len(need_scan)} cty...")

    enriched_count = 0
    with ThreadPoolExecutor(max_workers=16) as executor:
        future_to_rec = {executor.submit(crawl_site_for_emails, r["Web"]): r for r in need_scan}
        done_cnt = 0
        for future in as_completed(future_to_rec):
            done_cnt += 1
            rec = future_to_rec[future]
            try:
                found_email = future.result()
                if found_email:
                    rec["Email"] = found_email
                    enriched_count += 1
                    print(f"  [+] [{done_cnt:03d}/{len(need_scan)}] {rec['Công ty'][:30]:<30} -> {found_email}")
                else:
                    if done_cnt % 25 == 0:
                        print(f"  [-] Da quet {done_cnt}/{len(need_scan)} website (+{enriched_count} email moi)...")
            except Exception:
                pass

    print(f"[*] Da quet xong toan bo website! Tim thay them {enriched_count:,} email B2B.")

    # 3. Clean and Validate all Emails with B2B Scoring
    for r in unique_records:
        em = r.get("Email", "")
        if em:
            if score_email_b2b(em, r.get("Web", "")) <= 0:
                r["Email"] = ""
            else:
                r["Email"] = em.strip().lower()

    # 4. Sort 100% Companies with Email to the TOP (Rule 3)
    with_email = [r for r in unique_records if r.get("Email")]
    without_email = [r for r in unique_records if not r.get("Email")]

    final_sorted_records = with_email + without_email

    # Save 1ENR file
    enr_path_csdl = BASE_DIR / F_ENR
    enr_path_root = ROOT_DIR / F_ENR
    for p in [enr_path_csdl, enr_path_root]:
        with open(p, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=HEADERS_1ENR)
            writer.writeheader()
            for idx, r in enumerate(final_sorted_records, 1):
                writer.writerow({"No.": idx, **r})
    print(f"[V] Da xuat tệp lam giau: {F_ENR} ({len(final_sorted_records):,} cty, {len(with_email):,} email)")

    # 5. Format standard 20-column Cold Mail (2COL)
    rows_2col = []
    for idx, r in enumerate(final_sorted_records, 1):
        col_row = {
            "No.": idx,
            "Công ty": r.get("Công ty", ""),
            "Chức danh": "Giám đốc / Điều hành" if r.get("Direktorius") else "Đại diện doanh nghiệp",
            "Người liên hệ": r.get("Direktorius", ""),
            "SĐT": r.get("SĐT", ""),
            "Liên Hệ": r.get("Web", ""),
            "Email": r.get("Email", ""),
            "Liên Hệ mail": r.get("Source_URL", ""),
            "Địa chỉ": r.get("Địa chỉ", ""),
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
            "Category": r.get("Category", ""),
        }
        rows_2col.append(col_row)

    col_path_csdl = BASE_DIR / F_COL
    col_path_root = ROOT_DIR / F_COL
    for p in [col_path_csdl, col_path_root]:
        with open(p, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=HEADERS_2COL)
            writer.writeheader()
            writer.writerows(rows_2col)

    print(f"[V] Da xuat tệp Cold Mail 20 cot: {F_COL} (San sang gui chien dich)")

    print("\n" + "=" * 75)
    print(" HOAN TAT TOAN BO TIEN TRINH CHUAN HOA & XU LY DU LIEU!")
    print(f" Tong cong: {len(final_sorted_records):,} doanh nghiep che bien thuc pham Lithuania.")
    print(f" So doanh nghiep co Email sach: {len(with_email):,} ({len(with_email)*100/len(final_sorted_records):.1f}%) duoc xep 100% LEN DAU TEP!")
    print(f" Cac tep da xuat:")
    print(f" 1. {F_RAW} (File tho sau loc trung)")
    print(f" 2. {F_ENR} (File lam giau day du thong tin)")
    print(f" 3. {F_COL} (File chuan Cold Mail 20 cot gui email ngay)")
    print("=" * 75)


if __name__ == "__main__":
    run_pipeline()
