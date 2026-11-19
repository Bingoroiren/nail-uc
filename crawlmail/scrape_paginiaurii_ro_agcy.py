# -*- coding: utf-8 -*-
"""
ROMANIAN EMPLOYMENT AGENCIES SCRAPER & ENRICHER - PAGINI AURII (RO_AGCY)
========================================================================
Target: Pagini Aurii Romania (paginiaurii.ro)
Query : recrutare și plasare de personal (Recruitment & Staffing Agencies)
Input : Existing RO_AGCY_GMAP_2COL.csv + RO_AGCY_GMAP_1ENR.csv
Task  : Scrape all pages, enrich missing contacts, and append new companies.

Outputs (UTF-8 with BOM / csv-only / Rule 1, 2, 3, 5, 8, 10, 11, 12):
  - RO_AGCY_GMAP_2COL.csv (Master 20-col Cold Mail dataset, updated & emails first)
  - RO_AGCY_GMAP_1ENR.csv (Master enriched dataset with metadata, updated)
  - RO_AGCY_GMAP_ONLY_EMAILS_READY.csv (Filter rows with email for outreach)
  - RO_AGCY_PAUR_0RAW.csv (Standalone raw Pagini Aurii dataset)
  - RO_AGCY_PAUR_2COL.csv (Standalone 20-col Cold Mail Pagini Aurii dataset)
  - Synced to csdl_mlt/ and archive/ro_romania/
  - Safety backup: archive/ro_romania/RO_AGCY_GMAP_2COL_pre_paginiaurii_backup.csv
"""

import argparse
import html as html_lib
import json
import os
import re
import shutil
import ssl
import sys
import threading
import time
import unicodedata
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent
CRAWLMAIL_DIR = ROOT_DIR / "crawlmail"
CSDL_DIR = ROOT_DIR / "csdl_mlt"
ARCHIVE_DIR = ROOT_DIR / "archive" / "ro_romania"

TARGET_2COL_PATH = ROOT_DIR / "RO_AGCY_GMAP_2COL.csv"
TARGET_1ENR_PATH = ROOT_DIR / "RO_AGCY_GMAP_1ENR.csv"
TARGET_READY_PATH = ROOT_DIR / "RO_AGCY_GMAP_ONLY_EMAILS_READY.csv"

BACKUP_2COL_PATH = ARCHIVE_DIR / "RO_AGCY_GMAP_2COL_pre_paginiaurii_backup.csv"

PAUR_0RAW_PATH = ROOT_DIR / "RO_AGCY_PAUR_0RAW.csv"
PAUR_2COL_PATH = ROOT_DIR / "RO_AGCY_PAUR_2COL.csv"
PAUR_READY_PATH = ROOT_DIR / "RO_AGCY_PAUR_ONLY_EMAILS_READY.csv"

CACHE_LIST_PATH = CRAWLMAIL_DIR / "cache_paginiaurii_list.json"
CACHE_DETAILS_PATH = CRAWLMAIL_DIR / "cache_paginiaurii_details.json"

BASE_URL = "https://www.paginiaurii.ro"
SEARCH_URL = f"{BASE_URL}/firmy/-/q_recrutare+%C5%9Fi+plasare+de+personal/{{page}}/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

COLDMAIL_COLUMNS = [
    "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ",
    "Email", "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển",
    "Check gửi", "Last Subject", "Last Body HTML", "Trạng thái Reply",
    "Lần Follow-up", "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category",
]

PERMANENT_BLACKLIST_COMPANIES = [
    "scandi standard",
    "scandi-standard",
    "scandi standart",
    "biliarta",
    "daigre",
    "daigrė",
]

BLACKLIST_DOMAINS = {
    "facebook.com", "fb.com", "instagram.com", "linkedin.com", "youtube.com",
    "twitter.com", "x.com", "tiktok.com", "pinterest.com", "google.com", "google.ro",
    "maps.google.com", "goo.gl", "wikipedia.org", "yellowpages", "tripadvisor",
    "booking.com", "yelp.com", "sentry.io", "wix.com", "wixpress.com",
    "paginiaurii.ro", "termene.ro", "listafirme.ro", "topfirme.ro",
    "risco.ro", "totalfirme.ro", "romanian-companies.eu", "infobel.com",
    "cyberfolks.ro", "goldenpages.ie", "goudengids.be", "fcrmedia.ro", "fcrmedia.com",
    "rentasite.ro", "rentavideo.ro", "rentawidget.ro", "anofm.ro",
    "brat.ro", "sinda.com",
}

EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b")
INVALID_EXTS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js",
    ".pdf", ".woff", ".woff2", ".ico", ".mp4",
)

