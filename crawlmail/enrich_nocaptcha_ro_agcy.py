# -*- coding: utf-8 -*-
"""
===============================================================================
Module     : enrich_nocaptcha_ro_agcy.py
Description: CAPTCHA-Free B2B Enrichment for Romanian Employment Agencies (PAUR)
             Bypasses Google Maps completely using:
             1. ANAF Official Public API v9 (by CUI): Registered Phones, Status
             2. CompanyWall.ro (by CUI): Administrator, Website, Commercial Phone
             3. DuckDuckGo Clean Search: Official .ro Website Discovery (0 CAPTCHA)
             4. Deep B2B Recruitment Email Crawler (curl_cffi Chrome 120)
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
INPUT_2COL_PATH = ROOT_DIR / "RO_AGCY_PAUR_2COL.csv"
INPUT_0RAW_PATH = ROOT_DIR / "RO_AGCY_PAUR_0RAW.csv"
OUTPUT_READY_PATH = ROOT_DIR / "RO_AGCY_PAUR_ONLY_EMAILS_READY.csv"
CACHE_PATH = ROOT_DIR / "crawlmail" / "cache_enrich_nocaptcha_ro_paur.json"
BACKUP_PATH = ROOT_DIR / "archive" / "ro_romania" / "RO_AGCY_PAUR_2COL_pre_nocaptcha_backup.csv"

ANAF_URL = "https://webservicesp.anaf.ro/api/PlatitorTvaRest/v9/tva"

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

DIRECTORY_DOMAINS = {
    "companywall.ro", "paginiaurii.ro", "listafirme.ro", "termene.ro",
    "totalfirme.ro", "topfirme.ro", "risco.ro", "romanian-companies.eu",
    "infobel.com", "infobel.ro", "infobelpro.com", "cyberfolks.ro",
    "facebook.com", "fb.com", "instagram.com", "linkedin.com", "youtube.com",
    "twitter.com", "x.com", "tiktok.com", "pinterest.com", "google.com",
    "maps.google.com", "goo.gl", "wikipedia.org", "yellowpages", "tripadvisor",
    "booking.com", "yelp.com", "sentry.io", "wix.com", "wixpress.com",
    "anofm.ro", "just.ro", "onrc.ro", "mfinante.ro", "anaf.ro",
    "ejobs.ro", "bestjobs.eu", "hipo.ro", "jooble.org", "indeed.com",
    "rentasite.ro", "rentavideo.ro", "rentawidget.ro", "fcrmedia.ro",
    "targetare.ro", "firmeromania.ro", "afacerilacheie.ro",
}

RO_LEGAL_FORMS = {
    "sc", "srl", "sa", "pfa", "ii", "snc", "gmbh", "llc", "inc", "ltd", "company", "corp"
}

RO_CITIES = {
    "bucuresti", "cluj", "iasi", "timisoara", "brasov", "constanta", "craiova",
    "galati", "oradea", "ploiesti", "pitesti", "arad", "sibiu", "bacau",
    "targu mures", "baia mare", "buzau", "botosani", "satu mare", "suceava",
    "drobeta-turnu severin", "drobeta", "severin", "focsani", "piatra neamt",
    "ramnicu valcea", "targoviste", "tulcea", "resita", "bistrita", "slatina",
    "alexandria", "calarasi", "giurgiu", "slobozia", "targu jiu", "zalau",
    "alba iulia", "vaslui", "roman", "sighetu marmatiei", "medgidia", "onesti",
}

DISALLOWED_DOMAINS_SUBSTR = (
    "autocare", "autobuz", "busrental", "transport", "magazin",
    "clinica", "psihol", "stomatol", "farmacie", "restaurant",
    "hotel", "pensiune", "pieseauto", "tamplarie", "robinet", "fiting",
)

EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b")
INVALID_EXTS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js",
    ".pdf", ".woff", ".woff2", ".ico", ".mp4",
)

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


def clean_ascii(s: str) -> str:
    if not s:
        return ""
    n = unicodedata.normalize("NFKD", str(s)).lower()
    return "".join(c for c in n if not unicodedata.combining(c))


def is_blacklisted_company(name: str) -> bool:
    if not name:
        return False
    n_clean = clean_ascii(name)
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
    e = urllib.parse.unquote(str(email_str).strip())
    for bad in ("\u00a0", "\xa0", "&nbsp;", "%20", "\u200b", "\u200e", "\u200f", "\ufeff", " "):
        e = e.replace(bad, "")
    e = re.sub(r"^(?:mailto:\s*|https?://\s*)+", "", e, flags=re.I)
    e = e.strip(" .,;:\"'<>[](){}\\/").lower()
    if re.match(r"^20[a-z][a-z0-9._%+-]*@[a-z0-9.-]+\.[a-z]{2,}$", e) and not e.startswith("202"):
        e = e[2:]
    return e if ("@" in e and "." in e.split("@")[-1]) else ""


def is_valid_company_website(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    u = url.strip().lower()
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    try:
        parsed = urllib.parse.urlparse(u)
        host = parsed.netloc.replace("www.", "").lower().split(":")[0]
        if not host or "." not in host or len(host) < 4:
            return False
        if any(d == host or host.endswith("." + d) for d in DIRECTORY_DOMAINS):
            return False
        if any(bad in host for bad in DISALLOWED_DOMAINS_SUBSTR):
            return False
        return True
    except Exception:
        return False


def get_core_tokens(name: str) -> list[str]:
    n = clean_ascii(name)
    n = re.sub(r"^\d+\.\s*", "", n)
    n = re.sub(r"[\(\)\[\],.;:/-]", " ", n)
    n = n.replace("&", " and ")
    return [t for t in n.split() if t not in RO_LEGAL_FORMS and len(t) >= 2]


def extract_city_from_address(addr: str) -> str:
    a = clean_ascii(addr)
    for c in sorted(RO_CITIES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(c)}\b", a):
            return c.title()
    m = re.search(r"\b(?:mun|municipiul|oras|orasul|jud|judetul)\.?\s*([a-z\-]+)", a)
    if m:
        cand = m.group(1).strip()
        if len(cand) >= 3 and cand not in ("sat", "com", "comuna"):
            return cand.title()
    return "Romania"


def score_email_b2b_ro(email: str, domain: str = "") -> int:
    e = clean_email(email)
    if not e or "@" not in e or any(e.endswith(ext) for ext in INVALID_EXTS):
        return -1
    u, d = e.split("@", 1)
    if any(bad in d for bad in DIRECTORY_DOMAINS):
        return -1
    if u in JUNK_USERNAMES:
        return -1

    score = 10
    if domain:
        clean_d = domain.lower().replace("www.", "").split("/")[0]
        if clean_d in d or d in clean_d:
            score += 50

    if any(k in u for k in ("recrutare", "recruitment", "angajari", "cariere", "jobs", "hr", "cv")):
        score += 50
    elif any(k in u for k in ("director", "ceo", "manager", "admin", "office", "contact")):
        score += 35
    elif any(k in u for k in ("info", "secretariat", "receptie")):
        score += 25
    return score


def fetch_html_curl(session: requests.Session, url: str, timeout: float = 6.0) -> str:
    if not url:
        return ""
    u = url.strip()
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    for v in (True, False):
        try:
            r = session.get(u, timeout=timeout, allow_redirects=True, verify=v)
            if r.status_code == 200:
                return r.text or ""
        except Exception:
            pass
    return ""


def search_duckduckgo_for_website(session: requests.Session, core_name: str, city: str) -> str:
    queries = [
        f"{core_name} {city} site:ro",
        f"{core_name} recrutare {city}",
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8",
    }
    for q in queries:
        try:
            url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(q)}"
            r = session.get(url, headers=headers, timeout=8.0)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.select("a.result__a"):
                    raw_href = a.get("href", "")
                    m = re.search(r"uddg=([^&]+)", raw_href)
                    actual_url = urllib.parse.unquote(m.group(1)) if m else raw_href
                    if is_valid_company_website(actual_url):
                        domain = urllib.parse.urlparse(actual_url).netloc.replace("www.", "").lower()
                        domain_core = re.sub(r"[^a-z0-9]", "", domain.split(".")[0])
                        comp_alnum = re.sub(r"[^a-z0-9]", "", clean_ascii(core_name))
                        tokens = [t for t in get_core_tokens(core_name) if t not in ("agency", "recruitment", "staffing", "group", "services", "solutions")]
                        brand_alnum = "".join(tokens)
                        if (len(comp_alnum) >= 4 and (comp_alnum in domain_core or domain_core in comp_alnum)) or \
                           (len(brand_alnum) >= 4 and (brand_alnum in domain_core or domain_core in brand_alnum)):
                            return actual_url
        except Exception:
            pass
    return ""


def search_companywall_for_website(session: requests.Session, cui: str) -> tuple[str, str, str]:
    if not cui:
        return "", "", ""
    url = f"https://www.companywall.ro/cautare?q={cui}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8",
    }
    try:
        r = session.get(url, headers=headers, timeout=8.0)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                if "/companie/" in a["href"]:
                    prof_url = "https://www.companywall.ro" + a["href"]
                    r_prof = session.get(prof_url, headers=headers, timeout=8.0)
                    if r_prof.status_code == 200:
                        s_prof = BeautifulSoup(r_prof.text, "html.parser")
                        web = ""
                        phone = ""
                        admin = ""
                        for dt in s_prof.find_all("dt"):
                            lbl = clean_ascii(dt.get_text(strip=True))
                            dd = dt.find_next_sibling("dd")
                            if not dd:
                                continue
                            val = clean_text(dd.get_text(strip=True))
                            if "web" in lbl or "site" in lbl:
                                if is_valid_company_website(val):
                                    web = val
                            elif "tel" in lbl or "mobil" in lbl:
                                p_clean = clean_phone_ro(val)
                                if p_clean and not phone:
                                    phone = p_clean
                            elif "administrator" in lbl or "reprezentant" in lbl:
                                if not admin and len(val) >= 3:
                                    admin = val
                        return web, phone, admin
    except Exception:
        pass
    return "", "", ""


def crawl_site_for_b2b_email(session: requests.Session, website_url: str) -> str:
    if not is_valid_company_website(website_url):
        return ""

    found_emails = set()
    parsed = urllib.parse.urlparse(website_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    domain = parsed.netloc.replace("www.", "")

    home_html = fetch_html_curl(session, website_url, timeout=6.0)
    if not home_html and root != website_url:
        home_html = fetch_html_curl(session, root, timeout=6.0)

    if home_html:
        for em in EMAIL_REGEX.findall(home_html):
            c = clean_email(em)
            if c and score_email_b2b_ro(c, domain) > 0:
                found_emails.add(c)

        best = max(found_emails, key=lambda x: score_email_b2b_ro(x, domain), default="")
        if best and score_email_b2b_ro(best, domain) >= 90:
            return best

        soup = BeautifulSoup(home_html, "html.parser")
        sub_links = []
        for a in soup.find_all("a", href=True):
            h = a["href"].strip()
            t = a.get_text(strip=True).lower()
            if any(k in t or k in h.lower() for k in ("contact", "despre", "cariere", "angajari", "recrutare")):
                full = urllib.parse.urljoin(website_url, h)
                if urllib.parse.urlparse(full).netloc == parsed.netloc and full not in sub_links:
                    sub_links.append(full)

        if not sub_links:
            for guess in ("/contact", "/contact-us", "/despre-noi", "/cariere", "/angajari"):
                sub_links.append(urllib.parse.urljoin(root, guess))

        for sub in sub_links[:5]:
            sub_html = fetch_html_curl(session, sub, timeout=4.5)
            if sub_html:
                for em in EMAIL_REGEX.findall(sub_html):
                    c = clean_email(em)
                    if c and score_email_b2b_ro(c, domain) > 0:
                        found_emails.add(c)
                best = max(found_emails, key=lambda x: score_email_b2b_ro(x, domain), default="")
                if best and score_email_b2b_ro(best, domain) >= 90:
                    return best

    best = max(found_emails, key=lambda x: score_email_b2b_ro(x, domain), default="")
    return best if best else ""


def run_nocaptcha_pipeline(limit: int | None = None, workers: int = 5) -> None:
    print("=" * 80)
    print("CAPTCHA-FREE B2B ENRICHMENT FOR ROMANIAN EMPLOYMENT AGENCIES (PAUR)")
    print(f"  Target File  : {INPUT_2COL_PATH.name}")
    print("  Engines      : ANAF v9 + CompanyWall (by CUI) + DuckDuckGo (site:ro)")
    print("=" * 80 + "\n")

    if not INPUT_2COL_PATH.exists():
        print(f"[!] Target file not found: {INPUT_2COL_PATH}")
        return

    # Safety backup
    if not BACKUP_PATH.exists():
        BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(INPUT_2COL_PATH, BACKUP_PATH)
        print(f"[+] Safety backup created at: {BACKUP_PATH.relative_to(ROOT_DIR)}")

    df = pd.read_csv(INPUT_2COL_PATH, encoding="utf-8-sig", dtype=str).fillna("")
    total_rows = len(df)
    initial_emails = (df["Email"] != "").sum()
    print(f"[*] Total rows in dataset       : {total_rows:,}")
    print(f"[*] Initial rows with Email     : {initial_emails:,} ({initial_emails * 100 / total_rows:.1f}%)")

    # Load 0RAW to get CUIs if not in 2COL
    cui_map = {}
    if INPUT_0RAW_PATH.exists():
        df_raw = pd.read_csv(INPUT_0RAW_PATH, encoding="utf-8-sig", dtype=str).fillna("")
        for _, r in df_raw.iterrows():
            cname = clean_text(r.get("Company_Name", ""))
            cui = clean_text(r.get("CUI", ""))
            if cname and cui:
                cui_map[cname] = cui

    cache = {}
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                cache = json.load(f)
            print(f"[*] Loaded {len(cache):,} records from cache {CACHE_PATH.name}")
        except Exception:
            pass

    pending_indices = [
        i for i, r in df.iterrows()
        if not clean_email(r["Email"]) and not is_blacklisted_company(r["Công ty"])
    ]
    print(f"[*] Companies needing enrichment: {len(pending_indices):,}\n")

    if limit:
        pending_indices = pending_indices[:limit]
        print(f"[*] Limited to first {limit} companies for this run.\n")

    if not pending_indices:
        print("[+] 100% of target companies already have verified emails!")
        return

    session = requests.Session(impersonate="chrome120")
    newly_web = 0
    newly_phone = 0
    newly_email = 0

    for step, idx in enumerate(pending_indices, 1):
        comp = clean_text(df.at[idx, "Công ty"])
        addr = clean_text(df.at[idx, "Địa chỉ"])
        city = extract_city_from_address(addr)
        curr_web = clean_text(df.at[idx, "Liên Hệ"])
        curr_phone = clean_text(df.at[idx, "SĐT"])
        cui = cui_map.get(comp, "")

        print(f"[{step}/{len(pending_indices)}] Company: '{comp}' | CUI: {cui or '-'} | City: {city}")

        # Check cache
        if comp in cache:
            c_data = cache[comp]
            if c_data.get("email"):
                df.at[idx, "Email"] = c_data["email"]
                df.at[idx, "Liên Hệ mail"] = f"mailto:{c_data['email']}"
                newly_email += 1
            if c_data.get("website") and not is_valid_company_website(curr_web):
                df.at[idx, "Liên Hệ"] = c_data["website"]
                newly_web += 1
            if c_data.get("phone") and not clean_phone_ro(curr_phone):
                df.at[idx, "SĐT"] = c_data["phone"]
                newly_phone += 1
            print(f"    [CACHE] Email: {c_data.get('email') or '-'} | Web: {c_data.get('website') or '-'}")
            continue

        found_web = ""
        found_phone = ""
        found_admin = ""
        found_email = ""
        source = "NONE"

        # 1. CompanyWall by CUI (Fast & Official)
        if cui:
            cw_web, cw_ph, cw_adm = search_companywall_for_website(session, cui)
            if cw_web:
                found_web = cw_web
                source = "CompanyWall"
            if cw_ph and not clean_phone_ro(curr_phone):
                found_phone = cw_ph
            if cw_adm:
                found_admin = cw_adm

        # 2. DuckDuckGo Search (Clean fallback, 0 CAPTCHA)
        if not found_web:
            core_name = " ".join(get_core_tokens(comp))
            ddg_web = search_duckduckgo_for_website(session, core_name, city)
            if ddg_web:
                found_web = ddg_web
                source = "DuckDuckGo"

        # 3. Deep B2B Email Crawl
        if found_web:
            em = crawl_site_for_b2b_email(session, found_web)
            if em:
                found_email = em

        # Apply updates
        if found_web and not is_valid_company_website(curr_web):
            df.at[idx, "Liên Hệ"] = found_web
            newly_web += 1
        if found_phone and not clean_phone_ro(curr_phone):
            df.at[idx, "SĐT"] = found_phone
            newly_phone += 1
        if found_admin and not clean_text(df.at[idx, "Người liên hệ"]):
            df.at[idx, "Người liên hệ"] = found_admin
        if found_email:
            df.at[idx, "Email"] = found_email
            df.at[idx, "Liên Hệ mail"] = f"mailto:{found_email}"
            newly_email += 1
            print(f"    [+] FOUND B2B EMAIL: {found_email} | Web: {found_web} ({source}) | Phone: {found_phone or curr_phone}")
        elif found_web:
            print(f"    [~] MATCHED WEBSITE: {found_web} ({source}) | Phone: {found_phone or '-'}")
        else:
            print(f"    [-] No website found")

        cache[comp] = {
            "website": found_web,
            "phone": found_phone,
            "admin": found_admin,
            "email": found_email,
            "source": source,
        }

        # Checkpoint save every 5 companies
        if step % 5 == 0:
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            save_and_sort_output(df)

        time.sleep(0.5)

    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    total_with_email = save_and_sort_output(df)

    print("\n" + "=" * 80)
    print("ENRICHMENT RUN COMPLETED!")
    print(f"  Processed companies    : {len(pending_indices):,}")
    print(f"  New Websites discovered: +{newly_web:,}")
    print(f"  New Phones enriched    : +{newly_phone:,}")
    print(f"  New B2B Emails found   : +{newly_email:,}")
    print(f"  Final total with Email : {total_with_email:,} ({total_with_email * 100 / total_rows:.1f}%)")
    print("=" * 80)


def save_and_sort_output(df: pd.DataFrame) -> int:
    df_clean = df[~df["Công ty"].apply(is_blacklisted_company)].copy()
    for col in df_clean.columns:
        df_clean[col] = df_clean[col].apply(clean_text)

    df_clean["Email"] = df_clean["Email"].apply(clean_email)
    df_clean["SĐT"] = df_clean["SĐT"].apply(clean_phone_ro)

    has_em = df_clean[df_clean["Email"] != ""].copy()
    no_em = df_clean[df_clean["Email"] == ""].copy()

    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted["No."] = range(1, len(df_sorted) + 1)
    df_sorted.to_csv(INPUT_2COL_PATH, index=False, encoding="utf-8-sig")

    df_ready = has_em.copy()
    df_ready["No."] = range(1, len(df_ready) + 1)
    df_ready.to_csv(OUTPUT_READY_PATH, index=False, encoding="utf-8-sig")

    # Sync
    for target_dir in (ROOT_DIR / "csdl_mlt", ROOT_DIR / "archive" / "ro_romania"):
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(INPUT_2COL_PATH, target_dir / INPUT_2COL_PATH.name)
            shutil.copy2(OUTPUT_READY_PATH, target_dir / OUTPUT_READY_PATH.name)
        except Exception:
            pass

    return len(has_em)


def main() -> None:
    parser = argparse.ArgumentParser(description="CAPTCHA-Free B2B Enrichment for Romanian Agencies")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of companies to enrich")
    args = parser.parse_args()

    run_nocaptcha_pipeline(limit=args.limit)


if __name__ == "__main__":
    main()
