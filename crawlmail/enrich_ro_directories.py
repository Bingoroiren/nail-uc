# -*- coding: utf-8 -*-
"""
DIRECTORY ENRICHMENT FOR ROMANIAN EMPLOYMENT AGENCIES (RO_AGCY_DIR0)
====================================================================
Source : ro_romania/RO_AGCY_COMPANIES_CUI.csv (892 unique agencies, 891 CUI)
Layers :
  1. ANAF Official API v9 (Batch by CUI): Legal Name, Active/Radiata Status, CAEN,
     RegCom (J...), Official Address, Registered ANAF Phone/Fax.
  2. CompanyWall.ro (Lookup by CUI): Administrator (Decision Maker), Extra Phones,
     Website, Email (if listed), Active Status.
  3. PaginiAurii.ro (Yellow Pages Romania by CUI): Extra commercial Phone / Web / Email.
  4. Deep Website + Facebook Email Crawler (Romanian B2B Localized): Priority-10 DOM <a>
     links + Cloudflare decode + Obfuscated patterns + Romania B2B scoring.

Outputs (UTF-8 with BOM, utf-8-sig):
  - RO_AGCY_DIR0_1ENR.csv (Master enriched directory dataset)
  - RO_AGCY_DIR0_2COL.csv (Cold Mail 20-col format, with_email sorted first)
  - RO_AGCY_DIR0_ONLY_EMAILS_READY.csv
  - ro_romania/RO_AGCY_DIR0_1ENR.csv + ro_romania/RO_AGCY_DIR0_2COL.csv
"""

from __future__ import annotations

import argparse
import html
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
from datetime import datetime
from pathlib import Path

import curl_cffi.requests as requests
import pandas as pd
from bs4 import BeautifulSoup

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent
RO_DIR = ROOT_DIR / "ro_romania"
INPUT_CSV_PATH = RO_DIR / "RO_AGCY_COMPANIES_CUI.csv"

OUTPUT_1ENR_PATH = ROOT_DIR / "RO_AGCY_DIR0_1ENR.csv"
OUTPUT_2COL_PATH = ROOT_DIR / "RO_AGCY_DIR0_2COL.csv"
OUTPUT_READY_PATH = ROOT_DIR / "RO_AGCY_DIR0_ONLY_EMAILS_READY.csv"
CACHE_FILE = ROOT_DIR / "crawlmail" / "cache_enrich_ro_directories.json"

ANAF_URL = "https://webservicesp.anaf.ro/api/PlatitorTvaRest/v9/tva"

COLDMAIL_COLUMNS = [
    "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ",
    "Email", "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển",
    "Check gửi", "Last Subject", "Last Body HTML", "Trạng thái Reply",
    "Lần Follow-up", "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category",
]

PERMANENT_BLACKLIST_COMPANIES = (
    "scandi standard",
    "scandi-standard",
    "scandi standart",
    "biliarta",
    "daigre",
)

EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b")
OBFUSCATED_PATTERNS = (
    re.compile(r"([A-Za-z0-9._%+-]{1,64})\s*\[at\]\s*([A-Za-z0-9.-]{1,255})\s*\[dot\]\s*([A-Za-z]{2,10})", re.I),
    re.compile(r"([A-Za-z0-9._%+-]{1,64})\s*\(at\)\s*([A-Za-z0-9.-]{1,255})\s*\(dot\)\s*([A-Za-z]{2,10})", re.I),
    re.compile(r"([A-Za-z0-9._%+-]{1,64})\s+AT\s+([A-Za-z0-9.-]{1,255})\s+DOT\s+([A-Za-z]{2,10})"),
)
INVALID_EXTS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".css", ".js", ".pdf", ".woff", ".woff2", ".ico", ".mp4", ".mp3", ".zip",
)

JUNK_EMAIL_DOMAINS = {
    "example.com", "example.org", "example.net", "domain.com", "yourdomain.com",
    "yourcompany.com", "company.com", "email.com", "placeholder.com", "sample.com",
    "sentry.io", "sentry-next.wixpress.com", "wixpress.com", "wix.com",
    "wordpress.com", "wordpress.org", "squarespace.com", "weebly.com", "godaddy.com",
    "bootstrapmade.com", "templatemonster.com", "themeforest.net", "schema.org",
    "trustpilot.com", "google.com", "facebook.com", "instagram.com", "linkedin.com",
    "youtube.com", "twitter.com", "x.com", "bendingspoons.com", "aol.com",
    "paginiaurii.ro", "companywall.ro", "termene.ro", "listafirme.ro", "listafirme.eu",
    "topfirme.com", "totalfirme.ro", "date-firme.ro", "risco.ro", "fcrmedia.ro",
    "brat.ro", "sati.ro", "trafic.ro", "anpc.ro", "ec.europa.eu",
    "dataprotection.ro", "dataprotection.gov.uk", "edpb.europa.eu",
    "anaf.ro", "onrc.ro", "anofm.ro", "inspectiamuncii.ro", "mmuncii.gov.ro",
    "localservices.be", "bizbook.be", "pagesdor.be", "goudengids.be", "kodovizija.lt",
}

JUNK_USERNAMES = {
    "youremail", "your-email", "your_email", "yourname", "your-name",
    "yourcompany", "someone", "nobody", "john.doe", "johndoe", "jane.doe",
    "username", "user", "name", "sample", "demo", "test", "example",
    "no-reply", "noreply", "donotreply", "do-not-reply",
    "privacy", "terms", "cookies", "gdpr", "abuse", "security", "sentry",
    "mailer-daemon", "postmaster",
    "anspdcp", "daneosobowe", "rodo", "iod", "dpo", "protectiadatelor",
    "protectia-datelor", "datepersonale", "date-personale", "dsa-representative",
    "legal", "compliance",
}

