# -*- coding: utf-8 -*-
"""
GOOGLE MAPS DATA ENRICHMENT - LITHUANIAN HOTELS & ACCOMMODATION (LT_HOTL - NACE 55)
========================================================================================
Enriches LT_HOTL_INLT_2COL.csv (1,292 companies, NACE 55 Accommodation) combined with
metadata from LT_HOTL_INLT_1ENR.csv using:
  - Phase 1: Deep multi-tier crawl on companies with Website/Facebook missing Email.
  - Phase 2: Visual Chrome Google Maps lookup (strict Lithuanian name match & Place ID),
             Category validation (Rule 3 in scrape-hotel), OTA / Aggregator pre-filtering
             (Rule 5 in scrape-hotel), Website & Phone extraction, Priority Baltic subpage
             crawl (Rule 7), Facebook About fallback, and Maps panel fallback.

Outputs (UTF-8 with BOM / csv-only / GEMINI.md Rules 1, 2, 3, 5, 10, 11, 12):
  - LT_HOTL_GMAP_1ENR.csv
  - LT_HOTL_GMAP_2COL.csv
  - LT_HOTL_GMAP_ONLY_EMAILS_READY.csv
  - Syncs LT_HOTL_INLT_2COL.csv & LT_HOTL_INLT_ONLY_EMAILS_READY.csv
    (creates archive/lt_lithuania/LT_HOTL_INLT_2COL_pre_maps_backup.csv once)
  - Copies all outputs to csdl_mlt/ and archive/lt_lithuania/
"""

import argparse
import asyncio
import html as html_lib
import json
import os
import re
import shutil
import ssl
import sys
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent

INPUT_2COL_PATH = ROOT_DIR / "LT_HOTL_INLT_2COL.csv"
INPUT_1ENR_PATH = ROOT_DIR / "LT_HOTL_INLT_1ENR.csv"
BACKUP_2COL_PATH = ROOT_DIR / "archive" / "lt_lithuania" / "LT_HOTL_INLT_2COL_pre_maps_backup.csv"

OUTPUT_1ENR_PATH = ROOT_DIR / "LT_HOTL_GMAP_1ENR.csv"
OUTPUT_2COL_PATH = ROOT_DIR / "LT_HOTL_GMAP_2COL.csv"
OUTPUT_READY_PATH = ROOT_DIR / "LT_HOTL_GMAP_ONLY_EMAILS_READY.csv"

SYNC_INLT_2COL_PATH = ROOT_DIR / "LT_HOTL_INLT_2COL.csv"
SYNC_INLT_READY_PATH = ROOT_DIR / "LT_HOTL_INLT_ONLY_EMAILS_READY.csv"

CACHE_PATH = ROOT_DIR / "crawlmail" / "cache_enrich_maps_lt_hotl.json"
CSDL_DIR = ROOT_DIR / "csdl_mlt"
ARCHIVE_DIR = ROOT_DIR / "archive" / "lt_lithuania"

MAPS_TIMEOUT = 25000
DELAY_AFTER_SEARCH = 2.0
DELAY_AFTER_CLICK = 2.0

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
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

# Rule 5 in scrape-hotel: OTA & Aggregator Domains to strictly exclude from crawling
OTA_AND_DIRECTORY_DOMAINS = {
    "booking.com", "agoda.com", "airbnb.com", "expedia.com", "tripadvisor.com",
    "hotels.com", "trivago.com", "kayak.com", "priceline.com", "hostelworld.com",
    "vrbo.com", "viator.com", "getyourguide.com", "makemytrip.com", "trip.com",
    "orbitz.com", "travelocity.com", "hotwire.com", "skyscanner.com", "opentable.com",
    "freecancellations.com", "bluepillow.com", "bluepillow.lt", "placescollective.com",
    "reservation.expert", "exelentbnb.com", "linktr.ee", "yellowpages.com",
    "facebook.com", "fb.com", "instagram.com", "linkedin.com", "youtube.com",
    "twitter.com", "x.com", "tiktok.com", "pinterest.com", "google.com",
    "maps.google.com", "goo.gl", "wikipedia.org", "yelp.com", "sentry.io",
    "rekvizitai.vz.lt", "rekvizitai.lt", "info.lt", "visalietuva.lt", "imones.lt",
    "cr.lt", "okredo.com", "scoris.lt", "creditinfo.lt", "registrucentras.lt",
    "1588.lt", "1551.lt", "infoplius.lt", "imoniugidas.lt", "litorg.cc",
    "delfi.lt", "15min.lt", "lrytas.lt", "trustpilot.com", "schema.org",
}

BLACKLIST_DOMAINS = OTA_AND_DIRECTORY_DOMAINS | {
    "wix.com", "wixpress.com", "wordpress.com", "squarespace.com", "weebly.com",
    "godaddy.com", "example.com", "example.org", "domain.com", "yourdomain.com",
}

JUNK_EMAIL_DOMAINS = BLACKLIST_DOMAINS | {
    "placeholder.com", "templatemonster.com", "themeforest.net", "bootstrapmade.com",
    "pavyzdys.lt", "imone.lt", "email.com", "mail.com",
}

SYSTEM_USERNAMES = {
    "noreply", "no-reply", "donotreply", "privacy", "terms", "cookies",
    "gdpr", "abuse", "security", "webmaster", "sentry", "mailer-daemon",
    "test", "example", "hostmaster", "postmaster", "root", "dataprivacy",
}

TEMPLATE_USERNAMES = {
    "youremail", "your-email", "your_email", "your.email",
    "yourname", "your-name", "your_name", "your.name",
    "yourcompany", "myemail", "myname", "username", "user", "name",
    "sample", "demo", "testing", "placeholder", "someone", "nobody",
    "john.doe", "johndoe", "jane.doe", "janedoe", "first.last",
    "jusu", "tavo", "vardas", "pavarde",
}

EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b")
OBFUSCATED_EMAIL_REGEX = re.compile(
    r"\b([A-Za-z0-9._%+-]{1,64})\s*(?:\[at\]|\(at\)|\{at\}|\bat\b)\s*([A-Za-z0-9.-]+)\s*(?:\[dot\]|\(dot\)|\{dot\}|\.)\s*([A-Za-z]{2,10})\b",
    re.I,
)
INVALID_EXTS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js",
    ".pdf", ".woff", ".woff2", ".ico", ".mp4", ".avi", ".zip", ".rar",
)

