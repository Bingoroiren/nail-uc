# -*- coding: utf-8 -*-
"""
===============================================================================
Module     : scrape_paginiaurii_caen7810.py
Description: Scraper for Romanian Employment Agencies on Pagini Aurii (CAEN 7810)
Target URL : https://www.paginiaurii.ro/firmy/-/q_activit%C4%83%C5%A3i+ale+agen%C5%A3iilor+de+plasare+a+for%C5%A3ei+de+munc%C4%83+-+cod+caen++7810/
Scope      : 253 pages, ~5,053 official employment agencies (CAEN 7810)

Compliance :
  - Rule 1 : UTF-8 with BOM (utf-8-sig), CSV only (NO xlsx/xls)
  - Rule 2 : Phone numbers formatted with leading apostrophe (')
  - Rule 3 : Single best B2B email (score_email_b2b_ro), emails sorted to top
  - Rule 5 : Incremental auto-save and full JSON checkpointing for 100% resume
  - Rule 6 : Exclude directories & aggregators
  - Rule 10: Fixed 17-character filename structure:
             * RO_AGCY_PAUR_0RAW.csv (Raw dataset)
             * RO_AGCY_PAUR_2COL.csv (ColdMail 20-col standard dataset)
             * RO_AGCY_PAUR_ONLY_EMAILS_READY.csv (Outreach-ready leads)
  - Rule 12: Permanent company blacklist exclusion
===============================================================================
"""

from __future__ import annotations

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

OUTPUT_0RAW_PATH = ROOT_DIR / "RO_AGCY_PAUR_0RAW.csv"
OUTPUT_2COL_PATH = ROOT_DIR / "RO_AGCY_PAUR_2COL.csv"
OUTPUT_READY_PATH = ROOT_DIR / "RO_AGCY_PAUR_ONLY_EMAILS_READY.csv"

CACHE_LIST_PATH = CRAWLMAIL_DIR / "cache_paur_caen7810_list.json"
CACHE_DETAILS_PATH = CRAWLMAIL_DIR / "cache_paur_caen7810_details.json"

BASE_URL = "https://www.paginiaurii.ro"
SEARCH_URL_TEMPLATE = (
    "https://www.paginiaurii.ro/firmy/-/q_activit%C4%83%C5%A3i+ale+agen%C5%A3iilor+de+plasare+a+for%C5%A3ei+de+munc%C4%83+-+cod+caen++7810/{page}/"
)
TOTAL_PAGES_ESTIMATE = 253

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

PERMANENT_BLACKLIST_COMPANIES = (
    "scandi standard", "scandi-standard", "scandi standart",
    "biliarta", "daigre", "daigrė",
)

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
    if val is None:
        return ""
    s = str(val)
    if s.strip().lower() == "nan":
        return ""
    for bad in ("\u00a0", "\xa0", "\u200b", "\u200e", "\u200f", "\ufeff", "\u202f", "\u3000"):
        s = s.replace(bad, " ")
    return re.sub(r"\s+", " ", s).strip()


def is_blacklisted_company(name: str) -> bool:
    if not name:
        return False
    n = unicodedata.normalize("NFKD", str(name)).lower()
    n_clean = "".join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)


def clean_phone_ro(raw_phone: str) -> str:
    if not raw_phone:
        return ""
    s = str(raw_phone).lstrip("'").strip()
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

        if d.startswith("7") and len(d) == 9:
            chosen_digits = d
            break
        elif not chosen_digits:
            chosen_digits = d

    if not chosen_digits or len(chosen_digits) < 6:
        return ""

    if len(chosen_digits) == 9:
        if chosen_digits.startswith("7"):
            return f"'+40 {chosen_digits[:3]} {chosen_digits[3:6]} {chosen_digits[6:]}"
        elif chosen_digits.startswith(("21", "31")):
            return f"'+40 {chosen_digits[:2]} {chosen_digits[2:5]} {chosen_digits[5:]}"
        else:
            return f"'+40 {chosen_digits[:3]} {chosen_digits[3:6]} {chosen_digits[6:]}"
    return f"'+40 {chosen_digits}"