JUNK_EMAIL_DOMAINS = BLACKLIST_DOMAINS | {
    "example.com", "example.org", "example.net", "domain.com", "yourdomain.com",
    "yourcompany.com", "company.com", "email.com", "placeholder.com", "sample.com",
    "sentry.io", "wixpress.com", "wix.com", "wordpress.com",
}

JUNK_USERNAMES = {
    "youremail", "your-email", "your_email", "yourname", "your-name",
    "yourcompany", "someone", "nobody", "john.doe", "johndoe", "jane.doe",
    "username", "sample", "demo", "no-reply", "noreply", "donotreply",
    "privacy", "gdpr", "cookies", "abuse", "security", "mailer-daemon", "sentry",
}

RO_CONTACT_SUBPATHS = (
    "/contact", "/contact-us", "/contact.html", "/contact.php",
    "/despre-noi", "/despre", "/cariere", "/recrutare", "/angajari",
    "/about", "/about-us", "/jobs",
)


def clean_text(val) -> str:
    """Normalize non-breaking/zero-width spaces and collapse whitespace."""
    if val is None:
        return ""
    s = str(val)
    if s.strip().lower() == "nan":
        return ""
    for bad in ("\u00a0", "\xa0", "\u200b", "\u200e", "\u200f", "\ufeff", "\u202f", "\u3000"):
        s = s.replace(bad, " ")
    return re.sub(r"\s+", " ", s).strip()


def is_blacklisted_company(name: str) -> bool:
    """Enforce permanent company blacklist with Unicode NFKD accent folding."""
    if not name:
        return False
    n = unicodedata.normalize("NFKD", str(name)).lower()
    n_clean = "".join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)


def normalize_ro_name(name: str) -> str:
    """Strict Romanian company name normalizer with NFKD diacritics removal and legal forms stripping."""
    if not name:
        return ""
    raw = re.sub(r"\(.*?\)|\[.*?\]", " ", str(name))
    n = unicodedata.normalize("NFKD", raw).lower()
    clean = "".join(c for c in n if not unicodedata.combining(c))
    clean = clean.replace("ș", "s").replace("ş", "s").replace("ț", "t").replace("ţ", "t")

    legal_forms = [
        "societate cu raspundere limitata", "societate pe actiuni",
        "s.r.l.", "srl", "s.a.", "sa", "s.c.", "sc", "s.n.c.", "snc",
        "s.c.s.", "scs", "p.f.a.", "pfa", "i.i.", "ii"
    ]
    for lf in sorted(legal_forms, key=len, reverse=True):
        clean = re.sub(rf"\b{re.escape(lf)}\b", " ", clean)

    clean = re.sub(r"[^a-z0-9]", " ", clean)
    return " ".join(clean.split())


def clean_phone_ro(raw_phone: str) -> str:
    """Normalize Romanian phone numbers with leading apostrophe for CSV integrity."""
    if not raw_phone:
        return ""
    s = str(raw_phone).lstrip("'").strip()
    # If multiple phones separated by comma or slash, take first valid
    parts = re.split(r"[,;/|]", s)
    chosen_digits = ""
    for p in parts:
        d = re.sub(r"[^0-9]", "", p)
        if not d or len(d) < 6:
            continue
        if d.startswith("0040"):
            d = d[4:]
        elif d.startswith("40"):
            d = d[2:]
        elif d.startswith("0"):
            d = d[1:]

        if d.startswith("7") and len(d) == 9:  # Romanian mobile
            chosen_digits = d
            break
        elif not chosen_digits:
            chosen_digits = d

    if not chosen_digits or len(chosen_digits) < 6:
        return ""

    if len(chosen_digits) == 9:
        if chosen_digits.startswith("7"):  # Mobile (e.g. +40 744 109 480)
            return f"'+40 {chosen_digits[:3]} {chosen_digits[3:6]} {chosen_digits[6:]}"
        elif chosen_digits.startswith(("21", "31")):  # Bucharest landline
            return f"'+40 {chosen_digits[:2]} {chosen_digits[2:5]} {chosen_digits[5:]}"
        else:  # County landline (e.g. +40 264 123 456)
            return f"'+40 {chosen_digits[:3]} {chosen_digits[3:6]} {chosen_digits[6:]}"
    return f"'+40 {chosen_digits}"