LT_CONTACT_KEYWORDS_P10 = (
    "kontaktai", "kontakt", "susisiekite", "susisiekti", "contact", "contacts",
    "contact-us", "get-in-touch", "reach-us", "rekvizitai",
)
LT_HOTEL_KEYWORDS_P8 = (
    "rezervacija", "rezervacijos", "booking", "reservation", "reservations",
    "recepcija", "reception", "frontdesk", "karjera", "darbas", "apie", "apie-mus",
    "about", "about-us", "hotel", "viesbutis", "sodyba", "apartamentai",
)
LT_GUESS_SUBPATHS = (
    "/kontaktai", "/kontaktai/", "/kontaktai.html", "/kontaktai.php",
    "/rezervacija", "/rezervacijos", "/booking", "/reception",
    "/susisiekite", "/rekvizitai", "/apie-mus", "/apie-mus.html",
    "/karjera", "/darbas", "/contact", "/contact.html", "/contact-us",
    "/about", "/about-us",
)

# Hotel email scoring keywords
HR_KEYWORDS = (
    "karjera", "cv", "darbas", "personalas", "personalo", "atranka", "hr",
    "jobs", "recruitment", "career", "talent", "work",
)
HOTEL_RECEPTION_KEYWORDS = (
    "recepcija", "reception", "frontdesk", "rezervacija", "rezervacijos",
    "reservation", "reservations", "booking", "hotel", "viesbutis", "stay",
)
EXEC_KEYWORDS = (
    "direktorius", "vadovas", "ceo", "director", "manager", "savininkas",
    "general", "valdymas", "owner",
)
OFFICIAL_KEYWORDS = (
    "info", "kontaktai", "kontakt", "office", "biuras", "administracija",
    "sekretoriatas", "pastas", "mail", "bendras",
)

# Rule 3 in scrape-hotel: Allowed categories on Google Maps
ALLOWED_HOTEL_CATEGORIES = (
    "hotel", "viešbutis", "viesbutis", "motel", "motelis", "hostel", "hostelis",
    "resort", "poilsio", "svečių namai", "sveciu namai", "guest house", "inn",
    "lodging", "accommodation", "nakvynė", "nakvyne", "apartament", "apartamentai",
    "camping", "kempingas", "sodyba", "kaimo turizmo", "poilsiavietė", "spa",
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
    """Enforce permanent company blacklist with Unicode NFKD accent folding (Rule 12)."""
    if not name:
        return False
    n = unicodedata.normalize("NFKD", str(name)).lower()
    n_clean = "".join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)


def clean_phone_lt(raw_phone: str) -> str:
    """Normalize Lithuanian phone numbers and prefix with leading apostrophe (Rule 2)."""
    if not raw_phone or str(raw_phone).strip() in ("", "None", "nan"):
        return ""
    s = str(raw_phone).strip().lstrip("'").strip()
    digits = re.sub(r"[^0-9]", "", s)
    if not digits:
        return ""
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("370"):
        pass
    elif digits.startswith("8") and len(digits) == 9:
        digits = "370" + digits[1:]
    elif digits.startswith("0") and len(digits) in (9, 10):
        digits = "370" + digits[1:]
    elif len(digits) == 8:
        digits = "370" + digits

    if digits.startswith("370") and len(digits) == 11:
        return f"'+370 {digits[3:5]} {digits[5:8]} {digits[8:]}"
    return f"'+{digits}"


def clean_email(email_str: str) -> str:
    """Decode escapes, strip u00XX / %20 / nbsp / stuck tail artifacts, and normalize (Rule 3)."""
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
    for suffix in ("tel", "mob", "fax", "phone", "el"):
        if e.endswith(suffix) and "@" in e:
            tld = e.split("@")[-1].split(".")[-1]
            if len(tld) > 5:
                e = e[: -len(suffix)]
    return e.strip()


def decode_cf_hex(cf_hex: str) -> str:
    """Decode Cloudflare hex email protection payload."""
    try:
        r = int(cf_hex[:2], 16)
        return "".join(chr(int(cf_hex[i : i + 2], 16) ^ r) for i in range(2, len(cf_hex), 2))
    except Exception:
        return ""


def extract_place_id(url: str) -> str:
    """Rule 1 in scrape-hotel: Extract Google Place ID (0x...:0x...) to identify location."""
    if not url:
        return ""
    m = re.search(r"1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)", url)
    if m:
        return m.group(1).lower()
    return url.split("?")[0].lower()


def is_ota_or_directory_link(url: str) -> bool:
    """Rule 5 in scrape-hotel: Pre-crawl filter rejecting OTA / Aggregator / Booking platforms."""
    if not url:
        return True
    u_clean = urllib.parse.unquote(str(url)).strip().lower()
    if not u_clean.startswith(("http://", "https://")):
        u_clean = f"https://{u_clean}"
    try:
        parsed = urllib.parse.urlparse(u_clean)
        netloc = parsed.netloc.lower().replace("www.", "")
        for d in OTA_AND_DIRECTORY_DOMAINS:
            if netloc == d or netloc.endswith(f".{d}"):
                return True
        path = parsed.path.lower()
        if "/search/" in path or "/search?" in u_clean:
            return True
        if any(x in netloc for x in ["pillow", "cancellation", "booking", "voyager", "haven", "reservation"]):
            if not any(x in netloc for x in ["hotel", "resort", "villa", "guest", "viesbutis"]):
                return True
    except Exception:
        pass
    return False


def is_valid_website(url: str) -> bool:
    """Validate genuine business website; rejects directories and OTAs."""
    if not url or not isinstance(url, str):
        return False
    u = url.strip().lower()
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    try:
        parsed = urllib.parse.urlparse(u)
        netloc = parsed.netloc.replace("www.", "").lower().split(":")[0]
        if not netloc or "." not in netloc or len(netloc) < 4:
            return False
        if any(netloc == b or netloc.endswith("." + b) for b in BLACKLIST_DOMAINS):
            return False
        if is_ota_or_directory_link(u):
            return False
        return True
    except Exception:
        return False


def is_facebook_url(url: str) -> bool:
    """Check if URL points to a company Facebook page."""
    if not url or not isinstance(url, str):
        return False
    u = url.strip().lower()
    return ("facebook.com/" in u or "fb.com/" in u) and not any(
        x in u for x in ("/sharer", "/share.php", "/dialog/", "facebook.com/tr?", "profile.php?id=")
    )


def normalize_text(text: str) -> str:
    """Fold Unicode diacritics via NFKD and strip decorative quotes."""
    if not text:
        return ""
    n = unicodedata.normalize("NFKD", str(text)).lower()
    t = "".join(c for c in n if not unicodedata.combining(c))
    return re.sub(r"[\"'„“”«»`´]", "", t).strip()


