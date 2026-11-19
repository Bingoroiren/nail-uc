# -*- coding: utf-8 -*-
"""
DATA ENRICHMENT - LITHUANIAN RESTAURANTS & FOOD SERVICE VIA INFO.LT (NACE 56)
=============================================================================
Input:  LT_FOOD_LTOR_0RAW.csv (4,214 companies from litorg.cc catalog 56.1 & 56.2)
Output:
  - LT_FOOD_INLT_1ENR.csv (Master enriched dataset)
  - LT_FOOD_INLT_2COL.csv (Cold Mail 20-column format, email rows sorted first)
  - LT_FOOD_INLT_ONLY_EMAILS_READY.csv (Filtered ready-to-send campaign rows)
  - crawlmail/cache_enrich_infolt_lt_food.json (Thread-safe resume checkpoint)

Features:
  1. Exact FirmCode lookup on info.lt via Company_Code (100% exact match).
  2. Fallback to strict company name search per Rule 11.
  3. Base64 + XOR decoding for info.lt data-link-ob / data-text-ob email tokens.
  4. Automatic extraction of Manager/Director (Vadovas/Direktorius), Phone, Website, Address.
  5. Fallback website crawler targeting Baltic contact/career/restaurant subpaths.
  6. B2B recruitment email scoring tailored for cooks and restaurant staff.
  7. PreValidatedProxyPool with Chrome impersonation and direct fallback.
  8. Strict adherence to GEMINI.md data standards (UTF-8 BOM, '+' phone prefix, blacklist).
"""

import argparse
import base64
import json
import os
import random
import re
import shutil
import sys
import threading
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
INPUT_CSV_PATH = ROOT_DIR / "LT_FOOD_LTOR_0RAW.csv"

OUTPUT_1ENR_PATH = ROOT_DIR / "LT_FOOD_INLT_1ENR.csv"
OUTPUT_2COL_PATH = ROOT_DIR / "LT_FOOD_INLT_2COL.csv"
OUTPUT_READY_PATH = ROOT_DIR / "LT_FOOD_INLT_ONLY_EMAILS_READY.csv"

CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_enrich_infolt_lt_food.json"
CSDL_DIR = ROOT_DIR / "csdl_mlt"
ARCHIVE_DIR = ROOT_DIR / "archive" / "lt_lithuania"

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

EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b")
OBFUSCATED_PATTERNS = [
    re.compile(r"([A-Za-z0-9._%+-]{1,64})\s*\[at\]\s*([A-Za-z0-9.-]{1,255})\s*\[dot\]\s*([A-Za-z]{2,10})", re.I),
    re.compile(r"([A-Za-z0-9._%+-]{1,64})\s*\(at\)\s*([A-Za-z0-9.-]{1,255})\s*\(dot\)\s*([A-Za-z]{2,10})", re.I),
    re.compile(r"([A-Za-z0-9._%+-]{1,64})\s+AT\s+([A-Za-z0-9.-]{1,255})\s+DOT\s+([A-Za-z]{2,10})"),
]
INVALID_EXTS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".css", ".js", ".pdf", ".woff", ".woff2", ".ico", ".mp4", ".mp3",
)

JUNK_EMAIL_DOMAINS = {
    "example.com", "example.org", "example.net", "domain.com", "yourdomain.com",
    "yourcompany.com", "company.com", "email.com", "placeholder.com", "sample.com",
    "sentry.io", "sentry-next.wixpress.com", "wixpress.com", "wix.com",
    "wordpress.com", "squarespace.com", "weebly.com", "godaddy.com",
    "bootstrapmade.com", "templatemonster.com", "themeforest.net", "schema.org",
    "info.lt", "litorg.cc", "rekvizitai.vz.lt", "vz.lt", "kodovizija.lt",
    "facebook.com", "instagram.com", "linkedin.com", "google.com", "youtube.com",
    "localservices.be", "bizbook.be", "pagesdor.be", "goudengids.be",
}

JUNK_USERNAMES = {
    "youremail", "your-email", "your_email", "yourname", "your-name",
    "yourcompany", "someone", "nobody", "john.doe", "johndoe", "jane.doe",
    "username", "sample", "demo", "no-reply", "noreply", "donotreply",
    "privacy", "gdpr", "cookies", "abuse", "security", "mailer-daemon", "sentry",
}

SOCIAL_OR_DIRECTORY_DOMAINS = (
    "facebook.com", "fb.com", "instagram.com", "linkedin.com", "youtube.com",
    "twitter.com", "x.com", "tiktok.com", "info.lt", "rekvizitai.vz.lt",
    "litorg.cc", "spec.lt", "verslas.lt", "delfi.lt", "15min.lt", "meniu.lt",
)