def clean_email(email_str: str) -> str:
    """Decode escapes, strip u00XX / %20 / nbsp / stuck tail artifacts, and normalize."""
    if not email_str or not isinstance(email_str, str):
        return ""
    e = html_lib.unescape(urllib.parse.unquote(str(email_str).strip()))
    for bad in ("\u00a0", "\xa0", "&nbsp;", "%20", "\u200b", "\u200e", "\u200f", "\ufeff", "\u202f", "\u3000"):
        e = e.replace(bad, "")
    e = re.sub(r"^(?:mailto:\s*|https?://\s*|\\?u00[0-9a-f]{2})+", "", e, flags=re.I)
    e = re.sub(r"\s+", "", e)
    e = e.strip(" .,;:\"'<>[](){}\\/").lower()
    e = re.sub(r"^(?:u00[0-9a-f]{2})+", "", e)
    if re.match(r"^20[a-z][a-z0-9._%+-]*@[a-z0-9.-]+\.[a-z]{2,}$", e) and not e.startswith("202"):
        e = e[2:]
    e = re.sub(r"(\.[a-z]{2,6})www\..*$", r"\1", e, flags=re.I)
    e = re.sub(r"(\.[a-z]{2,6})(?:tel|mob|phone|\+?\d{6,}).*$", r"\1", e, flags=re.I)
    return e.strip(" .,;:\"'<>[](){}\\/")


def is_valid_website(url: str) -> bool:
    """Accept genuine company website while filtering out directories and aggregators."""
    if not url or not isinstance(url, str):
        return False
    u = url.strip().lower()
    if not u.startswith("http"):
        u = "https://" + u
    try:
        domain = urllib.parse.urlparse(u).netloc.replace("www.", "").lower().split(":")[0]
        if not domain or "." not in domain or len(domain) < 4:
            return False
        if any(domain == bad or domain.endswith("." + bad) for bad in BLACKLIST_DOMAINS):
            return False
        return True
    except Exception:
        return False


def score_email_b2b_ro(email: str, domain: str = "") -> int:
    """Score B2B recruitment value of an email for Romanian Manpower Agencies."""
    e = clean_email(email)
    if not e or "@" not in e or any(e.endswith(ext) for ext in INVALID_EXTS):
        return -1
    if not EMAIL_REGEX.match(e):
        return -1
    u, d = e.split("@", 1)
    if len(u) <= 1 or len(d) <= 3:
        return -1
    if d in JUNK_EMAIL_DOMAINS or any(d.endswith("." + jd) for jd in JUNK_EMAIL_DOMAINS):
        return -1
    if u in JUNK_USERNAMES or any(k in u for k in ("youremail", "your-email", "yourname", "placeholder")):
        return -1

    score = 10
    clean_d = domain.lower().replace("www.", "").split("/")[0] if domain else ""
    if clean_d and (clean_d in d or d in clean_d):
        score += 50
    elif d.endswith(".ro"):
        score += 30

    # Recruitment / Staffing priority
    if any(k in u for k in ("recrutare", "cariere", "hr", "jobs", "munca", "angajari", "personal", "plasare")):
        score += 55
    elif any(k in u for k in ("director", "manager", "ceo", "administrator", "general", "conducere")):
        score += 45
    elif any(k in u for k in ("office", "contact", "info", "secretariat", "receptie")):
        score += 40
    elif any(k in u for k in ("comercial", "vanzari", "sales", "clienti")):
        score += 35
    elif "." in u and score >= 60:
        score += 25
    elif d in ("gmail.com", "yahoo.com", "yahoo.ro", "mail.com"):
        score += 15
    elif any(k in u for k in ("support", "admin", "contabilitate", "facturare")):
        score += 5

    return score