SOCIAL_OR_DIRECTORY_DOMAINS = (
    "facebook.com", "fb.com", "instagram.com", "linkedin.com", "youtube.com",
    "twitter.com", "x.com", "tiktok.com", "plus.google.com",
    "aol.com", "gmail.com", "yahoo.com", "yahoo.ro", "hotmail.com", "outlook.com",
    "live.com", "icloud.com", "mail.ru", "yandex.ru", "yandex.com", "protonmail.com", "gmx.com",
    "paginiaurii.ro", "companywall.ro", "termene.ro", "listafirme.ro", "listafirme.eu",
    "topfirme.com", "totalfirme.ro", "date-firme.ro", "risco.ro", "cylex.ro",
    "firmepenet.ro", "bizoo.ro", "fcrmedia.ro", "rentasite.ro", "rentavideo.ro",
    "rentawidget.ro", "cyberfolks.ro", "goldenpages.ie", "goudengids.be", "sinda.com",
    "brat.ro", "sati.ro", "trafic.ro", "anpc.ro", "dataprotection.ro", "ec.europa.eu",
    "w3.org", "google.com", "maps.google.com", "apple.com", "blogspot.com",
)

RO_CONTACT_KEYWORDS_P10 = (
    "contact", "date-de-contact", "contacteaza", "contactati",
    "despre-noi", "despre", "echipa", "recrutare", "cariere", "angajari",
    "joburi", "locuri-de-munca", "termeni", "confidentialitate", "gdpr",
    "imprint", "about", "get-in-touch",
)
RO_SECONDARY_KEYWORDS_P5 = (
    "servicii", "resurse-umane", "plasare", "munca", "companie",
    "clienti", "angajatori", "parteneri", "faq", "ajutor", "services", "team",
)
RO_GUESS_SUBPATHS = (
    "/contact", "/contact/", "/contact.html", "/contact.php",
    "/date-de-contact", "/contacteaza-ne",
    "/despre-noi", "/despre-noi/", "/despre",
    "/recrutare", "/cariere", "/locuri-de-munca",
    "/termeni-si-conditii", "/politica-de-confidentialitate", "/gdpr",
    "/about", "/about-us",
)

RO_LEGAL_SUFFIXES = (
    "societate cu raspundere limitata",
    "societate pe actiuni",
    "s.r.l.-d", "srl-d", "s.r.l.", "s.r.l", "srl",
    "s.a.", "sa", "s.c.", "sc", "s.n.c.", "snc", "p.f.a.", "pfa", "i.i.", "ii", "ong",
)

THREAD_LOCAL = threading.local()
CACHE_LOCK = threading.Lock()


def get_session() -> requests.Session:
    """Thread-local Chrome TLS session."""
    sess = getattr(THREAD_LOCAL, "sess", None)
    if sess is None:
        sess = requests.Session(impersonate="chrome")
        THREAD_LOCAL.sess = sess
    return sess