CONTACT_PRIMARY_KEYWORDS = ("kontaktai", "kontakt", "contact", "get-in-touch")
CONTACT_HR_KEYWORDS = ("karjera", "darbas", "careers", "career", "jobs", "cv", "atranka")
CONTACT_ABOUT_KEYWORDS = ("apie-mus", "apie", "about", "restoranas")
BALTIC_FALLBACK_PATHS = (
    "/kontaktai", "/kontaktai.html", "/apie-mus", "/karjera", "/darbas",
    "/contact", "/contact-us", "/about-us", "/careers", "/jobs",
)

HR_USERNAMES = {
    "karjera", "cv", "atranka", "personalo", "personalas", "darbas", "hr",
    "jobs", "recruitment", "work", "career", "careers", "talent", "people",
    "virejas", "virejai", "cook", "chef",
}
EXEC_USERNAMES = {
    "direktorius", "vadovas", "ceo", "director", "valdymas", "manager", "owner",
    "sefas", "savininkas",
}
OFFICIAL_USERNAMES = {
    "info", "kontaktai", "kontakt", "contact", "biuras", "office",
    "administracija", "sekretoriatas", "bendras", "mail", "restoranas",
    "restaurant", "virtuve", "rezervacija", "uzsakymai", "booking", "orders",
}
COMMERCIAL_USERNAMES = {
    "komercija", "pardavimai", "uzsakymai", "sales", "prekyba", "tiekimas",
}


