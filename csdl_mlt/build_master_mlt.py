# -*- coding: utf-8 -*-
"""
CSDL MLT - Master Data Consolidation, Deduplication & Deep Enrichment:
Merges all Lithuanian Food / Meat / Fish / Dairy directory datasets from csdl_mlt/:
- visalietuva_database.csv
- infolt_database.csv
- imoneslt_database.csv
- b2lithuania_database.csv
- rekvizitai_database.csv (if exists)

Outputs:
1. csdl_mlt/LT_FOOD_WEBD_0RAW.csv (Raw merged dataset)
2. csdl_mlt/LT_FOOD_WEBD_1ENR.csv (Enriched with 100% emails on top, single quote phones)
3. LT_FOOD_WEBD_1ENR.csv (in workspace root)
"""

import sys
import os
import re
import csv
import time
import unicodedata
from pathlib import Path
from curl_cffi import requests
from bs4 import BeautifulSoup

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent

RAW_CSV = BASE_DIR / "LT_FOOD_WEBD_0RAW.csv"
ENR_CSV = BASE_DIR / "LT_FOOD_WEBD_1ENR.csv"
ROOT_ENR_CSV = ROOT_DIR / "LT_FOOD_WEBD_1ENR.csv"

LEGAL_FORMS = [
    "uždaroji akcinė bendrovė", "akcinė bendrovė", "mažoji bendrija",
    "individuali įmonė", "viešoji įstaiga", "tikroji ūkinė bendrija",
    "komanditinė ūkinė bendrija", "žemės ūkio bendrovė", "kooperatinė bendrovė",
    "uab", "ab", "mb", "iį", "všį", "tūb", "kūb", "žūb", "koop."
]

EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b")
INVALID_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js", ".pdf", ".woff", ".woff2", ".ico")

SUBPATHS = [
    "", "/kontaktai", "/kontaktai/", "/apie-mus", "/apie-mus/",
    "/karjera", "/karjera/", "/darbas", "/rekvizitai", "/contact", "/contacts"
]

