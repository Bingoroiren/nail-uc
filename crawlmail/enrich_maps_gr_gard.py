# -*- coding: utf-8 -*-
"""
GOOGLE MAPS DATA ENRICHMENT MODULE (enrich-maps)
=================================================
Target  : Rescue companies WITHOUT email in GR_GARD_VRIS_2COL.csv via Google Maps
Country : Greece (GR) | Industry: Garden Construction (GARD)
Source  : Google Maps Places API / Web UI Automation + Deep Website Email Crawling

Core Rules Complied:
  1. Smart & Strict Name Matcher (Rule 11 GEMINI.md & skill enrich-maps):
     - Unicode NFKD diacritics stripping (Greek/Latin accents).
     - Clean Greek & International legal forms (IKE, OE, EE, AE, EPE, MEPE, s.r.o., GmbH...).
     - Bracket translation stripping (...) and delimiter matching (-, |, /, :).
  2. Single Quote (') on Phone Numbers (Rule 2 GEMINI.md).
  3. Single Best B2B Email Scoring & Junk Email Filtering (Rule 3 GEMINI.md).
  4. Real Browser Execution (headless=False, Rule 4 GEMINI.md).
  5. Incremental Auto-Save & Resume Checkpoint (Rule 5 GEMINI.md).
  6. Email-First Sorting (with_email rows pushed to top).
  7. CSV UTF-8 with BOM only (utf-8-sig).
  8. Permanent Blacklist Companies filter (Rule 12 GEMINI.md).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import ssl
import sys
import time
import unicodedata
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import curl_cffi.requests as requests
import pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent
GR_DIR = ROOT_DIR / "gr_greece"
CRAWLMAIL_DIR = ROOT_DIR / "crawlmail"
DEFAULT_INPUT_CSV = ROOT_DIR / "GR_GARD_VRIS_2COL.csv"
DEFAULT_CACHE_JSON = CRAWLMAIL_DIR / "cache_enrich_maps_gr_gard.json"

COL_20_HEADERS = [
    "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ",
    "Email", "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển",
    "Check gửi", "Last Subject", "Last Body HTML", "Trạng thái Reply",
    "Lần Follow-up", "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category",
]

PERMANENT_BLACKLIST_COMPANIES = (
    "scandi standard", "scandi-standard", "scandi standart",
    "biliarta", "daigre", "daigrė",
)

INVALID_EXTS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".css", ".js", ".pdf", ".woff", ".woff2", ".ico", ".mp4", ".mp3", ".zip",
)

BLACKLIST_DOMAINS = {
    "facebook.com", "fb.com", "instagram.com", "linkedin.com", "youtube.com",
    "twitter.com", "x.com", "tiktok.com", "google.com", "maps.google.com",
    "vrisko.gr", "media.vrisko.gr", "11880.gr", "yellowpages.gr", "xo.gr",
    "tripadvisor.com", "booking.com", "wikipedia.org", "sentry.io", "wix.com",
}

JUNK_USERNAMES = {
    "youremail", "your-email", "yourname", "someone", "nobody", "john.doe",
    "no-reply", "noreply", "donotreply", "privacy", "gdpr", "abuse", "sentry",
    "domain", "email", "info@example.com",
}

EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b")

# Greek legal forms to strip during smart matching
GREEK_LEGAL_FORMS = [
    "monoprosopi ike", "monoprosopi i.k.e.", "monoprosopi epe", "monoprosopi e.p.e.",
    "i.k.e.", "ike", "o.e.", "oe", "e.e.", "ee", "a.e.", "ae",
    "e.p.e.", "epe", "m.e.p.e.", "mepe", "sole proprietorship",
    "s.r.o.", "a.s.", "uab", "mb", "gmbh",
]


def clean_text(val) -> str:
    """Normalize text, replace non-breaking spaces and strip excess whitespace."""
    if val is None or pd.isna(val):
        return ""
    s = str(val).replace("\u00a0", " ").replace("\xa0", " ").replace("&nbsp;", " ")
    s = s.replace("\u200b", "").replace("\ufeff", "")
    return re.sub(r"\s+", " ", s).strip()


def is_blacklisted_company(name: str) -> bool:
    """Strictly reject blacklisted companies across all layers."""
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


def ensure_phone_quote(phone: str) -> str:
    """Ensure every phone number starts with single quote (')."""
    p = clean_text(phone)
    if not p:
        return ""
    return p if p.startswith("'") else f"'{p}"


def normalize_gr_phone(raw_phone_str: str) -> str:
    """Normalize Greek phone numbers: 10 digits starting with 2 (landline) or 69 (mobile)."""
    cleaned = clean_text(raw_phone_str)
    if not cleaned:
        return ""
    pattern = re.compile(r"(?:\+30|0030)?\s*([26]\d{9})\b")
    matches = pattern.findall(re.sub(r"[\s.-]", "", cleaned))
    if not matches:
        matches = re.findall(r"\b[26]\d{9}\b", re.sub(r"[^\d]", " ", cleaned))
    if matches:
        return f"'{matches[0]}"
    return ensure_phone_quote(cleaned)


def normalize_text_core(s: str) -> str:
    """
    Strip Unicode NFKD diacritics, lowercase, remove punctuation, legal forms.
    Handles Greek letters and international diacritics.
    """
    if not s:
        return ""
    n = unicodedata.normalize("NFKD", str(s)).encode("ASCII", "ignore").decode("utf-8").lower()
    n = re.sub(r'["\'„“”«»]', "", n)
    # Strip legal forms
    for lf in GREEK_LEGAL_FORMS:
        n = re.sub(rf"\b{re.escape(lf)}\b", "", n)
    # Strip leading/trailing punctuation
    n = re.sub(r"^[,.\-_/|:\s]+|[,.\-_/|:\s]+$", "", n)
    return re.sub(r"\s+", " ", n).strip()


def is_valid_name_match(query_name: str, candidate_name: str) -> tuple[bool, str]:
    """
    Smart & Strict Name Matcher according to Rule 11 GEMINI.md and skill enrich-maps:
    1. Exact match after core normalization.
    2. Bracket match (removes Google Maps auto-translation in brackets).
    3. Delimiter match (after -, |, /, :).
    4. Safe substring match (query length >= 5).
    """
    if not query_name or not candidate_name:
        return False, "EMPTY"

    q_clean = normalize_text_core(query_name)
    c_clean = normalize_text_core(candidate_name)

    if not q_clean or not c_clean:
        return False, "EMPTY_AFTER_CLEAN"

    if q_clean == c_clean:
        return True, "EXACT"

    # Remove English translations/annotations in (...) or [...]
    c_nobrackets = re.sub(r"\(.*?\)|\[.*?\]", "", candidate_name)
    c_nobrackets_clean = normalize_text_core(c_nobrackets)
    if q_clean == c_nobrackets_clean:
        return True, "BRACKET_MATCH"

    # Delimiter parts (-, |, /, :)
    parts = [normalize_text_core(p) for p in re.split(r"[-–—|/:,]", candidate_name) if p.strip()]
    if any(p == q_clean for p in parts if p):
        return True, "DELIMITER_MATCH"

    # Substring match if core query is substantial
    if len(q_clean) >= 6 and (q_clean in c_clean or c_clean in q_clean or q_clean in c_nobrackets_clean):
        return True, "SUBSTRING_MATCH"

    return False, "NO_MATCH"


def score_email_b2b_gr(email: str, website_domain: str = "") -> int:
    """B2B Manpower / Service agency email scoring algorithm for Greece."""
    if not email or not isinstance(email, str):
        return -1
    e = clean_email(email)
    if not EMAIL_REGEX.match(e):
        return -1
    if any(e.endswith(ext) for ext in INVALID_EXTS):
        return -1

    u, d = e.split("@", 1)
    if any(bad in d for bad in BLACKLIST_DOMAINS):
        return -1
    if u in JUNK_USERNAMES or any(k in u for k in ("youremail", "yourname", "placeholder")):
        return -1

    score = 10
    clean_dom = website_domain.lower().replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
    if clean_dom and (clean_dom in d or d in clean_dom):
        score += 50
    elif d.endswith(".gr"):
        score += 20

    if u in ("info", "contact", "epikoinonia", "mail", "office", "sales"):
        score += 45
    elif u in ("ergasies", "kipoi", "geoponos", "kataskevi", "syntirisi", "services"):
        score += 40
    elif "." in u and score >= 60:
        score += 25
    elif d in ("gmail.com", "yahoo.gr", "yahoo.com", "hotmail.com", "outlook.com", "otenet.gr", "cosmotemail.gr"):
        score += 15

    return score


def select_best_email(emails: set[str] | list[str], website_domain: str = "") -> str:
    """Select the single highest-scoring B2B email."""
    valid = [clean_email(e) for e in set(emails) if score_email_b2b_gr(e, website_domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b_gr(e, website_domain))


def decode_cf(cf_hex: str) -> str:
    """Decode Cloudflare data-cfemail XOR encoded email."""
    if not cf_hex or len(cf_hex) < 4:
        return ""
    try:
        key = int(cf_hex[:2], 16)
        return "".join(chr(int(cf_hex[i : i + 2], 16) ^ key) for i in range(2, len(cf_hex), 2))
    except Exception:
        return ""


def is_valid_company_website(url: str) -> bool:
    """Reject social media, directories, maps, and invalid URLs."""
    u = clean_text(url).lower()
    if not u or not u.startswith(("http://", "https://")):
        return False
    try:
        netloc = urllib.parse.urlparse(u).netloc.lower()
        if any(bad in netloc for bad in BLACKLIST_DOMAINS):
            return False
        return "." in netloc
    except Exception:
        return False


def fetch_html(url: str, timeout: float = 8.0) -> str:
    """Fetch website HTML using curl_cffi Chrome impersonation."""
    s = requests.Session(impersonate="chrome120")
    for verify_flag in [True, False]:
        try:
            r = s.get(url, timeout=timeout, allow_redirects=True, verify=verify_flag)
            if r.status_code == 200:
                return r.text or ""
            return ""
        except Exception:
            time.sleep(0.3)
    return ""


def crawl_site_for_emails(web_url: str) -> tuple[str, str, str]:
    """
    Deep crawl official website for Greek B2B contact emails:
    1. Homepage DOM + mailto: + data-cfemail
    2. Priority 10 subpages from DOM menu (/epikoinonia, /contact, /about, /sxetika)
    3. Guess paths (/contact, /epikoinonia)
    4. Facebook fallback if static HTML is empty
    """
    if not is_valid_company_website(web_url):
        return "", "", ""

    found_emails: set[str] = set()
    fb_link = ""

    parsed_root = urllib.parse.urlparse(web_url)
    root = f"{parsed_root.scheme}://{parsed_root.netloc}"

    home_html = fetch_html(web_url, timeout=8.0)
    if not home_html and root != web_url:
        home_html = fetch_html(root, timeout=8.0)

    dom_contact_links: list[str] = []

    if home_html:
        try:
            soup = BeautifulSoup(home_html, "html.parser")
            # 1. Cloudflare decode
            for cf in soup.select("[data-cfemail]"):
                dec = clean_email(decode_cf(cf.get("data-cfemail", "")))
                if dec:
                    found_emails.add(dec)

            # 2. mailto: links
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if "mailto:" in href.lower():
                    em = clean_email(href.split(":", 1)[1].split("?")[0])
                    if em:
                        found_emails.add(em)
                elif not fb_link and ("facebook.com/" in href.lower() or "fb.com/" in href.lower()):
                    if not any(bad in href.lower() for bad in ("sharer", "share.php", "plugins")):
                        fb_link = href.split("?")[0]
                elif any(k in href.lower() for k in ("epikoinonia", "contact", "about", "sxetika")):
                    full = urllib.parse.urljoin(web_url, href)
                    if full not in dom_contact_links and not any(full.lower().endswith(ext) for ext in INVALID_EXTS):
                        dom_contact_links.append(full)

            # 3. Regex on text
            for tag in soup(["script", "style", "noscript", "svg"]):
                tag.decompose()
            for m in EMAIL_REGEX.findall(soup.get_text(" ", strip=True)):
                em = clean_email(m)
                if em:
                    found_emails.add(em)
        except Exception:
            pass

    best = select_best_email(found_emails, web_url)
    if best and score_email_b2b_gr(best, web_url) >= 90:
        return best, "Website", fb_link

    # Prioritized subpages
    sub_urls = dom_contact_links[:4]
    if not sub_urls:
        sub_urls = [f"{root}/epikoinonia", f"{root}/contact", f"{root}/about"]

    for sub in sub_urls:
        sub_html = fetch_html(sub, timeout=6.0)
        if not sub_html:
            continue
        try:
            s_sub = BeautifulSoup(sub_html, "html.parser")
            for cf in s_sub.select("[data-cfemail]"):
                dec = clean_email(decode_cf(cf.get("data-cfemail", "")))
                if dec:
                    found_emails.add(dec)
            for a in s_sub.find_all("a", href=True):
                href = a["href"].strip()
                if "mailto:" in href.lower():
                    em = clean_email(href.split(":", 1)[1].split("?")[0])
                    if em:
                        found_emails.add(em)
            for tag in s_sub(["script", "style", "noscript", "svg"]):
                tag.decompose()
            for m in EMAIL_REGEX.findall(s_sub.get_text(" ", strip=True)):
                em = clean_email(m)
                if em:
                    found_emails.add(em)
        except Exception:
            pass

        best = select_best_email(found_emails, web_url)
        if best and score_email_b2b_gr(best, web_url) >= 90:
            return best, "Website", fb_link

    # Facebook Fanpage Fallback
    if not found_emails and fb_link:
        fb_html = fetch_html(fb_link, timeout=6.0)
        if fb_html:
            for m in EMAIL_REGEX.findall(fb_html):
                em = clean_email(m)
                if em and score_email_b2b_gr(em, web_url) > 0:
                    found_emails.add(em)

    best = select_best_email(found_emails, web_url)
    src = "Website" if best else ""
    return best, src, fb_link


def save_and_reorder_dataset(df: pd.DataFrame, csv_2col_path: Path, csv_1enr_path: Path | None = None) -> int:
    """Save dataset incrementally, sorting companies with email to the top."""
    df_clean = df.copy()
    if "Cong_Ty" in df_clean.columns and "Công ty" not in df_clean.columns:
        df_clean["Công ty"] = df_clean["Cong_Ty"]
    if "Công ty" not in df_clean.columns:
        return 0

    df_clean = df_clean[~df_clean["Công ty"].apply(is_blacklisted_company)].reset_index(drop=True)

    # Clean phone and email
    if "SĐT" in df_clean.columns:
        df_clean["SĐT"] = df_clean["SĐT"].apply(ensure_phone_quote)
    if "Email" in df_clean.columns:
        df_clean["Email"] = df_clean["Email"].apply(clean_email)

    # Sort with_email first
    has_em = df_clean[df_clean["Email"] != ""].copy()
    no_em = df_clean[df_clean["Email"] == ""].copy()
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted["No."] = range(1, len(df_sorted) + 1)

    # Update mailto: link
    if "Liên Hệ mail" in df_sorted.columns:
        df_sorted["Liên Hệ mail"] = df_sorted["Email"].apply(lambda e: f"mailto:{e}" if e else "")

    # Ensure all 20 columns exist
    for col in COL_20_HEADERS:
        if col not in df_sorted.columns:
            df_sorted[col] = ""

    df_2col = df_sorted[COL_20_HEADERS]
    df_2col.to_csv(csv_2col_path, index=False, encoding="utf-8-sig")

    if csv_1enr_path:
        df_sorted.to_csv(csv_1enr_path, index=False, encoding="utf-8-sig")

    # Export READY file
    ready_path = csv_2col_path.parent / csv_2col_path.name.replace("_2COL.csv", "_ONLY_EMAILS_READY.csv")
    df_ready = df_sorted[df_sorted["Email"] != ""].copy()
    df_ready.to_csv(ready_path, index=False, encoding="utf-8-sig")

    # Mirror to gr_greece
    try:
        GR_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(csv_2col_path, GR_DIR / csv_2col_path.name)
        if csv_1enr_path and csv_1enr_path.exists():
            shutil.copy2(csv_1enr_path, GR_DIR / csv_1enr_path.name)
        if ready_path.exists():
            shutil.copy2(ready_path, GR_DIR / ready_path.name)
    except Exception:
        pass

    return len(has_em)


async def run_enrichment_pipeline(
    input_csv: Path,
    country_name: str = "Greece",
    headless: bool = False,
    limit: int | None = None,
) -> None:
    """Execute complete Google Maps enrichment for companies without email."""
    print("=" * 80)
    print("GOOGLE MAPS RESCUE & ENRICHMENT PIPELINE FOR COMPANIES WITHOUT EMAIL")
    print(f"Target CSV   : {input_csv.name}")
    print(f"Country      : {country_name}")
    print(f"Browser Mode : {'Headless (Background)' if headless else 'Interactive Visual (headless=False)'}")
    print("=" * 80 + "\n")

    if not input_csv.exists():
        print(f"[ERROR] Input CSV not found: {input_csv}")
        return

    df = pd.read_csv(input_csv, encoding="utf-8-sig", dtype=str).fillna("")
    name_col = "Công ty" if "Công ty" in df.columns else "Cong_Ty"
    web_col = "Liên Hệ" if "Liên Hệ" in df.columns else "Website"
    phone_col = "SĐT" if "SĐT" in df.columns else "SDT"
    addr_col = "Địa chỉ" if "Địa chỉ" in df.columns else "Dia_Chi"

    # Identify rows without email
    missing_indices = [
        i for i, r in df.iterrows()
        if not clean_email(r.get("Email", ""))
    ]

    total_rows = len(df)
    existing_emails = total_rows - len(missing_indices)
    print(f"[*] Total companies in dataset       : {total_rows}")
    print(f"[*] Already have email               : {existing_emails} ({(existing_emails * 100 / total_rows):.1f}%)")
    print(f"[*] NEED RESCUE (Without email)      : {len(missing_indices)} companies\n")

    if not missing_indices:
        print("[SUCCESS] 100% of companies already have email! Nothing to enrich.")
        return

    if limit:
        missing_indices = missing_indices[:limit]
        print(f"[*] Limiting run to {limit} companies as requested.")

    # Load cache
    cache = {}
    if DEFAULT_CACHE_JSON.exists():
        try:
            cache = json.loads(DEFAULT_CACHE_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass

    csv_1enr_path = input_csv.parent / input_csv.name.replace("_2COL.csv", "_1ENR.csv")
    if not csv_1enr_path.exists():
        csv_1enr_path = None

    rescued_emails = 0
    rescued_webs = 0
    rescued_phones = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chrome",
            headless=headless,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        context = await browser.new_context(
            no_viewport=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="el-GR" if country_name == "Greece" else "en-US",
        )
        # Preload Google consent cookies
        await context.add_cookies([
            {"name": "SOCS", "value": "CAESEwgDEgk2OTQ0NTgyODQaAmVuIAEaBgiA_LyaBg", "domain": ".google.com", "path": "/"},
            {"name": "CONSENT", "value": "YES+cb.20230531-04-p0.en+FX+999", "domain": ".google.com", "path": "/"},
        ])
        page = await context.new_page()

        for step, idx in enumerate(missing_indices, 1):
            comp = clean_text(df.at[idx, name_col])
            raw_addr = clean_text(df.at[idx, addr_col]) if addr_col in df.columns else ""
            curr_web = clean_text(df.at[idx, web_col]) if web_col in df.columns else ""
            curr_phone = clean_text(df.at[idx, phone_col]) if phone_col in df.columns else ""

            cache_key = f"{comp.lower()}::{raw_addr.lower()}"

            # Step 1: Check cache
            if cache_key in cache:
                c_data = cache[cache_key]
                if c_data.get("email"):
                    df.at[idx, "Email"] = c_data["email"]
                    rescued_emails += 1
                if c_data.get("website") and not curr_web:
                    df.at[idx, web_col] = c_data["website"]
                    rescued_webs += 1
                if c_data.get("phone") and not curr_phone:
                    df.at[idx, phone_col] = c_data["phone"]
                    rescued_phones += 1
                print(f"[{step}/{len(missing_indices)}] [CACHE] {comp[:32]:32s} | Mail={c_data.get('email') or '-'}")
                continue

            found_email = ""
            found_web = ""
            found_phone = ""

            # Step 2: Deep crawl website if already available (and not directory link)
            if curr_web and is_valid_company_website(curr_web):
                w_mail, _, _ = crawl_site_for_emails(curr_web)
                if w_mail:
                    found_email = w_mail
                    found_web = curr_web

            # Step 3: Google Maps Search if email still not found
            if not found_email:
                core_name = normalize_text_core(comp)
                city_hint = ""
                if raw_addr:
                    parts = [p.strip() for p in raw_addr.split(",") if p.strip()]
                    if len(parts) >= 2:
                        city_hint = parts[1]

                q_term = f"{core_name} {city_hint} {country_name}".strip()
                maps_url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(q_term)}?hl=en"

                try:
                    await page.goto(maps_url, wait_until="domcontentloaded", timeout=25000)
                    await page.wait_for_timeout(2000)

                    # Check Captcha
                    if "consent.google.com" in page.url or await page.query_selector("iframe[src*='recaptcha']"):
                        print("\a\a\n[!] GOOGLE MAPS CAPTCHA DETECTED! Vui long xac thuc tren Chrome...\n", flush=True)
                        await page.wait_for_timeout(10000)

                    matched = False

                    # Check single direct place card
                    h1 = await page.query_selector("h1.DUwDvf, h1.fontHeadlineLarge")
                    if h1:
                        title_txt = clean_text(await h1.inner_text())
                        is_ok, reason = is_valid_name_match(comp, title_txt)
                        if is_ok:
                            matched = True
                    else:
                        # Check multiple place results in feed
                        items = await page.query_selector_all('a[href*="/maps/place/"]')
                        for item in items[:4]:
                            aria = await item.get_attribute("aria-label") or ""
                            is_ok, reason = is_valid_name_match(comp, aria)
                            if is_ok:
                                await item.click()
                                await page.wait_for_timeout(2000)
                                matched = True
                                break

                    if matched:
                        # Extract official website
                        web_el = await page.query_selector('a[data-item-id="authority"], a[aria-label*="website" i]')
                        if web_el:
                            href = await web_el.get_attribute("href")
                            if href and is_valid_company_website(href):
                                found_web = href

                        # Extract phone
                        phone_el = await page.query_selector('button[data-item-id*="phone:"], button[aria-label*="phone" i]')
                        if phone_el:
                            p_txt = clean_text(await phone_el.inner_text())
                            if p_txt and any(ch.isdigit() for ch in p_txt):
                                found_phone = normalize_gr_phone(p_txt)

                        # Crawl website for email
                        if found_web:
                            w_mail, _, _ = crawl_site_for_emails(found_web)
                            if w_mail:
                                found_email = w_mail

                except Exception as e:
                    print(f"  [ERR] Maps search error on '{comp[:25]}': {e}")

            # Step 4: Apply results
            if found_email:
                df.at[idx, "Email"] = found_email
                rescued_emails += 1
            if found_web and not curr_web:
                df.at[idx, web_col] = found_web
                rescued_webs += 1
            if found_phone and not curr_phone:
                df.at[idx, phone_col] = found_phone
                rescued_phones += 1

            # Save to cache
            cache[cache_key] = {
                "company": comp,
                "email": found_email,
                "website": found_web or curr_web,
                "phone": found_phone or curr_phone,
                "done": True,
            }

            status_icon = "✔ RESCUED" if found_email else ("+WEB" if found_web else "-")
            print(
                f"[{step:3d}/{len(missing_indices):3d}] [{status_icon:8s}] {comp[:32]:32s} | "
                f"Mail={found_email or '-':26s} | Web={found_web or '-':30s}"
            )

            # Incremental auto-save every 5 rows
            if step % 5 == 0 or found_email:
                try:
                    DEFAULT_CACHE_JSON.parent.mkdir(parents=True, exist_ok=True)
                    tmp_c = DEFAULT_CACHE_JSON.with_suffix(".tmp")
                    with open(tmp_c, "w", encoding="utf-8") as cf:
                        json.dump(cache, cf, ensure_ascii=False, indent=2)
                    os.replace(tmp_c, DEFAULT_CACHE_JSON)
                    save_and_reorder_dataset(df, input_csv, csv_1enr_path)
                except Exception as e:
                    print(f"  [!] Auto-save error: {e}")

        # Final save
        try:
            DEFAULT_CACHE_JSON.parent.mkdir(parents=True, exist_ok=True)
            with open(DEFAULT_CACHE_JSON, "w", encoding="utf-8") as cf:
                json.dump(cache, cf, ensure_ascii=False, indent=2)
        except Exception:
            pass

        final_emails = save_and_reorder_dataset(df, input_csv, csv_1enr_path)
        await browser.close()

    print("\n" + "=" * 80)
    print("GOOGLE MAPS ENRICHMENT COMPLETED SUCCESSFULLY!")
    print(f"  Total Processed Companies : {len(missing_indices)}")
    print(f"  Newly Rescued Emails      : +{rescued_emails}")
    print(f"  Newly Rescued Websites    : +{rescued_webs}")
    print(f"  Newly Rescued Phones      : +{rescued_phones}")
    print(f"  Total Companies with Mail : {final_emails} / {total_rows} ({final_emails * 100 / total_rows:.1f}%)")
    print(f"  Output Saved              : {input_csv.name} (with_email sorted first)")
    print("=" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich companies without email via Google Maps")
    parser.add_argument("--input", type=str, default=str(DEFAULT_INPUT_CSV), help="Path to input 2COL or 1ENR CSV")
    parser.add_argument("--country", type=str, default="Greece", help="Country name for Google Maps search")
    parser.add_argument("--headless", action="store_true", help="Run browser in background headless mode")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of companies to enrich")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = ROOT_DIR / input_path

    # Auto-detect country from filename if default is Greece
    fn = input_path.name.upper()
    country = args.country
    if fn.startswith("LT_") and country == "Greece":
        country = "Lithuania"
    elif fn.startswith("SK_") and country == "Greece":
        country = "Slovakia"
    elif fn.startswith("RO_") and country == "Greece":
        country = "Romania"

    asyncio.run(
        run_enrichment_pipeline(
            input_csv=input_path,
            country_name=country,
            headless=args.headless,
            limit=args.limit,
        )
    )


if __name__ == "__main__":
    main()