def select_best_email(emails: list[str] | set[str], domain: str = "") -> str:
    """Pick the single highest-scoring valid B2B email."""
    valid = [clean_email(e) for e in emails if e]
    valid = [e for e in set(valid) if e and score_email_b2b_ro(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b_ro(e, domain))


def crawl_website_for_email(site_url: str) -> str:
    """Fallback crawler to search homepage and contact subpaths of the agency website."""
    if not is_valid_website(site_url):
        return ""
    u_str = site_url.strip()
    if not u_str.startswith("http"):
        u_str = "https://" + u_str

    try:
        parsed = urllib.parse.urlparse(u_str)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        domain = parsed.netloc
    except Exception:
        return ""

    found_emails = set()
    try:
        r = requests.get(u_str, headers=HEADERS, timeout=4.5, verify=False)
        if r.status_code == 200:
            for em in EMAIL_REGEX.findall(r.text):
                found_emails.add(clean_email(em))
            best = select_best_email(found_emails, domain)
            if best and score_email_b2b_ro(best, domain) >= 90:
                return best
    except Exception:
        pass

    # Check contact subpages
    for sp in RO_CONTACT_SUBPATHS[:6]:
        sub_url = urllib.parse.urljoin(base_url, sp)
        try:
            r_sub = requests.get(sub_url, headers=HEADERS, timeout=4.0, verify=False)
            if r_sub.status_code == 200:
                for em in EMAIL_REGEX.findall(r_sub.text):
                    found_emails.add(clean_email(em))
                best = select_best_email(found_emails, domain)
                if best and score_email_b2b_ro(best, domain) >= 90:
                    return best
        except Exception:
            pass

    return select_best_email(found_emails, domain)


# =============================================================================
# PHASE 1: HARVEST ALL RESULT PAGES (paginiaurii.ro)
# =============================================================================

def harvest_paginiaurii_list() -> dict[str, dict]:
    """Scrape all result pages from paginiaurii.ro under the recruitment query."""
    if CACHE_LIST_PATH.exists():
        try:
            with open(CACHE_LIST_PATH, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if cached and len(cached) >= 200:
                print(f"[*] Loaded {len(cached):,} companies from list cache {CACHE_LIST_PATH.name}")
                return cached
        except Exception as e:
            print(f"[!] Could not load list cache: {e}")

    print("=" * 80)
    print("PHASE 1: HARVESTING RECRUITMENT AGENCIES FROM PAGINI AURII ROMANIA")
    print("  Query URL : https://www.paginiaurii.ro/firmy/-/q_recrutare+%C5%9Fi+plasare+de+personal/{page}/")
    print("=" * 80)

    all_companies: dict[str, dict] = {}
    session = requests.Session()

    for page in range(1, 25):
        url = SEARCH_URL.format(page=page)
        try:
            r = session.get(url, headers=HEADERS, timeout=15, verify=False)
            if r.status_code != 200:
                print(f"  [Page {page}] HTTP Status {r.status_code}. Stopping.")
                break

            soup = BeautifulSoup(r.text, "html.parser")
            company_links = soup.select('a[href*="/companii/"]')
            if not company_links:
                print(f"  [Page {page}] No company links found. End of listings.")
                break

            page_new = 0
            for a in company_links:
                href = a.get("href", "")
                name = clean_text(a.get_text(strip=True))
                if not name or len(name) < 2 or not href.startswith("/companii/"):
                    continue

                m_id = re.search(r"/(L\d+)/", href)
                cid = m_id.group(1) if m_id else href

                if cid not in all_companies:
                    full_detail_url = BASE_URL + href
                    all_companies[cid] = {
                        "id": cid,
                        "name": name,
                        "detail_url": full_detail_url,
                        "page": page,
                    }
                    page_new += 1

            print(f"  [Page {page:2d}] +{page_new:2d} new companies (Cumulative: {len(all_companies):,})")
            if page_new == 0:
                break
        except Exception as err:
            print(f"  [Page {page}] Error: {err}")
            break

        time.sleep(0.4)

    CACHE_LIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_LIST_PATH, "w", encoding="utf-8") as f:
        json.dump(all_companies, f, ensure_ascii=False, indent=2)

    print(f"[+] Phase 1 Complete! Total unique agencies harvested: {len(all_companies):,}\n")
    return all_companies


# =============================================================================
# PHASE 2: EXTRACT DETAILS FROM EACH COMPANY PAGE
# =============================================================================

def extract_paur_detail(session: requests.Session, cid: str, base_item: dict) -> dict:
    """Fetch company detail page on paginiaurii.ro and extract contacts, website, address."""
    url = base_item["detail_url"]
    resp_text = ""
    for _ in range(3):
        try:
            r = session.get(url, headers=HEADERS, timeout=15, verify=False)
            if r.status_code == 200:
                resp_text = r.text
                break
        except Exception:
            time.sleep(0.5)

    if not resp_text:
        return {"checked": True, "error": "Fetch failed", **base_item}

    soup = BeautifulSoup(resp_text, "html.parser")

    # Name
    h1 = soup.select_one("h1")
    comp_name = clean_text(h1.get_text(strip=True)) if h1 else base_item["name"]

    # Contact container on paginiaurii.ro
    icons_ul = soup.select_one("ul.icons, ul.left.icons")

    # Address
    full_address = ""
    if icons_ul:
        addr_elem = icons_ul.select_one("li.address")
        if addr_elem:
            full_address = clean_text(addr_elem.get_text(" ", strip=True))
    if not full_address:
        addr_elem = soup.select_one('.address, [itemprop="address"], .company-address')
        if addr_elem:
            full_address = clean_text(addr_elem.get_text(" ", strip=True))

    # Extract City / Judet from address
    city = ""
    judet = ""
    m_jud = re.search(r"Jud\.\s*([^,;]+)", full_address, re.I)
    if m_jud:
        judet = clean_text(m_jud.group(1))
    m_city = re.search(r",\s*([A-ZĂÂÎȘȚa-zăâîșț\s-]+),\s*Cod Postal", full_address)
    if m_city:
        city = clean_text(m_city.group(1))

    # CUI / Fiscal Code (often in termene.ro link)
    cui = ""
    for a in soup.find_all("a", href=True):
        if "termene.ro/firma/" in a["href"]:
            m_cui = re.search(r"/firma/(\d+)-", a["href"])
            if m_cui:
                cui = m_cui.group(1)
                break

    # Phone numbers
    phone_candidates = []
    scope_phones = icons_ul.select('a[href^="tel:"]') if icons_ul else soup.select('a[href^="tel:"]')
    for a in scope_phones:
        ph_raw = a.get_text(strip=True) or a.get("href", "").replace("tel:", "").strip()
        ph_clean = clean_phone_ro(ph_raw)
        if ph_clean and ph_clean not in phone_candidates:
            phone_candidates.append(ph_clean)

    # Email addresses
    email_candidates = []
    scope_emails = icons_ul.select('a[href^="mailto:"]') if icons_ul else soup.select('a[href^="mailto:"]')
    for a in scope_emails:
        em_raw = a.get("href", "").replace("mailto:", "").strip() or a.get_text(strip=True)
        em_clean = clean_email(em_raw)
        if em_clean and em_clean not in email_candidates:
            email_candidates.append(em_clean)

    # Websites
    site_candidates = []
    if icons_ul:
        scope_sites = icons_ul.select('a[data-ta="LinkClick"], a[itemprop="url"], i.icon-link ~ a, li a')
        for a in scope_sites:
            h = a.get("href", "").strip()
            if is_valid_website(h) and h not in site_candidates:
                site_candidates.append(h)
    else:
        for a in soup.find_all("a", href=True):
            h = a.get("href", "").strip()
            if is_valid_website(h) and h not in site_candidates:
                site_candidates.append(h)

    best_website = site_candidates[0] if site_candidates else ""
    best_phone = phone_candidates[0] if phone_candidates else ""
    domain = urllib.parse.urlparse(best_website).netloc if best_website else ""
    best_email = select_best_email(email_candidates, domain)

    # Fallback crawl website if no direct email on Pagini Aurii
    if not best_email and best_website:
        crawl_em = crawl_website_for_email(best_website)
        if crawl_em:
            best_email = crawl_em

    # Description
    desc_elem = soup.select_one(".description, .activities, .about-company, [itemprop='description']")
    desc = clean_text(desc_elem.get_text(" ", strip=True)) if desc_elem else ""

    return {
        "checked": True,
        "id": cid,
        "Company_Name": comp_name,
        "CUI": cui,
        "Address_Full": full_address,
        "City": city,
        "Judet": judet,
        "Phone": best_phone,
        "All_Phones": "; ".join(phone_candidates),
        "Email": best_email,
        "Website": best_website,
        "Detail_URL": url,
        "Description": desc[:250],
    }


def fetch_all_paur_details(companies: dict[str, dict], workers: int = 8) -> dict[str, dict]:
    """Fetch detail page for all discovered Pagini Aurii companies with caching."""
    details_cache: dict[str, dict] = {}
    if CACHE_DETAILS_PATH.exists():
        try:
            with open(CACHE_DETAILS_PATH, "r", encoding="utf-8") as f:
                details_cache = json.load(f)
            print(f"[*] Loaded {len(details_cache):,} cached details from {CACHE_DETAILS_PATH.name}")
        except Exception as e:
            print(f"[!] Could not load details cache: {e}")

    pending_ids = [cid for cid in companies if cid not in details_cache]

    print("=" * 80)
    print("PHASE 2: FETCHING DETAIL PAGES & EXTRACTING CONTACTS")
    print(f"  Total Companies : {len(companies):,}")
    print(f"  Already Cached  : {len(details_cache):,}")
    print(f"  Pending Fetch   : {len(pending_ids):,}")
    print(f"  Workers         : {workers}")
    print("=" * 80)

    if pending_ids:
        lock = threading.Lock()
        processed = 0
        newly_emails = 0

        thread_local = threading.local()

        def get_session():
            if not hasattr(thread_local, "session"):
                thread_local.session = requests.Session()
            return thread_local.session

        def worker_task(cid):
            s = get_session()
            base = companies[cid]
            return extract_paur_detail(s, cid, base)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(worker_task, cid): cid for cid in pending_ids}
            for fut in as_completed(futures):
                cid = futures[fut]
                try:
                    res = fut.result()
                except Exception as err:
                    res = {"checked": True, "id": cid, "error": str(err), **companies[cid]}

                with lock:
                    processed += 1
                    details_cache[cid] = res
                    if res.get("Email"):
                        newly_emails += 1
                        print(f"  [{processed:3d}/{len(pending_ids)}] [+] {res['Company_Name']} -> {res['Email']} | Phone: {res.get('Phone', '')}")
                    elif res.get("Phone"):
                        print(f"  [{processed:3d}/{len(pending_ids)}] [~] {res['Company_Name']} -> Phone: {res['Phone']} | No email")
                    else:
                        print(f"  [{processed:3d}/{len(pending_ids)}] [-] {res['Company_Name']} -> No public phone/email")

                    if processed % 20 == 0:
                        CACHE_DETAILS_PATH.parent.mkdir(parents=True, exist_ok=True)
                        tmp_path = CACHE_DETAILS_PATH.with_suffix(".tmp")
                        with open(tmp_path, "w", encoding="utf-8") as f:
                            json.dump(details_cache, f, ensure_ascii=False, indent=2)
                        os.replace(tmp_path, CACHE_DETAILS_PATH)

        CACHE_DETAILS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_DETAILS_PATH, "w", encoding="utf-8") as f:
            json.dump(details_cache, f, ensure_ascii=False, indent=2)

    total_with_email = sum(1 for v in details_cache.values() if clean_email(v.get("Email", "")))
    print(f"\n[+] Phase 2 Complete! Total details: {len(details_cache):,} (With Email: {total_with_email:,})\n")
    return details_cache


