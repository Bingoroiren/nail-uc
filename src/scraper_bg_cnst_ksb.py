# -*- coding: utf-8 -*-
"""
BULGARIAN CONSTRUCTION CHAMBER (KSB) SCRAPER - CENTRAL REGISTER OF BUILDERS
=============================================================================
Target  : Central Professional Register of Builders (ЦПРС - register.ksb.bg)
Country : Bulgaria (BG) | Industry: Construction (CNST) | Source: KSB (KSBB)
Source  : https://register.ksb.bg/listFirms.php
Detail  : https://register.ksb.bg/pub_view.php?id_members={id} (Section 6 & 5 Contacts)

Outputs:
  - BG_CNST_KSBB_0RAW.csv (Comprehensive master dataset)
  - BG_CNST_KSBB_2COL.csv (Cold Mail 20-column standard, 100% emails sorted on top)
  - BG_CNST_KSBB_ONLY_EMAILS_READY.csv (Outreach-ready rows)
  - Synced to csdl_mlt/ and archive/bg_bulgaria/
  - Checkpoints:
      * crawlmail/cache_ksb_members_list.json (Discovered IDs)
      * crawlmail/cache_ksb_details.json (Enriched details, 100% resume)
"""

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
ARCHIVE_DIR = ROOT_DIR / "archive" / "bg_bulgaria"

OUTPUT_0RAW_PATH = ROOT_DIR / "BG_CNST_KSBB_0RAW.csv"
OUTPUT_2COL_PATH = ROOT_DIR / "BG_CNST_KSBB_2COL.csv"
OUTPUT_READY_PATH = ROOT_DIR / "BG_CNST_KSBB_ONLY_EMAILS_READY.csv"

CACHE_LIST_PATH = CRAWLMAIL_DIR / "cache_ksb_members_list.json"
CACHE_DETAILS_PATH = CRAWLMAIL_DIR / "cache_ksb_details.json"

BASE_URL = "https://register.ksb.bg"
LIST_URL = f"{BASE_URL}/listFirms.php"
DETAIL_URL = f"{BASE_URL}/pub_view.php?id_members="

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Origin": BASE_URL,
    "Referer": LIST_URL,
}

COLDMAIL_COLUMNS = [
    "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ",
    "Email", "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển",
    "Check gửi", "Last Subject", "Last Body HTML", "Trạng thái Reply",
    "Lần Follow-up", "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category",
]

RAW_COLUMNS = [
    "No.", "id_members", "EIK", "Company_Name", "Legal_Form", "Manager_Name",
    "Manager_Role", "Email", "Phone", "Website", "Address_Full", "City",
    "Obshtina", "Oblast", "Postcode", "Street", "Sec5_Email", "Sec5_Phone",
    "Sec5_Address", "Personnel", "Revenue_Thousand_BGN", "Categories_Summary",
    "Protocol_Date", "Detail_URL",
]

PERMANENT_BLACKLIST_COMPANIES = [
    "scandi standard",
    "scandi-standard",
    "scandi standart",
    "biliarta",
    "daigre",
    "daigrė",
]

EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b")
INVALID_EXTS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js",
    ".pdf", ".woff", ".woff2", ".ico", ".mp4",
)

JUNK_EMAIL_DOMAINS = {
    "example.com", "example.org", "example.net", "domain.com", "yourdomain.com",
    "yourcompany.com", "company.com", "email.com", "placeholder.com", "sample.com",
    "sentry.io", "wixpress.com", "wix.com", "wordpress.com", "ksb.bg",
    "localservices.be", "bizbook.be", "pagesdor.be", "goudengids.be",
}

JUNK_USERNAMES = {
    "youremail", "your-email", "your_email", "yourname", "your-name",
    "yourcompany", "someone", "nobody", "john.doe", "johndoe", "jane.doe",
    "username", "sample", "demo", "no-reply", "noreply", "donotreply",
    "privacy", "gdpr", "cookies", "abuse", "security", "mailer-daemon", "sentry",
}