def clean_company_name_lt(name: str) -> str:
    """Strip bracketed annotations, Lithuanian legal forms, and outer punctuation (Rule 11)."""
    if not name:
        return ""
    t = normalize_text(name)
    t = re.sub(r"\(.*?\)|\[.*?\]", "", t).strip()
    legal_forms = (
        "uzdaroji akcine bendrove", "mazoji bendrija", "akcine bendrove",
        "individuali imone", "viesoji istaiga", "zemes ukio bendrove",
        "bendra imone", "uab", "mb", "ab", "ii", "vsi", "tub", "kub",
        "zub", "kb", "filialas", "skyrius", "kooperatyvas", "atstovybe",
    )
    for lf in sorted(legal_forms, key=len, reverse=True):
        t = re.sub(rf"\b{re.escape(lf)}\b", "", t).strip()
    return re.sub(r"\s+", " ", t).strip(" ,.-:;|/")


def is_valid_name_match_lt(query_name: str, candidate_name: str) -> tuple[bool, str]:
    """Strict Lithuanian hotel business name matcher supporting NFKD, brackets, translations, and delimiters."""
    if not query_name or not candidate_name:
        return False, "EMPTY"

    q_clean = clean_company_name_lt(query_name)
    c_clean = clean_company_name_lt(candidate_name)
    if not q_clean or not c_clean:
        return False, "EMPTY_AFTER_CLEAN"

    # Hospitality transliteration folding (viktorija <-> victoria)
    q_norm = q_clean.replace("victoria", "viktorija")
    c_norm = c_clean.replace("victoria", "viktorija")

    q_alnum = re.sub(r"[^a-z0-9]", "", q_norm)
    c_alnum = re.sub(r"[^a-z0-9]", "", c_norm)

    if q_alnum == c_alnum:
        return True, "EXACT"

    # Match when candidate strips brackets
    c_nobrackets = re.sub(r"\(.*?\)|\[.*?\]", "", normalize_text(candidate_name)).strip()
    c_nobrackets_clean = clean_company_name_lt(c_nobrackets).replace("victoria", "viktorija")
    if q_norm == c_nobrackets_clean:
        return True, "BRACKET_MATCH"

    # Match across standard delimiters (-, |, /, :)
    c_norm_full = normalize_text(candidate_name).replace("victoria", "viktorija")
    parts = [clean_company_name_lt(p).replace("victoria", "viktorija") for p in re.split(r"[-–—|/:,]", c_norm_full) if p.strip()]
    if any(clean_company_name_lt(p).replace("victoria", "viktorija") == q_norm for p in parts if p):
        return True, "DELIMITER_MATCH"

    # Substring match (for commercial vs legal hotel names, e.g. "Victoria Hotel Klaipeda" vs "Klaipedos Viktorija")
    if len(q_norm) >= 4 and (q_norm in c_norm or c_norm in q_norm or q_norm in c_nobrackets_clean):
        return True, "SUBSTRING_MATCH"

    # Token overlap check
    q_tokens = [tok for tok in q_norm.split() if len(tok) >= 2]
    c_tokens = [tok for tok in c_norm.split() if len(tok) >= 2]
    if q_tokens and c_tokens:
        q_set = set(q_tokens)
        c_set = set(c_tokens)
        if q_set == c_set:
            return True, "TOKEN_SET_EXACT"
        if q_set.issubset(c_set) and len(q_set) >= 2:
            return True, "TOKEN_SUBSET"
        overlap = q_set & c_set
        if len(q_set) >= 2 and len(overlap) / len(q_set) >= 0.5:
            return True, "TOKEN_OVERLAP_HIGH"

    return False, "NO_MATCH"


def score_email_b2b_lt(email: str, domain: str = "") -> int:
    """Score B2B recruitment/hospitality value of email; returns -1 for junk."""
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
    if u in SYSTEM_USERNAMES or u in TEMPLATE_USERNAMES:
        return -1
    if any(k in u for k in ("youremail", "yourname", "placeholder", "demo", "sample", "test")):
        return -1

    score = 10
    clean_d = domain.lower().replace("www.", "").split("/")[0] if domain else ""
    if clean_d and (clean_d in d or d in clean_d):
        score += 50
    elif d.endswith(".lt"):
        score += 30

    # 1. Staffing / Recruitment / HR
    if any(k in u for k in HR_KEYWORDS):
        score += 55
    # 2. Reception / Booking / Hotel frontdesk
    elif any(k in u for k in HOTEL_RECEPTION_KEYWORDS):
        score += 48
    # 3. Executive leadership
    elif any(k in u for k in EXEC_KEYWORDS):
        score += 45
    # 4. Official hotel business contact
    elif any(k in u for k in OFFICIAL_KEYWORDS):
        score += 40
    elif "." in u and score >= 60:
        score += 25
    elif d in ("gmail.com", "inbox.lt", "one.lt"):
        score += 15
    elif any(k in u for k in ("support", "admin", "buhalterija")):
        score += 5

    return score


def select_best_email(emails: list[str] | set[str], domain: str = "") -> str:
    """Select the single highest-scoring valid B2B email."""
    valid = [clean_email(e) for e in emails if e]
    valid = [e for e in set(valid) if e and score_email_b2b_lt(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b_lt(e, domain))


def extract_emails_from_html(html_text: str) -> set[str]:
    """Extract and clean emails from mailto, Cloudflare hex, obfuscated, and visible DOM text."""
    found = set()
    if not html_text:
        return found

    for em in EMAIL_REGEX.findall(html_text):
        c = clean_email(em)
        if c and score_email_b2b_lt(c) > 0:
            found.add(c)

    for cf_hex in re.findall(r'data-cfemail="([0-9a-fA-F]+)"', html_text):
        c = clean_email(decode_cf_hex(cf_hex))
        if c and score_email_b2b_lt(c) > 0:
            found.add(c)

    for m in OBFUSCATED_EMAIL_REGEX.finditer(html_text):
        reconstructed = f"{m.group(1)}@{m.group(2)}.{m.group(3)}"
        c = clean_email(reconstructed)
        if c and score_email_b2b_lt(c) > 0:
            found.add(c)

    return found


def fetch_html_fast(url: str, timeout: float = 6.0) -> str:
    """Fetch website HTML using curl_cffi Chrome impersonation with urllib fallback."""
    if not url:
        return ""
    u = url.strip()
    if not u.startswith(("http://", "https://")):
        u = "https://" + u

    try:
        import curl_cffi.requests as c_requests
        s = c_requests.Session(impersonate="chrome120")
        for v in (True, False):
            try:
                r = s.get(u, timeout=timeout, allow_redirects=True, verify=v)
                if r.status_code == 200:
                    return r.text or ""
            except Exception:
                pass
    except Exception:
        pass

    try:
        req = urllib.request.Request(u, headers=HEADERS)
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=timeout) as resp:
            raw = resp.read()
            return raw.decode("utf-8", errors="ignore")
    except Exception:
        return ""


async def fetch_html_playwright(page, url: str, timeout: int = 10000) -> str:
    """Fallback fetch via Playwright browser tab."""
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        await asyncio.sleep(1.0)
        return await page.content()
    except Exception:
        return ""


