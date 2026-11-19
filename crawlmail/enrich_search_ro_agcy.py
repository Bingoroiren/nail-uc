# -*- coding: utf-8 -*-
"""
===============================================================================
Module     : enrich_search_ro_agcy.py
Description: Multi-engine Official Website Discovery & B2B Email Enrichment
             for Romanian Employment Agencies (RO_AGCY_GMAP_2COL.csv)
Pipeline   :
  1. Google Maps Visual Lookup (Strict Name Matching, Place Authority Website & Phone)
  2. Fallback Google Organic Search for genuine .ro domains
  3. Multi-tier B2B Email Crawler (curl_cffi Chrome 120 + Priority subpages + Facebook fallback)
  4. Auto-save checkpoints, 100% email rows sorted to top, Phone with leading quote (')
===============================================================================
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
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_2COL_PATH = ROOT_DIR / "RO_AGCY_GMAP_2COL.csv"
OUTPUT_READY_PATH = ROOT_DIR / "RO_AGCY_GMAP_ONLY_EMAILS_READY.csv"
CACHE_PATH = ROOT_DIR / "crawlmail" / "cache_search_ro_agcy.json"
BACKUP_PATH = ROOT_DIR / "archive" / "ro_romania" / "RO_AGCY_GMAP_2COL_pre_search_backup.csv"

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
}

RO_DESCRIPTOR_WORDS = {
    "recruitment", "recruiting", "recruiter", "staffing", "human", "resources",
    "resurse", "umane", "personal", "job", "jobs", "work", "workforce",
    "interim", "temporar", "plasare", "munca", "angajari", "consulting",
    "consultanta", "services", "servicii", "solutions", "solutii", "group",
    "romania", "romanian", "international", "management", "outsourcing", "hr",
    "agentia", "agenzia", "agency", "training",
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
}

DISALLOWED_CATEGORY_KEYWORDS = (
    "autocare", "autobuz", "inchirieri auto", "transport", "magazin",
    "clinica", "psihol", "stomatol", "farmacie", "restaurant",
    "hotel", "pensiune", "piese auto", "tamplarie", "instalatii",
    "robinet", "fiting", "mobila", "dentist", "cabinet", "barber",
    "salon", "beauty", "constructii", "tamplar", "service auto",
)


def is_valid_agency_category(cat_str: str) -> bool:
    if not cat_str:
        return True
    c = clean_ascii(cat_str).lower()
    return not any(bad in c for bad in DISALLOWED_CATEGORY_KEYWORDS)

EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b")
INVALID_EXTS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js",
    ".pdf", ".woff", ".woff2", ".ico", ".mp4",
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
    digits = re.sub(r"[^0-9]", "", s)
    if not digits or len(digits) < 6:
        return ""
    if digits.startswith("0040"):
        digits = digits[4:]
    elif digits.startswith("40"):
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = digits[1:]

    if digits.startswith("7") and len(digits) == 9:
        return f"'+40 {digits[:3]} {digits[3:6]} {digits[6:]}"
    elif digits.startswith(("2", "3")) and len(digits) == 9:
        return f"'+40 {digits[:2]} {digits[2:5]} {digits[5:]}"
    return f"'+40{digits}"


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
        host = parsed.netloc.replace("www.", "").lower()
        if not host or "." not in host or len(host) < 4:
            return False
        return not any(d == host or host.endswith("." + d) for d in DIRECTORY_DOMAINS)
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
    # Check for known Romanian cities
    for c in sorted(RO_CITIES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(c)}\b", a):
            return c.title()
    # Check MUN. or ORAS
    m = re.search(r"\b(?:mun|municipiul|oras|orasul|jud|judetul)\.?\s*([a-z\-]+)", a)
    if m:
        cand = m.group(1).strip()
        if len(cand) >= 3 and cand not in ("sat", "com", "comuna"):
            return cand.title()
    return "Romania"


def is_valid_name_match_ro(target_name: str, cand_title: str) -> tuple[bool, str]:
    if not target_name or not cand_title:
        return False, "EMPTY"

    t_core = get_core_tokens(target_name)
    c_core = get_core_tokens(cand_title)
    if not t_core or not c_core:
        return False, "NO_TOKENS"

    set_t = set(t_core)
    set_c = set(c_core)

    if set_t == set_c:
        return True, "EXACT"

    if set_c.issubset(set_t):
        extra = set_t - set_c
        if extra.issubset(RO_DESCRIPTOR_WORDS):
            return True, "BRAND_SUBSET"

    if set_t.issubset(set_c):
        extra = set_c - set_t
        if extra.issubset(RO_DESCRIPTOR_WORDS | RO_CITIES):
            return True, "BRAND_EXPANSION"
        if len(set_t) == 1:
            return False, f"REJECT_SINGLE_TOKEN_EXTRA ({extra})"

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

    return False, "NO_MATCH"


def score_email_b2b_ro(email: str, domain: str = "") -> int:
    e = clean_email(email)
    if not e or "@" not in e or any(e.endswith(ext) for ext in INVALID_EXTS):
        return -1
    u, d = e.split("@", 1)
    if any(bad in d for bad in DIRECTORY_DOMAINS):
        return -1
    if u in ("sentry", "privacy", "gdpr", "noreply", "no-reply", "abuse"):
        return -1

    score = 10
    if domain:
        clean_d = domain.lower().replace("www.", "").split("/")[0]
        if clean_d in d or d in clean_d:
            score += 45

    if any(k in u for k in ("recrutare", "recruitment", "angajari", "cariere", "jobs", "hr", "cv")):
        score += 50
    elif any(k in u for k in ("director", "ceo", "manager", "admin", "office", "contact")):
        score += 35
    elif any(k in u for k in ("info", "secretariat", "receptie")):
        score += 25
    return score


def fetch_html_curl(url: str, timeout: float = 6.0) -> str:
    if not url:
        return ""
    u = url.strip()
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    try:
        import curl_cffi.requests as requests
        s = requests.Session(impersonate="chrome120")
        for v in (True, False):
            try:
                r = s.get(u, timeout=timeout, allow_redirects=True, verify=v)
                if r.status_code == 200:
                    return r.text or ""
            except Exception:
                pass
    except Exception:
        pass
    return ""


def crawl_site_for_b2b_email(website_url: str) -> tuple[str, str]:
    if not is_valid_company_website(website_url):
        return "", ""

    found_emails = set()
    parsed = urllib.parse.urlparse(website_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    domain = parsed.netloc.replace("www.", "")

    home_html = fetch_html_curl(website_url, timeout=6.0)
    if not home_html and root != website_url:
        home_html = fetch_html_curl(root, timeout=6.0)

    if home_html:
        for em in EMAIL_REGEX.findall(home_html):
            c = clean_email(em)
            if c and score_email_b2b_ro(c, domain) > 0:
                found_emails.add(c)

        # Check for immediate high score email
        best = max(found_emails, key=lambda x: score_email_b2b_ro(x, domain), default="")
        if best and score_email_b2b_ro(best, domain) >= 90:
            return best, "Website"

        # Discover contact subpages
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
            sub_html = fetch_html_curl(sub, timeout=4.5)
            if sub_html:
                for em in EMAIL_REGEX.findall(sub_html):
                    c = clean_email(em)
                    if c and score_email_b2b_ro(c, domain) > 0:
                        found_emails.add(c)
                best = max(found_emails, key=lambda x: score_email_b2b_ro(x, domain), default="")
                if best and score_email_b2b_ro(best, domain) >= 90:
                    return best, "Website"

    best = max(found_emails, key=lambda x: score_email_b2b_ro(x, domain), default="")
    return (best, "Website") if best else ("", "")


async def run_discovery_pipeline(limit: int | None = None, headless: bool = False) -> None:
    print("=" * 80)
    print("OFFICIAL WEBSITE DISCOVERY & B2B EMAIL ENRICHMENT (RO_AGCY)")
    print(f"  Target File  : {INPUT_2COL_PATH.name}")
    print(f"  Browser Mode : {'HEADLESS' if headless else 'VISUAL (headless=False, 1280x800)'}")
    print("=" * 80 + "\n")

    if not INPUT_2COL_PATH.exists():
        print(f"[!] Target file not found: {INPUT_2COL_PATH}")
        return

    # Create safety backup
    if not BACKUP_PATH.exists():
        BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(INPUT_2COL_PATH, BACKUP_PATH)
        print(f"[+] Safety backup created at: {BACKUP_PATH.relative_to(ROOT_DIR)}")

    df = pd.read_csv(INPUT_2COL_PATH, encoding="utf-8-sig", dtype=str).fillna("")
    total_rows = len(df)
    initial_emails = (df["Email"] != "").sum()
    print(f"[*] Total rows in dataset     : {total_rows:,}")
    print(f"[*] Initial rows with Email   : {initial_emails:,} ({initial_emails * 100 / total_rows:.1f}%)")

    # Load cache
    cache = {}
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                cache = json.load(f)
            print(f"[*] Loaded {len(cache):,} records from cache {CACHE_PATH.name}")
        except Exception:
            pass

    # Find rows missing email
    pending_indices = [
        i for i, r in df.iterrows()
        if not clean_email(r["Email"]) and not is_blacklisted_company(r["Công ty"])
    ]
    print(f"[*] Companies needing enrichment: {len(pending_indices):,}\n")

    if limit:
        pending_indices = pending_indices[:limit]
        print(f"[*] Limited to first {limit} companies for this test run.\n")

    if not pending_indices:
        print("[+] 100% of target companies already have verified emails!")
        return

    newly_web = 0
    newly_phone = 0
    newly_email = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
            ],
        )

        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="ro-RO",
        )
        await context.add_cookies([
            {"name": "SOCS", "value": "CAESEwgDEgk2OTQ0NTgyODQaAmVuIAEaBgiA_LyaBg", "domain": ".google.com", "path": "/"},
            {"name": "CONSENT", "value": "YES+cb.20230531-04-p0.en+FX+999", "domain": ".google.com", "path": "/"},
        ])
        page = await context.new_page()

        # Warm up Google Maps session
        print("[*] Warming up Google Maps session...")
        try:
            await page.goto("https://www.google.com/maps?hl=ro", wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(2.0)
            if "consent.google" in page.url.lower():
                print("[*] Dismissing Google cookie consent...")
                for b in await page.query_selector_all("button"):
                    t = (await b.inner_text()).strip().lower()
                    if any(k in t for k in ("accept", "sunt de acord", "alles accepteren", "akkoord", "acceptă tot")):
                        await b.click()
                        await asyncio.sleep(2.5)
                        break
            print("[+] Google Maps session ready!\n")
        except Exception as e:
            print(f"[!] Warm-up note: {e}")

        for step, idx in enumerate(pending_indices, 1):
            comp = clean_text(df.at[idx, "Công ty"])
            addr = clean_text(df.at[idx, "Địa chỉ"])
            city = extract_city_from_address(addr)
            curr_web = clean_text(df.at[idx, "Liên Hệ"])
            curr_phone = clean_text(df.at[idx, "SĐT"])

            print(f"[{step}/{len(pending_indices)}] Company: '{comp}' ({city})")

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
            found_email = ""
            match_status = "NO_MATCH"

            # 1. Step 1: Google Maps Search
            core_name = " ".join(get_core_tokens(comp))
            q_term = f"{core_name} {city} Romania".strip()
            maps_url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(q_term)}?hl=ro"

            try:
                await page.goto(maps_url, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(2.0)

                if "consent.google" in page.url.lower():
                    for b in await page.query_selector_all("button"):
                        t = (await b.inner_text()).strip().lower()
                        if any(k in t for k in ("accept", "sunt de acord", "alles accepteren", "akkoord", "acceptă tot")):
                            await b.click()
                            await asyncio.sleep(2.0)
                            break

                h1 = await page.query_selector("h1.DUwDvf")
                cards = await page.query_selector_all("a.hfpxzc")

                matched = False
                if h1:
                    cand_title = clean_text(await h1.inner_text())
                    ok, reason = is_valid_name_match_ro(comp, cand_title)
                    if ok:
                        matched = True
                        match_status = f"DIRECT ({reason})"
                elif cards:
                    for c in cards[:4]:
                        cand_title = clean_text(await c.get_attribute("aria-label"))
                        ok, reason = is_valid_name_match_ro(comp, cand_title)
                        if ok:
                            await c.click()
                            await asyncio.sleep(1.5)
                            matched = True
                            match_status = f"CARD ({reason})"
                            break

                if matched:
                    # Category Guard: Reject non-agency businesses (bus rental, plumbing, dental, etc.)
                    cat_elem = await page.query_selector('button.DkEaCc, button[jsaction*="category"], span.mgr77e')
                    if cat_elem:
                        cat_txt = clean_text(await cat_elem.inner_text())
                        if not is_valid_agency_category(cat_txt):
                            matched = False
                            match_status = f"REJECT_CATEGORY ({cat_txt})"
                            print(f"    [-] Rejected category: '{cat_txt}' (Non-agency)")

                if matched:
                    web_btn = await page.query_selector('a[data-item-id="authority"]')
                    if web_btn:
                        w_href = (await web_btn.get_attribute("href") or "").strip()
                        if is_valid_company_website(w_href):
                            found_web = w_href

                    phone_btn = await page.query_selector('button[data-item-id^="phone:"]')
                    if phone_btn:
                        p_txt = await phone_btn.inner_text()
                        found_phone = clean_phone_ro(p_txt)
            except Exception as e:
                print(f"    [!] Maps error: {e}")

            # 2. Step 2: Fallback Google Search if no valid website found on Maps
            if not found_web:
                try:
                    search_q = f'"{core_name}" {city} site:ro OR recrutare'
                    g_search_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(search_q)}&hl=ro"
                    await page.goto(g_search_url, wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(1.5)

                    for a in await page.query_selector_all("div#search a[href^='http'], div#rso a[href^='http']"):
                        h = await a.get_attribute("href") or ""
                        if is_valid_company_website(h):
                            # Verify domain matches company brand
                            domain = urllib.parse.urlparse(h).netloc.replace("www.", "").lower()
                            domain_core = re.sub(r"[^a-z0-9]", "", domain.split(".")[0])
                            comp_alnum = re.sub(r"[^a-z0-9]", "", clean_ascii(core_name))
                            if len(comp_alnum) >= 4 and (comp_alnum in domain_core or domain_core in comp_alnum):
                                found_web = h
                                match_status = "GOOGLE_SEARCH_MATCH"
                                break
                except Exception:
                    pass

            # 3. Step 3: Deep Crawl official website for B2B email
            if found_web:
                em, src = crawl_site_for_b2b_email(found_web)
                if em:
                    found_email = em

            # Apply updates
            if found_web and not is_valid_company_website(curr_web):
                df.at[idx, "Liên Hệ"] = found_web
                newly_web += 1
            if found_phone and not clean_phone_ro(curr_phone):
                df.at[idx, "SĐT"] = found_phone
                newly_phone += 1
            if found_email:
                df.at[idx, "Email"] = found_email
                df.at[idx, "Liên Hệ mail"] = f"mailto:{found_email}"
                newly_email += 1
                print(f"    [+] FOUND B2B EMAIL: {found_email} | Web: {found_web} | Phone: {found_phone or curr_phone}")
            elif found_web:
                print(f"    [~] MATCHED WEBSITE: {found_web} | Phone: {found_phone or '-'}")
            else:
                print(f"    [-] {match_status}")

            cache[comp] = {
                "website": found_web,
                "phone": found_phone,
                "email": found_email,
                "status": match_status,
            }

            # Periodic checkpoint save every 5 companies
            if step % 5 == 0:
                with open(CACHE_PATH, "w", encoding="utf-8") as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
                save_and_sort_output(df)

            await asyncio.sleep(0.5)

        await browser.close()

    # Final save
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

    # Update READY file
    ready_df = has_em.copy()
    ready_df["No."] = range(1, len(ready_df) + 1)
    ready_df.to_csv(OUTPUT_READY_PATH, index=False, encoding="utf-8-sig")

    # Sync to archive
    try:
        shutil.copy2(INPUT_2COL_PATH, ROOT_DIR / "archive" / "ro_romania" / "RO_AGCY_GMAP_2COL.csv")
        shutil.copy2(OUTPUT_READY_PATH, ROOT_DIR / "archive" / "ro_romania" / "RO_AGCY_GMAP_ONLY_EMAILS_READY.csv")
    except Exception:
        pass

    return len(has_em)


def main():
    parser = argparse.ArgumentParser(description="Multi-engine Official Website Discovery & B2B Email Enrichment for Romanian Agencies")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of companies to process")
    parser.add_argument("--headless", action="store_true", help="Run headless mode (default: visual Chrome)")
    args = parser.parse_args()

    asyncio.run(run_discovery_pipeline(limit=args.limit, headless=args.headless))


if __name__ == "__main__":
    main()