# 28 Bulgarian administrative divisions (Pods)
PODS = [
    ("1", "Благоевград"),
    ("2", "Бургас"),
    ("3", "В. Търново"),
    ("4", "Варна"),
    ("5", "Видин"),
    ("6", "Враца"),
    ("7", "Габрово"),
    ("8", "Добрич"),
    ("9", "Кърджали"),
    ("10", "Кюстендил"),
    ("11", "Ловеч"),
    ("12", "Монтана"),
    ("13", "Пазарджик"),
    ("14", "Перник"),
    ("15", "Плевен"),
    ("16", "Пловдив"),
    ("17", "Разград"),
    ("18", "Русе"),
    ("19", "Силистра"),
    ("20", "Сливен"),
    ("21", "Смолян"),
    ("22", "София град и София област"),
    ("23", "Стара Загора"),
    ("24", "Търговище"),
    ("25", "Хасково"),
    ("26", "Шумен"),
    ("27", "Ямбол"),
    ("28", "ЧЮЛ"),
]

# 47 Selectable Group Types from register.ksb.bg
GROUP_TYPES = [
    ("11", "1.1 строежи от първа до пета категория"),
    ("12", "1.2 строежи от втора до пета категория"),
    ("13", "1.3 строежи от трета до пета категория"),
    ("14", "1.4 строежи от четвърта и пета категория"),
    ("21", "2.1 строежи от първа до четвърта категория"),
    ("22", "2.2 строежи от втора до четвърта категория"),
    ("23", "2.3 строежи от трета и четвърта категория"),
    ("24", "2.4 строежи от четвърта категория"),
    ("31", "3.1 строежи от първа до пета категория"),
    ("32", "3.2 строежи от втора до пета категория"),
    ("33", "3.3 строежи от трета до пета категория"),
    ("34", "3.4 строежи от четвърта и пета категория"),
    ("41", "4.1 строежи от първа до пета категория"),
    ("42", "4.2 строежи от втора до пета категория"),
    ("43", "4.3 строежи от трета до пета категория"),
    ("44", "4.4 строежи от четвърта и пета категория"),
    ("41.00", "41.00 Строителство на жилищни и нежилищни сгради"),
    ("41.20", "41.20 Строителство на жилищни и нежилищни сгради"),
    ("42.11", "42.11 Строителство на автомагистрали и пътища"),
    ("42.12", "42.12 Строителство на релсови пътища"),
    ("42.13", "42.13 Строителство на мостове и тунели"),
    ("42.21", "42.21 Строителство на тръбопроводи"),
    ("42.22", "42.22 Строителство на ел. и телеком мрежи"),
    ("42.91", "42.91 Строителство на хидротехнически съоръжения"),
    ("42.99", "42.99 Строителство на други съоръжения"),
    ("43.11", "43.11 Събаряне и разрушаване"),
    ("43.12", "43.12 Земни работи"),
    ("43.13", "43.13 Сондиране и пробиване"),
    ("43.21", "43.21 Електрически инсталации"),
    ("43.22", "43.22 Водопроводни и отоплителни инсталации"),
    ("43.23", "43.23 Изграждане на изолация"),
    ("43.24", "43.24 Изграждане на други инсталации"),
    ("43.29", "43.29 Изграждане на други инсталации"),
    ("43.31", "43.31 Полагане на мазилки"),
    ("43.32", "43.32 Монтаж на дограма и дърводелски работи"),
    ("43.33", "43.33 Облицовки и настилки"),
    ("43.34", "43.34 Боядисване и стъклопоставяне"),
    ("43.35", "43.35 Други довършителни дейности"),
    ("43.39", "43.39 Други довършителни дейности"),
    ("43.41", "43.41 Покривни работи"),
    ("43.42", "43.42 Специализирани дейности при сгради"),
    ("43.50", "43.50 Специализирани дейности при съоръжения"),
    ("43.91", "43.91 Зидарски и покривни дейности"),
    ("43.99", "43.99 Други строителни дейности"),
    ("80.09", "80.09 Технически системи за сигурност"),
    ("80.20", "80.20 Технически системи за сигурност"),
    ("71", "71 Строежи - Паметници"),
    ("72", "72 Строежи - Паметници"),
]


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