class PreValidatedProxyPool:
    """Thread-safe pool of proxies validated against info.lt to avoid HTTP 429 stalls."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.live_proxies: list[str] = []
        self.lock = threading.Lock()
        self.is_refreshing = False

    def validate_one(self, proxy_addr: str) -> str | None:
        try:
            r = requests.get(
                "https://www.info.lt",
                proxies={"http": f"http://{proxy_addr}", "https": f"http://{proxy_addr}"},
                impersonate="chrome120",
                timeout=3.5,
            )
            if r.status_code == 200 and len(r.text) > 1000:
                return proxy_addr
        except Exception:
            pass
        return None

    def refresh(self) -> None:
        if not self.enabled:
            return
        with self.lock:
            if self.is_refreshing:
                return
            self.is_refreshing = True

        try:
            candidates: list[str] = []
            endpoints = [
                "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=3500&country=all&ssl=yes&anonymity=elite",
                "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=3000&country=all",
            ]
            for url in endpoints:
                if len(candidates) >= 60:
                    break
                try:
                    resp = requests.get(url, timeout=5)
                    raw = [line.strip() for line in resp.text.splitlines() if line.strip()]
                    candidates.extend(raw[:50])
                except Exception:
                    pass

            candidates = list(dict.fromkeys(candidates))[:80]
            if candidates:
                print(f"[*] Testing {len(candidates)} candidate proxies against info.lt...")
                with ThreadPoolExecutor(max_workers=25) as ex:
                    valid = [res for res in ex.map(self.validate_one, candidates) if res]
                with self.lock:
                    self.live_proxies = list(dict.fromkeys(self.live_proxies + valid))
                print(f"[*] Proxy pool updated: +{len(valid)} live (total ready: {len(self.live_proxies)})")
        except Exception as e:
            print(f"[!] Proxy refresh error: {e}")
        finally:
            with self.lock:
                self.is_refreshing = False

    def get_proxy(self) -> str | None:
        if not self.enabled:
            return None
        with self.lock:
            if len(self.live_proxies) < 4 and not self.is_refreshing:
                threading.Thread(target=self.refresh, daemon=True).start()
            if self.live_proxies:
                return random.choice(self.live_proxies)
        for _ in range(6):
            time.sleep(0.5)
            with self.lock:
                if self.live_proxies:
                    return random.choice(self.live_proxies)
        return None

    def remove_proxy(self, proxy_addr: str) -> None:
        with self.lock:
            if proxy_addr in self.live_proxies:
                self.live_proxies.remove(proxy_addr)


PROXY_POOL = PreValidatedProxyPool(enabled=True)


def clean_text(val) -> str:
    """Normalize non-breaking / zero-width spaces and collapse whitespace."""
    if val is None or str(val).strip().lower() == "nan":
        return ""
    s = str(val)
    for bad in ("\u00a0", "\xa0", "\u200b", "\u200e", "\u200f", "\ufeff", "\u202f", "\u3000"):
        s = s.replace(bad, " ")
    return re.sub(r"\s+", " ", s).strip()


def is_blacklisted_company(name: str) -> bool:
    """Enforce permanent blacklist using Unicode NFKD folding."""
    if not name:
        return False
    n = unicodedata.normalize("NFKD", str(name)).lower()
    n_clean = "".join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)


def clean_phone_lt(raw_phone: str) -> str:
    """Normalize Lithuanian phone numbers with leading apostrophe for CSV integrity."""
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
    elif digits.startswith("6") and len(digits) == 8:
        digits = "370" + digits
    elif len(digits) == 8:
        digits = "370" + digits

    if digits.startswith("370") and len(digits) == 11:
        return f"'+370 {digits[3:5]} {digits[5:8]} {digits[8:]}"
    return f"'+{digits}"


def clean_email(email_str: str) -> str:
    """Decode escapes, strip u00XX / %20 / nbsp / stuck tail artifacts, and validate."""
    if not email_str or not isinstance(email_str, str):
        return ""
    em = urllib.parse.unquote(str(email_str).strip())
    for bad in ("\u00a0", "\xa0", "&nbsp;", "%20", "\u200b", "\u200e", "\u200f", "\ufeff", "\u202f", "\u3000"):
        em = em.replace(bad, "")
    em = re.sub(r"^(?:mailto:|https?://)\s*", "", em, flags=re.I)
    em = re.sub(r"\s+", "", em)
    em = em.strip(" .,;:\"'<>[](){}\\/").lower()
    em = re.sub(r"^(?:\\?u00[0-9a-f]{2})+", "", em)
    if re.match(r"^20[a-z][a-z0-9._%+-]*@", em):
        em = em[2:]
    em = re.sub(r"(\.[a-z]{2,6})www\..*$", r"\1", em, flags=re.I)
    em = re.sub(r"(\.[a-z]{2,6})(?:tel|mob|phone|\+?\d{6,}).*$", r"\1", em, flags=re.I)
    return em.strip(" .,;:\"'<>[](){}\\/")


def decode_info_lt_ob(encoded_str: str) -> str:
    """Decode info.lt Base64 + XOR email/link obfuscation."""
    if not encoded_str:
        return ""
    try:
        raw = base64.b64decode(encoded_str).decode("utf-8").split(",")
        key = int(raw[0])
        decoded = "".join(chr(int(x) ^ key) for x in raw[1:])
        return clean_email(decoded)
    except Exception:
        return ""


def decode_cloudflare_emails(html_text: str) -> list[str]:
    """Extract and XOR-decode any Cloudflare data-cfemail tokens in HTML."""
    results = []
    for hex_str in re.findall(r'data-cfemail="([0-9a-fA-F]+)"', html_text or ""):
        try:
            data = bytes.fromhex(hex_str)
            key = data[0]
            decoded = "".join(chr(b ^ key) for b in data[1:])
            em = clean_email(decoded)
            if em and "@" in em:
                results.append(em)
        except Exception:
            pass
    return results


def score_email_b2b_lt(email: str, domain: str = "") -> int:
    """Score B2B recruitment/business value of an email; return -1 for junk."""
    e = clean_email(email)
    if not e or "@" not in e or any(e.endswith(ext) for ext in INVALID_EXTS):
        return -1
    if not re.match(r"^[a-z0-9._%+-]{1,64}@[a-z0-9.-]+\.[a-z]{2,10}$", e):
        return -1
    u, d = e.split("@", 1)
    if len(u) <= 1 or len(d) <= 3:
        return -1

    if d in JUNK_EMAIL_DOMAINS or any(d.endswith("." + jd) for jd in JUNK_EMAIL_DOMAINS):
        return -1
    if u in JUNK_USERNAMES or any(b in u for b in ("youremail", "your-email", "yourname", "placeholder", "noreply", "donotreply")):
        return -1

    score = 10
    clean_d = domain.lower().replace("www.", "").split("/")[0] if domain else ""
    if clean_d and (clean_d in d or d in clean_d):
        score += 50
    elif d.endswith(".lt"):
        score += 30

    # Recruitment / Kitchen staffing (highest priority for restaurants)
    if u in HR_USERNAMES:
        score += 55
    elif u in EXEC_USERNAMES:
        score += 45
    elif u in OFFICIAL_USERNAMES:
        score += 40
    elif u in COMMERCIAL_USERNAMES:
        score += 35
    elif "." in u and score >= 60:
        score += 25
    elif d in ("gmail.com", "inbox.lt", "one.lt"):
        score += 10
    elif u in ("support", "admin", "help", "webmaster", "buhalterija", "saskaitos"):
        score += 5
    return score


def select_best_email(emails: list[str] | set[str], domain: str = "") -> str:
    """Return single highest-scoring valid B2B email."""
    valid = [clean_email(e) for e in emails if e]
    valid = [e for e in set(valid) if e and score_email_b2b_lt(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b_lt(e, domain))


def normalize_company_name(name: str) -> str:
    """Normalize Lithuanian/EU company names per Rule 11 for strict comparison."""
    raw = re.sub(r"\([^\)]*\)|\[[^\]]*\]", " ", str(name or ""))
    norm = unicodedata.normalize("NFKD", raw).lower()
    ascii_name = "".join(c for c in norm if not unicodedata.combining(c))
    legal_forms = ("uab", "mb", "ab", "ii", "vsi", "tub", "kub", "filialas", "atstovybe")
    for lf in legal_forms:
        ascii_name = re.sub(rf"\b{lf}\b", " ", ascii_name)
    return " ".join(re.sub(r"[^a-z0-9]", " ", ascii_name).split())


def is_valid_name_match(csv_name: str, candidate_name: str) -> bool:
    """Strict token/substring match between input company name and info.lt search result."""
    q = normalize_company_name(csv_name)
    c = normalize_company_name(candidate_name)
    if not q or not c:
        return False
    if q == c:
        return True
    if len(q) >= 4 and (q in c or c in q):
        return True
    q_tok = set(q.split())
    c_tok = set(c.split())
    return bool(len(q_tok) > 1 and len(q_tok & c_tok) >= len(q_tok) * 0.7)


def is_clean_business_website(url_str: str) -> bool:
    """Reject social media and directory URLs when extracting company website."""
    low = (url_str or "").lower()
    return bool(low and not any(bad in low for bad in SOCIAL_OR_DIRECTORY_DOMAINS))


def fetch_infolt_html(url: str, max_retries: int = 4) -> str | None:
    """Fetch HTML from info.lt using pre-validated proxies with direct fallback."""
    for _ in range(max_retries):
        p = PROXY_POOL.get_proxy()
        proxies = {"http": f"http://{p}", "https": f"http://{p}"} if p else None
        try:
            r = requests.get(url, proxies=proxies, impersonate="chrome120", timeout=6.0)
            if r.status_code == 200 and len(r.text) > 800:
                return r.text
            if r.status_code in (403, 429) and p:
                PROXY_POOL.remove_proxy(p)
        except Exception:
            if p:
                PROXY_POOL.remove_proxy(p)

    # Direct fallback without proxy
    try:
        r = requests.get(url, impersonate="chrome120", timeout=5.5)
        if r.status_code == 200 and len(r.text) > 800:
            return r.text
    except Exception:
        pass
    return None


def extract_emails_from_html(html_text: str) -> set[str]:
    """Extract mailto, Cloudflare data-cfemail, obfuscated, and visible-DOM emails from HTML."""
    found: set[str] = set()
    if not html_text:
        return found

    soup = BeautifulSoup(html_text, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith("mailto:") or "@" in href:
            em = clean_email(href)
            if em and "@" in em:
                found.add(em)

    for cf_em in decode_cloudflare_emails(html_text):
        found.add(cf_em)

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    visible_text = soup.get_text(" ", strip=True)

    for pattern in OBFUSCATED_PATTERNS:
        for m in pattern.finditer(visible_text):
            em = clean_email(f"{m.group(1)}@{m.group(2)}.{m.group(3)}")
            if em and "@" in em:
                found.add(em)

    for raw_em in EMAIL_REGEX.findall(visible_text):
        em = clean_email(raw_em)
        if em and "@" in em:
            found.add(em)

    return found


def link_priority(label: str) -> int:
    """Assign Baltic/Global Priority 12 (Contact) > 10 (Careers) > 8 (About) for <a> menu links."""
    if any(kw in label for kw in CONTACT_PRIMARY_KEYWORDS):
        return 12
    if any(kw in label for kw in CONTACT_HR_KEYWORDS):
        return 10
    if any(kw in label for kw in CONTACT_ABOUT_KEYWORDS):
        return 8
    return 0


def crawl_website_for_email(site_url: str) -> str:
    """Fallback crawler checking homepage plus Priority-12/10/8 Baltic contact links."""
    if not is_clean_business_website(site_url):
        return ""
    u_str = site_url.strip()
    if not u_str.startswith(("http://", "https://")):
        u_str = "https://" + u_str

    try:
        parsed = urllib.parse.urlparse(u_str)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        domain = parsed.netloc
    except Exception:
        return ""

    try:
        resp = requests.get(u_str, impersonate="chrome120", timeout=4.5, verify=False)
        if resp.status_code != 200:
            return ""
        home_html = resp.text
    except Exception:
        return ""

    emails = extract_emails_from_html(home_html)
    best = select_best_email(emails, domain)
    if best and score_email_b2b_lt(best, domain) >= 90:
        return best

    soup = BeautifulSoup(home_html, "html.parser")
    prioritized: list[tuple[int, str]] = []
    seen_paths = {u_str.rstrip("/"), base_url.rstrip("/")}

    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        full_u = urllib.parse.urljoin(base_url, href)
        clean_u = full_u.split("#")[0].rstrip("/")
        if not clean_u.startswith(base_url) or clean_u in seen_paths:
            continue
        label = (a.get_text(" ", strip=True) + " " + href).lower()
        prio = link_priority(label)
        if prio > 0:
            seen_paths.add(clean_u)
            prioritized.append((prio, clean_u))

    if not prioritized:
        for sp in BALTIC_FALLBACK_PATHS:
            guess_u = f"{base_url.rstrip('/')}{sp}"
            if guess_u.rstrip("/") not in seen_paths:
                seen_paths.add(guess_u.rstrip("/"))
                prioritized.append((2, guess_u))

    prioritized.sort(key=lambda x: -x[0])
    for _, sub_url in prioritized[:5]:
        try:
            sub_resp = requests.get(sub_url, impersonate="chrome120", timeout=4.0, verify=False)
            if sub_resp.status_code == 200:
                emails.update(extract_emails_from_html(sub_resp.text))
                best = select_best_email(emails, domain)
                if best and score_email_b2b_lt(best, domain) >= 90:
                    return best
        except Exception:
            pass

    return select_best_email(emails, domain)


def resolve_infolt_detail_url(comp_code: str, comp_name: str) -> tuple[str | None, bool]:
    """Locate exact company detail URL on info.lt by FirmCode, then strict name match."""
    saw_response = False
    clean_code = re.sub(r"\D", "", str(comp_code or "").strip())
    if len(clean_code) in (7, 8, 9):
        search_url = f"https://www.info.lt/en?action=ieskoti&page=imones&view=detali&FirmCode={clean_code}"
        html = fetch_infolt_html(search_url)
        if html:
            saw_response = True
            soup = BeautifulSoup(html, "html.parser")
            a = soup.select_one("h2.pavadinimas_paprastas a[href]")
            if a:
                return a["href"], True

    if comp_name:
        clean_q = re.sub(r"\([^\)]*\)|\[[^\]]*\]", "", comp_name).strip()
        clean_q = re.sub(r"\b(UAB|MB|AB|IĮ|VšĮ|TŪB|KŪB)\b", "", clean_q, flags=re.I).strip(" ,-\"'")
        if clean_q:
            search_url = f"https://www.info.lt/en?action=ieskoti&page=imones&view=greita&q={urllib.parse.quote_plus(clean_q)}"
            html = fetch_infolt_html(search_url)
            if html:
                saw_response = True
                soup = BeautifulSoup(html, "html.parser")
                for h2 in soup.find_all("h2", class_="pavadinimas_paprastas"):
                    a = h2.find("a", href=True)
                    if a and is_valid_name_match(comp_name, a.get_text(" ", strip=True)):
                        return a["href"], True
    return None, saw_response


def search_and_enrich_from_infolt(comp_code: str, comp_name: str) -> dict | None:
    """Lookup a company on info.lt, decode emails/contacts, and fallback-crawl website."""
    detail_url, saw_response = resolve_infolt_detail_url(comp_code, comp_name)
    if not detail_url:
        return {"checked": True, "not_found": True} if saw_response else None

    det_html = fetch_infolt_html(detail_url)
    if not det_html:
        return None

    soup = BeautifulSoup(det_html, "html.parser")
    found_emails: list[str] = []
    found_phones: list[str] = []
    found_website = ""
    manager_name = ""
    manager_title = "Vadovas"
    full_address = ""

    for attr in ("data-text-ob", "data-link-ob"):
        for tag in soup.find_all(attrs={attr: True}):
            dec = decode_info_lt_ob(tag.get(attr, ""))
            if dec and "@" in dec:
                found_emails.append(dec)

    for row in soup.find_all("div", class_="row"):
        c4 = row.find("div", class_="col-xs-4")
        c8 = row.find("div", class_="col-xs-8")
        if not c4 or not c8:
            continue
        label = clean_text(c4.get_text()).lower()
        val = clean_text(" ".join(c8.stripped_strings))

        if any(k in label for k in ("website", "tinklapis", "tinklalapis")):
            a_tag = c8.find("a", href=True)
            cand_web = a_tag["href"].strip() if a_tag and a_tag["href"].startswith("http") else ""
            if not cand_web and val and "." in val:
                cand_web = val if val.startswith("http") else f"https://{val}"
            if cand_web and is_clean_business_website(cand_web):
                found_website = cand_web
        elif "phone" in label or "telefonas" in label:
            m_ph = re.search(r"(\(\+370\)\s*\d+[\d\s]*|\+370\s*\d+[\d\s]*|\(0\s*\d+\)\s*\d+[\d\s]*|8\s*\d+[\d\s]*)", val)
            if m_ph:
                ph = clean_phone_lt(m_ph.group(1))
                if ph:
                    found_phones.append(ph)
        elif any(k in label for k in ("direktor", "vadov", "manager", "prezident", "savinink", "chef")):
            manager_title = clean_text(c4.get_text()) or "Vadovas"
            manager_name = val

    for kt in soup.select('span.kont_tel, [itemprop="telephone"]'):
        ph = clean_phone_lt(kt.get_text(strip=True))
        if ph:
            found_phones.append(ph)

    addr_elem = soup.find(attrs={"itemprop": "address"})
    if addr_elem:
        full_address = clean_text(addr_elem.get_text(" ", strip=True))
    if not full_address:
        h1 = soup.find("h1")
        if h1 and h1.find_next_sibling():
            sib_lines = h1.find_next_sibling().get_text(" ", strip=True).splitlines()
            if sib_lines:
                full_address = clean_text(sib_lines[0])

    best_phone = found_phones[0] if found_phones else ""
    best_email = select_best_email(found_emails, found_website)

    if not best_email and found_website:
        best_email = crawl_website_for_email(found_website)

    return {
        "checked": True,
        "Email": best_email,
        "SDT": best_phone,
        "Website": found_website,
        "Nguoi_Quan_Ly": manager_name,
        "Chuc_Danh": manager_title,
        "Dia_Chi": full_address,
        "InfoLT_URL": detail_url,
    }


def apply_cache_record(df: pd.DataFrame, idx: int, rec: dict) -> None:
    """Populate a DataFrame row safely from a cached enrichment dictionary."""
    em = rec.get("Email", "")
    if em:
        df.at[idx, "Email"] = clean_email(em)

    web = rec.get("Website") or rec.get("Web") or ""
    if web and not clean_text(df.at[idx, "Website"]):
        df.at[idx, "Website"] = clean_text(web)

    sdt = rec.get("SDT") or rec.get("Phone") or ""
    if sdt and not clean_text(df.at[idx, "SDT"]):
        df.at[idx, "SDT"] = clean_phone_lt(sdt)

    manager = rec.get("Nguoi_Quan_Ly") or rec.get("Leader") or ""
    if manager and not clean_text(df.at[idx, "Nguoi_Quan_Ly"]):
        df.at[idx, "Nguoi_Quan_Ly"] = clean_text(manager)

    title = rec.get("Chuc_Danh") or rec.get("Role") or ""
    if title and not clean_text(df.at[idx, "Chuc_Danh"]):
        df.at[idx, "Chuc_Danh"] = clean_text(title)

    addr = rec.get("Dia_Chi") or rec.get("Address") or ""
    if addr and not clean_text(df.at[idx, "Dia_Chi"]):
        df.at[idx, "Dia_Chi"] = clean_text(addr)


def save_cache(cache: dict) -> None:
    """Persist checkpoint JSON atomically."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = CACHE_FILE.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, CACHE_FILE)


