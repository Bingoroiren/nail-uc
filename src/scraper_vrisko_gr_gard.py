# -*- coding: utf-8 -*-
"""
VRISKO.GR DIRECTORY SCRAPER & ENRICHER - GREEK GARDEN CONSTRUCTION (GR_GARD_VRIS)
==================================================================================
Target  : https://www.vrisko.gr/en/dir/garden-construction/ (Garden Construction Greece)
Country : Greece (GR) | Industry: Garden Construction (GARD) | Source: Vrisko (VRIS)

Layers:
  1. Directory Pagination Scraper (Pages 0-9, 200 listings):
     - Company Name, Listing Type (AdvListing vs FreeListing), Detail URL, Address, Categories.
  2. Detail Page Scraper (AdvDetails & FreeDetails):
     - AdvListing: direct 'mailTo:' email, Phone (.phones-btn), Website, Full Address.
     - FreeListing: Phone, Website (a.websiteMarker_ClassForLogging), Address, Email contact link.
  3. Deep Website B2B Email Crawler (Greek localized):
     - Priority 10 DOM contact links (/epikoinonia, /contact, /about, /sxetika)
     - Cloudflare decode, obfuscated mail decode, Greek B2B scoring.

Outputs (UTF-8 with BOM, utf-8-sig):
  - GR_GARD_VRIS_0RAW.csv (Raw scraped directory records)
  - GR_GARD_VRIS_1ENR.csv (Enriched with website emails + normalized phones)
  - GR_GARD_VRIS_2COL.csv (Standard 20-column Cold Mail format, with_email sorted first)
  - GR_GARD_VRIS_ONLY_EMAILS_READY.csv (Verified ready-to-send leads)
  - gr_greece/GR_GARD_VRIS_*.csv (Organized copy)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import shutil
import sys
import time
import unicodedata
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import curl_cffi.requests as requests
import pandas as pd
from bs4 import BeautifulSoup

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent
GR_DIR = ROOT_DIR / "gr_greece"
CRAWLMAIL_DIR = ROOT_DIR / "crawlmail"

BASE_CATEGORY_URL = "https://www.vrisko.gr/en/dir/garden-construction/"
CACHE_FILE = CRAWLMAIL_DIR / "cache_scraper_vrisko_gr_gard.json"

OUTPUT_0RAW_PATH = ROOT_DIR / "GR_GARD_VRIS_0RAW.csv"
OUTPUT_1ENR_PATH = ROOT_DIR / "GR_GARD_VRIS_1ENR.csv"
OUTPUT_2COL_PATH = ROOT_DIR / "GR_GARD_VRIS_2COL.csv"
OUTPUT_READY_PATH = ROOT_DIR / "GR_GARD_VRIS_ONLY_EMAILS_READY.csv"

COLDMAIL_COLUMNS = [
    "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ",
    "Email", "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển",
    "Check gửi", "Last Subject", "Last Body HTML", "Trạng thái Reply",
    "Lần Follow-up", "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category",
]

PERMANENT_BLACKLIST_COMPANIES = (
    "scandi standard", "scandi-standard", "scandi standart",
    "biliarta", "daigre", "daigre",
)

INVALID_EXTS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".css", ".js", ".pdf", ".woff", ".woff2", ".ico", ".mp4", ".mp3", ".zip",
)

JUNK_EMAIL_DOMAINS = {
    "example.com", "example.org", "domain.com", "yourdomain.com",
    "yourcompany.com", "email.com", "sentry.io", "wixpress.com", "wix.com",
    "wordpress.com", "schema.org", "google.com", "facebook.com", "instagram.com",
    "vrisko.gr", "media.vrisko.gr", "11880.gr", "webador.com",
}

JUNK_USERNAMES = {
    "youremail", "your-email", "yourname", "someone", "nobody", "john.doe",
    "no-reply", "noreply", "donotreply", "privacy", "gdpr", "abuse", "sentry",
}

SOCIAL_OR_DIRECTORY_DOMAINS = (
    "facebook.com", "fb.com", "instagram.com", "linkedin.com", "youtube.com",
    "twitter.com", "x.com", "tiktok.com", "vrisko.gr", "google.com", "maps.google.com",
)

GR_CONTACT_KEYWORDS_P10 = (
    "epikoinonia", "epikoinoniste", "contact", "contacts", "contact-us",
    "epikoinonisi", "about", "about-us", "sxetika", "etairia", "profil",
)
GR_SECONDARY_KEYWORDS_P5 = (
    "ypiresies", "services", "erga", "projects", "kipoi", "kataskevi",
    "fytoria", "garden", "syntirisi", "team", "omada",
)
GR_GUESS_SUBPATHS = (
    "/contact", "/contact/", "/epikoinonia", "/epikoinonia/",
    "/el/epikoinonia", "/el/contact", "/about", "/about-us",
    "/sxetika", "/el/about", "/contact-us",
)

EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def clean_text(val) -> str:
    """Normalize text, replace non-breaking spaces and strip excess whitespace."""
    if val is None or pd.isna(val):
        return ""
    s = str(val).replace("\u00a0", " ").replace("\xa0", " ").replace("&nbsp;", " ")
    s = s.replace("\u200b", "").replace("\ufeff", "")
    return re.sub(r"\s+", " ", s).strip()


def is_blacklisted_company(name: str) -> bool:
    """Check against workspace permanent blacklist."""
    if not name:
        return False
    n = unicodedata.normalize("NFKD", str(name)).lower()
    n_clean = "".join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)


def clean_email(email_str: str) -> str:
    """Clean URL encoding and extraneous whitespace from email strings."""
    if not email_str:
        return ""
    em = urllib.parse.unquote(str(email_str)).strip()
    em = re.sub(r"^[\s%20\xa0\u00a0\u200b]+|[\s%20\xa0\u00a0\u200b]+$", "", em)
    em = em.replace(" ", "").replace("%20", "").replace("\xa0", "").replace("\u00a0", "")
    if re.match(r"^20[a-zA-Z0-9._%+-]+@", em):
        em = em[2:]
    return em.lower()


def normalize_gr_phones(raw_phone_str: str) -> tuple[str, str]:
    """
    Normalize Greek phone numbers and prefix with single quote (').
    Landlines: 10 digits starting with 2 (e.g. 210xxxxxxx, 2310xxxxxx, 27410xxxxx)
    Mobiles: 10 digits starting with 69 (e.g. 697xxxxxxx, 694xxxxxxx)
    """
    cleaned = clean_text(raw_phone_str)
    if not cleaned:
        return "", ""

    # Match 10-digit Greek numbers with optional +30 or 0030 prefix
    pattern = re.compile(r"(?:\+30|0030)?\s*([26]\d{9})\b")
    matches = pattern.findall(re.sub(r"[\s.-]", "", cleaned))

    if not matches:
        # Fallback: extract any 10-digit sequence
        matches = re.findall(r"\b[26]\d{9}\b", re.sub(r"[^\d]", " ", cleaned))

    unique_phones = []
    for ph in matches:
        formatted = f"'{ph}"
        if formatted not in unique_phones:
            unique_phones.append(formatted)

    primary = unique_phones[0] if unique_phones else (f"'{cleaned}" if cleaned else "")
    all_phones = "; ".join(unique_phones) if unique_phones else primary
    return primary, all_phones


def ensure_phone_quote(phone: str) -> str:
    """Ensure every non-empty phone starts with single quote (')."""
    p = clean_text(phone)
    if not p:
        return ""
    return p if p.startswith("'") else f"'{p}"


def decode_cf_hex(cf_hex: str) -> str:
    """Decode Cloudflare data-cfemail XOR encoded email."""
    if not cf_hex or len(cf_hex) < 4:
        return ""
    try:
        key = int(cf_hex[:2], 16)
        return "".join(chr(int(cf_hex[i : i + 2], 16) ^ key) for i in range(2, len(cf_hex), 2))
    except Exception:
        return ""


def is_valid_website(url: str) -> bool:
    """Reject social media, directory, and invalid URLs."""
    u = clean_text(url).lower()
    if not u:
        return False
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    try:
        netloc = urllib.parse.urlparse(u).netloc.lower()
    except Exception:
        return False
    if not netloc or "." not in netloc:
        return False
    if any(bad in netloc for bad in SOCIAL_OR_DIRECTORY_DOMAINS):
        return False
    if any(u.endswith(ext) for ext in INVALID_EXTS):
        return False
    return True


def normalize_website_url(url: str) -> str:
    """Normalize website string with https:// scheme when valid."""
    u = clean_text(url)
    if not u:
        return ""
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u if is_valid_website(u) else ""


def is_facebook_url(url: str) -> bool:
    """Check if URL points to a company Facebook page."""
    u = clean_text(url).lower()
    if not u or not any(k in u for k in ("facebook.com/", "fb.com/")):
        return False
    if any(x in u for x in ("sharer.php", "/share", "tr?", "plugins/", "/policies", "/help")):
        return False
    return True


def score_email_b2b_gr(email: str, website_domain: str = "") -> int:
    """Score Greek B2B garden construction emails; return -1 for junk/template."""
    e = clean_email(email)
    if not e or not EMAIL_REGEX.fullmatch(e):
        return -1
    u, d = e.split("@", 1)
    if d in JUNK_EMAIL_DOMAINS or any(d.endswith("." + jd) for jd in JUNK_EMAIL_DOMAINS):
        return -1
    if u in JUNK_USERNAMES or any(k in u for k in ("youremail", "yourname", "placeholder")):
        return -1
    if any(e.endswith(ext) for ext in INVALID_EXTS):
        return -1

    score = 10
    clean_dom = website_domain.lower().replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
    if clean_dom and (clean_dom in d or d in clean_dom):
        score += 50

    if u in ("info", "contact", "epikoinonia", "mail", "office", "sales"):
        score += 45
    elif u in ("ergasies", "kipoi", "geoponos", "kataskevi", "syntirisi", "services"):
        score += 40
    elif "." in u and score >= 60:
        score += 25
    elif d in ("gmail.com", "yahoo.gr", "yahoo.com", "hotmail.com", "outlook.com", "tee.gr", "otenet.gr", "cosmotemail.gr"):
        score += 15

    return score


def select_best_email(emails: set[str] | list[str], website_domain: str = "") -> str:
    """Pick the single highest-scoring B2B email."""
    valid = [clean_email(e) for e in set(emails) if score_email_b2b_gr(e, website_domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b_gr(e, website_domain))


def extract_emails_from_html(raw_html: str) -> set[str]:
    """Extract emails from data-cfemail, mailto:, and visible text."""
    found: set[str] = set()
    if not raw_html:
        return found

    soup = BeautifulSoup(raw_html, "html.parser")
    for cf in soup.select("[data-cfemail]"):
        dec = clean_email(decode_cf_hex(cf.get("data-cfemail", "")))
        if dec:
            found.add(dec)

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if "mailto:" in href.lower():
            part = re.split(r"mailto:", href, flags=re.I)[-1].split("?")[0]
            em = clean_email(part)
            if em:
                found.add(em)

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    visible_text = soup.get_text(" ", strip=True)
    for m in EMAIL_REGEX.findall(visible_text):
        em = clean_email(m)
        if em:
            found.add(em)

    return found


GLOBAL_SESSION = requests.Session(impersonate="chrome120")


def fetch_html_fast(url: str, timeout: float = 8.0) -> str:
    """Fetch HTML with impersonated Chrome headers, session cookies, and SSL fallback."""
    for verify_flag in [True, False]:
        try:
            r = GLOBAL_SESSION.get(url, timeout=timeout, allow_redirects=True, verify=verify_flag)
            if r.status_code == 200 and "captchapage" not in str(r.url).lower():
                return r.text or ""
            return ""
        except Exception:
            time.sleep(0.3)
    return ""


def collect_prioritized_subpages_gr(home_html: str, web_url: str) -> list[str]:
    """Rank DOM <a> links (Priority 10/5) ahead of guess subpaths (Priority 2)."""
    parsed_root = urllib.parse.urlparse(web_url)
    root = f"{parsed_root.scheme}://{parsed_root.netloc}"
    canon = lambda u: re.sub(r"^https?://(?:www\.)?", "", u.split("#")[0].rstrip("/").lower())
    seen = {canon(web_url), canon(root)}
    prioritized: list[tuple[int, str]] = []

    try:
        soup = BeautifulSoup(home_html, "html.parser")
        for a in soup.find_all("a", href=True):
            raw_href = a["href"].strip()
            if not raw_href or raw_href.startswith("#") or raw_href.lower().startswith(("javascript:", "tel:", "mailto:")):
                continue
            full = urllib.parse.urljoin(web_url, raw_href).split("#")[0]
            p_full = urllib.parse.urlparse(full)
            if parsed_root.netloc.replace("www.", "") not in p_full.netloc.replace("www.", ""):
                continue
            c_url = canon(full)
            if c_url in seen or any(full.lower().endswith(ext) for ext in INVALID_EXTS):
                continue

            h_low = raw_href.lower()
            t_low = a.get_text(" ", strip=True).lower()
            prio = 0
            if any(k in h_low or k in t_low for k in GR_CONTACT_KEYWORDS_P10):
                prio = 10
            elif any(k in h_low or k in t_low for k in GR_SECONDARY_KEYWORDS_P5):
                prio = 5
            if prio > 0:
                seen.add(c_url)
                prioritized.append((prio, full))
    except Exception:
        pass

    prioritized.sort(key=lambda x: x[0], reverse=True)
    queue = [u for _, u in prioritized]
    for gp in GR_GUESS_SUBPATHS:
        g_url = urllib.parse.urljoin(root, gp)
        cg = canon(g_url)
        if cg not in seen:
            seen.add(cg)
            queue.append(g_url)
    return queue


def crawl_website_for_email_gr(web_url: str) -> tuple[str, str, str]:
    """Crawl homepage + top 6 prioritized subpages for B2B email."""
    if not web_url or not is_valid_website(web_url):
        return "", "", ""
    home_html = fetch_html_fast(web_url, timeout=8.0)
    if not home_html:
        return "", "", ""

    all_emails = extract_emails_from_html(home_html)
    fb_url = ""
    try:
        soup = BeautifulSoup(home_html, "html.parser")
        for a in soup.find_all("a", href=True):
            if is_facebook_url(a["href"]):
                fb_url = a["href"].split("?")[0]
                break
    except Exception:
        pass

    best = select_best_email(all_emails, web_url)
    if best and score_email_b2b_gr(best, web_url) >= 90:
        return best, "Website", fb_url

    for sub_url in collect_prioritized_subpages_gr(home_html, web_url)[:6]:
        sub_html = fetch_html_fast(sub_url, timeout=6.0)
        if not sub_html:
            continue
        all_emails |= extract_emails_from_html(sub_html)
        best = select_best_email(all_emails, web_url)
        if best and score_email_b2b_gr(best, web_url) >= 90:
            return best, "Website", fb_url

    best = select_best_email(all_emails, web_url)
    return best, ("Website" if best else ""), fb_url


def load_existing_raw_items() -> list[dict]:
    """Load already scraped items from 0RAW so we never restart from Page 0."""
    if not OUTPUT_0RAW_PATH.exists():
        return []
    try:
        df_old = pd.read_csv(OUTPUT_0RAW_PATH, encoding="utf-8-sig", dtype=str).fillna("")
        if df_old.empty:
            return []
        name_col = "Cong_Ty" if "Cong_Ty" in df_old.columns else ("Công ty" if "Công ty" in df_old.columns else "")
        url_col = "Detail_URL" if "Detail_URL" in df_old.columns else ("Liên Hệ" if "Liên Hệ" in df_old.columns else "")
        if not name_col or not url_col:
            return []
        items = []
        for _, r in df_old.iterrows():
            durl = r.get(url_col, "").strip()
            if not durl:
                continue
            items.append({
                "No.": len(items) + 1,
                "Cong_Ty": clean_text(r.get(name_col, "")),
                "Listing_Type": r.get("Listing_Type", "AdvListing" if "advdetails" in durl else "FreeListing"),
                "Detail_URL": durl,
                "Dia_Chi": clean_text(r.get("Dia_Chi") or r.get("Địa chỉ", "")),
                "Category": clean_text(r.get("Category", "Garden Construction")),
                "Card_Phone": clean_text(r.get("Card_Phone") or r.get("SDT") or r.get("SĐT", "")),
            })
        print(f"[CACHE] Da tai san {len(items)} cong ty tu {OUTPUT_0RAW_PATH.name}")
        return items
    except Exception as e:
        print(f"[CACHE] Khong the doc {OUTPUT_0RAW_PATH.name}: {e}")
        return []


def scrape_pages_with_browser(start_page: int, known_items: list[dict], base_url: str) -> tuple[list[dict], dict]:
    """
    Launch interactive visible browser (headless=False) to solve reCAPTCHA
    and scrape remaining pages up to 275 companies.
    """
    from playwright.sync_api import sync_playwright

    items = list(known_items)
    seen_urls = {it.get("Detail_URL", "").strip() for it in items if it.get("Detail_URL")}
    cookies_map = {}

    print("\a\a", flush=True)
    print("\n" + "=" * 80)
    print("  KICH HOAT TRINH DUYET TRUC QUAN (headless=False, Viewport 1280x800)")
    print(f"  Muc tieu: Cao tiep tu Trang {start_page} den Trang 13 de dat du 275 cong ty")
    print("=" * 80)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=False,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            no_viewport=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
        page = context.new_page()

        curr_page = start_page
        while curr_page < 14:
            target_url = f"{base_url}?page={curr_page}" if curr_page > 0 else base_url
            print(f"\n  [Trinh Duyet] Dang mo Trang {curr_page}: {target_url}")
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=40000)
            except Exception as e:
                print(f"  [!] Loi tai trang: {e}")

            # Check if captcha challenge
            if "captchapage" in page.url.lower():
                print("\a\a\a", flush=True)
                print("\n" + "!" * 80)
                print(f"[!] PHAT HIEN RECAPTCHA TAI TRANG {curr_page}")
                print("[!] Cua so Google Chrome da mo san tren man hinh!")
                print("[!] VUI LONG CLICK TICH CHON 'I'M NOT A ROBOT' TREN CUA SO TRINH DUYET...")
                print("!" * 80 + "\n", flush=True)
                try:
                    page.wait_for_selector("h2.CompanyName", timeout=180000)
                    print("[+] Xac thuc thanh cong! Dang tu dong thu thap tiep...")
                except Exception as e:
                    print(f"[-] Het thoi gian cho xac thuc Captcha: {e}")
                    break
            else:
                try:
                    page.wait_for_selector("h2.CompanyName", timeout=6000)
                except Exception:
                    pass

            soup = BeautifulSoup(page.content(), "html.parser")
            h2_list = soup.select("h2.CompanyName")
            if not h2_list:
                if "captchapage" in page.url.lower():
                    continue
                print(f"  [Trinh Duyet] Trang {curr_page} khong co them doanh nghiep nao -> Hoan tat danh ba!")
                break

            added_this_page = 0
            for h2 in h2_list:
                a = h2.find("a", href=True)
                if not a:
                    continue
                durl = a["href"].strip()
                if durl in seen_urls:
                    continue
                name = clean_text(a.get_text(" ", strip=True))
                card = h2.find_parent("div", class_=lambda c: c and any(k in str(c).lower() for k in ["area", "box", "item"]))
                if not card:
                    card = h2.parent.parent

                addr_el = card.select_one(".AdvAddress, .address") if card else None
                addr = clean_text(addr_el.get_text(" ", strip=True) if addr_el else "")

                cats = [clean_text(c.get_text(strip=True)) for c in card.select(".AdvCategory")] if card else []
                cat_str = ", ".join(cats) or "Garden Construction"

                card_phone = ""
                phone_txt = card.select_one(".DetailsText") if card else None
                if phone_txt and any(ch.isdigit() for ch in phone_txt.get_text()):
                    card_phone = clean_text(phone_txt.get_text(strip=True))

                is_adv = "advdetails" in durl
                items.append({
                    "No.": len(items) + 1,
                    "Cong_Ty": name,
                    "Listing_Type": "AdvListing" if is_adv else "FreeListing",
                    "Detail_URL": durl,
                    "Dia_Chi": addr,
                    "Category": cat_str,
                    "Card_Phone": card_phone,
                })
                seen_urls.add(durl)
                added_this_page += 1

            print(f"  [Trinh Duyet] Trang {curr_page:2d} -> them {added_this_page:2d} cong ty (Tong so hien tai: {len(items)} / 275)")
            curr_page += 1
            page.wait_for_timeout(1500)

        for ck in context.cookies():
            cookies_map[ck["name"]] = ck["value"]

        browser.close()

    return items, cookies_map


def scrape_listing_pages(force_browser: bool = False) -> list[dict]:
    """Scrape all listing pages from vrisko.gr up to 275 companies."""
    print("=" * 80)
    print("STAGE 1: SCRAPING VRISKO.GR LISTING PAGES (Garden Construction Greece)")
    print(f"Base URL: {BASE_CATEGORY_URL}")
    print("=" * 80)

    items = load_existing_raw_items()
    seen_urls = {it.get("Detail_URL", "").strip() for it in items if it.get("Detail_URL")}

    if len(items) >= 275 and not force_browser:
        print(f"[CACHE] Da co du {len(items)} cong ty (Target: 275). Bo qua buoc cao danh sach.")
        return items

    start_page = len(items) // 20
    print(f"[*] Bat dau tu Trang {start_page} (Hien da co {len(items)} / 275 cong ty)...")

    if not force_browser and start_page < 14:
        page = start_page
        while page < 14:
            url = f"{BASE_CATEGORY_URL}?page={page}" if page > 0 else BASE_CATEGORY_URL
            try:
                r = GLOBAL_SESSION.get(url, timeout=12)
            except Exception as e:
                print(f"  [!] HTTP error on page {page}: {e}. Switching to browser.")
                break

            if r.status_code != 200:
                print(f"  Page {page} status {r.status_code}, stopping HTTP mode.")
                break

            if "captchapage" in str(r.url).lower() or "captchapage" in r.text.lower()[:2000]:
                print(f"\n[!] PHAT HIEN CAPTCHA TAI TRANG {page} (Da thu thap duoc {len(items)} / 275 cong ty)")
                print(f"    Chuyen sang Trinh duyet Truc quan (headless=False) de mo khoa tiep...")
                break

            soup = BeautifulSoup(r.text, "html.parser")
            h2_list = soup.select("h2.CompanyName")
            if not h2_list:
                print(f"  Page {page} has 0 listings.")
                break

            added = 0
            for h2 in h2_list:
                a = h2.find("a", href=True)
                if not a:
                    continue
                durl = a["href"].strip()
                if durl in seen_urls:
                    continue
                name = clean_text(a.get_text(" ", strip=True))
                card = h2.find_parent("div", class_=lambda c: c and any(k in str(c).lower() for k in ["area", "box", "item"]))
                if not card:
                    card = h2.parent.parent

                addr_el = card.select_one(".AdvAddress, .address") if card else None
                addr = clean_text(addr_el.get_text(" ", strip=True) if addr_el else "")

                cats = [clean_text(c.get_text(strip=True)) for c in card.select(".AdvCategory")] if card else []
                cat_str = ", ".join(cats) or "Garden Construction"

                card_phone = ""
                phone_txt = card.select_one(".DetailsText") if card else None
                if phone_txt and any(ch.isdigit() for ch in phone_txt.get_text()):
                    card_phone = clean_text(phone_txt.get_text(strip=True))

                is_adv = "advdetails" in durl
                items.append({
                    "No.": len(items) + 1,
                    "Cong_Ty": name,
                    "Listing_Type": "AdvListing" if is_adv else "FreeListing",
                    "Detail_URL": durl,
                    "Dia_Chi": addr,
                    "Category": cat_str,
                    "Card_Phone": card_phone,
                })
                seen_urls.add(durl)
                added += 1

            print(f"  Page {page:2d} -> them {added:2d} listings (Tong: {len(items)} / 275)")
            page += 1

    # If category not complete (< 275 items), launch browser for the rest
    if len(items) < 275:
        start_p = len(items) // 20
        print(f"\n[*] Dang tiep tuc cao tu Trang {start_p} bang Trinh Duyet Thuc Te de lay du 275 cong ty...")
        items, captured_cookies = scrape_pages_with_browser(
            start_page=start_p,
            known_items=items,
            base_url=BASE_CATEGORY_URL,
        )
        if captured_cookies:
            for k, v in captured_cookies.items():
                GLOBAL_SESSION.cookies.set(k, v, domain=".vrisko.gr")

    print(f"\n[+] Total listings collected: {len(items)} (Target: 275)\n")
    return items


def scrape_single_detail(item: dict) -> dict:
    """Fetch detail page of a single listing and extract email, phone, website."""
    durl = item.get("Detail_URL", "")
    out = {
        "SDT": "",
        "Tat_Ca_SDT": "",
        "Website": "",
        "Email": "",
        "Email_Source": "",
        "Facebook_URL": "",
    }
    if not durl:
        return out

    html_content = fetch_html_fast(durl, timeout=10.0)
    if not html_content:
        return out

    soup = BeautifulSoup(html_content, "html.parser")

    # 1. Address refinement
    addr_el = soup.select_one("#AddressLbl, .details-address, .AdvAddress")
    if addr_el:
        addr_text = clean_text(addr_el.get_text(" ", strip=True))
        if addr_text:
            out["Dia_Chi"] = addr_text

    # 2. Phones
    phone_texts = [clean_text(p.get_text(" ", strip=True)) for p in soup.select(".phones-btn, [class*='phone']")]
    phone_texts = [p for p in phone_texts if any(c.isdigit() for c in p)]
    raw_phone_str = " ".join(phone_texts) if phone_texts else item.get("Card_Phone", "")
    p_primary, p_all = normalize_gr_phones(raw_phone_str)
    out["SDT"] = p_primary
    out["Tat_Ca_SDT"] = p_all

    # 3. Website
    web_a = soup.select_one("a.websiteMarker_ClassForLogging")
    if web_a and web_a.has_attr("href") and is_valid_website(web_a["href"]):
        out["Website"] = normalize_website_url(web_a["href"])

    # 4. Direct Email (mailTo:)
    em_a = soup.select_one("a.emailMarker_ClassForLogging[href^='mailTo:'], a[href^='mailto:']")
    if em_a and em_a.has_attr("href"):
        raw_em = em_a["href"].split(":", 1)[1].strip()
        cleaned_em = clean_email(raw_em)
        if cleaned_em and score_email_b2b_gr(cleaned_em, out["Website"]) > 0:
            out["Email"] = cleaned_em
            out["Email_Source"] = "Vrisko"

    # 5. Deep crawl website if email not found directly on Vrisko
    if not out["Email"] and out["Website"]:
        w_mail, w_src, w_fb = crawl_website_for_email_gr(out["Website"])
        if w_mail:
            out["Email"] = w_mail
            out["Email_Source"] = w_src
        if w_fb and not out["Facebook_URL"]:
            out["Facebook_URL"] = w_fb

    return out


def load_cache() -> dict:
    """Load JSON resume cache."""
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            pass
    return {}


def save_cache(cache: dict) -> None:
    """Atomic write for checkpoint cache."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CACHE_FILE)


def export_all_csvs(df: pd.DataFrame) -> int:
    """Export 0RAW, 1ENR, 2COL (email-first), ONLY_EMAILS_READY and mirror to gr_greece/."""
    if df.empty:
        print("[!] Empty DataFrame, skipping export.")
        return 0
    df_clean = df.copy()
    if "Cong_Ty" not in df_clean.columns:
        df_clean["Cong_Ty"] = ""
    if "SDT" not in df_clean.columns:
        df_clean["SDT"] = ""
    if "Email" not in df_clean.columns:
        df_clean["Email"] = ""
    df_clean = df_clean[~df_clean["Cong_Ty"].apply(is_blacklisted_company)].reset_index(drop=True)
    df_clean["SDT"] = df_clean["SDT"].apply(ensure_phone_quote)
    df_clean["Email"] = df_clean["Email"].apply(clean_email)

    # Sort with_email first
    has_em = df_clean[df_clean["Email"] != ""].copy()
    no_em = df_clean[df_clean["Email"] == ""].copy()
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted["No."] = range(1, len(df_sorted) + 1)

    # 1. 0RAW: raw directory fields
    raw_cols = ["No.", "Cong_Ty", "Listing_Type", "SDT", "Tat_Ca_SDT", "Website", "Email", "Dia_Chi", "Category", "Detail_URL"]
    df_raw = df_sorted[[c for c in raw_cols if c in df_sorted.columns]]
    df_raw.to_csv(OUTPUT_0RAW_PATH, index=False, encoding="utf-8-sig")

    # 2. 1ENR: master enriched dataset
    df_sorted.to_csv(OUTPUT_1ENR_PATH, index=False, encoding="utf-8-sig")

    # 3. 2COL: standard 20-column Cold Mail format
    coldmail_rows = []
    for _, r in df_sorted.iterrows():
        comp = clean_text(r.get("Cong_Ty", ""))
        phone = ensure_phone_quote(r.get("SDT", ""))
        web = clean_text(r.get("Website", ""))
        durl = clean_text(r.get("Detail_URL", ""))
        link = web or durl
        email = clean_email(r.get("Email", ""))
        addr = clean_text(r.get("Dia_Chi", ""))
        if addr and "greece" not in addr.lower() and "hellas" not in addr.lower():
            addr = f"{addr}, Greece"

        coldmail_rows.append({
            "No.": r.get("No.", ""),
            "Công ty": comp,
            "Chức danh": "Owner / Manager",
            "Người liên hệ": "",
            "SĐT": phone,
            "Liên Hệ": link,
            "Email": email,
            "Liên Hệ mail": f"mailto:{email}" if email else link,
            "Địa chỉ": addr or "Greece",
            "Lương": "",
            "Ngày đăng": "",
            "Hạn tuyển": "",
            "Check gửi": "Chưa gửi",
            "Last Subject": "",
            "Last Body HTML": "",
            "Trạng thái Reply": "",
            "Lần Follow-up": "",
            "Ngày Follow-up gần nhất": "",
            "Mailbox đã dùng": "",
            "Category": f"Garden Construction (Greece) | {clean_text(r.get('Category', ''))}",
        })

    df_2col = pd.DataFrame(coldmail_rows, columns=COLDMAIL_COLUMNS)
    df_2col.to_csv(OUTPUT_2COL_PATH, index=False, encoding="utf-8-sig")

    # 4. ONLY_EMAILS_READY
    df_ready = df_2col[df_2col["Email"] != ""].copy()
    df_ready["No."] = range(1, len(df_ready) + 1)
    df_ready.to_csv(OUTPUT_READY_PATH, index=False, encoding="utf-8-sig")

    # Mirror to gr_greece/
    GR_DIR.mkdir(parents=True, exist_ok=True)
    for p in (OUTPUT_0RAW_PATH, OUTPUT_1ENR_PATH, OUTPUT_2COL_PATH, OUTPUT_READY_PATH):
        try:
            shutil.copy2(p, GR_DIR / p.name)
        except Exception:
            pass

    return len(df_ready)


def run_pipeline(
    workers: int = 5,
    limit: int | None = None,
    force_retry: bool = False,
    force_browser: bool = False,
) -> None:
    """Execute complete 2-stage scraping and enrichment pipeline."""
    cache = {} if force_retry else load_cache()
    items = scrape_listing_pages(force_browser=force_browser)

    if limit:
        items = items[:limit]

    df = pd.DataFrame(items)
    for col in ("SDT", "Tat_Ca_SDT", "Website", "Email", "Email_Source", "Facebook_URL"):
        if col not in df.columns:
            df[col] = ""

    # Apply cached records
    for idx, row in df.iterrows():
        key = row.get("Detail_URL", "")
        if key in cache and not force_retry:
            rec = cache[key]
            for c in ("SDT", "Tat_Ca_SDT", "Website", "Email", "Email_Source", "Facebook_URL", "Dia_Chi"):
                if rec.get(c):
                    df.at[idx, c] = rec[c]

    pending_indices = [
        i for i, r in df.iterrows()
        if force_retry or not cache.get(r.get("Detail_URL", ""), {}).get("done")
    ]

    print("=" * 80)
    print("STAGE 2: SCRAPING DETAIL PAGES & ENRICHING WEBSITES FOR EMAILS")
    print(f"Total listings   : {len(df)}")
    print(f"Pending to crawl : {len(pending_indices)}")
    print(f"Workers          : {workers}")
    print("=" * 80)

    done_cnt = 0
    new_emails = 0
    new_phones = 0
    new_webs = 0

    def _worker_task(idx: int):
        it = df.loc[idx].to_dict()
        res = scrape_single_detail(it)
        return idx, it.get("Detail_URL", ""), res

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futures = {ex.submit(_worker_task, idx): idx for idx in pending_indices}
        for fut in as_completed(futures):
            try:
                idx, key, res = fut.result()
                for c in ("SDT", "Tat_Ca_SDT", "Website", "Email", "Email_Source", "Facebook_URL"):
                    if res.get(c):
                        df.at[idx, c] = res[c]
                if res.get("Dia_Chi"):
                    df.at[idx, "Dia_Chi"] = res["Dia_Chi"]

                res["done"] = True
                cache[key] = res
                done_cnt += 1

                if res.get("Email"):
                    new_emails += 1
                if res.get("SDT"):
                    new_phones += 1
                if res.get("Website"):
                    new_webs += 1

                comp = df.at[idx, "Cong_Ty"]
                ph = df.at[idx, "SDT"]
                em = df.at[idx, "Email"]
                wb = df.at[idx, "Website"]

                if done_cnt % 10 == 0 or em:
                    print(
                        f"  [{done_cnt}/{len(pending_indices)}] {comp[:30]:30s} | "
                        f"Phone={ph or '-':12s} | Mail={em or '-':28s} | Web={wb or '-'}"
                    )

                if done_cnt % 15 == 0:
                    save_cache(cache)
                    export_all_csvs(df)
            except Exception as e:
                print(f"  [ERR] Detail crawl failure: {e}")

    save_cache(cache)
    ready_count = export_all_csvs(df)

    print("\n" + "=" * 80)
    print("VRISKO.GR GREEK GARDEN CONSTRUCTION SCRAPING COMPLETED!")
    print(f"  Total Companies Scraped : {len(df)}")
    print(f"  Total with Phone        : {(df['SDT'] != '').sum()} ({((df['SDT'] != '').sum() * 100 / len(df)):.1f}%)")
    print(f"  Total with Website      : {(df['Website'] != '').sum()}")
    print(f"  Total with Clean Email  : {ready_count} ({ready_count * 100 / len(df):.1f}%)")
    print(f"  Outputs Saved           : {OUTPUT_0RAW_PATH.name} | {OUTPUT_1ENR_PATH.name}")
    print(f"                            {OUTPUT_2COL_PATH.name} | {OUTPUT_READY_PATH.name}")
    print("=" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape and enrich Garden Construction companies from vrisko.gr")
    parser.add_argument("--workers", type=int, default=5, help="Number of concurrent worker threads (default: 5)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of companies to scrape (for testing)")
    parser.add_argument("--force-retry", action="store_true", help="Ignore cache and re-crawl all details")
    parser.add_argument("--browser", action="store_true", help="Force interactive browser mode (headless=False)")
    parser.add_argument("--re-export", action="store_true", help="Re-export CSV outputs from existing cache only")
    args = parser.parse_args()

    if args.re_export:
        if CACHE_FILE.exists():
            cache = load_cache()
            items = scrape_listing_pages(force_browser=args.browser)
            df = pd.DataFrame(items)
            for idx, r in df.iterrows():
                key = r.get("Detail_URL", "")
                if key in cache:
                    for c, v in cache[key].items():
                        if c in df.columns:
                            df.at[idx, c] = v
            ready = export_all_csvs(df)
            print(f"[RE-EXPORT] Successfully re-exported {len(df)} rows ({ready} with email).")
        return

    run_pipeline(
        workers=args.workers,
        limit=args.limit,
        force_retry=args.force_retry,
        force_browser=args.browser,
    )


if __name__ == "__main__":
    main()