def clean_phone_bg(tel_code: str, raw_phone: str) -> str:
    """Normalize Bulgarian phone numbers, handle multi-numbers, and prefix with leading apostrophe."""
    if not raw_phone and not tel_code:
        return ""

    candidates = re.split(r"[,;/|]|\bили\b", str(raw_phone or ""))
    t_digits = re.sub(r"[^0-9]", "", str(tel_code or ""))

    mobile_cand = ""
    valid_cand = ""
    for c in candidates:
        d = re.sub(r"[^0-9]", "", c)
        if not d:
            continue
        if d.startswith(("087", "088", "089", "87", "88", "89")):
            if len(d) == 9 and not d.startswith("0"):
                d = "0" + d
            if len(d) == 10:
                mobile_cand = d
                break
        elif d.startswith("3598") and len(d) == 12:
            mobile_cand = d
            break
        elif not valid_cand:
            if t_digits and not d.startswith(("0", "359", "00359")):
                t = t_digits.lstrip("0")
                valid_cand = "0" + t + d
            else:
                valid_cand = d

    chosen = mobile_cand or valid_cand
    if not chosen or len(chosen) < 5:
        return ""

    if chosen.startswith("00359"):
        digits = chosen[2:]
    elif chosen.startswith("359"):
        digits = chosen
    elif chosen.startswith("0"):
        digits = "359" + chosen[1:]
    else:
        digits = "359" + chosen

    if digits.startswith("359") and len(digits) >= 9:
        if digits.startswith("3592") and len(digits) == 10:  # Sofia landline
            return f"'+359 2 {digits[4:7]} {digits[7:]}"
        elif digits.startswith(("35987", "35988", "35989")) and len(digits) == 11:  # Mobile
            return f"'+359 {digits[3:5]} {digits[5:8]} {digits[8:]}"
        elif len(digits) == 11:
            return f"'+359 {digits[3:5]} {digits[5:8]} {digits[8:]}"
        elif len(digits) == 12:
            return f"'+359 {digits[3:6]} {digits[6:9]} {digits[9:]}"
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
    return e.strip(" .,;:\"'<>[](){}\\/")


def score_email_b2b_bg(email: str, domain: str = "") -> int:
    """Score B2B email value for Bulgarian construction firms."""
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
    elif d.endswith(".bg"):
        score += 35

    # Prioritize recruitment & management
    if any(k in u for k in ("hr", "jobs", "rabota", "kariera", "personal", "kadri")):
        score += 55
    elif any(k in u for k in ("upravitel", "director", "manager", "ceo", "shef", "boss")):
        score += 45
    elif any(k in u for k in ("office", "info", "kontakt", "contact", "biuro", "sekretar")):
        score += 40
    elif any(k in u for k in ("sales", "stroitelstvo", "proekti", "inzenier")):
        score += 35
    elif "." in u and score >= 60:
        score += 25
    # Standard Bulgarian webmails
    elif d in ("abv.bg", "mail.bg", "dir.bg", "gmail.com"):
        score += 20
    elif any(k in u for k in ("support", "admin", "schetovodstvo")):
        score += 5

    return score


def select_best_email(emails: list[str] | set[str], domain: str = "") -> str:
    """Select the single highest-scoring B2B email."""
    valid = [clean_email(e) for e in emails if e]
    valid = [e for e in set(valid) if e and score_email_b2b_bg(e, domain) > 0]
    if not valid:
        return ""
    return max(valid, key=lambda e: score_email_b2b_bg(e, domain))


# =============================================================================
# PHASE 1: DISCOVER ALL BUILDER MEMBERS (listFirms.php)
# =============================================================================