# =============================================================================
# PHASE 3: MATCH & SUPPLEMENT RO_AGCY_GMAP_2COL.CSV
# =============================================================================

GENERIC_RO_WORDS = {
    "consult", "consulting", "solutions", "solution", "group", "servicii",
    "services", "service", "agency", "agentie", "recruitment", "recrutare",
    "resurse", "umane", "human", "resources", "international", "romania",
    "partner", "partners", "team", "management", "invest", "global",
}


def strict_name_match(name1: str, name2: str) -> bool:
    """Strict name matcher for Romanian companies excluding generic false-positives."""
    n1 = normalize_ro_name(name1)
    n2 = normalize_ro_name(name2)
    if not n1 or not n2:
        return False
    if n1 == n2:
        return True

    tok1 = set(n1.split())
    tok2 = set(n2.split())
    if not tok1 or not tok2:
        return False

    # Distinctive tokens
    dist1 = tok1 - GENERIC_RO_WORDS
    dist2 = tok2 - GENERIC_RO_WORDS
    if dist1 and dist2:
        if dist1 == dist2:
            return True
        if len(dist1) >= 2 and len(dist1 & dist2) >= len(dist1) * 0.8:
            return True
    elif len(tok1) >= 3 and len(tok1 & tok2) >= len(tok1) * 0.8 and len(tok2 & tok1) >= len(tok2) * 0.8:
        return True

    return False