def export_and_sync_all_files(df: pd.DataFrame) -> int:
    """Export 1ENR, 2COL, and ONLY_EMAILS_READY CSVs (utf-8-sig) and sync folders."""
    df_out = df.copy()
    if "Cong ty" in df_out.columns:
        df_out = df_out[~df_out["Cong ty"].apply(is_blacklisted_company)].reset_index(drop=True)

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
        email_val = clean_email(r.get("Email", ""))
        phone_val = clean_phone_lt(r.get("SDT", ""))
        city_val = clean_text(r.get("City", ""))
        addr_val = clean_text(r.get("Dia_Chi", "")) or clean_text(r.get("Dia chi", ""))
        if not addr_val and city_val:
            addr_val = f"{city_val}, Lithuania"

        cat_val = clean_text(r.get("Category", "")) or clean_text(r.get("Catalog_Name", ""))
        if not cat_val:
            cat_val = "Restaurants & Food Service (Lithuania)"

        coldmail_rows.append(
            {
                "No.": r.get("No.", ""),
                "Công ty": comp_name,
                "Chức danh": title,
                "Người liên hệ": manager,
                "SĐT": phone_val,
                "Liên Hệ": web_val if web_val else clean_text(r.get("Detail_URL", "")),
                "Email": email_val,
                "Liên Hệ mail": f"mailto:{email_val}" if email_val else web_val,
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
                "Category": cat_val,
            }
        )

    df_2col = pd.DataFrame(coldmail_rows, columns=COLDMAIL_COLUMNS)
    df_2col.to_csv(OUTPUT_2COL_PATH, index=False, encoding="utf-8-sig")

    df_ready = df_2col[df_2col["Email"] != ""].copy()
    df_ready["No."] = range(1, len(df_ready) + 1)
    df_ready.to_csv(OUTPUT_READY_PATH, index=False, encoding="utf-8-sig")

    for extra_dir in (CSDL_DIR, ARCHIVE_DIR):
        extra_dir.mkdir(parents=True, exist_ok=True)
        for src_path in (OUTPUT_1ENR_PATH, OUTPUT_2COL_PATH, OUTPUT_READY_PATH):
            try:
                shutil.copy2(src_path, extra_dir / src_path.name)
            except Exception:
                pass

    return len(has_em)