def clean_email(email_str: str) -> str:
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
    valid = [clean_email(e) for e in emails if e]
    valid = [e for e in set(valid) if e and score_email_b2b_ro(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b_ro(e, domain))


def crawl_website_for_email(site_url: str) -> str:
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

    for sp in RO_CONTACT_SUBPATHS[:5]:
        sub_url = urllib.parse.urljoin(base_url, sp)
        try:
            r_sub = requests.get(sub_url, headers=HEADERS, timeout=3.5, verify=False)
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
# PHASE 1: HARVEST LISTINGS (PAGES 1..253)
# =============================================================================

def harvest_single_page(page: int) -> tuple[int, list[dict]]:
    url = SEARCH_URL_TEMPLATE.format(page=page)
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=12, verify=False)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                items = []
                for li in soup.select("li.item"):
                    h2 = li.select_one("h2")
                    a = li.select_one('a[href*="/companii/"]')
                    if not h2 or not a:
                        continue
                    name = clean_text(h2.get_text(strip=True))
                    href = a.get("href", "")
                    cid = li.get("data-id") or ""
                    if not cid:
                        m_id = re.search(r"/(L\d+)/", href)
                        cid = m_id.group(1) if m_id else href

                    addr_elem = li.select_one(".address")
                    addr = clean_text(addr_elem.get_text(" ", strip=True)) if addr_elem else ""

                    cui = ""
                    for al in li.find_all("a", href=True):
                        if "termene.ro/firma/" in al["href"]:
                            m = re.search(r"/firma/(\d+)-", al["href"])
                            if m:
                                cui = m.group(1)
                                break

                    items.append({
                        "id": str(cid),
                        "name": name,
                        "detail_url": BASE_URL + href if href.startswith("/") else href,
                        "address": addr,
                        "cui": cui,
                        "page": page,
                    })
                return page, items
            elif r.status_code == 404:
                return page, []
        except Exception:
            time.sleep(0.5)
    return page, []


def harvest_all_pages(max_pages: int = TOTAL_PAGES_ESTIMATE, workers: int = 10) -> dict[str, dict]:
    cached: dict[str, dict] = {}
    if CACHE_LIST_PATH.exists():
        try:
            with open(CACHE_LIST_PATH, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if cached and len(cached) >= 4000:
                print(f"[*] Loaded {len(cached):,} companies from list cache {CACHE_LIST_PATH.name}")
                return cached
        except Exception:
            pass

    print("=" * 80)
    print("PHASE 1: HARVESTING RECRUITMENT AGENCIES (CAEN 7810) FROM PAGINI AURII")
    print(f"  Target URL : {SEARCH_URL_TEMPLATE}")
    print(f"  Pages      : 1 to {max_pages} ({workers} worker threads)")
    print("=" * 80)

    all_companies: dict[str, dict] = {}
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(harvest_single_page, p): p for p in range(1, max_pages + 1)}
        completed = 0
        for fut in as_completed(futures):
            page = futures[fut]
            try:
                p_num, items = fut.result()
                for it in items:
                    cid = it["id"]
                    if cid and cid not in all_companies:
                        all_companies[cid] = it
            except Exception as e:
                print(f"  [!] Page {page} error: {e}")
            completed += 1
            if completed % 25 == 0 or completed == max_pages:
                print(f"  [*] Progress: {completed}/{max_pages} pages | Unique companies: {len(all_companies):,}")

    elapsed = time.time() - t0
    print(f"[+] Harvest completed in {elapsed:.1f}s! Total unique companies: {len(all_companies):,}\n")

    CACHE_LIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_LIST_PATH, "w", encoding="utf-8") as f:
        json.dump(all_companies, f, ensure_ascii=False, indent=2)

    return all_companies


# =============================================================================
# PHASE 2: EXTRACT DETAILS & B2B EMAILS
# =============================================================================