HEADERS = [
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

    # HR & Recruitment
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
    """DOM-First Multi-Tier Email Extractor"""
    if not web_url or not str(web_url).startswith("http"):
        return ""
    if any(bad in web_url.lower() for bad in ["facebook", "linkedin", "instagram", "youtube", "twitter"]):
        return ""

    found = set()
    root = web_url.rstrip("/")

    for sub in SUBPATHS:
        target = f"{root}{sub}"
        try:
            r = requests.get(target, impersonate="chrome120", timeout=8, verify=False)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                # mailto
                for a in soup.select('a[href^="mailto:"]'):
                    em = a["href"].replace("mailto:", "").split("?")[0].strip()
                    if score_email_b2b(em, web_url) > 0:
                        found.add(em)

                # cloudflare cfemail
                for cf in soup.select("[data-cfemail]"):
                    em = decode_cf(cf["data-cfemail"])
                    if score_email_b2b(em, web_url) > 0:
                        found.add(em)

                # regex in html text
                for em in EMAIL_REGEX.findall(r.text):
                    if score_email_b2b(em, web_url) > 0:
                        found.add(em)

                if any(score_email_b2b(e, web_url) >= 80 for e in found):
                    break
        except Exception:
            pass

    return select_best_email(list(found), web_url)


def build_master():
    print("=" * 70)
    print(" CSDL MLT - CONSOLIDATING AND DEDUPLICATING FOOD DATABASES")
    print("=" * 70)

    input_files = [
        BASE_DIR / "visalietuva_database.csv",
        BASE_DIR / "infolt_database.csv",
        BASE_DIR / "imoneslt_database.csv",
        BASE_DIR / "b2lithuania_database.csv",
        BASE_DIR / "rekvizitai_database.csv",
    ]

    records_by_ico = {}
    records_by_name = {}
    total_raw_rows = 0

    for fpath in input_files:
        if not fpath.exists():
            print(f"[-] File not found (skipped): {fpath.name}")
            continue

        print(f"[+] Loading: {fpath.name}")
        with open(fpath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                total_raw_rows += 1
                count += 1
                comp_name = (row.get("Công ty") or "").strip()
                ico = str(row.get("IČO") or "").strip()
                norm_name = normalize_company_name(comp_name)

                # Match key: priority to ICO
                matched_rec = None
                if ico and ico in records_by_ico:
                    matched_rec = records_by_ico[ico]
                elif norm_name and norm_name in records_by_name:
                    matched_rec = records_by_name[norm_name]

                if matched_rec:
                    # Merge data
                    for field in ["SĐT", "Web", "Email", "Địa chỉ", "Thành phố", "Direktorius", "Nhân sự", "Doanh thu (EUR)"]:
                        if not matched_rec.get(field) and row.get(field):
                            matched_rec[field] = str(row.get(field)).strip()
                    if not matched_rec.get("IČO") and ico:
                        matched_rec["IČO"] = ico
                        records_by_ico[ico] = matched_rec
                    # Merge categories
                    old_cat = matched_rec.get("Category", "")
                    new_cat = row.get("Category", "")
                    if new_cat and new_cat not in old_cat:
                        matched_rec["Category"] = f"{old_cat}; {new_cat}".strip("; ")
                    # Merge sources
                    old_src = matched_rec.get("Source", "")
                    new_src = row.get("Source", "")
                    if new_src and new_src not in old_src:
                        matched_rec["Source"] = f"{old_src}, {new_src}".strip(", ")
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

            print(f"    Loaded {count:,} records.")

    unique_records = list({id(v): v for v in list(records_by_ico.values()) + list(records_by_name.values())}.values())
    print(f"\n[*] Total raw entries: {total_raw_rows:,}")
    print(f"[*] Total unique entities after deduplication: {len(unique_records):,}")

    # Save RAW unified dataset
    with open(RAW_CSV, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        for idx, rec in enumerate(unique_records, 1):
            row_dict = {"No.": idx, **rec}
            writer.writerow(row_dict)
    print(f"[V] Saved unified raw dataset to: {RAW_CSV}")

    # Deep Email Enrichment for entries with Web but no Email
    print("\n[*] Starting Deep Web Email Enrichment for companies with Website...")
    enriched_count = 0
    total_to_scan = sum(1 for r in unique_records if r.get("Web") and not r.get("Email"))
    scanned = 0

    for idx, rec in enumerate(unique_records, 1):
        web = rec.get("Web", "")
        current_email = rec.get("Email", "")
        if web and not current_email:
            scanned += 1
            found_email = crawl_site_for_emails(web)
            if found_email:
                rec["Email"] = found_email
                enriched_count += 1
                print(f"  [+] [{scanned:03d}/{total_to_scan}] {rec['Công ty'][:30]:<30} | {web[:30]:<30} -> {found_email}")
            else:
                if scanned % 10 == 0:
                    print(f"  [-] [{scanned:03d}/{total_to_scan}] Scanned... (+{enriched_count} new emails found)")

            # Incremental checkpoint save every 15 scanned
            if scanned % 15 == 0:
                with_em = [r for r in unique_records if r.get("Email")]
                without_em = [r for r in unique_records if not r.get("Email")]
                interim = with_em + without_em
                for out_path in [ENR_CSV, ROOT_ENR_CSV]:
                    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
                        writer = csv.DictWriter(f, fieldnames=HEADERS)
                        writer.writeheader()
                        for i, r in enumerate(interim, 1):
                            writer.writerow({"No.": i, **r})

        rec["SĐT"] = clean_phone(rec.get("SĐT"))

    print(f"\n[*] Successfully enriched {enriched_count:,} additional B2B emails!")

    # Separate into with_email and without_email to place 100% emails on top
    with_email = [r for r in unique_records if r.get("Email")]
    without_email = [r for r in unique_records if not r.get("Email")]

    final_records = with_email + without_email

    # Save final ENRICHED dataset in csdl_mlt and workspace root
    for out_path in [ENR_CSV, ROOT_ENR_CSV]:
        with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=HEADERS)
            writer.writeheader()
            for idx, rec in enumerate(final_records, 1):
                row_dict = {"No.": idx, **rec}
                writer.writerow(row_dict)

    print("\n" + "=" * 70)
    print(" HARVEST & ENRICHMENT COMPLETED SUCCESSFULLY!")
    print(f" Total Companies: {len(final_records):,}")
    print(f" Companies with Email: {len(with_email):,} ({len(with_email)*100/len(final_records):.1f}%) sorted to TOP!")
    print(f" Local Output: {ENR_CSV}")
    print(f" Root Output: {ROOT_ENR_CSV}")
    print("=" * 70)


if __name__ == "__main__":
    build_master()