async def crawl_site_and_socials(
    website_url: str, existing_fb: str = "", pw_page=None
) -> tuple[str, str, str]:
    """
    Multi-tier crawler:
      1. Homepage
      2. Priority 10 Contact / Booking / Reception subpages
      3. Facebook Fanpage About fallback
    """
    found_emails = set()
    fb_candidates = [existing_fb] if existing_fb else []

    if is_valid_website(website_url):
        home_html = fetch_html_fast(website_url, timeout=4.5)
        if not home_html and pw_page:
            home_html = await fetch_html_playwright(pw_page, website_url, timeout=9000)

        if home_html:
            found_emails.update(extract_emails_from_html(home_html))

            soup = BeautifulSoup(home_html, "html.parser")
            parsed_home = urllib.parse.urlparse(website_url)
            root = parsed_home.netloc.lower().replace("www.", "")

            # Look for Facebook link
            for a in soup.find_all("a", href=True):
                h = a["href"].strip()
                if is_facebook_url(h) and h not in fb_candidates:
                    fb_candidates.append(h)

            cur_best = select_best_email(found_emails, root)
            if cur_best and score_email_b2b_lt(cur_best, root) >= 90:
                return cur_best, (fb_candidates[0] if fb_candidates else ""), "Website"

            # Discover Contact & Booking subpages
            subpage_urls = []
            for a in soup.find_all("a", href=True):
                h = a["href"].strip()
                t = a.get_text(strip=True).lower()
                is_contact = any(k in t or k in h.lower() for k in LT_CONTACT_KEYWORDS_P10)
                is_hotel = any(k in t or k in h.lower() for k in LT_HOTEL_KEYWORDS_P8)
                if is_contact or is_hotel:
                    full = urllib.parse.urljoin(website_url, h)
                    parsed_full = urllib.parse.urlparse(full)
                    if parsed_full.netloc.lower().replace("www.", "") == root:
                        if full not in subpage_urls and full.rstrip("/") != website_url.rstrip("/"):
                            subpage_urls.append(full)

            if not subpage_urls:
                for sp in LT_GUESS_SUBPATHS[:6]:
                    subpage_urls.append(urllib.parse.urljoin(website_url, sp))

            for sp_url in subpage_urls[:6]:
                sub_html = fetch_html_fast(sp_url, timeout=3.5)
                if sub_html:
                    found_emails.update(extract_emails_from_html(sub_html))
                    cur_best = select_best_email(found_emails, root)
                    if cur_best and score_email_b2b_lt(cur_best, root) >= 90:
                        return cur_best, (fb_candidates[0] if fb_candidates else ""), "Website"

            best_email = select_best_email(found_emails, root)
            if best_email:
                return best_email, (fb_candidates[0] if fb_candidates else ""), "Website"

    best_fb = fb_candidates[0] if fb_candidates else ""
    if best_fb:
        for fb_url in (best_fb.rstrip("/") + "/about", best_fb):
            fb_html = fetch_html_fast(fb_url, timeout=4.5)
            if not fb_html and pw_page:
                fb_html = await fetch_html_playwright(pw_page, fb_url, timeout=10000)
            if fb_html:
                fb_best = select_best_email(extract_emails_from_html(fb_html))
                if fb_best:
                    return fb_best, best_fb, "Facebook"

    return "", best_fb, ""


def make_cache_key(row) -> str:
    """Build deterministic cache key using Company_Code when present or normalized name+city."""
    code = clean_text(row.get("Company_Code", ""))
    if code:
        return code
    comp = normalize_text(row.get("Cong ty", "") or row.get("Công ty", ""))
    city = normalize_text(row.get("City", ""))
    return f"{comp}::{city}"


def load_cache() -> dict:
    """Load persistent JSON cache if present."""
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(f"[*] Loaded {len(data):,} records from cache {CACHE_PATH.name}.")
            return data
        except Exception as e:
            print(f"[!] Could not load cache cleanly: {e}")
    return {}