def clean_text(val) -> str:
    """Strip NBSP, zero-width spaces and normalize whitespace."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val)
    if s.strip().lower() in ("nan", "none", "null"):
        return ""
    for bad in ("\u00a0", "\xa0", "\u200b", "\u200e", "\u200f", "\ufeff", "\u202f", "\u3000"):
        s = s.replace(bad, " ")
    return re.sub(r"\s+", " ", s).strip()


def is_blacklisted_company(name: str) -> bool:
    """Permanent company exclusion filter (Rule 12 / GEMINI.md)."""
    if not name or not isinstance(name, str):
        return False
    n = unicodedata.normalize("NFKD", name).lower()
    n_clean = "".join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)


def strip_diacritics(text: str) -> str:
    """Lowercase ASCII approximation removing Romanian diacritics."""
    n = unicodedata.normalize("NFKD", clean_text(text).replace("ă", "a").replace("â", "a").replace("î", "i").replace("ș", "s").replace("ş", "s").replace("ț", "t").replace("ţ", "t")).lower()
    return "".join(c for c in n if not unicodedata.combining(c))


def clean_company_for_match(name: str) -> str:
    """Normalize Romanian company name for strict verification."""
    s = strip_diacritics(name)
    # Compact dotted legal forms (e.g. "S.C.", "S.R.L.", "P.F.A.") before punctuation removal
    s = re.sub(
        r"\b(?:s\s*\.\s*c|s\s*\.\s*r\s*\.\s*l(?:\s*-\s*d)?|s\s*\.\s*a|p\s*\.\s*f\s*\.\s*a|i\s*\.\s*i|s\s*\.\s*n\s*\.\s*c)\b\.?",
        lambda m: re.sub(r"[\s.]", "", m.group(0)),
        s,
    )
    s = re.sub(r"[^a-z0-9\s-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    changed = True
    while changed and s:
        changed = False
        for suf in RO_LEGAL_SUFFIXES:
            s_tok = strip_diacritics(suf)
            if s == s_tok:
                s = ""
                changed = True
                break
            if s.endswith(" " + s_tok):
                s = s[: -(len(s_tok) + 1)].strip()
                changed = True
            elif s.startswith(s_tok + " "):
                s = s[len(s_tok) + 1 :].strip()
                changed = True
    return re.sub(r"\s+", " ", s).strip()


def is_name_match_ro(name_a: str, name_b: str) -> bool:
    """Check strict token overlap between source company name and directory card name."""
    ca = clean_company_for_match(name_a)
    cb = clean_company_for_match(name_b)
    if not ca or not cb:
        return False
    if ca == cb or ca in cb or cb in ca:
        return True
    ta = {w for w in ca.split() if len(w) > 1}
    tb = {w for w in cb.split() if len(w) > 1}
    if not ta or not tb:
        return False
    inter = ta & tb
    return len(inter) >= min(2, len(ta), len(tb)) and (len(inter) / min(len(ta), len(tb))) >= 0.65


def normalize_ro_phones(raw_values: list[str]) -> tuple[str, str]:
    """Normalize Romanian phone strings and ALWAYS prefix each with single quote (')."""
    out: list[str] = []
    seen: set[str] = set()
    pattern = re.compile(
        r"(?<!\d)(?:\+?40[ .-]?|0040[ .-]?|0)(?:"
        r"\d{9}"
        r"|\d{1,2}[ ./-]\d{6,7}"
        r"|\d{2,3}(?:[ ./-]\d{2,4}){2,3}"
        r")(?!\d)"
    )
    for raw in raw_values:
        s = clean_text(raw)
        if not s or s == "-":
            continue
        for m in pattern.finditer(s):
            tok = m.group(0)
            digits = re.sub(r"\D", "", tok)
            if digits.startswith("0040"):
                digits = "+40" + digits[4:]
            elif tok.strip().startswith("+40"):
                digits = "+40" + digits[2:]
            elif digits.startswith("40") and len(digits) == 11:
                digits = "+40" + digits[2:]
            raw_d = re.sub(r"\D", "", digits)
            # Valid Romanian numbers: 10 digits starting with 0, or 11 digits starting with +40
            if ((digits.startswith("0") and len(raw_d) == 10) or (digits.startswith("+40") and len(raw_d) == 11)) and digits not in seen:
                seen.add(digits)
                out.append(f"'{digits}")
    return (out[0] if out else ""), "; ".join(out)


def ensure_phone_quote(phone: str) -> str:
    """Ensure every non-empty phone starts with single quote (')."""
    p = clean_text(phone)
    if not p:
        return ""
    return p if p.startswith("'") else f"'{p}"


def clean_email(email: str) -> str:
    """Clean hidden whitespace, NBSP, URL-encoding, and mailto prefix from candidate email."""
    if not email or not isinstance(email, str):
        return ""
    em = urllib.parse.unquote(html.unescape(email).strip())
    for bad in ("\u00a0", "\xa0", "&nbsp;", "%20", "\u200b", "\u200e", "\u200f", "\ufeff", "\u202f", "\u3000"):
        em = em.replace(bad, "")
    em = re.sub(r"^mailto:\s*", "", em, flags=re.I)
    em = em.split("?")[0]
    em = re.sub(r"\s+", "", em)
    em = em.strip(" .,;:\"'<>[](){}\\/")
    if re.match(r"^20[A-Za-z][A-Za-z0-9._%+-]*@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", em):
        em = em[2:]
    return em.lower()


def decode_cf_hex(cf_hex: str) -> str:
    """Decode Cloudflare data-cfemail XOR obfuscation."""
    try:
        key = int(cf_hex[:2], 16)
        return "".join(chr(int(cf_hex[i : i + 2], 16) ^ key) for i in range(2, len(cf_hex), 2))
    except Exception:
        return ""


def is_valid_website(url: str) -> bool:
    """Reject social media, directory, and malformed URLs."""
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
    """Check if URL points to a company Facebook page rather than share/sharer dialog."""
    u = clean_text(url).lower()
    if not u or not any(k in u for k in ("facebook.com/", "fb.com/")):
        return False
    if any(x in u for x in ("sharer.php", "/share", "tr?", "plugins/", "/policies", "/help")):
        return False
    return True


def score_email_b2b_ro(email: str, website_domain: str = "") -> int:
    """Score Romanian B2B manpower agency emails; return -1 for junk/template addresses."""
    e = clean_email(email)
    if not e or not EMAIL_REGEX.fullmatch(e):
        return -1
    u, d = e.split("@", 1)
    if d in JUNK_EMAIL_DOMAINS or any(d.endswith("." + jd) for jd in JUNK_EMAIL_DOMAINS):
        return -1
    if u in JUNK_USERNAMES or any(
        k in u
        for k in (
            "youremail", "your-email", "yourname", "placeholder",
            "daneosobowe", "protectia", "datepersonale", "anspdcp", "dsa-",
        )
    ):
        return -1
    if any(e.endswith(ext) for ext in INVALID_EXTS):
        return -1

    score = 10
    clean_dom = website_domain.lower().replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
    if clean_dom and (clean_dom in d or d in clean_dom):
        score += 50

    if u in (
        "recrutare", "recrutari", "resurseumane", "resurse-umane", "hr", "cariere", "angajari",
        "angajare", "jobs", "job", "recruitment", "career", "careers", "talent", "personal",
        "staffing", "munca", "lucru", "cv", "work", "nabor", "praca", "plaseaza", "solicitari",
    ):
        score += 50
    elif u in (
        "director", "manager", "ceo", "administrator", "conducere", "management",
        "owner", "sales", "vanzari", "comercial", "obchod",
    ):
        score += 45
    elif u in (
        "office", "contact", "info", "secretariat", "receptie", "relatii", "mail", "birou", "buro",
    ):
        score += 40
    elif "." in u and score >= 60:
        score += 25
    elif d in ("gmail.com", "yahoo.com", "yahoo.ro", "hotmail.com", "outlook.com", "live.com"):
        score += 10
    elif u in ("support", "help", "facturi", "contabilitate", "admin", "webmaster"):
        score += 5

    return score


def select_best_email(emails: set[str] | list[str], website_domain: str = "") -> str:
    """Pick the single highest-scoring B2B email."""
    valid = [clean_email(e) for e in set(emails) if score_email_b2b_ro(e, website_domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b_ro(e, website_domain))


def extract_emails_from_html(raw_html: str) -> set[str]:
    """Multi-layer HTML email extraction: data-cfemail, mailto, obfuscated text, clean body."""
    found: set[str] = set()
    if not raw_html:
        return found

    soup = BeautifulSoup(raw_html, "html.parser")
    for cf in soup.select("[data-cfemail]"):
        dec = clean_email(decode_cf_hex(cf.get("data-cfemail", "")))
        if dec:
            found.add(dec)

    for a in soup.find_all("a", href=True):
        href = html.unescape(a["href"]).strip()
        if "mailto:" in href.lower():
            part = re.split(r"mailto:", href, flags=re.I)[-1].split("?")[0]
            em = clean_email(part)
            if em:
                found.add(em)

    # Extract Schema.org JSON-LD emails before removing JS/script noise
    for ld in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw_ld = ld.string or ld.get_text() or ""
        if "@" in raw_ld:
            for m in EMAIL_REGEX.findall(html.unescape(raw_ld)):
                em = clean_email(m)
                if em:
                    found.add(em)

    # Remove script/style/noscript tags before regex extraction so JS config junk isn't scraped
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    visible_text = html.unescape(soup.get_text(" ", strip=True))
    for pat in OBFUSCATED_PATTERNS:
        for m in pat.finditer(visible_text):
            em = clean_email(f"{m.group(1)}@{m.group(2)}.{m.group(3)}")
            if em:
                found.add(em)
    for m in EMAIL_REGEX.findall(visible_text):
        em = clean_email(m)
        if em:
            found.add(em)

    return found


def fetch_html_fast(url: str, timeout: float = 8.0, allow_insecure: bool = False) -> str:
    """Fetch HTML cleanly using thread-local Chrome session with SSL fallback & backoff."""
    sess = get_session()
    for verify_flag in ([True, False] if allow_insecure else [True]):
        for attempt in range(2):
            try:
                r = sess.get(url, timeout=timeout, allow_redirects=True, verify=verify_flag)
                if r.status_code == 200:
                    return r.text or ""
                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(1.5 * (attempt + 1) + random.uniform(0.2, 0.8))
                    continue
                return ""
            except Exception as exc:
                err_txt = str(exc).lower()
                if allow_insecure and verify_flag and ("ssl" in err_txt or "cert" in err_txt or "curl: (60)" in err_txt):
                    break
                time.sleep(0.4)
    return ""


def collect_prioritized_subpages_ro(home_html: str, web_url: str) -> list[str]:
    """Rank DOM <a> links (Priority 10/5) ahead of localized Romanian guess paths (Priority 2)."""
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

            h_low = strip_diacritics(raw_href)
            t_low = strip_diacritics(a.get_text(" ", strip=True))
            prio = 0
            if any(k in h_low or k in t_low for k in RO_CONTACT_KEYWORDS_P10):
                prio = 10
            elif any(k in h_low or k in t_low for k in RO_SECONDARY_KEYWORDS_P5):
                prio = 5
            if prio > 0:
                seen.add(c_url)
                prioritized.append((prio, full))
    except Exception:
        pass

    prioritized.sort(key=lambda x: x[0], reverse=True)
    queue = [u for _, u in prioritized]
    for gp in RO_GUESS_SUBPATHS:
        g_url = urllib.parse.urljoin(root, gp)
        cg = canon(g_url)
        if cg not in seen:
            seen.add(cg)
            queue.append(g_url)
    return queue


def crawl_website_for_email_ro(web_url: str) -> tuple[str, str, str]:
    """Deep-crawl homepage + top 8 prioritized subpages + Facebook About fallback."""
    if not web_url or not is_valid_website(web_url):
        return "", "", ""

    parsed = urllib.parse.urlparse(web_url)
    host = parsed.netloc
    bare_host = host[4:] if host.lower().startswith("www.") else host
    candidates = [web_url]
    for alt in (f"https://{bare_host}", f"http://{host}", f"http://{bare_host}"):
        if alt not in candidates:
            candidates.append(alt)

    home_html = ""
    working_url = web_url
    for cand in candidates:
        home_html = fetch_html_fast(cand, timeout=9.0, allow_insecure=True)
        if home_html:
            working_url = cand
            break
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

    best = select_best_email(all_emails, working_url)
    if best and score_email_b2b_ro(best, working_url) >= 95:
        return best, "Website", fb_url

    for sub_url in collect_prioritized_subpages_ro(home_html, working_url)[:8]:
        sub_html = fetch_html_fast(sub_url, timeout=7.0, allow_insecure=True)
        if not sub_html:
            continue
        all_emails |= extract_emails_from_html(sub_html)
        best = select_best_email(all_emails, working_url)
        if best and score_email_b2b_ro(best, working_url) >= 95:
            return best, "Website", fb_url

    best = select_best_email(all_emails, working_url)
    if best:
        return best, "Website", fb_url

    if fb_url:
        fb_about = fb_url.rstrip("/") + "/about"
        fb_html = fetch_html_fast(fb_about, timeout=8.0, allow_insecure=True) or fetch_html_fast(fb_url, timeout=8.0, allow_insecure=True)
        fb_best = select_best_email(extract_emails_from_html(fb_html), working_url)
        if fb_best:
            return fb_best, "Facebook", fb_url

    return "", "", fb_url


def fetch_anaf_batch(cui_list: list[str]) -> dict[str, dict]:
    """Query ANAF official public v9 REST API in chunks of 100 CUIs (~1.1s between chunks)."""
    results: dict[str, dict] = {}
    unique_digits = sorted({re.sub(r"\D", "", c) for c in cui_list if re.sub(r"\D", "", c)})
    today = datetime.now().strftime("%Y-%m-%d")
    sess = requests.Session(impersonate="chrome")

    for i in range(0, len(unique_digits), 100):
        chunk = unique_digits[i : i + 100]
        payload = [{"cui": int(c), "data": today} for c in chunk]
        try:
            r = sess.post(ANAF_URL, json=payload, timeout=20)
            if r.status_code == 200:
                js = r.json()
                for item in js.get("found", []):
                    dg = item.get("date_generale", {}) or {}
                    si = item.get("stare_inactiv", {}) or {}
                    ass = item.get("adresa_sediu_social", {}) or {}
                    c_str = str(dg.get("cui", "")).strip()
                    if not c_str:
                        continue
                    _, phones_joined = normalize_ro_phones(
                        [clean_text(dg.get("telefon", "")), clean_text(dg.get("fax", ""))]
                    )
                    inact = "INACTIV" if si.get("statusInactivi") else ""
                    stare = clean_text(dg.get("stare_inregistrare", ""))
                    full_stare = f"{stare} ({inact})".strip() if inact else stare
                    results[c_str] = {
                        "cui": c_str,
                        "denumire": clean_text(dg.get("denumire", "")),
                        "adresa": clean_text(dg.get("adresa", "")),
                        "judet": clean_text(ass.get("sdenumire_Judet", "")),
                        "localitate": clean_text(ass.get("sdenumire_Localitate", "")),
                        "telefon": phones_joined,
                        "nrRegCom": clean_text(dg.get("nrRegCom", "")),
                        "cod_CAEN": clean_text(dg.get("cod_CAEN", "")),
                        "stare_inregistrare": full_stare,
                    }
        except Exception as e:
            print(f"  [ANAF WARN] chunk {i}: {e}")
        if i + 100 < len(unique_digits):
            time.sleep(1.15)
    return results


def parse_companywall_by_cui(cui_digits: str, target_name: str) -> dict:
    """Lookup company on CompanyWall.ro by CUI -> extract Administrator, Phones, Web, Email."""
    out = {
        "matched": False, "url": "", "admin": "", "phones": [],
        "website": "", "emails": set(), "caen": "", "nrRegCom": "", "status": "", "city": "", "address": "",
    }
    if not cui_digits:
        return out

    search_html = fetch_html_fast(f"https://www.companywall.ro/cautare?q={cui_digits}", timeout=10.0)
    if not search_html:
        return out

    soup = BeautifulSoup(search_html, "html.parser")
    cand_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/companie/" not in href.lower():
            continue
        card = a.parent.parent if a.parent and a.parent.parent else a.parent
        card_txt = card.get_text(" ", strip=True) if card else ""
        if cui_digits in card_txt or is_name_match_ro(target_name, a.get_text(" ", strip=True)):
            full = href if href.startswith("http") else ("https://www.companywall.ro" + href)
            if full not in cand_links:
                cand_links.append(full)

    if not cand_links:
        return out

    profile_url = cand_links[0]
    prof_html = fetch_html_fast(profile_url, timeout=10.0)
    if not prof_html:
        return out

    psoup = BeautifulSoup(prof_html, "html.parser")
    if not re.search(rf"\b{re.escape(cui_digits)}\b", psoup.get_text(" ", strip=True)):
        return out

    out["matched"] = True
    out["url"] = profile_url

    admins: list[str] = []
    raw_phones: list[str] = []
    webs: list[str] = []
    for dl in psoup.find_all("dl"):
        # Walk <dt>/<dd> children pairs inside Bootstrap <dl class="row">
        cur_label = ""
        for child in dl.children:
            name = getattr(child, "name", None)
            if name == "dt":
                cur_label = strip_diacritics(child.get_text(" ", strip=True)).rstrip(":")
            elif name == "dd":
                val = clean_text(child.get_text(" ", strip=True))
                if not val or val == "-":
                    continue
                if cur_label in ("tel", "telefon", "mobil", "fax"):
                    raw_phones.append(val)
                elif cur_label in ("web", "website", "site"):
                    for tok in val.split():
                        w = normalize_website_url(tok)
                        if w and w not in webs:
                            webs.append(w)
                elif cur_label in ("e-mail", "email"):
                    for em in EMAIL_REGEX.findall(val):
                        cem = clean_email(em)
                        if cem:
                            out["emails"].add(cem)
                elif "administrator" in cur_label or "reprezentant" in cur_label or "persoana de contact" in cur_label:
                    if val not in admins:
                        admins.append(val)
                elif "inmatriculare" in cur_label and not out["nrRegCom"]:
                    out["nrRegCom"] = val
                elif cur_label == "activitate" and not out["caen"]:
                    out["caen"] = val

    if webs:
        ro_webs = [w for w in webs if ".ro" in urllib.parse.urlparse(w).netloc.lower()]
        out["website"] = ro_webs[0] if ro_webs else webs[0]

    for chrome in psoup.find_all(["header", "nav", "footer"]):
        chrome.decompose()
    out["emails"] |= extract_emails_from_html(str(psoup))
    out["emails"] = {e for e in out["emails"] if "companywall" not in e}
    out["admin"] = "; ".join(admins[:3])
    out["phones"] = raw_phones
    return out


def parse_paginiaurii_by_cui(cui_digits: str, target_name: str) -> dict:
    """Lookup commercial listing on PaginiAurii.ro (Romania Yellow Pages) by CUI."""
    out = {"matched": False, "url": "", "phones": [], "website": "", "emails": set()}
    if not cui_digits:
        return out

    search_html = fetch_html_fast(f"https://www.paginiaurii.ro/cauta/{cui_digits}/", timeout=10.0)
    if not search_html:
        return out

    soup = BeautifulSoup(search_html, "html.parser")
    pa_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/companii/" in href:
            full = href if href.startswith("http") else ("https://www.paginiaurii.ro" + href)
            if full not in pa_links:
                pa_links.append(full)

    for cand_url in pa_links[:3]:
        dhtml = fetch_html_fast(cand_url, timeout=9.0)
        if not dhtml:
            continue
        dsoup = BeautifulSoup(dhtml, "html.parser")
        for chrome in dsoup.find_all(["header", "nav", "footer"]):
            chrome.decompose()
        dtext = dsoup.get_text(" ", strip=True)
        h1 = dsoup.find("h1")
        cand_title = clean_text(h1.get_text(" ", strip=True) if h1 else (dsoup.title.get_text() if dsoup.title else ""))
        cui_ok = bool(re.search(rf"COD\s+FISCAL\s*:?\s*{re.escape(cui_digits)}\b", dtext, re.I))
        name_ok = is_name_match_ro(target_name, cand_title)
        if not (cui_ok or name_ok):
            continue

        out["matched"] = True
        out["url"] = cand_url
        for a in dsoup.find_all("a", href=True):
            href = a["href"].strip()
            if href.lower().startswith("tel:"):
                out["phones"].append(href[4:].strip())
            elif href.lower().startswith("mailto:"):
                em = clean_email(href)
                if em and "paginiaurii" not in em:
                    out["emails"].add(em)
            elif href.startswith("http") and is_valid_website(href) and not out["website"]:
                out["website"] = normalize_website_url(href)

        out["emails"] |= {e for e in extract_emails_from_html(str(dsoup)) if "paginiaurii" not in e}
        break
    return out


def enrich_single_company(
    idx: int,
    row_dict: dict,
    anaf_map: dict[str, dict],
    skip_paginiaurii: bool = False,
) -> tuple[int, str, dict]:
    """Run all 4 directory layers for one company and return updated cache record."""
    comp = clean_text(row_dict.get("Cong_Ty", ""))
    cui_raw = clean_text(row_dict.get("Ma_Dinh_Danh_CUI", ""))
    cui_digits = re.sub(r"\D", "", cui_raw)
    existing_phone = clean_text(row_dict.get("SDT", ""))
    existing_addr = clean_text(row_dict.get("Dia_Chi_Tru_So", ""))

    # Layer 1: ANAF official data
    anaf = anaf_map.get(cui_digits, {})
    legal_name = anaf.get("denumire") or comp
    raw_phones: list[str] = []
    if existing_phone:
        raw_phones.append(existing_phone)
    if anaf.get("telefon"):
        raw_phones.append(anaf["telefon"])

    # Layer 2: CompanyWall.ro
    cw = parse_companywall_by_cui(cui_digits, comp)
    if cw["phones"]:
        raw_phones.extend(cw["phones"])

    website = cw["website"]
    emails = set(cw["emails"])
    email_source = "CompanyWall" if select_best_email(emails, website) else ""
    dir_sources = []
    if anaf:
        dir_sources.append("ANAF")
    if cw["matched"]:
        dir_sources.append("CompanyWall")

    # Layer 3: PaginiAurii.ro (only skip if skipped by flag)
    pa = {"matched": False, "url": "", "phones": [], "website": "", "emails": set()}
    if not skip_paginiaurii and cui_digits and (not website or not emails or not raw_phones):
        pa = parse_paginiaurii_by_cui(cui_digits, comp)
        if pa["matched"]:
            dir_sources.append("PaginiAurii")
        if pa["phones"]:
            raw_phones.extend(pa["phones"])
        if not website and pa["website"]:
            website = pa["website"]
        if pa["emails"]:
            emails |= pa["emails"]
            if not email_source and select_best_email(pa["emails"], website):
                email_source = "PaginiAurii"

    best_email = select_best_email(emails, website)
    fb_url = ""

    # Layer 4: Deep Website + Facebook Email Crawl whenever a Directory revealed a Website
    if not best_email and website:
        w_email, w_src, w_fb = crawl_website_for_email_ro(website)
        if w_email:
            best_email = w_email
            email_source = w_src
        if w_fb:
            fb_url = w_fb

    p1, p_all = normalize_ro_phones(raw_phones)
    city = anaf.get("localitate") or ""
    county = anaf.get("judet") or clean_text(row_dict.get("ITM_Tinh", ""))
    addr = anaf.get("adresa") or existing_addr

    rec = {
        "done": True,
        "CUI": cui_digits,
        "Legal_Name_ANAF": legal_name,
        "Administrator": cw.get("admin", ""),
        "SDT": p1 or ensure_phone_quote(existing_phone),
        "Tat_Ca_SDT": p_all or ensure_phone_quote(existing_phone),
        "Website": website,
        "Email": clean_email(best_email),
        "Email_Source": email_source if best_email else "",
        "Facebook_URL": fb_url,
        "CAEN": anaf.get("cod_CAEN") or cw.get("caen", ""),
        "Nr_Reg_Com": anaf.get("nrRegCom") or cw.get("nrRegCom", ""),
        "Trang_Thai_ANAF": anaf.get("stare_inregistrare", ""),
        "City": city,
        "Judet": county,
        "Dia_Chi": addr,
        "CompanyWall_URL": cw.get("url", ""),
        "PaginiAurii_URL": pa.get("url", ""),
        "Dir_Source": " | ".join(dir_sources),
    }
    cache_key = f"CUI:{cui_digits}" if cui_digits else f"NAME:{strip_diacritics(comp)}"
    return idx, cache_key, rec


def load_cache() -> dict:
    """Load resume checkpoint JSON if available."""
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}


def save_cache(cache: dict) -> None:
    """Write checkpoint JSON atomically."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_FILE.with_suffix(".tmp")
    with CACHE_LOCK:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CACHE_FILE)


def export_all_csvs(df: pd.DataFrame) -> int:
    """Export 1ENR, 2COL (email-first), ONLY_EMAILS_READY, and sync ro_romania/."""
    df_out = df.copy()
    df_out = df_out[~df_out["Cong_Ty"].apply(is_blacklisted_company)].reset_index(drop=True)
    df_out["SDT"] = df_out["SDT"].apply(ensure_phone_quote)
    df_out["Email"] = df_out["Email"].apply(clean_email)

    has_em = df_out[df_out["Email"] != ""].copy()
    no_em = df_out[df_out["Email"] == ""].copy()
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted["No."] = range(1, len(df_sorted) + 1)
    df_sorted.to_csv(OUTPUT_1ENR_PATH, index=False, encoding="utf-8-sig")

    coldmail_rows = []
    for _, r in df_sorted.iterrows():
        comp = clean_text(r.get("Cong_Ty", ""))
        admin = clean_text(r.get("Nguoi_Lien_He_Admin", ""))
        chuc_danh = "Administrator / Director" if admin else "Director / Recruitment Manager"
        phone = ensure_phone_quote(r.get("SDT", ""))
        web = clean_text(r.get("Website", ""))
        dir_link = web or clean_text(r.get("CompanyWall_URL", "")) or clean_text(r.get("PaginiAurii_URL", ""))
        email = clean_email(r.get("Email", ""))
        addr = clean_text(r.get("Dia_Chi", ""))
        judet = clean_text(r.get("Judet", ""))
        if not addr and judet:
            addr = f"{judet}, Romania"
        elif addr and "romania" not in addr.lower() and "românia" not in addr.lower():
            addr = f"{addr}, Romania"

        cat_parts = ["Licensed Recruitment Agency (Romania)"]
        if clean_text(r.get("CAEN", "")):
            cat_parts.append(f"CAEN {clean_text(r.get('CAEN', ''))}")
        if clean_text(r.get("Trang_Thai_AMT", "")):
            cat_parts.append(f"AMT: {clean_text(r.get('Trang_Thai_AMT', ''))}")
        if clean_text(r.get("Trang_Thai_ANAF", "")):
            cat_parts.append(f"ANAF: {clean_text(r.get('Trang_Thai_ANAF', ''))}")

        coldmail_rows.append(
            {
                "No.": r.get("No.", ""),
                "Công ty": comp,
                "Chức danh": chuc_danh,
                "Người liên hệ": admin,
                "SĐT": phone,
                "Liên Hệ": dir_link,
                "Email": email,
                "Liên Hệ mail": f"mailto:{email}" if email else dir_link,
                "Địa chỉ": addr or "Romania",
                "Lương": f"CUI: {clean_text(r.get('Ma_Dinh_Danh_CUI', ''))}" if clean_text(r.get("Ma_Dinh_Danh_CUI", "")) else "",
                "Ngày đăng": clean_text(r.get("Nr_Reg_Com", "")),
                "Hạn tuyển": "",
                "Check gửi": "Chưa gửi",
                "Last Subject": "",
                "Last Body HTML": "",
                "Trạng thái Reply": "",
                "Lần Follow-up": "",
                "Ngày Follow-up gần nhất": "",
                "Mailbox đã dùng": "",
                "Category": " | ".join(cat_parts),
            }
        )

    df_2col = pd.DataFrame(coldmail_rows, columns=COLDMAIL_COLUMNS)
    df_2col.to_csv(OUTPUT_2COL_PATH, index=False, encoding="utf-8-sig")

    df_ready = df_2col[df_2col["Email"] != ""].copy()
    df_ready["No."] = range(1, len(df_ready) + 1)
    df_ready.to_csv(OUTPUT_READY_PATH, index=False, encoding="utf-8-sig")

    RO_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OUTPUT_1ENR_PATH, RO_DIR / OUTPUT_1ENR_PATH.name)
    shutil.copy2(OUTPUT_2COL_PATH, RO_DIR / OUTPUT_2COL_PATH.name)
    return len(df_ready)


def apply_record_to_row(df: pd.DataFrame, idx: int, rec: dict) -> None:
    """Mutate a single DataFrame row in-place from an enrichment checkpoint record."""
    if not rec:
        return
    if rec.get("Administrator"):
        df.at[idx, "Nguoi_Lien_He_Admin"] = clean_text(rec["Administrator"])
    if rec.get("SDT"):
        df.at[idx, "SDT"] = ensure_phone_quote(rec["SDT"])
    if rec.get("Tat_Ca_SDT"):
        df.at[idx, "Tat_Ca_SDT"] = rec["Tat_Ca_SDT"]
    if rec.get("Website"):
        df.at[idx, "Website"] = clean_text(rec["Website"])
    if rec.get("Email"):
        df.at[idx, "Email"] = clean_email(rec["Email"])
    if rec.get("Email_Source"):
        df.at[idx, "Email_Source"] = clean_text(rec["Email_Source"])
    if rec.get("Facebook_URL"):
        df.at[idx, "Facebook_URL"] = clean_text(rec["Facebook_URL"])
    for col_df, col_rec in (
        ("CAEN", "CAEN"),
        ("Nr_Reg_Com", "Nr_Reg_Com"),
        ("Trang_Thai_ANAF", "Trang_Thai_ANAF"),
        ("City", "City"),
        ("Judet", "Judet"),
        ("Dia_Chi", "Dia_Chi"),
        ("CompanyWall_URL", "CompanyWall_URL"),
        ("PaginiAurii_URL", "PaginiAurii_URL"),
        ("Dir_Source", "Dir_Source"),
    ):
        val = clean_text(rec.get(col_rec, ""))
        if val:
            df.at[idx, col_df] = val


def apply_cache_to_df(df: pd.DataFrame, cache: dict) -> None:
    """Apply already-fetched checkpoint records onto DataFrame."""
    for idx, row in df.iterrows():
        cui_digits = re.sub(r"\D", "", clean_text(row.get("Ma_Dinh_Danh_CUI", "")))
        comp = clean_text(row.get("Cong_Ty", ""))
        key = f"CUI:{cui_digits}" if cui_digits else f"NAME:{strip_diacritics(comp)}"
        rec = cache.get(key)
        if rec:
            apply_record_to_row(df, idx, rec)


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich RO_AGCY companies from Romanian public directories (ANAF + CompanyWall + PaginiAurii)")
    parser.add_argument("--limit", type=int, default=0, help="Only process first N uncached companies")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent HTTP workers (default: 4)")
    parser.add_argument("--skip-anaf", action="store_true", help="Skip ANAF API v9 batch call")
    parser.add_argument("--skip-paginiaurii", action="store_true", help="Skip PaginiAurii Yellow Pages lookup")
    parser.add_argument("--force-retry", action="store_true", help="Ignore existing cache and re-scrape all")
    parser.add_argument("--refresh-websites", action="store_true", help="Scrub junk webmail/GDPR traps and re-crawl cached websites lacking clean emails")
    parser.add_argument("--re-export", action="store_true", help="Only regenerate CSVs from existing cache")
    args = parser.parse_args()

    if not INPUT_CSV_PATH.exists():
        print(f"[ERROR] Input CSV not found: {INPUT_CSV_PATH}")
        sys.exit(1)

    df = pd.read_csv(INPUT_CSV_PATH, encoding="utf-8-sig", dtype=str).fillna("")
    df = df[~df["Cong_Ty"].apply(is_blacklisted_company)].reset_index(drop=True)

    for extra_col in (
        "Nguoi_Lien_He_Admin", "Tat_Ca_SDT", "Website", "Email", "Email_Source",
        "Facebook_URL", "CAEN", "Nr_Reg_Com", "Trang_Thai_ANAF", "City",
        "Judet", "Dia_Chi", "CompanyWall_URL", "PaginiAurii_URL", "Dir_Source",
    ):
        if extra_col not in df.columns:
            df[extra_col] = ""
    df["Dia_Chi"] = df["Dia_Chi_Tru_So"]
    df["Judet"] = df["ITM_Tinh"]
    df["SDT"] = df["SDT"].apply(ensure_phone_quote)

    cache = {} if args.force_retry else load_cache()
    if args.refresh_websites and cache:
        scrubbed = 0
        for k, rec in cache.items():
            w = rec.get("Website", "")
            e = rec.get("Email", "")
            if w and not is_valid_website(w):
                rec["Website"] = ""
                scrubbed += 1
            if e and score_email_b2b_ro(e, rec.get("Website", "")) <= 0:
                rec["Email"] = ""
                rec["Email_Source"] = ""
                scrubbed += 1
        refresh_targets = [
            (k, rec) for k, rec in cache.items()
            if rec.get("Website") and not rec.get("Email")
        ]
        print(f"[REFRESH] Scrubbed {scrubbed} junk web/GDPR fields; re-crawling {len(refresh_targets)} websites...")
        def _recheck(item):
            k, rec = item
            w_email, w_src, w_fb = crawl_website_for_email_ro(rec["Website"])
            return k, w_email, w_src, w_fb
        new_mails = 0
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
            for k, w_email, w_src, w_fb in ex.map(_recheck, refresh_targets):
                if w_email:
                    cache[k]["Email"] = w_email
                    cache[k]["Email_Source"] = w_src
                    new_mails += 1
                if w_fb and not cache[k].get("Facebook_URL"):
                    cache[k]["Facebook_URL"] = w_fb
        save_cache(cache)
        apply_cache_to_df(df, cache)
        ready = export_all_csvs(df)
        print(f"[REFRESH] Recovered {new_mails} clean emails -> Total ready with Email: {ready}")
        return

    apply_cache_to_df(df, cache)

    if args.re_export:
        ready = export_all_csvs(df)
        print(f"[RE-EXPORT] Exported {len(df)} rows ({ready} with Email)")
        return

    pending_indices = []
    for idx, row in df.iterrows():
        cui_digits = re.sub(r"\D", "", clean_text(row.get("Ma_Dinh_Danh_CUI", "")))
        comp = clean_text(row.get("Cong_Ty", ""))
        key = f"CUI:{cui_digits}" if cui_digits else f"NAME:{strip_diacritics(comp)}"
        if args.force_retry or not cache.get(key, {}).get("done"):
            pending_indices.append(idx)

    if args.limit > 0:
        pending_indices = pending_indices[: args.limit]

    print("=" * 80)
    print("ROMANIAN DIRECTORY ENRICHMENT (ANAF v9 + COMPANYWALL + PAGINIAURII + WEB CRAWL)")
    print(f"  Input CSV   : {INPUT_CSV_PATH.name} ({len(df)} unique agencies)")
    print(f"  Pending     : {len(pending_indices)} companies")
    print(f"  Workers     : {args.workers}")
    print("=" * 80)

    anaf_map: dict[str, dict] = {}
    if pending_indices and not args.skip_anaf:
        pending_cuis = [df.at[i, "Ma_Dinh_Danh_CUI"] for i in pending_indices]
        print("[1/2] Querying official ANAF REST API v9 in batches of 100 CUIs...")
        anaf_map = fetch_anaf_batch(pending_cuis)
        print(f"  -> ANAF returned {len(anaf_map)} official company records.")

    print("[2/2] Crawling CompanyWall.ro + PaginiAurii.ro + Websites...")
    done_cnt = 0
    found_admin = 0
    found_web = 0
    found_email = 0
    new_phones = 0

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futures = {
            ex.submit(
                enrich_single_company,
                idx,
                df.loc[idx].to_dict(),
                anaf_map,
                args.skip_paginiaurii,
            ): idx
            for idx in pending_indices
        }
        for fut in as_completed(futures):
            try:
                idx, key, rec = fut.result()
                old_phone = ensure_phone_quote(df.at[idx, "SDT"])
                with CACHE_LOCK:
                    cache[key] = rec
                apply_record_to_row(df, idx, rec)
                done_cnt += 1
                if rec["Administrator"]:
                    found_admin += 1
                if rec["Website"]:
                    found_web += 1
                if rec["Email"]:
                    found_email += 1
                if rec["SDT"] and not old_phone:
                    new_phones += 1

                if done_cnt % 20 == 0 or rec["Email"] or rec["Website"]:
                    print(
                        f"  [{done_cnt}/{len(pending_indices)}] {df.at[idx, 'Cong_Ty'][:34]:34s} | "
                        f"CUI={rec['CUI'] or '-':9s} | Admin={'Y' if rec['Administrator'] else '-'} | "
                        f"Phone={rec['SDT'] or '-':12s} | Web={rec['Website'] or '-'} | Mail={rec['Email'] or '-'}"
                    )
                if done_cnt % 20 == 0:
                    save_cache(cache)
                    export_all_csvs(df)
            except Exception as e:
                print(f"  [ERR] Worker failure: {e}")

    save_cache(cache)
    ready_count = export_all_csvs(df)
    print("\n" + "=" * 80)
    print("DIRECTORY ENRICHMENT SUMMARY:")
    print(f"  Total Agencies   : {len(df)}")
    print(f"  Admins Found     : {(df['Nguoi_Lien_He_Admin'] != '').sum()}")
    print(f"  Total Phones     : {(df['SDT'] != '').sum()} (+{new_phones} new this run)")
    print(f"  Websites Found   : {(df['Website'] != '').sum()} (+{found_web} this run)")
    print(f"  B2B Emails Found : {ready_count} (+{found_email} this run)")
    print(f"  Master Output    : {OUTPUT_1ENR_PATH.name}")
    print(f"  Cold Mail Output : {OUTPUT_2COL_PATH.name}")
    print("=" * 80)


if __name__ == "__main__":
    main()