def fetch_list_slice(session: requests.Session, pod_code: str, pod_name: str, grp_code: str, grp_name: str) -> list[dict]:
    """POST listFirms.php for a given Province and GroupType and extract builder items."""
    data = {
        "Pod": str(pod_code),
        "GroupType": str(grp_code),
        "Podphp": str(pod_code),
        "GroupTypephp": str(grp_code),
        "filter": "Покажи строителите",
    }
    items = []
    for _ in range(3):
        try:
            r = session.post(LIST_URL, data=data, headers=HEADERS, verify=False, timeout=18)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.content.decode("utf-8", errors="replace"), "html.parser")
            for a in soup.find_all("a", href=lambda h: h and "pub_view.php?id_members=" in h):
                href = a.get("href", "")
                m_id = re.search(r"id_members=(\d+)", href)
                if not m_id:
                    continue
                member_id = m_id.group(1)
                eik = a.text.strip()
                # Find parent tr to get company name and protocol date
                tr = a.find_parent("tr")
                comp_name = ""
                proto_date = ""
                if tr:
                    tds = [td.text.strip() for td in tr.find_all("td")]
                    if len(tds) >= 3:
                        comp_name = clean_text(tds[2])
                    if len(tds) >= 4:
                        proto_date = clean_text(tds[3])

                items.append({
                    "id_members": member_id,
                    "EIK": eik,
                    "Company_Name": comp_name,
                    "Protocol_Date": proto_date,
                    "Pod_Code": pod_code,
                    "Pod_Name": pod_name,
                    "Group_Code": grp_code,
                    "Group_Name": grp_name,
                })
            return items
        except Exception:
            time.sleep(0.5)
    return items


def collect_all_members(workers: int = 8) -> dict[str, dict]:
    """Iterate over all Pods and GroupTypes to collect unique builder records."""
    if CACHE_LIST_PATH.exists():
        try:
            with open(CACHE_LIST_PATH, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if cached and len(cached) > 500:
                print(f"[*] Loaded {len(cached):,} discovered members from {CACHE_LIST_PATH.name}")
                return cached
        except Exception as e:
            print(f"[!] Could not load cached member list: {e}")

    print("=" * 80)
    print("PHASE 1: DISCOVERING BUILDERS ACROSS ALL PROVINCES AND GROUPS (listFirms.php)")
    print(f"  Provinces : {len(PODS)} | Groups : {len(GROUP_TYPES)} | Total Combinations : {len(PODS) * len(GROUP_TYPES)}")
    print(f"  Workers   : {workers}")
    print("=" * 80)

    combos = []
    for pod_code, pod_name in PODS:
        for grp_code, grp_name in GROUP_TYPES:
            combos.append((pod_code, pod_name, grp_code, grp_name))

    unique_members: dict[str, dict] = {}
    lock = threading.Lock()
    processed_combos = 0

    def worker_job(c):
        p_code, p_name, g_code, g_name = c
        s = requests.Session()
        return fetch_list_slice(s, p_code, p_name, g_code, g_name)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(worker_job, c): c for c in combos}
        for fut in as_completed(futures):
            c = futures[fut]
            try:
                res = fut.result()
            except Exception:
                res = []

            with lock:
                processed_combos += 1
                for item in res:
                    m_id = item["id_members"]
                    if m_id not in unique_members:
                        unique_members[m_id] = item
                    else:
                        # Append category code if not present
                        existing = unique_members[m_id]
                        if not existing.get("Company_Name") and item.get("Company_Name"):
                            existing["Company_Name"] = item["Company_Name"]
                        if not existing.get("Protocol_Date") and item.get("Protocol_Date"):
                            existing["Protocol_Date"] = item["Protocol_Date"]

                if processed_combos % 50 == 0 or processed_combos == len(combos):
                    print(
                        f"  [{processed_combos:4d}/{len(combos)}] Progress... Unique builders found: {len(unique_members):,}"
                    )

    # Save to JSON cache
    CACHE_LIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_LIST_PATH, "w", encoding="utf-8") as f:
        json.dump(unique_members, f, ensure_ascii=False, indent=2)

    print(f"[+] Phase 1 finished! Total unique builders discovered: {len(unique_members):,}\n")
    return unique_members


# =============================================================================
# PHASE 2: EXTRACT BUILDER DETAILS (pub_view.php?id_members=...)
# =============================================================================