def supplement_and_merge_datasets(paur_records: list[dict]) -> None:
    """Match Pagini Aurii records against RO_AGCY_GMAP_2COL.csv, enrich existing, append new."""
    print("=" * 80)
    print("PHASE 3: MATCHING & SUPPLEMENTING RO_AGCY_GMAP_2COL.CSV")
    print("=" * 80)

    if not TARGET_2COL_PATH.exists():
        print(f"[!] Target file not found: {TARGET_2COL_PATH}")
        return

    # Safety Backup
    if not BACKUP_2COL_PATH.exists():
        BACKUP_2COL_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(TARGET_2COL_PATH, BACKUP_2COL_PATH)
        print(f"[+] Safety backup created: {BACKUP_2COL_PATH.relative_to(ROOT_DIR)}")

    df_2col = pd.read_csv(TARGET_2COL_PATH, encoding="utf-8-sig", dtype=str).fillna("")
    print(f"[*] Loaded {len(df_2col):,} existing rows from {TARGET_2COL_PATH.name}")

    initial_emails = (df_2col["Email"] != "").sum()
    print(f"[*] Initial companies with email: {initial_emails:,} ({initial_emails * 100 / len(df_2col):.1f}%)")

    # Build CUI index and Normalized Name index
    cui_index = {}
    name_index = {}
    for idx, row in df_2col.iterrows():
        c_name = row.get("Công ty", "")
        norm = normalize_ro_name(c_name)
        if norm:
            name_index[norm] = idx

    matched_count = 0
    enriched_emails = 0
    enriched_phones = 0
    enriched_webs = 0
    new_rows = []

    for item in paur_records:
        p_name = item.get("Company_Name", "")
        if is_blacklisted_company(p_name):
            continue

        p_norm = normalize_ro_name(p_name)
        p_email = clean_email(item.get("Email", ""))
        p_phone = clean_phone_ro(item.get("Phone", ""))
        p_web = item.get("Website", "")
        p_addr = item.get("Address_Full", "") or f"{item.get('City', '')}, {item.get('Judet', '')}, Romania"

        # Check match
        matched_idx = None
        if p_norm in name_index:
            matched_idx = name_index[p_norm]
        else:
            for k, idx in name_index.items():
                if strict_name_match(p_norm, k):
                    matched_idx = idx
                    break

        if matched_idx is not None:
            matched_count += 1
            # Enrich existing row
            cur_email = clean_email(df_2col.at[matched_idx, "Email"])
            cur_phone = clean_phone_ro(df_2col.at[matched_idx, "SĐT"])
            cur_web = str(df_2col.at[matched_idx, "Liên Hệ"]).strip()

            if not cur_email and p_email:
                df_2col.at[matched_idx, "Email"] = p_email
                df_2col.at[matched_idx, "Liên Hệ mail"] = f"mailto:{p_email}"
                enriched_emails += 1

            if not cur_phone and p_phone:
                df_2col.at[matched_idx, "SĐT"] = p_phone
                enriched_phones += 1

            if (not cur_web or not cur_web.startswith("http")) and p_web:
                df_2col.at[matched_idx, "Liên Hệ"] = p_web
                enriched_webs += 1

            if not clean_text(df_2col.at[matched_idx, "Địa chỉ"]) and p_addr:
                df_2col.at[matched_idx, "Địa chỉ"] = p_addr
        else:
            # Brand new company from Pagini Aurii
            new_rows.append({
                "No.": "",
                "Công ty": p_name,
                "Chức danh": "Director / Administrator",
                "Người liên hệ": "",
                "SĐT": p_phone,
                "Liên Hệ": p_web if p_web else item.get("Detail_URL", ""),
                "Email": p_email,
                "Liên Hệ mail": f"mailto:{p_email}" if p_email else (p_web or item.get("Detail_URL", "")),
                "Địa chỉ": p_addr or "Romania",
                "Lương": "",
                "Ngày đăng": "2026-11",
                "Hạn tuyển": "",
                "Check gửi": "Chưa gửi",
                "Last Subject": "",
                "Last Body HTML": "",
                "Trạng thái Reply": "",
                "Lần Follow-up": "",
                "Ngày Follow-up gần nhất": "",
                "Mailbox đã dùng": "",
                "Category": "Recruitment & Staffing Agency (Romania)",
            })

    print(f"\n[*] Matching Summary:")
    print(f"    - Matched with existing rows : {matched_count:,}")
    print(f"    - Enriched missing emails    : +{enriched_emails:,}")
    print(f"    - Enriched missing phones    : +{enriched_phones:,}")
    print(f"    - Enriched missing websites  : +{enriched_webs:,}")
    print(f"    - Brand new agencies to add  : +{len(new_rows):,}")

    # Append new rows
    if new_rows:
        df_new = pd.DataFrame(new_rows)
        df_combined = pd.concat([df_2col, df_new], ignore_index=True)
    else:
        df_combined = df_2col

    # Standards: UTF-8 BOM, '+' phone prefix, email-first sorting
    df_combined["Công ty"] = df_combined["Công ty"].apply(clean_text)
    df_combined = df_combined[~df_combined["Công ty"].apply(is_blacklisted_company)].reset_index(drop=True)

    df_combined["Email"] = df_combined["Email"].apply(clean_email)
    df_combined["SĐT"] = df_combined["SĐT"].apply(clean_phone_ro)

    for col in df_combined.columns:
        df_combined[col] = df_combined[col].apply(clean_text)

    # Sort 100% of rows with email on top
    has_email_df = df_combined[df_combined["Email"] != ""].copy()
    no_email_df = df_combined[df_combined["Email"] == ""].copy()
    df_sorted = pd.concat([has_email_df, no_email_df], ignore_index=True)
    df_sorted["No."] = range(1, len(df_sorted) + 1)

    # Save to RO_AGCY_GMAP_2COL.csv
    df_sorted.to_csv(TARGET_2COL_PATH, index=False, encoding="utf-8-sig")

    # Save to ONLY_EMAILS_READY
    df_ready = df_sorted[df_sorted["Email"] != ""].copy()
    df_ready["No."] = range(1, len(df_ready) + 1)
    df_ready.to_csv(TARGET_READY_PATH, index=False, encoding="utf-8-sig")

    # Export standalone Pagini Aurii datasets
    df_paur_raw = pd.DataFrame(paur_records)
    df_paur_raw.to_csv(PAUR_0RAW_PATH, index=False, encoding="utf-8-sig")

    paur_2col_rows = []
    for item in paur_records:
        p_name = item.get("Company_Name", "")
        p_email = clean_email(item.get("Email", ""))
        p_phone = clean_phone_ro(item.get("Phone", ""))
        p_web = item.get("Website", "")
        p_addr = item.get("Address_Full", "") or f"{item.get('City', '')}, {item.get('Judet', '')}, Romania"

        paur_2col_rows.append({
            "No.": "",
            "Công ty": p_name,
            "Chức danh": "Director / Administrator",
            "Người liên hệ": "",
            "SĐT": p_phone,
            "Liên Hệ": p_web if p_web else item.get("Detail_URL", ""),
            "Email": p_email,
            "Liên Hệ mail": f"mailto:{p_email}" if p_email else (p_web or item.get("Detail_URL", "")),
            "Địa chỉ": p_addr or "Romania",
            "Lương": "",
            "Ngày đăng": "2026-11",
            "Hạn tuyển": "",
            "Check gửi": "Chưa gửi",
            "Last Subject": "",
            "Last Body HTML": "",
            "Trạng thái Reply": "",
            "Lần Follow-up": "",
            "Ngày Follow-up gần nhất": "",
            "Mailbox đã dùng": "",
            "Category": "Recruitment & Staffing Agency (Romania)",
        })
    df_paur_2col = pd.DataFrame(paur_2col_rows)
    df_paur_2col_em = df_paur_2col[df_paur_2col["Email"] != ""].copy()
    df_paur_2col_no = df_paur_2col[df_paur_2col["Email"] == ""].copy()
    df_paur_sorted = pd.concat([df_paur_2col_em, df_paur_2col_no], ignore_index=True)
    df_paur_sorted["No."] = range(1, len(df_paur_sorted) + 1)
    df_paur_sorted.to_csv(PAUR_2COL_PATH, index=False, encoding="utf-8-sig")

    df_paur_ready = df_paur_sorted[df_paur_sorted["Email"] != ""].copy()
    df_paur_ready["No."] = range(1, len(df_paur_ready) + 1)
    df_paur_ready.to_csv(PAUR_READY_PATH, index=False, encoding="utf-8-sig")

    # Sync to csdl_mlt/ and archive/ro_romania/
    for extra_dir in (CSDL_DIR, ARCHIVE_DIR):
        extra_dir.mkdir(parents=True, exist_ok=True)
        for p in (TARGET_2COL_PATH, TARGET_READY_PATH, PAUR_0RAW_PATH, PAUR_2COL_PATH, PAUR_READY_PATH):
            try:
                shutil.copy2(p, extra_dir / p.name)
            except Exception:
                pass

    final_total = len(df_sorted)
    final_emails = len(has_email_df)
    print("\n" + "=" * 80)
    print("DONE UPDATING RO_AGCY_GMAP_2COL.CSV!")
    print(f"  Previous rows    : {len(df_2col):,} (Emails: {initial_emails:,})")
    print(f"  Final total rows : {final_total:,} (Emails: {final_emails:,} - {final_emails * 100 / final_total:.1f}%)")
    print(f"  Net new emails   : +{final_emails - initial_emails:,}")
    print(f"  Updated files    : {TARGET_2COL_PATH.name}, {TARGET_READY_PATH.name}")
    print(f"  Standalone files : {PAUR_0RAW_PATH.name}, {PAUR_2COL_PATH.name}")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Scrape Pagini Aurii RO and supplement RO_AGCY_GMAP_2COL.csv")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent workers for detail fetching (default: 8)")
    parser.add_argument("--skip-harvest", action="store_true", help="Skip Phase 1 and use cached list")
    parser.add_argument("--re-merge", action="store_true", help="Re-merge existing cached details into CSVs without fetching")
    args = parser.parse_args()

    if args.re_merge and CACHE_DETAILS_PATH.exists():
        with open(CACHE_DETAILS_PATH, "r", encoding="utf-8") as f:
            details = json.load(f)
        supplement_and_merge_datasets(list(details.values()))
        return

    # 1. Harvest List
    companies = harvest_paginiaurii_list()

    # 2. Extract Details
    details = fetch_all_paur_details(companies, workers=args.workers)

    # 3. Match and Supplement
    supplement_and_merge_datasets(list(details.values()))


if __name__ == "__main__":
    main()