def load_clean_dataframe() -> pd.DataFrame:
    """Load LT_FOOD_LTOR_0RAW.csv, ensure enrichment columns, and drop blacklisted companies."""
    df = pd.read_csv(INPUT_CSV_PATH, encoding="utf-8-sig", dtype=str).fillna("")
    if "Cong ty" in df.columns:
        df = df[~df["Cong ty"].apply(is_blacklisted_company)].reset_index(drop=True)
    for col in ("Website", "Email", "SDT", "Nguoi_Quan_Ly", "Chuc_Danh", "Dia_Chi"):
        if col not in df.columns:
            df[col] = ""
    return df


def run_enrichment(limit: int | None = None, workers: int = 6, retry_empty: bool = False) -> None:
    """Execute concurrent info.lt enrichment with proxy rotation and atomic checkpoints."""
    print("=" * 80)
    print("ENRICH LT RESTAURANTS & FOOD SERVICE (NACE 56) VIA INFO.LT")
    print(f"  Input CSV   : {INPUT_CSV_PATH.name}")
    print(f"  Master 1ENR : {OUTPUT_1ENR_PATH.name}")
    print(f"  ColdMail    : {OUTPUT_2COL_PATH.name}")
    print(f"  Ready Only  : {OUTPUT_READY_PATH.name}")
    print(f"  Workers     : {workers} | Proxy pool: {'ON' if PROXY_POOL.enabled else 'OFF'}")
    if limit:
        print(f"  Limit       : {limit} companies")
    print("=" * 80)

    if not INPUT_CSV_PATH.exists():
        print(f"[ERROR] Input file not found: {INPUT_CSV_PATH}")
        return

    df = load_clean_dataframe()
    cache: dict[str, dict] = {}
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
            print(f"[*] Loaded {len(cache):,} entries from cache.")
        except Exception as e:
            print(f"[!] Could not load cache: {e}")

    pending_indices: list[int] = []
    cached_emails = 0

    for idx, row in df.iterrows():
        comp = clean_text(row.get("Cong ty", ""))
        code = clean_text(row.get("Company_Code", ""))
        key = code if code else comp

        # Check by code or by name
        rec = cache.get(key)
        if not rec and comp.lower() in cache:
            rec = cache.get(comp.lower())

        if rec:
            apply_cache_record(df, idx, rec)
            if clean_email(df.at[idx, "Email"]):
                cached_emails += 1
                continue
            if rec.get("checked") and not retry_empty:
                continue
        if not clean_email(df.at[idx, "Email"]):
            pending_indices.append(idx)

    if limit:
        pending_indices = pending_indices[:limit]

    print(
        f"[*] Total rows: {len(df):,} | Cached with Email: {cached_emails:,} | Pending lookup: {len(pending_indices):,}\n"
    )

    if not pending_indices:
        total_em = export_and_sync_all_files(df)
        print(f"[+] Nothing pending to fetch. Exported total emails: {total_em:,}")
        return

    PROXY_POOL.refresh()

    lock = threading.Lock()
    processed = 0
    newly_found = 0

    tasks = []
    for idx in pending_indices:
        row = df.loc[idx]
        comp = clean_text(row.get("Cong ty", ""))
        code = clean_text(row.get("Company_Code", ""))
        city = clean_text(row.get("City", ""))
        key = code if code else comp
        tasks.append((idx, key, comp, code, city))

    def process_one(task: tuple[int, str, str, str, str]):
        idx, key, comp, code, city = task
        res = search_and_enrich_from_infolt(code, comp)
        return idx, key, comp, code, city, res

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as executor:
        futures = [executor.submit(process_one, t) for t in tasks]
        for fut in as_completed(futures):
            try:
                idx, key, comp, code, city, res = fut.result()
            except Exception as err:
                with lock:
                    processed += 1
                    print(f"[{processed}/{len(pending_indices)}] [ERR] {err}")
                continue

            with lock:
                processed += 1
                if res and not res.get("not_found"):
                    apply_cache_record(df, idx, res)
                    if res.get("Email"):
                        newly_found += 1
                        print(
                            f"[{processed}/{len(pending_indices)}] [+] {comp} ({code}) -> {res['Email']} | Web: {res.get('Website', '')}"
                        )
                    elif res.get("Website") or res.get("SDT"):
                        print(
                            f"[{processed}/{len(pending_indices)}] [~] {comp} ({code}) -> Web: {res.get('Website', '')} | Phone: {res.get('SDT', '')}"
                        )
                    else:
                        print(f"[{processed}/{len(pending_indices)}] [-] {comp} ({code}) -> Found on info.lt, no public contact")
                    cache[key] = {
                        "checked": True,
                        "Email": res.get("Email", ""),
                        "SDT": clean_phone_lt(res.get("SDT", "") or df.at[idx, "SDT"]),
                        "Website": res.get("Website", "") or df.at[idx, "Website"],
                        "Nguoi_Quan_Ly": res.get("Nguoi_Quan_Ly", "") or df.at[idx, "Nguoi_Quan_Ly"],
                        "Chuc_Danh": res.get("Chuc_Danh", "") or df.at[idx, "Chuc_Danh"],
                        "Dia_Chi": res.get("Dia_Chi", "") or df.at[idx, "Dia_Chi"],
                    }
                elif res and res.get("not_found"):
                    print(f"[{processed}/{len(pending_indices)}] [x] {comp} ({code} | {city}) -> Not listed on info.lt")
                    cache[key] = {
                        "checked": True,
                        "Email": "",
                        "SDT": clean_phone_lt(df.at[idx, "SDT"]),
                        "Website": clean_text(df.at[idx, "Website"]),
                        "Nguoi_Quan_Ly": clean_text(df.at[idx, "Nguoi_Quan_Ly"]),
                        "Chuc_Danh": clean_text(df.at[idx, "Chuc_Danh"]),
                        "Dia_Chi": clean_text(df.at[idx, "Dia_Chi"]),
                    }
                else:
                    print(f"[{processed}/{len(pending_indices)}] [!] {comp} ({code} | {city}) -> Temporary network fail (will retry)")

                if processed % 20 == 0:
                    save_cache(cache)
                    cur_em = export_and_sync_all_files(df)
                    print(
                        f"    [*] Checkpoint saved ({processed}/{len(pending_indices)} | Total Emails: {cur_em:,} | +{newly_found} new)"
                    )

    save_cache(cache)
    total_valid_emails = export_and_sync_all_files(df)
    print("\n" + "=" * 80)
    print("DONE ENRICHING LITHUANIAN RESTAURANTS & FOOD SERVICE VIA INFO.LT!")
    print(f"  Total companies : {len(df):,}")
    print(f"  Valid emails    : {total_valid_emails:,} ({total_valid_emails * 100 / max(1, len(df)):.1f}%)")
    print(f"  New this run    : +{newly_found:,}")
    print(f"  Exported        : {OUTPUT_1ENR_PATH.name}, {OUTPUT_2COL_PATH.name}, {OUTPUT_READY_PATH.name}")
    print("=" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich LT_FOOD_LTOR_0RAW.csv via info.lt")
    parser.add_argument("--limit", type=int, default=None, help="Max companies to enrich in this run")
    parser.add_argument("--workers", type=int, default=6, help="Concurrent worker threads (1-12, default: 6)")
    parser.add_argument("--retry-empty", action="store_true", help="Re-check previously cached companies with empty Email")
    parser.add_argument("--no-proxy", action="store_true", help="Disable ProxyScrape pool and query directly")
    parser.add_argument("--re-export", action="store_true", help="Regenerate CSV outputs from cache only")
    args = parser.parse_args()

    PROXY_POOL.enabled = not args.no_proxy

    if args.re_export:
        if INPUT_CSV_PATH.exists():
            df = load_clean_dataframe()
            if CACHE_FILE.exists():
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                for idx, row in df.iterrows():
                    key = clean_text(row.get("Company_Code", "")) or clean_text(row.get("Cong ty", ""))
                    if key in cache:
                        apply_cache_record(df, idx, cache[key])
                    elif clean_text(row.get("Cong ty", "")).lower() in cache:
                        apply_cache_record(df, idx, cache[clean_text(row.get("Cong ty", "")).lower()])
            cnt = export_and_sync_all_files(df)
            print(f"[+] Re-exported cleanly from cache. Valid emails: {cnt:,}")
        return

    run_enrichment(limit=args.limit, workers=args.workers, retry_empty=args.retry_empty)


if __name__ == "__main__":
    main()