def extract_builder_details(session: requests.Session, member_id: str, base_info: dict) -> dict:
    """Fetch pub_view.php?id_members={id} and parse Section 6/5 contacts and financials."""
    url = f"{DETAIL_URL}{member_id}"
    resp_text = ""
    for _ in range(3):
        try:
            r = session.get(url, headers=HEADERS, verify=False, timeout=18)
            if r.status_code == 200:
                resp_text = r.content.decode("utf-8", errors="replace")
                break
        except Exception:
            time.sleep(0.5)

    if not resp_text:
        return {"checked": True, "error": "Fetch failed", **base_info}

    soup = BeautifulSoup(resp_text, "html.parser")
    full_text = soup.get_text(" ", strip=True)

    # 1. EIK & Company Name
    eik_m = re.search(r"ЕИК\s*(?:по\s*БУЛСТАТ)?:\s*([0-9]{9,13})", full_text)
    eik = eik_m.group(1) if eik_m else base_info.get("EIK", "")

    name_m = re.search(r"наименование:\s*([^:\n\r]+?)(?:правно-организационна|2\.|\n)", full_text)
    comp_name = clean_text(name_m.group(1)) if name_m else base_info.get("Company_Name", "")

    legal_m = re.search(r"правно-организационна форма:\s*([^:\n\r]+?)(?:2\.|\n)", full_text)
    legal_form = clean_text(legal_m.group(1)) if legal_m else ""

    # 2. Manager / Representative (Section 4)
    manager_name = ""
    manager_role = "Управител"
    for tr in soup.find_all("tr"):
        txt = tr.get_text(" ", strip=True)
        if "Лице/а/, представляващо/и/" in txt or "представляващ за удостоверението" in txt:
            continue
        tds = [td.text.strip() for td in tr.find_all("td")]
        if len(tds) >= 6 and tds[0].isdigit():
            # No, ime, prezime, familiya, darzhava, dlazhnost
            cand_name = f"{tds[1]} {tds[2]} {tds[3]}".strip()
            cand_role = tds[5].strip() if len(tds) > 5 else "Управител"
            if cand_name and not manager_name:
                manager_name = clean_text(cand_name)
                manager_role = clean_text(cand_role) or "Управител"
                break

    # 3. Section 5: Registered Office (Седалище на строителя)
    s5_m = re.search(r"5\.\s*Седалище на строителя(.*?)(?:6\.\s*Адрес за кореспонденция|7\.|$)", full_text, re.DOTALL)
    s5_text = s5_m.group(1) if s5_m else ""

    def get_fld(pattern, src):
        m = re.search(pattern, src, re.I)
        return clean_text(m.group(1)) if m else ""

    s5_oblast = get_fld(r"област:\s*([^:\n\r]+?)(?:община:|$)", s5_text)
    s5_obshtina = get_fld(r"община:\s*([^:\n\r]+?)(?:град|$)", s5_text)
    s5_city = get_fld(r"град\(село\):\s*([^:\n\r]+?)(?:пощенски|$)", s5_text)
    s5_postcode = get_fld(r"пощенски код:\s*([0-9]{4})", s5_text)
    s5_street = get_fld(r"улица,[^:]*:\s*([^:\n\r]+?)(?:номер:|$)", s5_text)
    s5_number = get_fld(r"номер:\s*([^:\n\r]+?)(?:тел\.код:|$)", s5_text)
    s5_tel_code = get_fld(r"тел\.код:\s*([^:\n\r]+?)(?:Телефон:|$)", s5_text)
    s5_phone_raw = get_fld(r"Телефон:\s*([^:\n\r]+?)(?:E-mail:|$)", s5_text)
    s5_emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", s5_text)
    s5_web = get_fld(r"Уеб сайт:\s*([^\s]+)", s5_text)

    # 4. Section 6: Correspondence Address (Адрес за кореспонденция - Mục số 6)
    s6_m = re.search(r"6\.\s*Адрес за кореспонденция(.*?)(?:7\.|$)", full_text, re.DOTALL)
    s6_text = s6_m.group(1) if s6_m else ""

    s6_oblast = get_fld(r"област:\s*([^:\n\r]+?)(?:община:|$)", s6_text)
    s6_obshtina = get_fld(r"община:\s*([^:\n\r]+?)(?:град|$)", s6_text)
    s6_city = get_fld(r"град\(село\):\s*([^:\n\r]+?)(?:пощенски|$)", s6_text)
    s6_postcode = get_fld(r"пощенски код:\s*([0-9]{4})", s6_text)
    s6_street = get_fld(r"улица,[^:]*:\s*([^:\n\r]+?)(?:номер:|$)", s6_text)
    s6_number = get_fld(r"номер:\s*([^:\n\r]+?)(?:тел\.код:|$)", s6_text)
    s6_tel_code = get_fld(r"тел\.код:\s*([^:\n\r]+?)(?:Телефон:|$)", s6_text)
    s6_phone_raw = get_fld(r"Телефон:\s*([^:\n\r]+?)(?:E-mail:|$)", s6_text)
    s6_emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", s6_text)
    s6_web = get_fld(r"Уеб сайт:\s*([^\s]+)", s6_text)

    # Build clean website
    cand_web = s6_web or s5_web
    clean_web = ""
    if cand_web and cand_web not in ("-", "няма", "none", "област:"):
        if not cand_web.startswith("http"):
            clean_web = f"http://{cand_web}"
        else:
            clean_web = cand_web

    # Determine best email (Prioritize Section 6 Correspondence)
    domain = urllib.parse.urlparse(clean_web).netloc if clean_web else ""
    best_email = select_best_email(s6_emails, domain)
    if not best_email:
        best_email = select_best_email(s5_emails, domain)

    # Determine best phone
    s6_clean_phone = clean_phone_bg(s6_tel_code, s6_phone_raw)
    s5_clean_phone = clean_phone_bg(s5_tel_code, s5_phone_raw)
    best_phone = s6_clean_phone or s5_clean_phone

    # Address assembly
    oblast = s6_oblast or s5_oblast or base_info.get("Pod_Name", "")
    obshtina = s6_obshtina or s5_obshtina
    city = s6_city or s5_city
    postcode = s6_postcode or s5_postcode
    street = s6_street or s5_street
    num = s6_number or s5_number

    addr_parts = []
    if street:
        addr_parts.append(f"{street} No.{num}" if num else street)
    if city:
        addr_parts.append(city)
    if postcode:
        addr_parts.append(postcode)
    if oblast:
        addr_parts.append(f"обл. {oblast}")
    addr_parts.append("Bulgaria")
    full_address = ", ".join(p for p in addr_parts if p)

    # 5. Section V: Financials & Staff (Table with Година / НПП / Персонал)
    personnel = ""
    revenue = ""
    for tr in soup.find_all("tr"):
        txt = tr.get_text(" ", strip=True)
        if "Персонал" in txt and "НПП" in txt:
            tds = [td.text.strip() for td in tr.find_all("td")]
            # Format: No, Godina, NPP, DMA, Personal
            if len(tds) >= 5 and tds[0].isdigit():
                revenue = clean_text(tds[2]) + " хил. лв."
                personnel = clean_text(tds[4])
                break

    # 6. Categories summary
    cat_m = re.search(r"ГРУПИ И КАТЕГОРИИ СТРОЕЖИ.*?-(.*?)(?:Срок на валидност|СПРАВКИ|$)", full_text, re.DOTALL)
    cat_summary = clean_text(cat_m.group(1))[:250] if cat_m else "Construction & Building (Bulgaria - KSB)"

    return {
        "checked": True,
        "id_members": member_id,
        "EIK": eik,
        "Company_Name": comp_name,
        "Legal_Form": legal_form,
        "Manager_Name": manager_name,
        "Manager_Role": manager_role,
        "Email": best_email,
        "Phone": best_phone,
        "Website": clean_web,
        "Address_Full": full_address,
        "City": city,
        "Obshtina": obshtina,
        "Oblast": oblast,
        "Postcode": postcode,
        "Street": street,
        "Sec5_Email": s5_emails[0] if s5_emails else "",
        "Sec5_Phone": s5_clean_phone,
        "Sec5_Address": f"{s5_city}, {s5_oblast}, Bulgaria" if s5_city else "",
        "Personnel": personnel,
        "Revenue_Thousand_BGN": revenue,
        "Categories_Summary": cat_summary,
        "Protocol_Date": base_info.get("Protocol_Date", ""),
        "Detail_URL": url,
    }


