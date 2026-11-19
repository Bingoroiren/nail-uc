# -*- coding: utf-8 -*-
"""
GOOGLE MAPS DATA ENRICHMENT - LITHUANIAN WAREHOUSING & TRANSPORT SUPPORT (LT_WARE)
==================================================================================
Enriches LT_WARE_INLT_2COL.csv (3,529 companies, NACE 52) combined with metadata from
LT_WARE_INLT_1ENR.csv using:
  - Phase 1: Deep multi-tier crawl on companies with Website/Facebook missing Email.
  - Phase 2: Visual Chrome Google Maps lookup (strict Lithuanian name match), Website
             & Phone extraction, Priority-10 Baltic subpage crawl, Facebook About
             fallback, and Maps panel email fallback.

Outputs (UTF-8 with BOM / csv-only / Rule 1, 2, 3, 5, 10, 11, 12):
  - LT_WARE_GMAP_1ENR.csv
  - LT_WARE_GMAP_2COL.csv
  - LT_WARE_GMAP_ONLY_EMAILS_READY.csv
  - Syncs LT_WARE_INLT_2COL.csv & LT_WARE_INLT_ONLY_EMAILS_READY.csv
    (creates archive/lt_lithuania/LT_WARE_INLT_2COL_pre_maps_backup.csv once)
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

INPUT_2COL_PATH = ROOT_DIR / "LT_WARE_INLT_2COL.csv"
INPUT_1ENR_PATH = ROOT_DIR / "LT_WARE_INLT_1ENR.csv"
BACKUP_2COL_PATH = ROOT_DIR / "archive" / "lt_lithuania" / "LT_WARE_INLT_2COL_pre_maps_backup.csv"

OUTPUT_1ENR_PATH = ROOT_DIR / "LT_WARE_GMAP_1ENR.csv"
OUTPUT_2COL_PATH = ROOT_DIR / "LT_WARE_GMAP_2COL.csv"
OUTPUT_READY_PATH = ROOT_DIR / "LT_WARE_GMAP_ONLY_EMAILS_READY.csv"

SYNC_INLT_2COL_PATH = ROOT_DIR / "LT_WARE_INLT_2COL.csv"
SYNC_INLT_READY_PATH = ROOT_DIR / "LT_WARE_INLT_ONLY_EMAILS_READY.csv"

CACHE_PATH = ROOT_DIR / "crawlmail" / "cache_enrich_maps_lt_ware.json"
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
]

BLACKLIST_DOMAINS = {
    "facebook.com", "fb.com", "instagram.com", "linkedin.com", "youtube.com",
    "twitter.com", "x.com", "tiktok.com", "pinterest.com", "google.com",
    "maps.google.com", "goo.gl", "wikipedia.org", "yellowpages", "tripadvisor",
    "booking.com", "yelp.com", "sentry.io", "wix.com", "wixpress.com",
    "rekvizitai.vz.lt", "rekvizitai.lt", "rekv.lt", "info.lt", "visalietuva.lt",
    "imones.lt", "statyba.lt", "cr.lt", "okredo.com", "scoris.lt",
    "creditinfo.lt", "cvbankas.lt", "cvonline.lt", "cvmarket.lt", "dirbk.lt",
    "registrucentras.lt", "vmi.lt", "sodra.lt", "1588.lt", "1551.lt",
    "infoplius.lt", "imoniugidas.lt", "imoniubaze.lt", "imoniukatalogai.lt",
    "verslas.lt", "spec.lt", "litorg.cc", "delfi.lt", "15min.lt", "lrytas.lt",
    "tv3.lt", "alfa.lt", "lrt.lt", "b2lithuania.com", "geltoni.lt", "tax.lt",
    "balticlei.lt", "business-baltics.com", "ltkatalogas.lt", "expo.lt",
    "lovejob.lt", "tinklalapiai.lt", "trustpilot.com", "schema.org",
    "kodovizija.lt",
}

SUBSTRING_BLACKLIST_BRANDS = ("yellowpages", "tripadvisor", "booking.com", "yelp.com")
GAMBLING_KEYWORDS = (
    "casino", "kazino", "ggbet", "vulkan", "betting", "lazybos",
    "poker", "slots", "jackpot", "roulette", "bukmeker", "gambling",
)

JUNK_EMAIL_DOMAINS = BLACKLIST_DOMAINS | {
    "wordpress.com", "squarespace.com", "weebly.com", "godaddy.com",
    "example.com", "example.org", "example.net", "domain.com", "yourdomain.com",
    "yourcompany.com", "company.com", "website.com", "site.com",
    "placeholder.com", "templatemonster.com", "themeforest.net",
    "bootstrapmade.com", "pavyzdys.lt", "imone.lt", "email.com", "mail.com",
}

SYSTEM_USERNAMES = {
    "noreply", "no-reply", "donotreply", "privacy", "terms", "cookies",
    "gdpr", "abuse", "security", "webmaster", "sentry", "mailer-daemon",
    "test", "example", "hostmaster", "postmaster", "root", "dataprivacy",
    "datenschutz",
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
LT_SECONDARY_KEYWORDS_P5 = (
    "apie", "apie-mus", "karjera", "darbas", "administracija", "prekyba",
    "pardavimai", "logistika", "transportas", "ekspedicija", "sandelis",
    "about", "about-us", "career", "careers", "jobs", "team", "company",
)
LT_GUESS_SUBPATHS = (
    "/kontaktai", "/kontaktai/", "/kontaktai.html", "/kontaktai.php",
    "/susisiekite", "/rekvizitai", "/apie-mus", "/apie-mus.html",
    "/karjera", "/darbas", "/contact", "/contact.html", "/contact-us",
    "/about", "/about-us",
)

HR_KEYWORDS = ("karjera", "darbas", "personalas", "personalo", "atranka", "cv", "hr", "jobs", "recruitment", "career", "talent")
EXEC_KEYWORDS = ("direktorius", "vadovas", "ceo", "director", "manager", "savininkas", "pardavimai", "prekyba", "logistika", "transport")
OFFICIAL_KEYWORDS = ("info", "kontaktai", "kontakt", "office", "biuras", "administracija", "sekretoriatas", "bendras", "pastas", "mail", "dispecerine", "ekspedicija", "cargo", "freight", "sandelis")


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


def clean_phone_lt(raw_phone: str) -> str:
    """Normalize Lithuanian phone numbers and prefix with leading apostrophe."""
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


def normalize_text(text: str) -> str:
    """Fold Unicode diacritics via NFKD and strip decorative quotes."""
    if not text:
        return ""
    n = unicodedata.normalize("NFKD", str(text)).lower()
    t = "".join(c for c in n if not unicodedata.combining(c))
    return re.sub(r"[\"'„“”«»`´]", "", t).strip()


def clean_company_name_lt(name: str) -> str:
    """Strip bracketed annotations, Lithuanian legal forms, and outer punctuation."""
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
    """Strict Lithuanian business name matcher supporting NFKD, brackets, and delimiters."""
    if not query_name or not candidate_name:
        return False, "EMPTY"

    q_clean = clean_company_name_lt(query_name)
    c_clean = clean_company_name_lt(candidate_name)
    if not q_clean or not c_clean:
        return False, "EMPTY_AFTER_CLEAN"

    q_alnum = re.sub(r"[^a-z0-9]", "", q_clean)
    c_alnum = re.sub(r"[^a-z0-9]", "", c_clean)

    if q_clean == c_clean or (q_alnum and q_alnum == c_alnum):
        return True, "EXACT"

    c_raw_norm = normalize_text(candidate_name)
    c_nobrack_clean = clean_company_name_lt(re.sub(r"\(.*?\)|\[.*?\]", "", c_raw_norm))
    c_nobrack_alnum = re.sub(r"[^a-z0-9]", "", c_nobrack_clean)
    if q_clean == c_nobrack_clean or (q_alnum and q_alnum == c_nobrack_alnum):
        return True, "BRACKET_MATCH"

    parts = [p.strip() for p in re.split(r"[-–—|/:,]", c_raw_norm) if p.strip()]
    for part in parts:
        p_clean = clean_company_name_lt(part)
        p_alnum = re.sub(r"[^a-z0-9]", "", p_clean)
        if p_clean and (q_clean == p_clean or (q_alnum and q_alnum == p_alnum)):
            return True, "DELIMITER_MATCH"

    return False, "NO_MATCH"


def is_valid_website(url: str) -> bool:
    """Accept genuine business websites while rejecting socials and directories."""
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
        if any(sb in domain for sb in SUBSTRING_BLACKLIST_BRANDS):
            return False
        if any(g in domain for g in GAMBLING_KEYWORDS):
            return False
        return True
    except Exception:
        return False


def is_facebook_url(url: str) -> bool:
    """Validate whether a URL points to a real Facebook page."""
    if not url or not isinstance(url, str):
        return False
    u = url.strip().lower()
    if not ("facebook.com/" in u or "fb.com/" in u):
        return False
    bad_fb = (
        "/sharer", "/share", "/plugins/", "/tr?", "/dialog/", "/groups/",
        "/events/", "/watch/", "/marketplace/", "/login", "/policies/",
        "/privacy", "/help/", "/ads/", "l.facebook.com",
    )
    if any(b in u for b in bad_fb):
        return False
    parsed = urllib.parse.urlparse(u if u.startswith("http") else "https://" + u)
    return len(parsed.path.strip("/")) >= 2


def score_email_b2b_lt(email: str, domain: str = "") -> int:
    """Score B2B recruitment/business priority of an email for LT Logistics/Warehousing."""
    if not email or not isinstance(email, str):
        return -1
    e = clean_email(email)
    if not EMAIL_REGEX.match(e) or any(e.endswith(ext) for ext in INVALID_EXTS):
        return -1
    u, d = e.split("@", 1)

    if any(d == jd or d.endswith("." + jd) for jd in JUNK_EMAIL_DOMAINS):
        return -1
    if any(sb in d for sb in SUBSTRING_BLACKLIST_BRANDS):
        return -1
    if u in SYSTEM_USERNAMES or u in TEMPLATE_USERNAMES:
        return -1
    if any(k in u for k in ("youremail", "your-email", "yourname", "your-name", "sample", "placeholder", "jusu", "tavo")):
        return -1
    if re.search(r"\d+\.\d+", d) or len(u) <= 1 or len(d) <= 3:
        return -1
    if u in ("mail", "email") and d in ("mail.lt", "email.com", "mail.com", "email.lt", "domain.com"):
        return -1

    score = 10
    clean_d = ""
    if domain:
        d_tmp = domain.strip().lower()
        if "://" in d_tmp:
            d_tmp = urllib.parse.urlparse(d_tmp).netloc
        clean_d = d_tmp.replace("www.", "").split(":")[0].split("/")[0]
    if clean_d and (clean_d in d or d in clean_d):
        score += 50
    elif d.endswith(".lt"):
        score += 35

    if any(k in u for k in HR_KEYWORDS):
        score += 50
    elif any(k in u for k in EXEC_KEYWORDS):
        score += 45
    elif any(k in u for k in OFFICIAL_KEYWORDS):
        score += 40
    elif "." in u and score >= 60:
        score += 25
    elif d in ("gmail.com", "inbox.lt", "one.lt", "zebra.lt", "yahoo.com", "outlook.com"):
        score += 10
    elif any(k in u for k in ("support", "admin", "buhalterija", "servisas", "fakturos")):
        score += 5

    return score


def select_best_email(emails: set[str] | list[str], domain: str = "") -> str:
    """Pick the single highest-scoring valid B2B email."""
    valid = [clean_email(e) for e in set(emails) if score_email_b2b_lt(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b_lt(e, domain))


def extract_emails_from_html(raw_html: str) -> set[str]:
    """Extract Cloudflare XOR, mailto:, obfuscated, and visible-DOM emails (ignoring <script>/<style>)."""
    found: set[str] = set()
    if not raw_html:
        return found

    for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', raw_html):
        dec = clean_email(decode_cf_hex(cf))
        if "@" in dec:
            found.add(dec)
    for cf in re.findall(r"/cdn-cgi/l/email-protection#([a-fA-F0-9]+)", raw_html):
        dec = clean_email(decode_cf_hex(cf))
        if "@" in dec:
            found.add(dec)
    for m in re.findall(r'href=["\']mailto:([^"?\'>]+)', raw_html, re.I):
        cm = clean_email(m)
        if "@" in cm:
            found.add(cm)

    # Strip script/style/noscript tags so Yoast JSON-LD dev emails do not pollute visible emails
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    visible_text = html_lib.unescape(urllib.parse.unquote(soup.get_text(" ", strip=True)))

    for em in EMAIL_REGEX.findall(visible_text):
        cm = clean_email(em)
        if "@" in cm:
            found.add(cm)
    for u, dom, tld in OBFUSCATED_EMAIL_REGEX.findall(visible_text):
        cm = clean_email(f"{u}@{dom}.{tld}")
        if "@" in cm:
            found.add(cm)

    return found


def extract_facebook_links(raw_html: str, base_url: str) -> list[str]:
    """Collect unique Facebook page URLs linked from HTML."""
    fb_links: list[str] = []
    if not raw_html:
        return fb_links
    try:
        soup = BeautifulSoup(raw_html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = urllib.parse.urljoin(base_url, a["href"].strip()).split("?")[0]
            if is_facebook_url(href) and href not in fb_links:
                fb_links.append(href)
    except Exception:
        pass
    return fb_links


def extract_city_from_address(addr: str) -> str:
    """Extract clean Lithuanian municipality/city from an address string."""
    if not addr:
        return ""
    s = re.sub(r",?\s*Lithuania$", "", str(addr).strip(), flags=re.I).strip()
    last_part = s.split(",")[-1].strip() if "," in s else s
    last_part = re.sub(r"\b\d{4,5}\b", "", last_part).strip()
    return re.sub(r"\(.*?\)", "", last_part).strip(" ,.-")


def fetch_html_fast(url: str, timeout: float = 4.5) -> str:
    """Fast HTML fetch using curl_cffi Chrome impersonation with urllib fallback."""
    try:
        from curl_cffi import requests as c_requests
        r = c_requests.get(url, impersonate="chrome120", timeout=timeout, verify=False)
        if r.status_code == 200:
            return r.text
        if r.status_code in (403, 404, 410, 500, 502, 503):
            return ""
    except Exception:
        pass
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""


async def fetch_html_playwright(pw_page, url: str, timeout: int = 15000) -> str:
    """Fallback Playwright page render when HTTP requests fail."""
    if not pw_page:
        return ""
    try:
        await pw_page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        await asyncio.sleep(1.5)
        return await pw_page.content()
    except Exception:
        return ""


def collect_prioritized_subpages(home_html: str, web_url: str, root: str) -> list[str]:
    """Rank DOM <a> links (Priority 10/5) ahead of localized Baltic guess paths (Priority 2)."""
    parsed = urllib.parse.urlparse(root)
    canon = lambda u: re.sub(r"^https?://(?:www\.)?", "", u.split("#")[0].rstrip("/").lower())
    prioritized: list[tuple[int, str]] = []
    seen_norm = {canon(web_url), canon(root)}

    try:
        soup = BeautifulSoup(home_html, "html.parser")
        for a in soup.find_all("a", href=True):
            raw_href = a["href"].strip()
            if not raw_href or raw_href.startswith("#") or raw_href.lower().startswith(("javascript:", "tel:", "mailto:")):
                continue
            full_url = urllib.parse.urljoin(web_url, raw_href)
            full_clean = full_url.split("#")[0]
            norm_url = canon(full_clean)
            p_full = urllib.parse.urlparse(full_clean)
            if parsed.netloc.replace("www.", "") not in p_full.netloc.replace("www.", ""):
                continue
            if norm_url in seen_norm or any(full_clean.lower().endswith(ext) for ext in INVALID_EXTS):
                continue

            h_low = raw_href.lower()
            t_low = a.get_text(" ", strip=True).lower()
            prio = 0
            if any(k in h_low or k in t_low for k in LT_CONTACT_KEYWORDS_P10):
                prio = 10
            elif any(k in h_low or k in t_low for k in LT_SECONDARY_KEYWORDS_P5):
                prio = 5
            if prio > 0:
                seen_norm.add(norm_url)
                prioritized.append((prio, full_clean))
    except Exception:
        pass

    prioritized.sort(key=lambda x: x[0], reverse=True)
    queue = [u for _, u in prioritized]

    for gp in LT_GUESS_SUBPATHS:
        g_url = urllib.parse.urljoin(root, gp)
        norm_g = canon(g_url)
        if norm_g not in seen_norm:
            seen_norm.add(norm_g)
            queue.append(g_url)
    return queue


async def crawl_site_and_socials(web_url: str, existing_fb: str = "", pw_page=None) -> tuple[str, str, str]:
    """Multi-tier extraction: Website Priority-10 subpages -> Facebook Fanpage About."""
    found_emails: set[str] = set()
    fb_candidates: list[str] = []
    if existing_fb and is_facebook_url(existing_fb):
        fb_candidates.append(existing_fb)

    root = ""
    if web_url and is_valid_website(web_url):
        if not web_url.startswith("http"):
            web_url = "https://" + web_url
        parsed = urllib.parse.urlparse(web_url)
        root = f"{parsed.scheme}://{parsed.netloc}"

        home_html = fetch_html_fast(web_url)
        if not home_html and web_url.rstrip("/") != root.rstrip("/"):
            home_html = fetch_html_fast(root)
        if not home_html and pw_page:
            home_html = await fetch_html_playwright(pw_page, web_url)

        if home_html:
            found_emails |= extract_emails_from_html(home_html)
            for fb in extract_facebook_links(home_html, web_url):
                if fb not in fb_candidates:
                    fb_candidates.append(fb)

            best_home = select_best_email(found_emails, root)
            if best_home and score_email_b2b_lt(best_home, root) >= 95:
                return best_home, (fb_candidates[0] if fb_candidates else ""), "Website"

            for sub_url in collect_prioritized_subpages(home_html, web_url, root)[:8]:
                sub_html = fetch_html_fast(sub_url, timeout=3.5)
                if not sub_html:
                    continue
                found_emails |= extract_emails_from_html(sub_html)
                for fb in extract_facebook_links(sub_html, sub_url):
                    if fb not in fb_candidates:
                        fb_candidates.append(fb)
                cur_best = select_best_email(found_emails, root)
                if cur_best and score_email_b2b_lt(cur_best, root) >= 95:
                    return cur_best, (fb_candidates[0] if fb_candidates else ""), "Website"

            best_email = select_best_email(found_emails, root)
            if best_email:
                return best_email, (fb_candidates[0] if fb_candidates else ""), "Website"

    best_fb = fb_candidates[0] if fb_candidates else ""
    if best_fb:
        for fb_url in (best_fb.rstrip("/") + "/about", best_fb):
            fb_html = fetch_html_fast(fb_url, timeout=4.5)
            if not fb_html and pw_page:
                fb_html = await fetch_html_playwright(pw_page, fb_url, timeout=12000)
            if fb_html:
                fb_best = select_best_email(extract_emails_from_html(fb_html), root)
                if fb_best:
                    return fb_best, best_fb, "Facebook"

    return "", best_fb, ""


def make_cache_key(row) -> str:
    """Build deterministic cache key using Company_Code when present or normalized name+city."""
    code = clean_text(row.get("Company_Code", ""))
    if code:
        return code
    comp = normalize_text(row.get("Cong ty", ""))
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
    """Persist cache JSON atomically to prevent partial writes."""
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
            continue
        if c.get("Email") and not clean_email(df.at[idx, "Email"]):
            df.at[idx, "Email"] = clean_email(c["Email"])
        if c.get("Website") and is_valid_website(c["Website"]) and not is_valid_website(df.at[idx, "Website"]):
            df.at[idx, "Website"] = c["Website"]
        if c.get("SDT") and not clean_phone_lt(df.at[idx, "SDT"]):
            df.at[idx, "SDT"] = clean_phone_lt(c["SDT"])
        if c.get("Dia_Chi") and not clean_text(df.at[idx, "Dia_Chi"]):
            df.at[idx, "Dia_Chi"] = clean_text(c["Dia_Chi"])
        if c.get("Facebook_URL") and not clean_text(df.at[idx, "Facebook_URL"]):
            df.at[idx, "Facebook_URL"] = c["Facebook_URL"]
        if c.get("Email_Source") and not clean_text(df.at[idx, "Email_Source"]):
            df.at[idx, "Email_Source"] = c["Email_Source"]


def load_source_dataset() -> pd.DataFrame | None:
    """Load GMAP master if resuming, else combine LT_WARE_INLT_2COL + LT_WARE_INLT_1ENR."""
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
    )
    for col in required_cols:
        if col not in df.columns:
            df[col] = ""

    for idx, r in df.iterrows():
        raw_w = str(r.get("Website", "")).strip()
        if raw_w and is_facebook_url(raw_w) and not str(r.get("Facebook_URL", "")).strip():
            df.at[idx, "Facebook_URL"] = raw_w
        if not clean_text(r.get("City", "")):
            df.at[idx, "City"] = extract_city_from_address(r.get("Dia_Chi", "") or r.get("Dia chi", ""))

    df["Website"] = df["Website"].apply(lambda w: w.strip() if is_valid_website(w) else "")
    if "Cong ty" in df.columns:
        df = df[~df["Cong ty"].apply(is_blacklisted_company)].reset_index(drop=True)
    return df


def export_and_sync_all_files(df: pd.DataFrame, sync_inlt: bool = True) -> int:
    """Export 1ENR, 2COL, READY CSVs (utf-8-sig, email rows sorted first) and sync folders."""
    df_out = df.copy()
    if "Cong ty" in df_out.columns:
        df_out = df_out[~df_out["Cong ty"].apply(is_blacklisted_company)].reset_index(drop=True)

    for col in df_out.columns:
        df_out[col] = df_out[col].apply(clean_text)
    df_out["SDT"] = df_out["SDT"].apply(clean_phone_lt)
    df_out["Email"] = df_out["Email"].apply(clean_email)

    has_em = df_out[df_out["Email"] != ""].copy()
    no_em = df_out[df_out["Email"] == ""].copy()
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted["No."] = range(1, len(df_sorted) + 1)
    df_sorted.to_csv(OUTPUT_1ENR_PATH, index=False, encoding="utf-8-sig")

    coldmail_rows = []
    for _, r in df_sorted.iterrows():
        comp_name = clean_text(r.get("Cong ty", ""))
        manager = clean_text(r.get("Nguoi_Quan_Ly", ""))
        title = clean_text(r.get("Chuc_Danh", "")) or ("Direktorius" if manager else "Vadovas")
        web_val = clean_text(r.get("Website", ""))
        detail_val = clean_text(r.get("Detail_URL", ""))
        email_val = clean_email(r.get("Email", ""))
        phone_val = clean_phone_lt(r.get("SDT", ""))
        city_val = clean_text(r.get("City", ""))
        addr_val = clean_text(r.get("Dia_Chi", "")) or clean_text(r.get("Dia chi", ""))
        if not addr_val and city_val:
            addr_val = f"{city_val}, Lithuania"
        link_val = web_val or detail_val

        coldmail_rows.append(
            {
                "No.": r.get("No.", ""),
                "Công ty": comp_name,
                "Chức danh": title,
                "Người liên hệ": manager,
                "SĐT": phone_val,
                "Liên Hệ": link_val,
                "Email": email_val,
                "Liên Hệ mail": f"mailto:{email_val}" if email_val else link_val,
                "Địa chỉ": addr_val or "Lithuania",
                "Lương": clean_text(r.get("Doanh_Thu", "")),
                "Ngày đăng": clean_text(r.get("Nam_Thanh_Lap", "")),
                "Hạn tuyển": "",
                "Check gửi": "Chưa gửi",
                "Last Subject": "",
                "Last Body HTML": "",
                "Trạng thái Reply": "",
                "Lần Follow-up": "",
                "Ngày Follow-up gần nhất": "",
                "Mailbox đã dùng": "",
                "Category": clean_text(r.get("Category", "")) or "Warehousing & transportation support",
            }
        )

    df_2col = pd.DataFrame(coldmail_rows, columns=COLDMAIL_COLUMNS)
    df_2col.to_csv(OUTPUT_2COL_PATH, index=False, encoding="utf-8-sig")

    df_ready = df_2col[df_2col["Email"] != ""].copy()
    df_ready["No."] = range(1, len(df_ready) + 1)
    df_ready.to_csv(OUTPUT_READY_PATH, index=False, encoding="utf-8-sig")

    copy_targets = [OUTPUT_1ENR_PATH, OUTPUT_2COL_PATH, OUTPUT_READY_PATH]
    if sync_inlt:
        df_2col.to_csv(SYNC_INLT_2COL_PATH, index=False, encoding="utf-8-sig")
        df_ready.to_csv(SYNC_INLT_READY_PATH, index=False, encoding="utf-8-sig")
        copy_targets.extend([SYNC_INLT_2COL_PATH, SYNC_INLT_READY_PATH])

    for extra_dir in (CSDL_DIR, ARCHIVE_DIR):
        extra_dir.mkdir(parents=True, exist_ok=True)
        for src in copy_targets:
            try:
                shutil.copy2(src, extra_dir / src.name)
            except Exception:
                pass

    return len(has_em)


async def handle_google_captcha_if_present(maps_page, df: pd.DataFrame, cache: dict, sync_inlt: bool) -> bool:
    """Alert operator on Google Captcha and pause safely after persisting progress."""
    cur_u = maps_page.url.lower()
    page_txt_low = (await maps_page.content()).lower()
    has_recaptcha = await maps_page.query_selector("iframe[src*='recaptcha']")
    if "sorry" in cur_u or "captcha" in cur_u or "unusual traffic" in page_txt_low or has_recaptcha:
        save_cache(cache)
        export_and_sync_all_files(df, sync_inlt=sync_inlt)
        print("\a" * 3)
        print("\n[!] GOOGLE CAPTCHA DETECTED! Progress saved cleanly.")
        print("    Please solve the Captcha directly in the Chrome window, then press ENTER here to continue...")
        await asyncio.to_thread(input, "")
        return True
    return False


async def extract_maps_place_fields(maps_page) -> tuple[str, str, str, str]:
    """Extract Website, Facebook URL, Phone, and Address from an open Maps place panel."""
    found_web = ""
    found_fb = ""
    found_phone = ""
    found_addr = ""

    web_btn = await maps_page.query_selector(
        'a[data-item-id="authority"], a[aria-label*="Svetain"], a[aria-label*="svetain"], a[aria-label*="Website"]'
    )
    if web_btn:
        w_href = (await web_btn.get_attribute("href") or "").strip()
        if is_valid_website(w_href):
            found_web = w_href
        elif is_facebook_url(w_href):
            found_fb = w_href

    phone_btn = await maps_page.query_selector(
        'button[data-item-id^="phone:"], button[aria-label*="Telefon"], button[aria-label*="Phone"]'
    )
    if phone_btn:
        p_attr = await phone_btn.get_attribute("data-item-id") or ""
        raw_ph = p_attr.replace("phone:tel:", "") if p_attr.startswith("phone:tel:") else await phone_btn.inner_text()
        found_phone = clean_phone_lt(raw_ph)

    addr_btn = await maps_page.query_selector(
        'button[data-item-id="address"], button[aria-label*="Adresas"], button[aria-label*="Address"]'
    )
    if addr_btn:
        found_addr = re.sub(r"^(Adresas|Address):\s*", "", clean_text(await addr_btn.inner_text()), flags=re.I).strip()

    return found_web, found_fb, found_phone, found_addr


async def run_enrichment(
    headless: bool = False,
    limit: int | None = None,
    skip_phase1: bool = False,
    phase1_only: bool = False,
    force_retry: bool = False,
    sync_inlt: bool = True,
) -> None:
    """Execute Phase 1 website crawl + Phase 2 Google Maps enrichment."""
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
    print("GOOGLE MAPS ENRICHMENT - LITHUANIAN WAREHOUSING & TRANSPORT SUPPORT (LT_WARE)")
    print(f"  Source CSV    : {INPUT_2COL_PATH.name} ({len(df):,} companies)")
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

            em_found, fb_found, em_src = await crawl_site_and_socials(web_url, existing_fb=fb_in)
            if fb_found and not df.at[idx, "Facebook_URL"]:
                df.at[idx, "Facebook_URL"] = fb_found

            if em_found:
                df.at[idx, "Email"] = em_found
                df.at[idx, "Email_Source"] = em_src
                phase1_found += 1
                print(f"  [{p1_idx}/{len(p1_candidates)}] [+] WEB EMAIL ({em_src}): {comp} -> {em_found}")
            else:
                print(f"  [{p1_idx}/{len(p1_candidates)}] [-] No public email on website: {web_url}")

            cache[key] = {
                "Website": web_url,
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
        await context.add_cookies(
            [{"name": "SOCS", "value": "CAESEwgDEgk2OTQ0NTgyODQaAmVuIAEaBgiA_LyaBg", "domain": ".google.com", "path": "/"}]
        )
        maps_page = await context.new_page()
        web_page = await context.new_page()

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

                loc_str = f"{city} Lietuva".strip() if city else "Lietuva"
                maps_url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(f'{comp} {loc_str}')}?hl=lt"
                print(f"[{processed}/{len(pending_to_run)}] Maps: {comp} ({city or 'Lietuva'})")

                found_web = found_fb = found_phone = found_addr = found_email = email_src = ""
                matched = False
                match_reason = "NO_MATCH"

                try:
                    await maps_page.goto(maps_url, wait_until="domcontentloaded", timeout=MAPS_TIMEOUT)
                    await asyncio.sleep(DELAY_AFTER_SEARCH)

                    if "consent.google.com" in maps_page.url.lower():
                        c_btn = await maps_page.query_selector(
                            'button:has-text("Priimti visus"), button:has-text("Accept all"), form[action*="consent"] button'
                        )
                        if c_btn:
                            await c_btn.click()
                            await asyncio.sleep(2.5)

                    await handle_google_captcha_if_present(maps_page, df, cache, sync_inlt)

                    # Wait briefly for either single place panel (even when URL stays /maps/search/) or result cards
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
                        found_web, found_fb, found_phone, found_addr = await extract_maps_place_fields(maps_page)
                        target_web = found_web or (df.at[idx, "Website"] if is_valid_website(df.at[idx, "Website"]) else "")
                        target_fb = found_fb or clean_text(df.at[idx, "Facebook_URL"])

                        if not clean_email(df.at[idx, "Email"]) and (target_web or target_fb):
                            found_email, fb_from_site, email_src = await crawl_site_and_socials(
                                target_web, existing_fb=target_fb, pw_page=web_page
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
    print("DONE ENRICHING LT WAREHOUSING & TRANSPORT SUPPORT VIA GOOGLE MAPS!")
    print(f"  Total clean rows : {len(df):,}")
    print(f"  Valid B2B emails : {cur_em:,} ({cur_em * 100 / max(1, len(df)):.1f}%)")
    print(f"  Added this run   : +{phase1_found + newly_email} Email | +{newly_phone} Phone | +{newly_web} Web")
    print("=" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(description="Google Maps Enrichment for LT_WARE_INLT_2COL.csv")
    parser.add_argument("--headless", action="store_true", help="Run headless browser (default: visible Chrome)")
    parser.add_argument("--limit", type=int, default=None, help="Limit rows processed in this run")
    parser.add_argument("--skip-phase1", action="store_true", help="Skip Phase 1 website crawl and jump to Maps")
    parser.add_argument("--phase1-only", action="store_true", help="Only run Phase 1 on existing websites")
    parser.add_argument("--force-retry", action="store_true", help="Retry companies already marked done in cache")
    parser.add_argument("--no-sync-inlt", action="store_true", help="Do not overwrite LT_WARE_INLT_2COL.csv")
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