def save_cache(cache: dict) -> None:
    """Persist cache JSON atomically to prevent partial writes (Rule 5)."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = CACHE_PATH.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, CACHE_PATH)


def apply_cache_to_df(df: pd.DataFrame, cache: dict) -> None:
    """Merge cached Maps/Web enrichments cleanly into DataFrame."""
    for idx, row in df.iterrows():
        key = make_cache_key(row)
        c = cache.get(key)
        if not c:
            comp_clean = normalize_text(row.get("Cong ty", "") or row.get("Công ty", ""))
            c = cache.get(comp_clean)
        if not c:
            continue

        c_em = c.get("Email", "")
        if c_em and not clean_email(df.at[idx, "Email"]):
            df.at[idx, "Email"] = clean_email(c_em)

        c_web = c.get("Website") or c.get("Web") or ""
        if c_web and is_valid_website(c_web) and not is_valid_website(df.at[idx, "Website"]):
            df.at[idx, "Website"] = c_web

        c_sdt = c.get("SDT") or c.get("SĐT") or c.get("Phone") or ""
        if c_sdt and not clean_phone_lt(df.at[idx, "SDT"]):
            df.at[idx, "SDT"] = clean_phone_lt(c_sdt)

        c_addr = c.get("Dia_Chi") or c.get("Address") or ""
        if c_addr and not clean_text(df.at[idx, "Dia_Chi"]):
            df.at[idx, "Dia_Chi"] = clean_text(c_addr)

        if c.get("Facebook_URL") and not clean_text(df.at[idx, "Facebook_URL"]):
            df.at[idx, "Facebook_URL"] = c["Facebook_URL"]
        if c.get("Email_Source") and not clean_text(df.at[idx, "Email_Source"]):
            df.at[idx, "Email_Source"] = c["Email_Source"]


def extract_city_from_address(addr: str) -> str:
    """Extract city or municipality from Lithuanian address string."""
    if not addr:
        return ""
    parts = [p.strip() for p in addr.split(",") if p.strip()]
    if len(parts) >= 2:
        for p in parts:
            if any(k in p.lower() for k in ("vilnius", "kaunas", "klaipėda", "klaipeda", "šėta", "palanga", "druskininkai", "birštonas", "neringa")):
                return p
        return parts[-1]
    return parts[0] if parts else ""


def load_source_dataset() -> pd.DataFrame | None:
    """Load GMAP master if resuming, else combine LT_HOTL_INLT_2COL + LT_HOTL_INLT_1ENR."""
    if OUTPUT_1ENR_PATH.exists():
        print(f"[*] Resuming from master file: {OUTPUT_1ENR_PATH.name}")
        df = pd.read_csv(OUTPUT_1ENR_PATH, encoding="utf-8-sig", dtype=str).fillna("")
    elif INPUT_1ENR_PATH.exists():
        print(f"[*] Loading enriched base: {INPUT_1ENR_PATH.name} + {INPUT_2COL_PATH.name}")
        df = pd.read_csv(INPUT_1ENR_PATH, encoding="utf-8-sig", dtype=str).fillna("")
        if INPUT_2COL_PATH.exists():
            df2 = pd.read_csv(INPUT_2COL_PATH, encoding="utf-8-sig", dtype=str).fillna("")
            map_2col = {normalize_text(r.get("Công ty", "")): r for _, r in df2.iterrows() if normalize_text(r.get("Công ty", ""))}
            for idx, r in df.iterrows():
                r2 = map_2col.get(normalize_text(r.get("Cong ty", "")))
                if r2 is None:
                    continue
                em2 = clean_email(r2.get("Email", ""))
                if em2 and not clean_email(r.get("Email", "")):
                    df.at[idx, "Email"] = em2
                sdt2 = clean_phone_lt(r2.get("SĐT", ""))
                if sdt2 and not clean_phone_lt(r.get("SDT", "")):
                    df.at[idx, "SDT"] = sdt2
                lh2 = str(r2.get("Liên Hệ", "")).strip()
                if is_valid_website(lh2) and not is_valid_website(r.get("Website", "")):
                    df.at[idx, "Website"] = lh2
                elif is_facebook_url(lh2) and not str(r.get("Facebook_URL", "")).strip():
                    df.at[idx, "Facebook_URL"] = lh2
    elif INPUT_2COL_PATH.exists():
        print(f"[*] Loading directly from Cold Mail CSV: {INPUT_2COL_PATH.name}")
        df2 = pd.read_csv(INPUT_2COL_PATH, encoding="utf-8-sig", dtype=str).fillna("")
        rows = []
        for idx, r in df2.iterrows():
            lh = str(r.get("Liên Hệ", "")).strip()
            addr_val = clean_text(r.get("Địa chỉ", ""))
            rows.append(
                {
                    "No.": r.get("No.", str(idx + 1)),
                    "Company_Code": "",
                    "Cong ty": clean_text(r.get("Công ty", "")),
                    "City": extract_city_from_address(addr_val),
                    "Nam_Thanh_Lap": clean_text(r.get("Ngày đăng", "")),
                    "Category": clean_text(r.get("Category", "")),
                    "Doanh_Thu": clean_text(r.get("Lương", "")),
                    "Detail_URL": lh if "litorg.cc" in lh.lower() else "",
                    "SDT": clean_text(r.get("SĐT", "")),
                    "Website": lh if is_valid_website(lh) else "",
                    "Facebook_URL": lh if is_facebook_url(lh) else "",
                    "Email": clean_text(r.get("Email", "")),
                    "Dia chi": addr_val,
                    "Nguoi_Quan_Ly": clean_text(r.get("Người liên hệ", "")),
                    "Chuc_Danh": clean_text(r.get("Chức danh", "")),
                    "Dia_Chi": addr_val,
                }
            )
        df = pd.DataFrame(rows)
    else:
        return None

    required_cols = (
        "Website", "Email", "SDT", "Dia chi", "Dia_Chi", "City",
        "Nguoi_Quan_Ly", "Chuc_Danh", "Detail_URL", "Facebook_URL", "Email_Source",
        "Place_ID", "Google_Category", "Permanently_Closed",
    )
    for col in required_cols:
        if col not in df.columns:
            df[col] = ""

    for idx, r in df.iterrows():
        if not clean_text(df.at[idx, "City"]):
            df.at[idx, "City"] = extract_city_from_address(clean_text(r.get("Dia_Chi") or r.get("Dia chi", "")))

    return df


def export_and_sync_all_files(df: pd.DataFrame, sync_inlt: bool = True) -> int:
    """Export 1ENR, 2COL, and ONLY_EMAILS_READY CSVs (utf-8-sig) and sync folders (Rules 1, 2, 3, 10)."""
    df_clean = df[~df["Cong ty"].apply(is_blacklisted_company)].copy()
    df_clean["SDT"] = df_clean["SDT"].apply(clean_phone_lt)
    df_clean["Email"] = df_clean["Email"].apply(clean_email)

    # Sort rows with email first (Rule 3)
    has_em = df_clean[df_clean["Email"] != ""].copy()
    no_em = df_clean[df_clean["Email"] == ""].copy()
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted["No."] = range(1, len(df_sorted) + 1)
    df_sorted.to_csv(OUTPUT_1ENR_PATH, index=False, encoding="utf-8-sig")

    coldmail_rows = []
    for _, r in df_sorted.iterrows():
        comp_name = clean_text(r.get("Cong ty", ""))
        manager = clean_text(r.get("Nguoi_Quan_Ly", ""))
        title = clean_text(r.get("Chuc_Danh", "")) or ("Direktorius" if manager else "Vadovas / Viešbučio Vadovas")
        web_val = clean_text(r.get("Website", ""))
        email_val = clean_email(r.get("Email", ""))
        phone_val = clean_phone_lt(r.get("SDT", ""))
        city_val = clean_text(r.get("City", ""))
        addr_val = clean_text(r.get("Dia_Chi", "")) or clean_text(r.get("Dia chi", ""))
        if not addr_val and city_val:
            addr_val = f"{city_val}, Lithuania"

        cat_val = clean_text(r.get("Category", "")) or clean_text(r.get("Google_Category", ""))
        if not cat_val:
            cat_val = "Hotels & Accommodation (Lithuania)"

        durl = clean_text(r.get("Detail_URL", ""))
        gmap_url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(comp_name)}" if not web_val else ""
        contact_val = web_val or durl or gmap_url

        coldmail_rows.append(
            {
                "No.": r.get("No.", ""),
                "Công ty": comp_name,
                "Chức danh": title,
                "Người liên hệ": manager,
                "SĐT": phone_val,
                "Liên Hệ": contact_val,
                "Email": email_val,
                "Liên Hệ mail": f"mailto:{email_val}" if email_val else contact_val,
                "Địa chỉ": addr_val or "Lithuania",
                "Lương": clean_text(r.get("Doanh_Thu", "")),
                "Ngày đăng": clean_text(r.get("Nam_Thanh_Lap", "")),
                "Hạn tuyển": f"Darbuotojai: {clean_text(r.get('So_Nhan_Vien', ''))}" if clean_text(r.get('So_Nhan_Vien', '')) else "",
                "Check gửi": "Chưa gửi",
                "Last Subject": "",
                "Last Body HTML": "",
                "Trạng thái Reply": "",
                "Lần Follow-up": "",
                "Ngày Follow-up gần nhất": "",
                "Mailbox đã dùng": "",
                "Category": cat_val,
            }
        )

    df_2col = pd.DataFrame(coldmail_rows, columns=COLDMAIL_COLUMNS)
    df_2col.to_csv(OUTPUT_2COL_PATH, index=False, encoding="utf-8-sig")

    df_ready = df_2col[df_2col["Email"] != ""].copy()
    df_ready["No."] = range(1, len(df_ready) + 1)
    df_ready.to_csv(OUTPUT_READY_PATH, index=False, encoding="utf-8-sig")

    if sync_inlt:
        try:
            df_2col.to_csv(SYNC_INLT_2COL_PATH, index=False, encoding="utf-8-sig")
            df_ready.to_csv(SYNC_INLT_READY_PATH, index=False, encoding="utf-8-sig")
        except Exception as e:
            print(f"[WARN] Failed to sync to INLT CSV files: {e}")

    for extra_dir in (CSDL_DIR, ARCHIVE_DIR):
        extra_dir.mkdir(parents=True, exist_ok=True)
        for src_path in (OUTPUT_1ENR_PATH, OUTPUT_2COL_PATH, OUTPUT_READY_PATH):
            try:
                shutil.copy2(src_path, extra_dir / src_path.name)
            except Exception:
                pass

    return len(has_em)


async def handle_google_captcha_if_present(maps_page, df, cache, sync_inlt: bool) -> bool:
    """Detect Google Captcha, sound chime alert (\a), and wait for user resolution (Rule 4)."""
    cur_u = maps_page.url.lower()
    page_txt_low = (await maps_page.content()).lower()
    has_recaptcha = await maps_page.query_selector("iframe[src*='recaptcha']")
    if "sorry" in cur_u or "captcha" in cur_u or "unusual traffic" in page_txt_low or has_recaptcha:
        save_cache(cache)
        export_and_sync_all_files(df, sync_inlt=sync_inlt)
        print("\a" * 3)
        print("\n" + "=" * 80)
        print("  [!] >>> PHÁT HIỆN GOOGLE CAPTCHA! <<<")
        print("  [!] Cửa sổ Chrome đang mở. Vui lòng giải quyết Captcha trên trình duyệt.")
        print("  [!] Sau khi giải xong, nhấn phím ENTER tại Terminal này để tiếp tục...")
        print("=" * 80 + "\n")
        await asyncio.to_thread(input, "")
        return True
    return False


async def extract_hotel_place_fields(maps_page) -> tuple[str, str, str, str, str, str, str]:
    """
    Extract Hotel Website, Facebook, Phone, Address, Category, Place ID, and Closed status.
    Adheres strictly to Rule 1, 2, 3, 4, 5 of scrape-hotel skill.
    """
    found_web = ""
    found_fb = ""
    found_phone = ""
    found_addr = ""
    found_cat = ""
    place_id = extract_place_id(maps_page.url)
    is_closed = "No"

    # Rule 4 in scrape-hotel: Detect Permanently Closed
    page_content_low = (await maps_page.content()).lower()
    if any(k in page_content_low for k in ("permanently closed", "uždaryta visam laikui", "uzdaryta visam laikui")):
        is_closed = "Yes"

    # Rule 2 in scrape-hotel: Category selector with retry loop
    category_selector = "span.mgr77e, button.DkEaCc, button.DkEaL, div.F7nice ~ span, div.F7nice ~ button"
    for _ in range(8):
        cat_el = await maps_page.query_selector(category_selector)
        if cat_el:
            found_cat = clean_text(await cat_el.inner_text())
            if found_cat:
                break
        await asyncio.sleep(0.15)

    # Website button
    web_btn = await maps_page.query_selector(
        'a[data-item-id="authority"], a[aria-label*="Svetain"], a[aria-label*="svetain"], a[aria-label*="Website"]'
    )
    if web_btn:
        w_href = (await web_btn.get_attribute("href") or "").strip()
        # Rule 5 in scrape-hotel: Pre-crawl OTA / Aggregator check
        if is_ota_or_directory_link(w_href):
            found_web = ""  # Discard OTA link
        elif is_valid_website(w_href):
            found_web = w_href
        elif is_facebook_url(w_href):
            found_fb = w_href

    # Phone button
    phone_btn = await maps_page.query_selector(
        'button[data-item-id^="phone:"], button[aria-label*="Telefon"], button[aria-label*="Phone"]'
    )
    if phone_btn:
        p_attr = await phone_btn.get_attribute("data-item-id") or ""
        raw_ph = p_attr.replace("phone:tel:", "") if p_attr.startswith("phone:tel:") else await phone_btn.inner_text()
        found_phone = clean_phone_lt(raw_ph)

    # Address button
    addr_btn = await maps_page.query_selector(
        'button[data-item-id="address"], button[aria-label*="Adresas"], button[aria-label*="Address"]'
    )
    if addr_btn:
        found_addr = re.sub(r"^(Adresas|Address):\s*", "", clean_text(await addr_btn.inner_text()), flags=re.I).strip()

    return found_web, found_fb, found_phone, found_addr, found_cat, place_id, is_closed


async def run_enrichment(
    headless: bool = False,
    limit: int | None = None,
    skip_phase1: bool = False,
    phase1_only: bool = False,
    force_retry: bool = False,
    sync_inlt: bool = True,
) -> None:
    """Execute Phase 1 website crawl + Phase 2 Google Maps enrichment for Lithuanian Hotels."""
    df = load_source_dataset()
    if df is None:
        print(f"[!] Could not find {INPUT_2COL_PATH.name} or {INPUT_1ENR_PATH.name}!")
        return

    if INPUT_2COL_PATH.exists() and not BACKUP_2COL_PATH.exists():
        BACKUP_2COL_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(INPUT_2COL_PATH, BACKUP_2COL_PATH)
        print(f"[+] Created one-time safety backup: {BACKUP_2COL_PATH.relative_to(ROOT_DIR)}")

    cache = load_cache()
    apply_cache_to_df(df, cache)

    no_email_indices = [i for i, r in df.iterrows() if not clean_email(r["Email"])]
    no_sdt_only_indices = [i for i, r in df.iterrows() if clean_email(r["Email"]) and not clean_phone_lt(r["SDT"])]

    print("=" * 80)
    print("GOOGLE MAPS ENRICHMENT - LITHUANIAN HOTELS & ACCOMMODATION (LT_HOTL - NACE 55)")
    print(f"  Source CSV    : {INPUT_2COL_PATH.name} ({len(df):,} hotels/resorts)")
    print(f"  Has Email     : {len(df) - len(no_email_indices):,}")
    print(f"  Missing Email : {len(no_email_indices):,}")
    print(f"  Missing Phone : {len(no_sdt_only_indices):,} (among rows with email)")
    print(f"  Browser Mode  : {'HEADLESS' if headless else 'VISUAL (headless=False, 1280x800)'}")
    print("=" * 80 + "\n")

    # PHASE 1: Deep crawl existing websites missing email
    phase1_found = 0
    if not skip_phase1:
        p1_candidates = [
            i for i in no_email_indices
            if is_valid_website(df.at[i, "Website"]) or is_facebook_url(df.at[i, "Facebook_URL"])
        ]
        if limit:
            p1_candidates = p1_candidates[:limit]

        print("-" * 80)
        print(f"  PHASE 1: Deep-crawling {len(p1_candidates):,} existing websites / fanpages")
        print("-" * 80)

        for p1_idx, idx in enumerate(p1_candidates, 1):
            row = df.loc[idx]
            key = make_cache_key(row)
            if not force_retry and cache.get(key, {}).get("phase1_done"):
                continue

            comp = clean_text(row["Cong ty"])
            web_url = clean_text(row.get("Website", ""))
            fb_in = clean_text(row.get("Facebook_URL", ""))

            # Filter out OTA links before crawling
            if is_ota_or_directory_link(web_url):
                df.at[idx, "Website"] = ""
                web_url = ""

            em_found, fb_found, em_src = await crawl_site_and_socials(web_url, existing_fb=fb_in)
            if fb_found and not df.at[idx, "Facebook_URL"]:
                df.at[idx, "Facebook_URL"] = fb_found

            if em_found:
                df.at[idx, "Email"] = em_found
                df.at[idx, "Email_Source"] = em_src
                phase1_found += 1
                print(f"  [{p1_idx}/{len(p1_candidates)}] [+] WEB EMAIL ({em_src}): {comp} -> {em_found}")
            else:
                print(f"  [{p1_idx}/{len(p1_candidates)}] [-] No public email on website: {web_url or '-'}")

            cache[key] = {
                "Website": web_url or df.at[idx, "Website"],
                "Email": em_found or df.at[idx, "Email"],
                "SDT": clean_phone_lt(df.at[idx, "SDT"]),
                "Dia_Chi": df.at[idx, "Dia_Chi"],
                "Facebook_URL": fb_found or df.at[idx, "Facebook_URL"],
                "Email_Source": em_src or df.at[idx, "Email_Source"],
                "phase1_done": True,
            }
            if p1_idx % 10 == 0:
                save_cache(cache)

        save_cache(cache)
        cur_em = export_and_sync_all_files(df, sync_inlt=sync_inlt)
        print(f"[*] Phase 1 finished: +{phase1_found:,} emails (Total Emails: {cur_em:,})\n")
        if phase1_only:
            return

    # PHASE 2: Visual Google Maps Enrichment
    pending_email = [i for i, r in df.iterrows() if not clean_email(r["Email"])]
    pending_phone = [i for i, r in df.iterrows() if clean_email(r["Email"]) and not clean_phone_lt(r["SDT"])]
    all_pending = pending_email + pending_phone

    if force_retry:
        pending_to_run = all_pending
    else:
        pending_to_run = [i for i in all_pending if not cache.get(make_cache_key(df.loc[i]), {}).get("maps_done")]

    if limit:
        pending_to_run = pending_to_run[:limit]

    print("-" * 80)
    print(f"  PHASE 2: Google Maps Lookup (Visual Chrome) - Pending: {len(pending_to_run):,}")
    print("-" * 80)

    if not pending_to_run:
        export_and_sync_all_files(df, sync_inlt=sync_inlt)
        print("[+] All target companies are already processed!")
        return

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=headless, channel="chrome", args=["--start-maximized", "--no-sandbox"])
        except Exception:
            browser = await p.chromium.launch(headless=headless, args=["--start-maximized", "--no-sandbox"])

        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="lt-LT",
            user_agent=HEADERS["User-Agent"],
        )
        await context.add_cookies([
            {"name": "SOCS", "value": "CAESEwgDEgk2OTQ0NTgyODQaAmVuIAEaBgiA_LyaBg", "domain": ".google.com", "path": "/"},
            {"name": "CONSENT", "value": "YES+cb.20230531-04-p0.en+FX+999", "domain": ".google.com", "path": "/"},
        ])
        maps_page = await context.new_page()

        print("[*] Warming up Google Maps session...")
        try:
            await maps_page.goto("https://www.google.com/maps?hl=lt", wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(1.5)
            if "consent.google.com" in maps_page.url.lower():
                print("[*] Dismissing Google consent...")
                for b in await maps_page.query_selector_all("button"):
                    t = (await b.inner_text()).strip()
                    if any(k in t.lower() for k in ("priimti", "accept", "sutinku")):
                        await b.click()
                        await asyncio.sleep(2)
                        break
            print("[+] Google Maps ready.")
        except Exception as init_err:
            print(f"[!] Warm-up note: {init_err}")

        processed = 0
        newly_email = 0
        newly_phone = 0
        newly_web = 0

        try:
            for idx in pending_to_run:
                row = df.loc[idx]
                comp = clean_text(row["Cong ty"])
                city = clean_text(row.get("City", ""))
                key = make_cache_key(row)
                processed += 1

                core_name = clean_company_name_lt(comp)
                loc_str = f"{city} Lietuva".strip() if city else "Lietuva"
                q_term = f"{core_name} {loc_str}".strip() if core_name else f"{comp} {loc_str}".strip()
                maps_url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(q_term)}?hl=lt"
                print(f"[{processed}/{len(pending_to_run)}] Maps: {comp} -> '{q_term}'")

                found_web = found_fb = found_phone = found_addr = found_email = email_src = ""
                found_cat = place_id = ""
                is_closed = "No"
                matched = False
                match_reason = "NO_MATCH"

                try:
                    await maps_page.goto(maps_url, wait_until="domcontentloaded", timeout=MAPS_TIMEOUT)
                    await asyncio.sleep(DELAY_AFTER_SEARCH)

                    if "consent.google.com" in maps_page.url.lower():
                        for b in await maps_page.query_selector_all("button"):
                            t = (await b.inner_text()).strip()
                            if any(k in t.lower() for k in ("priimti", "accept", "sutinku")):
                                await b.click()
                                await asyncio.sleep(2)
                                break

                    await handle_google_captcha_if_present(maps_page, df, cache, sync_inlt)

                    # Wait briefly for single place panel or result cards
                    try:
                        await maps_page.wait_for_selector(
                            'h1.DUwDvf, a.hfpxzc[href*="/maps/place/"]',
                            timeout=5000,
                        )
                    except Exception:
                        pass

                    cards = await maps_page.query_selector_all(
                        'div[role="feed"] a.hfpxzc[href*="/maps/place/"], a.hfpxzc[href*="/maps/place/"]'
                    )
                    h1 = await maps_page.query_selector("h1.DUwDvf")

                    if "/maps/place/" in maps_page.url or (h1 is not None and not cards):
                        cand_name = clean_text(await h1.inner_text()) if h1 else ""
                        matched, match_reason = is_valid_name_match_lt(comp, cand_name)
                    else:
                        for card in cards[:5]:
                            cand_name = clean_text(await card.get_attribute("aria-label") or await card.inner_text())
                            ok, reason = is_valid_name_match_lt(comp, cand_name)
                            if ok:
                                matched, match_reason = True, reason
                                await card.click()
                                try:
                                    await maps_page.wait_for_selector("h1.DUwDvf", timeout=4000)
                                except Exception:
                                    pass
                                await asyncio.sleep(DELAY_AFTER_CLICK)
                                break

                    if matched:
                        (
                            found_web, found_fb, found_phone, found_addr,
                            found_cat, place_id, is_closed
                        ) = await extract_hotel_place_fields(maps_page)

                        # Rule 3 in scrape-hotel: Validate category
                        if found_cat and not any(k in found_cat.lower() for k in ALLOWED_HOTEL_CATEGORIES):
                            matched = False
                            match_reason = f"REJECTED_CATEGORY ({found_cat})"
                            found_web = found_fb = found_phone = found_addr = ""

                        target_web = found_web or (df.at[idx, "Website"] if is_valid_website(df.at[idx, "Website"]) else "")
                        target_fb = found_fb or clean_text(df.at[idx, "Facebook_URL"])

                        if not clean_email(df.at[idx, "Email"]) and (target_web or target_fb):
                            found_email, fb_from_site, email_src = await crawl_site_and_socials(
                                target_web, existing_fb=target_fb
                            )
                            if fb_from_site and not found_fb:
                                found_fb = fb_from_site

                        if not clean_email(df.at[idx, "Email"]) and not found_email:
                            panel_best = select_best_email(extract_emails_from_html(await maps_page.content()), target_web)
                            if panel_best:
                                found_email = panel_best
                                email_src = "GoogleMaps"
                except Exception as err:
                    print(f"    [!] Maps lookup error: {err}")

                if found_web and not is_valid_website(df.at[idx, "Website"]):
                    df.at[idx, "Website"] = found_web
                    newly_web += 1
                if found_fb and not clean_text(df.at[idx, "Facebook_URL"]):
                    df.at[idx, "Facebook_URL"] = found_fb
                if found_phone and not clean_phone_lt(df.at[idx, "SDT"]):
                    df.at[idx, "SDT"] = found_phone
                    newly_phone += 1
                if found_addr and not clean_text(df.at[idx, "Dia_Chi"]):
                    df.at[idx, "Dia_Chi"] = found_addr
                if found_cat and not clean_text(df.at[idx, "Google_Category"]):
                    df.at[idx, "Google_Category"] = found_cat
                if place_id and not clean_text(df.at[idx, "Place_ID"]):
                    df.at[idx, "Place_ID"] = place_id
                if is_closed == "Yes":
                    df.at[idx, "Permanently_Closed"] = "Yes"
                if found_email and not clean_email(df.at[idx, "Email"]):
                    df.at[idx, "Email"] = found_email
                    df.at[idx, "Email_Source"] = email_src
                    newly_email += 1

                if found_email:
                    print(
                        f"    [+] EMAIL ({email_src} | {match_reason}): {found_email} | Web: {found_web or df.at[idx, 'Website']} | Phone: {found_phone or df.at[idx, 'SDT']}"
                    )
                elif matched and (found_web or found_phone):
                    print(f"    [~] MAPS MATCH ({match_reason}): Web: {found_web or '-'} | Phone: {found_phone or '-'}")
                else:
                    print(f"    [-] No strict Maps match ({match_reason}).")

                cache[key] = {
                    "Website": df.at[idx, "Website"],
                    "Email": df.at[idx, "Email"],
                    "SDT": clean_phone_lt(df.at[idx, "SDT"]),
                    "Dia_Chi": df.at[idx, "Dia_Chi"],
                    "Facebook_URL": df.at[idx, "Facebook_URL"],
                    "Email_Source": df.at[idx, "Email_Source"],
                    "Place_ID": place_id or df.at[idx, "Place_ID"],
                    "Google_Category": found_cat or df.at[idx, "Google_Category"],
                    "Permanently_Closed": df.at[idx, "Permanently_Closed"],
                    "phase1_done": True,
                    "maps_done": True,
                }
                save_cache(cache)

                if processed % 5 == 0:
                    cur_em = export_and_sync_all_files(df, sync_inlt=sync_inlt)
                    print(
                        f"    [*] Checkpoint CSV ({processed}/{len(pending_to_run)} | Total Emails: {cur_em:,} | +{newly_email} email, +{newly_phone} phone, +{newly_web} web)"
                    )

                await asyncio.sleep(0.8)
        finally:
            save_cache(cache)
            cur_em = export_and_sync_all_files(df, sync_inlt=sync_inlt)
            await browser.close()

    print("\n" + "=" * 80)
    print("DONE ENRICHING LITHUANIAN HOTELS VIA GOOGLE MAPS!")
    print(f"  Total clean rows : {len(df):,}")
    print(f"  Valid B2B emails : {cur_em:,} ({cur_em * 100 / max(1, len(df)):.1f}%)")
    print(f"  Added this run   : +{phase1_found + newly_email} Email | +{newly_phone} Phone | +{newly_web} Web")
    print("=" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(description="Google Maps Enrichment for LT_HOTL_INLT_2COL.csv")
    parser.add_argument("--headless", action="store_true", help="Run headless browser (default: visible Chrome)")
    parser.add_argument("--limit", type=int, default=None, help="Limit rows processed in this run")
    parser.add_argument("--skip-phase1", action="store_true", help="Skip Phase 1 website crawl and jump to Maps")
    parser.add_argument("--phase1-only", action="store_true", help="Only run Phase 1 on existing websites")
    parser.add_argument("--force-retry", action="store_true", help="Retry companies already marked done in cache")
    parser.add_argument("--no-sync-inlt", action="store_true", help="Do not overwrite LT_HOTL_INLT_2COL.csv")
    parser.add_argument("--re-export", action="store_true", help="Re-export CSV outputs from cache only")
    args = parser.parse_args()

    if args.re_export:
        df = load_source_dataset()
        if df is not None:
            apply_cache_to_df(df, load_cache())
            cnt = export_and_sync_all_files(df, sync_inlt=not args.no_sync_inlt)
            print(f"[+] Re-exported cleanly from cache. Valid emails: {cnt:,} / {len(df):,}")
        return

    asyncio.run(
        run_enrichment(
            headless=args.headless,
            limit=args.limit,
            skip_phase1=args.skip_phase1,
            phase1_only=args.phase1_only,
            force_retry=args.force_retry,
            sync_inlt=not args.no_sync_inlt,
        )
    )


if __name__ == "__main__":
    main()