def save_cache(cache: dict, cache_path: Path) -> None:
    """Atomic write JSON cache to avoid corrupted files upon interruption."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, cache_path)


def export_and_sync_csvs(records: list[dict]) -> tuple[int, int]:
    """Export 0RAW and 2COL CSVs in UTF-8 BOM with 100% email rows sorted on top."""
    df_raw = pd.DataFrame(records)
    if "Company_Name" in df_raw.columns:
        df_raw = df_raw[~df_raw["Company_Name"].apply(is_blacklisted_company)].reset_index(drop=True)

    for col in df_raw.columns:
        df_raw[col] = df_raw[col].apply(clean_text)

    df_raw["Phone"] = df_raw["Phone"].apply(lambda p: f"'{p}" if p and not p.startswith("'") else p)
    df_raw["Email"] = df_raw["Email"].apply(clean_email)

    # Sort with emails first
    has_em = df_raw[df_raw["Email"] != ""].copy()
    no_em = df_raw[df_raw["Email"] == ""].copy()
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted["No."] = range(1, len(df_sorted) + 1)

    # Write 0RAW
    OUTPUT_0RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    df_sorted.to_csv(OUTPUT_0RAW_PATH, index=False, encoding="utf-8-sig")

    # Generate Cold Mail 20 columns
    coldmail_rows = []
    for _, r in df_sorted.iterrows():
        comp_name = r.get("Company_Name", "")
        manager = r.get("Manager_Name", "")
        role = r.get("Manager_Role", "") or ("Управител" if manager else "Представител")
        phone_val = r.get("Phone", "")
        email_val = r.get("Email", "")
        web_val = r.get("Website", "")
        detail_val = r.get("Detail_URL", "")
        link_val = web_val or detail_val
        addr_val = r.get("Address_Full", "") or f"{r.get('City', '')}, {r.get('Oblast', '')}, Bulgaria"
        revenue_val = r.get("Revenue_Thousand_BGN", "")
        date_val = r.get("Protocol_Date", "")

        coldmail_rows.append({
            "No.": r.get("No.", ""),
            "Công ty": comp_name,
            "Chức danh": role,
            "Người liên hệ": manager,
            "SĐT": phone_val,
            "Liên Hệ": link_val,
            "Email": email_val,
            "Liên Hệ mail": f"mailto:{email_val}" if email_val else link_val,
            "Địa chỉ": addr_val,
            "Lương": revenue_val,
            "Ngày đăng": date_val,
            "Hạn tuyển": "",
            "Check gửi": "Chưa gửi",
            "Last Subject": "",
            "Last Body HTML": "",
            "Trạng thái Reply": "",
            "Lần Follow-up": "",
            "Ngày Follow-up gần nhất": "",
            "Mailbox đã dùng": "",
            "Category": "Construction & Building (Bulgaria - KSB)",
        })

    df_2col = pd.DataFrame(coldmail_rows, columns=COLDMAIL_COLUMNS)
    df_2col.to_csv(OUTPUT_2COL_PATH, index=False, encoding="utf-8-sig")

    df_ready = df_2col[df_2col["Email"] != ""].copy()
    df_ready["No."] = range(1, len(df_ready) + 1)
    df_ready.to_csv(OUTPUT_READY_PATH, index=False, encoding="utf-8-sig")

    # Sync to csdl_mlt/ and archive/bg_bulgaria/
    for extra_dir in (CSDL_DIR, ARCHIVE_DIR):
        extra_dir.mkdir(parents=True, exist_ok=True)
        for p in (OUTPUT_0RAW_PATH, OUTPUT_2COL_PATH, OUTPUT_READY_PATH):
            try:
                shutil.copy2(p, extra_dir / p.name)
            except Exception:
                pass

    return len(df_sorted), len(has_em)


def run_pipeline(limit: int | None = None, workers: int = 8, skip_list: bool = False) -> None:
    """Run full two-stage scraper pipeline."""
    # Phase 1: Collect members list
    if skip_list and CACHE_LIST_PATH.exists():
        with open(CACHE_LIST_PATH, "r", encoding="utf-8") as f:
            members_dict = json.load(f)
        print(f"[*] Loaded {len(members_dict):,} members from list cache.")
    else:
        members_dict = collect_all_members(workers=workers)

    # Phase 2: Details extraction
    details_cache: dict[str, dict] = {}
    if CACHE_DETAILS_PATH.exists():
        try:
            with open(CACHE_DETAILS_PATH, "r", encoding="utf-8") as f:
                details_cache = json.load(f)
            print(f"[*] Loaded {len(details_cache):,} cached details from {CACHE_DETAILS_PATH.name}")
        except Exception as e:
            print(f"[!] Could not load details cache: {e}")

    pending_ids = [m_id for m_id in members_dict if m_id not in details_cache]
    if limit:
        pending_ids = pending_ids[:limit]

    print("=" * 80)
    print("PHASE 2: EXTRACTING DETAILED CONTACTS & FINANCIALS (pub_view.php)")
    print(f"  Total Discovered : {len(members_dict):,}")
    print(f"  Already Cached   : {len(details_cache):,}")
    print(f"  Pending to Fetch : {len(pending_ids):,}")
    print(f"  Workers          : {workers}")
    print("=" * 80 + "\n")

    if pending_ids:
        lock = threading.Lock()
        processed = 0
        newly_emails = 0

        # Local thread sessions
        thread_local = threading.local()

        def get_session():
            if not hasattr(thread_local, "session"):
                thread_local.session = requests.Session()
            return thread_local.session

        def fetch_job(m_id):
            s = get_session()
            base = members_dict.get(m_id, {})
            return extract_builder_details(s, m_id, base)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(fetch_job, m_id): m_id for m_id in pending_ids}
            for fut in as_completed(futures):
                m_id = futures[fut]
                try:
                    res = fut.result()
                except Exception as err:
                    res = {"checked": True, "id_members": m_id, "error": str(err), **members_dict.get(m_id, {})}

                with lock:
                    processed += 1
                    details_cache[m_id] = res
                    if res.get("Email"):
                        newly_emails += 1
                        print(
                            f"[{processed}/{len(pending_ids)}] [+] {res.get('Company_Name', '')} ({res.get('EIK', '')}) -> {res['Email']} | Phone: {res.get('Phone', '')}"
                        )
                    elif res.get("Phone"):
                        print(
                            f"[{processed}/{len(pending_ids)}] [~] {res.get('Company_Name', '')} ({res.get('EIK', '')}) -> Phone: {res['Phone']} | No email"
                        )
                    else:
                        print(f"[{processed}/{len(pending_ids)}] [-] {res.get('Company_Name', '')} -> No contacts in register")

                    if processed % 25 == 0:
                        save_cache(details_cache, CACHE_DETAILS_PATH)
                        all_recs = list(details_cache.values())
                        tot, em = export_and_sync_csvs(all_recs)
                        print(f"    [*] Checkpoint saved ({processed}/{len(pending_ids)} | Total: {tot:,} | Emails: {em:,})")

        save_cache(details_cache, CACHE_DETAILS_PATH)

    all_records = list(details_cache.values())
    tot_rows, tot_em = export_and_sync_csvs(all_records)

    print("\n" + "=" * 80)
    print("DONE SCRAPING BULGARIAN CONSTRUCTION CHAMBER (register.ksb.bg)!")
    print(f"  Total companies  : {tot_rows:,}")
    print(f"  Companies w/ mail: {tot_em:,} ({tot_em * 100 / max(1, tot_rows):.1f}%)")
    print(f"  Master Output    : {OUTPUT_0RAW_PATH.name}")
    print(f"  Cold Mail 20-col : {OUTPUT_2COL_PATH.name}")
    print(f"  Ready for Send   : {OUTPUT_READY_PATH.name}")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Scraper for Bulgarian Construction Chamber (register.ksb.bg)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of companies to fetch in this run")
    parser.add_argument("--workers", type=int, default=8, help="Number of concurrent worker threads (default: 8)")
    parser.add_argument("--skip-list", action="store_true", help="Skip Phase 1 and use cached members list")
    parser.add_argument("--re-export", action="store_true", help="Re-export CSVs from cached JSON without fetching")
    args = parser.parse_args()

    if args.re_export:
        if CACHE_DETAILS_PATH.exists():
            with open(CACHE_DETAILS_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
            tot, em = export_and_sync_csvs(list(d.values()))
            print(f"[+] Re-exported {tot:,} companies ({em:,} with emails) from cache.")
        else:
            print("[!] No details cache found to re-export.")
        return

    run_pipeline(limit=args.limit, workers=args.workers, skip_list=args.skip_list)


if __name__ == "__main__":
    main()

