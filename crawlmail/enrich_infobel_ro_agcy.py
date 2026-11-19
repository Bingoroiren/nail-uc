#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
Module: enrich_infobel_ro_agcy.py
Description: Data Enrichment for Romanian Recruitment Agencies using Infobel Romania
Target URL : https://local.infobel.ro/
Rules      : Adheres strictly to GEMINI.md (headless=False, UTF-8 BOM CSV,
             SĐT with leading single quote, B2B email scoring, captcha manual prompt,
             incremental checkpoints, and sorting email rows to top).
===============================================================================
"""

import sys
import os
import re
import json
import time
import shutil
import html as html_lib
import urllib.parse
from pathlib import Path
import unicodedata
import requests
import urllib3
from bs4 import BeautifulSoup
import pandas as pd
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =============================================================================
# PATHS & CONFIGURATION
# =============================================================================
ROOT_DIR = Path(__file__).resolve().parent.parent
TARGET_2COL_PATH = ROOT_DIR / "RO_AGCY_GMAP_2COL.csv"
TARGET_READY_PATH = ROOT_DIR / "RO_AGCY_GMAP_ONLY_EMAILS_READY.csv"
BACKUP_2COL_PATH = ROOT_DIR / "archive" / "ro_romania" / "RO_AGCY_GMAP_2COL_pre_infobel_backup.csv"
CACHE_ENRICH_PATH = ROOT_DIR / "crawlmail" / "cache_infobel_enrich.json"
PROFILE_DIR = ROOT_DIR / "chrome_user_data" / "infobel_profile"
CSDL_DIR = ROOT_DIR / "csdl_mlt"
ARCHIVE_DIR = ROOT_DIR / "archive" / "ro_romania"

BASE_URL = "https://local.infobel.ro"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
}

# =============================================================================
# BLACKLISTS & REGEX
# =============================================================================
PERMANENT_BLACKLIST_COMPANIES = [
    "scandi standard", "scandi-standard", "scandi standart",
    "biliarta",
    "daigre", "daigrė",
]

BLACKLIST_DOMAINS = {
    "facebook.com", "fb.com", "instagram.com", "linkedin.com", "youtube.com",
    "twitter.com", "x.com", "tiktok.com", "pinterest.com", "google.com", "google.ro",
    "maps.google.com", "goo.gl", "wikipedia.org", "yellowpages", "tripadvisor",
    "booking.com", "yelp.com", "sentry.io", "wix.com", "wixpress.com",
    "paginiaurii.ro", "termene.ro", "listafirme.ro", "topfirme.ro",
    "risco.ro", "totalfirme.ro", "romanian-companies.eu", "infobel.com", "infobel.ro",
    "infobelpro.com", "cyberfolks.ro", "goldenpages.ie", "goudengids.be", "fcrmedia.ro",
    "fcrmedia.com", "rentasite.ro", "rentavideo.ro", "rentawidget.ro", "anofm.ro",
    "brat.ro", "sinda.com", "companywall.ro",
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


# =============================================================================
# NORMALIZATION & CLEANING FUNCTIONS
# =============================================================================

def clean_text(val) -> str:
    """Normalize non-breaking / zero-width spaces and collapse whitespace."""
    if val is None:
        return ""
    s = str(val)
    if s.strip().lower() == "nan":
        return ""
    for bad in ("\u00a0", "\xa0", "\u200b", "\u200e", "\u200f", "\ufeff", "\u202f", "\u3000"):
        s = s.replace(bad, " ")
    return re.sub(r"\s+", " ", s).strip()


def is_blacklisted_company(name: str) -> bool:
    """Rule 12: Check if company belongs to permanent blacklist."""
    if not name:
        return False
    n = unicodedata.normalize("NFKD", str(name)).lower()
    n_clean = "".join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)


def clean_phone_ro(raw_phone: str) -> str:
    """Rule 2: Normalize Romanian phone numbers with leading apostrophe for CSV integrity."""
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

        if d.startswith("7") and len(d) == 9:  # Mobile
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
    """Rule 3: Strip %20, \u00a0, stuck tail artifacts, and normalize email."""
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
    """Check if URL is a genuine company website while filtering directories."""
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
    """Rule 3: Score B2B recruitment value of email for Romanian Manpower Agencies."""
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

    # Priority 1: Recruitment / HR
    if any(k in u for k in ("recrutare", "cariere", "hr", "jobs", "munca", "angajari", "personal", "plasare")):
        score += 55
    # Priority 2: Executive leadership
    elif any(k in u for k in ("director", "manager", "ceo", "administrator", "general", "conducere")):
        score += 45
    # Priority 3: Official business contact
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
    """Select the single highest-scoring valid B2B email."""
    valid = [clean_email(e) for e in emails if e]
    valid = [e for e in set(valid) if e and score_email_b2b_ro(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b_ro(e, domain))


def crawl_website_for_email(site_url: str) -> str:
    """Fallback crawler: Search company website and contact subpages for recruitment emails."""
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
        r = requests.get(u_str, headers=HEADERS, timeout=5.0, verify=False)
        if r.status_code == 200:
            for em in EMAIL_REGEX.findall(r.text):
                found_emails.add(clean_email(em))
            best = select_best_email(found_emails, domain)
            if best and score_email_b2b_ro(best, domain) >= 90:
                return best
    except Exception:
        pass

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


def clean_name_for_infobel(company_name: str) -> str:
    """Clean legal forms for optimal searching on Infobel."""
    s = re.sub(r"\b(s\.?c\.?|s\.?r\.?l\.?|s\.?a\.?)\b", "", company_name, flags=re.I)
    s = re.sub(r"[\"'\(\)\[\],.;:/-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


RO_DESCRIPTOR_WORDS = {
    "recruitment", "recruiting", "recruiter", "staffing", "human", "resources",
    "resurse", "umane", "personal", "job", "jobs", "work", "workforce",
    "interim", "temporar", "plasare", "munca", "angajari", "consulting",
    "consultanta", "services", "servicii", "solutions", "solutii", "group",
    "romania", "romanian", "international", "management", "outsourcing", "hr",
    "agentia", "agenzia", "agency", "training",
}

RO_CITIES = {
    "bucuresti", "cluj", "iasi", "timisoara", "brasov", "constanta", "craiova",
    "galati", "oradea", "ploiesti", "pitesti", "arad", "sibiu", "bacau",
    "targu mures", "baia mare", "buzau", "botosani", "satu mare", "suceava",
}

RO_LEGAL_FORMS = {
    "sc", "srl", "sa", "pfa", "ii", "snc", "gmbh", "llc", "inc", "ltd", "company", "corp"
}


def clean_ascii(s: str) -> str:
    """Normalize text by stripping accents, lowercasing, and removing punctuation."""
    if not s:
        return ""
    n = unicodedata.normalize("NFKD", str(s)).lower()
    return "".join(c for c in n if not unicodedata.combining(c))


def get_core_tokens(name: str) -> list[str]:
    """Tokenize company name, removing legal forms and standardizing conjunctions."""
    n = clean_ascii(name)
    n = re.sub(r"^\d+\.\s*", "", n)
    n = re.sub(r"[\(\)\[\],.;:/-]", " ", n)
    n = n.replace("&", " and ")
    return [t for t in n.split() if t not in RO_LEGAL_FORMS and len(t) >= 2]


def is_valid_infobel_match(target_name: str, cand_title: str) -> tuple[bool, str]:
    """
    Rule 11 (GEMINI.md) Strict Name Matcher for Romanian Employment Agencies.
    Strictly forbids random fallback to unrelated companies in different fields.
    """
    if not target_name or not cand_title:
        return False, "EMPTY"

    t_core = get_core_tokens(target_name)
    c_core = get_core_tokens(cand_title)
    if not t_core or not c_core:
        return False, "NO_TOKENS"

    set_t = set(t_core)
    set_c = set(c_core)

    # 1. Exact core tokens match
    if set_t == set_c:
        return True, "EXACT_CORE"

    # 2. Candidate brand match (candidate dropped descriptor words e.g. 'resurse umane' or 'recruiting')
    if set_c.issubset(set_t):
        extra = set_t - set_c
        if extra.issubset(RO_DESCRIPTOR_WORDS):
            return True, "BRAND_SUBSET"

    # 3. Target brand match (candidate added descriptor words e.g. 'romania', 'group', or city)
    if set_t.issubset(set_c):
        extra = set_c - set_t
        if extra.issubset(RO_DESCRIPTOR_WORDS | RO_CITIES):
            return True, "BRAND_EXPANSION"
        # Crucial Rule 11 guard: Single-token target MUST NOT match candidate with extra non-descriptor words
        # (e.g. 'ISHTAR' must NEVER match 'Ishtar Internet Group'!)
        if len(set_t) == 1:
            return False, f"REJECT_SINGLE_TOKEN_EXTRA ({extra})"

    # 4. Brand-only tokens comparison (excluding descriptors & cities from both sides)
    t_brand = [t for t in t_core if t not in RO_DESCRIPTOR_WORDS and t not in RO_CITIES]
    c_brand = [t for t in c_core if t not in RO_DESCRIPTOR_WORDS and t not in RO_CITIES]
    if t_brand and c_brand:
        set_tb = set(t_brand)
        set_cb = set(c_brand)
        if set_tb == set_cb:
            return True, "BRAND_CORE_EXACT"
        if set_tb.issubset(set_cb) and len(set_tb) >= 2:
            return True, "BRAND_MULTI_SUBSET"
        if set_cb.issubset(set_tb) and len(set_cb) >= 2:
            return True, "BRAND_MULTI_SUPERSET"
        if "prohuman" in set_tb and "prohuman" in set_cb:
            return True, "PROHUMAN_MATCH"
        if "gigroup" in "".join(t_brand) or ("gi" in set_tb and "gi" in set_cb):
            return True, "GI_GROUP_MATCH"

    return False, "NO_MATCH"


def normalize_ro_name(name: str) -> str:
    """Normalize Romanian company name for strict matching."""
    if not name:
        return ""
    n = unicodedata.normalize("NFKD", str(name)).lower()
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"\b(sc|srl|sa|pfa|ii|snc|gmbh|llc|inc|ltd)\b", "", n)
    n = re.sub(r"[^a-z0-9\s]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


# =============================================================================
# INFOBEL SEARCH & EXTRACTION WITH VISIBLE BROWSER
# =============================================================================

def handle_infobel_challenges(page) -> bool:
    """Check for Captcha / Bot Challenge or Consent on Infobel and handle gracefully."""
    # 1. Dismiss Google CMP consent dialog
    try:
        page.evaluate("document.querySelectorAll('.fc-consent-root, .fc-dialog-container').forEach(el => el.remove())")
    except Exception:
        pass

    try:
        accept_btn = page.locator('button.fc-cta-consent, button:has-text("Accept all"), button:has-text("Consent"), .fc-primary-button').first
        if accept_btn.is_visible(timeout=500):
            accept_btn.click()
    except Exception:
        pass

    # 2. Check for real Captcha / Bot Challenge / Abuse redirect
    url = ""
    try:
        url = page.url.lower()
    except Exception:
        pass

    is_challenged = False
    if "landing/abuse" in url:
        is_challenged = True
    else:
        try:
            content = page.content().lower()
            if "ooops...looks like our computer has identified" in content:
                is_challenged = True
            elif "cf-turnstile-wrapper" in content or "cf-challenge-running" in content:
                is_challenged = True
        except Exception:
            pass

    if is_challenged:
        print("\a" * 3)
        print("\n" + "=" * 80)
        print("  [!] >>> PHÁT HIỆN CAPTCHA XÁC THỰC TRÊN INFOBEL (landing/abuse) <<<")
        print("  [!] Cửa sổ trình duyệt Chrome đang hiển thị trang xác thực reCAPTCHA.")
        print("  [!] VUI LÒNG NHẤN VÀO HỘP KIỂM 'I'M NOT A ROBOT' TRÊN TRÌNH DUYỆT ĐỂ VƯỢT QUA.")
        print("  [!] Hệ thống đang tạm dừng và lắng nghe tự động...")
        print("=" * 80 + "\n")

        # Wait loop until user solves challenge
        for wait_sec in range(1, 76):  # Wait up to 150 seconds
            time.sleep(2)
            try:
                cur_url = page.url.lower()
                cur_content = page.content().lower()
                if "landing/abuse" not in cur_url and "ooops...looks like" not in cur_content:
                    print(f"\n  [+] Xác thực CAPTCHA thành công (sau {wait_sec * 2}s)! Tiếp tục tiến trình cào...\n")
                    time.sleep(1.5)
                    return True
                if wait_sec % 5 == 0:
                    print(f"  [...] Vẫn đang chờ bạn tích CAPTCHA trên trình duyệt ({wait_sec * 2}/150s)...")
            except Exception:
                pass

        print("\n  [!] Hết 150 giây chờ xác thực. Bỏ qua lượt này...")
        return False

    return True


def query_infobel_company(page, company_name: str, city: str = "") -> dict:
    """Search company on local.infobel.ro, extract detail page, website, and phone."""
    search_term = clean_name_for_infobel(company_name)
    if not search_term or len(search_term) < 2:
        return {}

    # Ensure page is on Infobel and search form is available
    on_infobel = False
    try:
        if "infobel.ro" in page.url and page.locator("#search-term-input-header").is_visible(timeout=1000):
            on_infobel = True
    except Exception:
        pass

    if not on_infobel:
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)
        time.sleep(1)

    handle_infobel_challenges(page)

    inp = page.locator('#search-term-input-header, input.search-input-field:visible').first
    if not inp.is_visible(timeout=2000):
        handle_infobel_challenges(page)
        inp = page.locator('#search-term-input-header, input.search-input-field:visible').first

    if not inp.is_visible():
        return {}

    inp.fill(search_term)
    time.sleep(0.3)
    inp.press("Enter")

    try:
        page.wait_for_url("**/Search/BusinessResults*", timeout=7000)
    except Exception:
        pass

    time.sleep(1.5)
    handle_infobel_challenges(page)

    soup = BeautifulSoup(page.content(), "html.parser")
    comp_links = []
    for a in soup.find_all("a", href=True):
        h = a["href"]
        if "/RO10" in h:
            txt = a.get_text(strip=True)
            if txt and "Mai multe" not in txt and h not in [x[0] for x in comp_links]:
                full_h = urllib.parse.urljoin(BASE_URL, h)
                comp_links.append((full_h, txt))

    if not comp_links:
        return {}

    # Strictly evaluate candidates per Rule 11 (DO NOT blindly fallback to comp_links[0])
    best_link = ""
    best_title = ""
    match_reason = ""
    for h, title in comp_links:
        ok, reason = is_valid_infobel_match(company_name, title)
        if ok:
            best_link, best_title, match_reason = h, title, reason
            break

    if not best_link:
        # No strict match found on Infobel -> Reject completely
        return {}

    # Navigate to detail page
    page.goto(best_link, wait_until="domcontentloaded", timeout=15000)
    time.sleep(1.5)
    handle_infobel_challenges(page)

    detail_soup = BeautifulSoup(page.content(), "html.parser")

    # Extract Website
    website = ""
    for a in detail_soup.find_all("a", href=True):
        h = a["href"].strip()
        t = a.get_text(strip=True).lower()
        if any(k in t for k in ("pagina web", "website", "site web")):
            if is_valid_website(h):
                website = h
                break

    if not website:
        for a in detail_soup.find_all("a", href=True):
            h = a["href"].strip()
            if is_valid_website(h) and not any(bad in h.lower() for bad in BLACKLIST_DOMAINS):
                website = h
                break

    # Extract Phone
    phone = ""
    m_ph = re.search(r"/RO10\d+-(\d+)/", best_link)
    if m_ph:
        phone = clean_phone_ro(m_ph.group(1))

    # Extract Email if listed directly on Infobel
    direct_email = ""
    for a in detail_soup.select('a[href^="mailto:"]'):
        em = clean_email(a["href"].replace("mailto:", ""))
        if em and score_email_b2b_ro(em) > 0:
            direct_email = em
            break

    # Fallback crawl website if website discovered
    best_email = direct_email
    if not best_email and website:
        crawl_em = crawl_website_for_email(website)
        if crawl_em:
            best_email = crawl_em

    return {
        "Company_Name": company_name,
        "Infobel_Title": best_title,
        "Infobel_URL": best_link,
        "Website": website,
        "Phone": phone,
        "Email": best_email,
    }


# =============================================================================
# MAIN ENRICHMENT PIPELINE
# =============================================================================

def run_infobel_enrichment(limit: int = 0) -> None:
    """Run data enrichment via Infobel Romania on rows needing email or website."""
    print("=" * 80)
    print("ENRICHMENT: ROMANIAN AGENCIES VIA INFOBEL ROMANIA (local.infobel.ro)")
    print("  Target Dataset : RO_AGCY_GMAP_2COL.csv")
    print("  Browser Mode   : Visible (headless=False, 1280x800) per Rule 4")
    print("  Captcha Prompt : Interactive chime alert (\a) for manual resolution")
    print("========================================================================")

    if not TARGET_2COL_PATH.exists():
        print(f"[ERROR] Target file not found: {TARGET_2COL_PATH}")
        return

    # Safety Backup
    if not BACKUP_2COL_PATH.exists():
        BACKUP_2COL_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(TARGET_2COL_PATH, BACKUP_2COL_PATH)
        print(f"[+] Safety backup created at: {BACKUP_2COL_PATH.relative_to(ROOT_DIR)}")

    df = pd.read_csv(TARGET_2COL_PATH, encoding="utf-8-sig", dtype=str).fillna("")
    print(f"[*] Total rows in dataset: {len(df):,}")
    initial_emails = (df["Email"] != "").sum()
    print(f"[*] Initial rows with Email: {initial_emails:,} ({initial_emails * 100 / len(df):.1f}%)")

    # Load cache
    cache = {}
    if CACHE_ENRICH_PATH.exists():
        try:
            with open(CACHE_ENRICH_PATH, "r", encoding="utf-8") as f:
                cache = json.load(f)
            print(f"[*] Loaded {len(cache):,} cached enrichments from {CACHE_ENRICH_PATH.name}")
        except Exception:
            pass

    # Find rows to enrich (Email is empty or Website is empty)
    to_enrich_indices = []
    for idx, row in df.iterrows():
        c_name = row.get("Công ty", "").strip()
        c_email = clean_email(row.get("Email", ""))
        c_web = str(row.get("Liên Hệ", "")).strip()

        if is_blacklisted_company(c_name):
            continue

        if not c_email or not c_web or not c_web.startswith("http"):
            to_enrich_indices.append(idx)

    print(f"[*] Candidate rows needing enrichment: {len(to_enrich_indices):,}")
    if limit > 0:
        to_enrich_indices = to_enrich_indices[:limit]
        print(f"[*] Limited to first {limit:,} candidates for this run.")

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    enriched_emails_count = 0
    enriched_websites_count = 0
    enriched_phones_count = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        # Rule 4: Immediately load the Infobel portal so the browser is active and responsive (NOT about:blank)
        print("[*] Loading Infobel Romania portal (https://local.infobel.ro/)...")
        try:
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=20000)
            handle_infobel_challenges(page)
            print("[+] Infobel portal ready.")
        except Exception as init_err:
            print(f"[!] Initial load notice: {init_err}")

        for step, idx in enumerate(to_enrich_indices, start=1):
            comp_name = df.at[idx, "Công ty"].strip()
            city = df.at[idx, "Địa chỉ"][:30]

            # Check cache
            is_cached = comp_name in cache
            if is_cached:
                res = cache[comp_name]
            else:
                try:
                    res = query_infobel_company(page, comp_name, city)
                    cache[comp_name] = res
                except Exception as err:
                    print(f"  [{step}/{len(to_enrich_indices)}] Error querying '{comp_name}': {err}")
                    res = {}

                # Save cache periodically
                if step % 5 == 0:
                    with open(CACHE_ENRICH_PATH, "w", encoding="utf-8") as f:
                        json.dump(cache, f, ensure_ascii=False, indent=2)

            if res:
                res_email = clean_email(res.get("Email", ""))
                res_web = res.get("Website", "")
                res_phone = clean_phone_ro(res.get("Phone", ""))

                updated = False
                if not clean_email(df.at[idx, "Email"]) and res_email:
                    df.at[idx, "Email"] = res_email
                    df.at[idx, "Liên Hệ mail"] = f"mailto:{res_email}"
                    enriched_emails_count += 1
                    updated = True

                if (not df.at[idx, "Liên Hệ"] or not str(df.at[idx, "Liên Hệ"]).startswith("http")) and res_web:
                    df.at[idx, "Liên Hệ"] = res_web
                    enriched_websites_count += 1
                    updated = True

                if not clean_phone_ro(df.at[idx, "SĐT"]) and res_phone:
                    df.at[idx, "SĐT"] = res_phone
                    enriched_phones_count += 1
                    updated = True

                if updated:
                    tag = "[CACHED+]" if is_cached else "[+]"
                    print(f"  [{step:3d}/{len(to_enrich_indices)}] {tag} {comp_name} -> Email: {res_email or 'N/A'} | Web: {res_web or 'N/A'}")
                else:
                    if not is_cached:
                        print(f"  [{step:3d}/{len(to_enrich_indices)}] [~] {comp_name} -> Infobel found, no new contacts")
            else:
                if not is_cached:
                    print(f"  [{step:3d}/{len(to_enrich_indices)}] [-] {comp_name} -> Not found on Infobel")

            # Checkpoint save to CSV every 10 companies
            if step % 10 == 0:
                save_and_sort_dataset(df)

            # Only pause between live network requests, bypass pause for cached entries
            if not is_cached:
                time.sleep(1.5)

        context.close()
        browser.close()

    # Final cache save
    with open(CACHE_ENRICH_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    save_and_sort_dataset(df)

    final_emails = (df["Email"] != "").sum()
    print("\n" + "=" * 80)
    print("ENRICHMENT COMPLETED SUCCESSFULLY!")
    print(f"  Initial rows with Email : {initial_emails:,}")
    print(f"  Net new emails enriched : +{enriched_emails_count:,}")
    print(f"  Net new websites added  : +{enriched_websites_count:,}")
    print(f"  Net new phones added    : +{enriched_phones_count:,}")
    print(f"  Final total with Email  : {final_emails:,} ({final_emails * 100 / len(df):.1f}%)")
    print("=" * 80)


def save_and_sort_dataset(df: pd.DataFrame) -> None:
    """Save dataset strictly formatted with 100% of rows with email on top per Rule 3."""
    # Exclude blacklist
    df_clean = df[~df["Công ty"].apply(is_blacklisted_company)].copy()

    # Normalize fields
    df_clean["Công ty"] = df_clean["Công ty"].apply(clean_text)
    df_clean["Email"] = df_clean["Email"].apply(clean_email)
    df_clean["SĐT"] = df_clean["SĐT"].apply(clean_phone_ro)

    for col in df_clean.columns:
        df_clean[col] = df_clean[col].apply(clean_text)

    # Sort 100% email rows on top
    has_email = df_clean[df_clean["Email"] != ""].copy()
    no_email = df_clean[df_clean["Email"] == ""].copy()
    df_sorted = pd.concat([has_email, no_email], ignore_index=True)
    df_sorted["No."] = range(1, len(df_sorted) + 1)

    df_sorted.to_csv(TARGET_2COL_PATH, index=False, encoding="utf-8-sig")

    # Update ONLY_EMAILS_READY
    df_ready = df_sorted[df_sorted["Email"] != ""].copy()
    df_ready["No."] = range(1, len(df_ready) + 1)
    df_ready.to_csv(TARGET_READY_PATH, index=False, encoding="utf-8-sig")

    # Sync to csdl_mlt and archive
    for extra_dir in (CSDL_DIR, ARCHIVE_DIR):
        extra_dir.mkdir(parents=True, exist_ok=True)
        for p in (TARGET_2COL_PATH, TARGET_READY_PATH):
            try:
                shutil.copy2(p, extra_dir / p.name)
            except Exception:
                pass


if __name__ == "__main__":
    limit_arg = 0
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        limit_arg = int(sys.argv[1])
    run_infobel_enrichment(limit=limit_arg)