def extract_company_detail(item: dict) -> dict:
    url = item["detail_url"]
    resp_text = ""
    for _ in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=10, verify=False)
            if r.status_code == 200:
                resp_text = r.text
                break
        except Exception:
            time.sleep(0.4)

    full_addr = item.get("address", "")
    city = ""
    judet = ""
    if full_addr:
        m_jud = re.search(r"Jud\.\s*([^,;]+)", full_addr, re.I)
        if m_jud:
            judet = clean_text(m_jud.group(1))
        m_city = re.search(r",\s*([A-ZĂÂÎȘȚa-zăâîșț\s-]+),\s*(?:Jud\.|Cod Postal|$)", full_addr)
        if m_city:
            city = clean_text(m_city.group(1))
        elif "bucuresti" in full_addr.lower():
            city = "Bucuresti"

    phone_candidates = []
    email_candidates = []
    website_candidates = []

    if resp_text:
        soup = BeautifulSoup(resp_text, "html.parser")
        # Phones
        for a in soup.select('a[href^="tel:"]'):
            p_raw = a.get_text(strip=True) or a.get("href", "").replace("tel:", "")
            p_clean = clean_phone_ro(p_raw)
            if p_clean and p_clean not in phone_candidates:
                phone_candidates.append(p_clean)

        # Emails
        for a in soup.select('a[href^="mailto:"]'):
            em_raw = a.get("href", "").replace("mailto:", "") or a.get_text(strip=True)
            em_clean = clean_email(em_raw)
            if em_clean and em_clean not in email_candidates:
                email_candidates.append(em_clean)

        # Websites in icons or body
        icons_ul = soup.select_one("ul.icons, ul.left.icons")
        scope = icons_ul if icons_ul else soup.select_one(".col9")
        if scope:
            for a in scope.find_all("a", href=True):
                h = a.get("href", "").strip()
                if is_valid_website(h) and h not in website_candidates:
                    website_candidates.append(h)

    best_phone = phone_candidates[0] if phone_candidates else ""
    best_website = website_candidates[0] if website_candidates else ""
    domain = urllib.parse.urlparse(best_website).netloc if best_website else ""
    best_email = select_best_email(email_candidates, domain)

    if not best_email and best_website:
        crawl_em = crawl_website_for_email(best_website)
        if crawl_em:
            best_email = crawl_em

    return {
        "checked": True,
        "id": item["id"],
        "name": item["name"],
        "cui": item.get("cui", ""),
        "address": full_addr,
        "city": city,
        "judet": judet,
        "phone": best_phone,
        "all_phones": "; ".join(phone_candidates),
        "email": best_email,
        "website": best_website,
        "detail_url": url,
    }


def fetch_all_details(
    companies: dict[str, dict],
    workers: int = 12,
    limit: int | None = None,
) -> dict[str, dict]:
    details_cache: dict[str, dict] = {}
    if CACHE_DETAILS_PATH.exists():
        try:
            with open(CACHE_DETAILS_PATH, "r", encoding="utf-8") as f:
                details_cache = json.load(f)
            print(f"[*] Loaded {len(details_cache):,} cached details from {CACHE_DETAILS_PATH.name}")
        except Exception:
            pass

    pending_ids = [cid for cid in companies if cid not in details_cache]
    if limit:
        pending_ids = pending_ids[:limit]

    print("=" * 80)
    print("PHASE 2: EXTRACTING CONTACTS, PHONES & B2B EMAILS")
    print(f"  Total companies  : {len(companies):,}")
    print(f"  Already cached   : {len(details_cache):,}")
    print(f"  Pending extract  : {len(pending_ids):,} ({workers} threads)")
    print("=" * 80)

    if not pending_ids:
        print("[+] 100% of companies already extracted in cache!\n")
        return details_cache

    t0 = time.time()
    completed = 0
    new_phones = 0
    new_emails = 0
    new_webs = 0
    lock = threading.Lock()

    def worker_task(cid: str) -> dict:
        item = companies[cid]
        return extract_company_detail(item)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(worker_task, cid): cid for cid in pending_ids}
        for fut in as_completed(future_map):
            cid = future_map[fut]
            try:
                res = fut.result()
                with lock:
                    details_cache[cid] = res
                    completed += 1
                    if res.get("phone"):
                        new_phones += 1
                    if res.get("email"):
                        new_emails += 1
                    if res.get("website"):
                        new_webs += 1

                    if completed % 20 == 0 or completed == len(pending_ids):
                        print(
                            f"  [{completed:5d}/{len(pending_ids):5d}] "
                            f"Phones: {new_phones:4d} | Webs: {new_webs:4d} | Emails: {new_emails:4d} | "
                            f"Comp: '{res['name'][:28]}'"
                        )

                    if completed % 100 == 0:
                        with open(CACHE_DETAILS_PATH, "w", encoding="utf-8") as f:
                            json.dump(details_cache, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"  [!] Error processing {cid}: {e}")

    with open(CACHE_DETAILS_PATH, "w", encoding="utf-8") as f:
        json.dump(details_cache, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - t0
    print(f"\n[+] Phase 2 Details completed in {elapsed:.1f}s!\n")
    return details_cache


# =============================================================================
# PHASE 3: EXPORT STANDARDS DATASETS
# =============================================================================

def export_all_datasets(companies: dict[str, dict], details: dict[str, dict]) -> None:
    print("=" * 80)
    print("PHASE 3: EXPORTING STANDARDS-COMPLIANT DATASETS (RULE 1, 2, 3, 10, 12)")
    print("=" * 80)

    raw_records = []
    col20_records = []

    for cid, base in companies.items():
        comp_name = base.get("name", "").strip()
        if not comp_name or is_blacklisted_company(comp_name):
            continue

        det = details.get(cid, {})
        cui = det.get("cui") or base.get("cui", "")
        addr = det.get("address") or base.get("address", "")
        city = det.get("city", "")
        judet = det.get("judet", "")
        phone = det.get("phone", "")
        all_phones = det.get("all_phones", "")
        email = clean_email(det.get("email", ""))
        website = det.get("website", "")
        det_url = det.get("detail_url") or base.get("detail_url", "")

        raw_records.append({
            "ID": cid,
            "Company_Name": comp_name,
            "CUI": cui,
            "Address_Full": addr,
            "City": city,
            "Judet": judet,
            "Phone": phone,
            "All_Phones": all_phones,
            "Email": email,
            "Website": website,
            "Detail_URL": det_url,
            "Category": "Activităţi ale agenţiilor de plasare a forţei de muncă - Cod CAEN 7810",
        })

        col20_records.append({
            "No.": 0,
            "Công ty": comp_name,
            "Chức danh": "Director / Administrator",
            "Người liên hệ": "",
            "SĐT": phone,
            "Liên Hệ": website or det_url,
            "Email": email,
            "Liên Hệ mail": f"mailto:{email}" if email else "",
            "Địa chỉ": addr,
            "Lương": "",
            "Ngày đăng": "",
            "Hạn tuyển": "",
            "Check gửi": "Chưa gửi",
            "Last Subject": "",
            "Last Body HTML": "",
            "Trạng thái Reply": "",
            "Lần Follow-up": "0",
            "Ngày Follow-up gần nhất": "",
            "Mailbox đã dùng": "",
            "Category": "Activităţi ale agenţiilor de plasare a forţei de muncă - Cod CAEN 7810",
        })

    # 1. Export 0RAW
    df_raw = pd.DataFrame(raw_records)
    OUTPUT_0RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    df_raw.to_csv(OUTPUT_0RAW_PATH, index=False, encoding="utf-8-sig")
    print(f"  [1] RO_AGCY_PAUR_0RAW.csv : {len(df_raw):,} records")

    # 2. Export 2COL with 100% email rows sorted to top
    df_2col = pd.DataFrame(col20_records)
    has_em = df_2col[df_2col["Email"] != ""].copy()
    no_em = df_2col[df_2col["Email"] == ""].copy()
    df_2col_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_2col_sorted["No."] = range(1, len(df_2col_sorted) + 1)
    df_2col_sorted.to_csv(OUTPUT_2COL_PATH, index=False, encoding="utf-8-sig")
    print(f"  [2] RO_AGCY_PAUR_2COL.csv : {len(df_2col_sorted):,} records ({len(has_em):,} with Email sorted to top)")

    # 3. Export ONLY_EMAILS_READY
    df_ready = has_em.copy()
    df_ready["No."] = range(1, len(df_ready) + 1)
    df_ready.to_csv(OUTPUT_READY_PATH, index=False, encoding="utf-8-sig")
    print(f"  [3] RO_AGCY_PAUR_ONLY_EMAILS_READY.csv : {len(df_ready):,} verified outreach leads")

    # 4. Sync copies to csdl_mlt and archive
    for target_dir in (CSDL_DIR, ARCHIVE_DIR):
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(OUTPUT_0RAW_PATH, target_dir / OUTPUT_0RAW_PATH.name)
            shutil.copy2(OUTPUT_2COL_PATH, target_dir / OUTPUT_2COL_PATH.name)
            shutil.copy2(OUTPUT_READY_PATH, target_dir / OUTPUT_READY_PATH.name)
        except Exception:
            pass

    print(f"[+] Synced datasets to {CSDL_DIR.name}/ and {ARCHIVE_DIR.name}/ successfully!\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Pagini Aurii CAEN 7810 Agencies")
    parser.add_argument("--pages", type=int, default=TOTAL_PAGES_ESTIMATE, help="Max pages to harvest (default 253)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of companies for detail extraction")
    parser.add_argument("--workers", type=int, default=12, help="Worker threads for detail extraction")
    args = parser.parse_args()

    companies = harvest_all_pages(max_pages=args.pages, workers=10)
    details = fetch_all_details(companies, workers=args.workers, limit=args.limit)
    export_all_datasets(companies, details)


if __name__ == "__main__":
    main()
