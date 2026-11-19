# -*- coding: utf-8 -*-
"""
GOOGLE MAPS ENRICHMENT FOR ROMANIAN EMPLOYMENT AGENCIES (RO_AGCY_GMAP)
======================================================================
Input  : RO_AGCY_DIR0_1ENR.csv (892 unique agencies enriched with ANAF/CompanyWall/PaginiAurii)
Scope  : By default targets Active / Unmatched agencies missing Email (or Phone), skipping
         ANAF-dissolved / inactive entities (use --include-inactive to include all).
Phases :
  1. Playwright JS + HTTP Deep Re-Crawl of existing directory Websites / Facebook links
     that returned no email via plain HTTP (handles JS-rendered contact pages).
  2. Visual Chrome Google Maps Search (headless=False, 1280x800, hl=ro) with Strict
     Delimiter-Aware Name Matching (NFKD + Romanian diacritics + legal forms) -> Phone ('),
     Website, Facebook, Address, Permanently Closed detection -> Deep Email Crawl.

Outputs (UTF-8 with BOM, utf-8-sig):
  - RO_AGCY_GMAP_1ENR.csv (Master enriched dataset)
  - RO_AGCY_GMAP_2COL.csv (Cold Mail 20-col format, with_email sorted first)
  - RO_AGCY_GMAP_ONLY_EMAILS_READY.csv (Filtered ready-to-send leads)
  - ro_romania/RO_AGCY_GMAP_1ENR.csv + ro_romania/RO_AGCY_GMAP_2COL.csv
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
import urllib.parse
from pathlib import Path

import pandas as pd
from playwright.async_api import async_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
RO_DIR = ROOT_DIR / "ro_romania"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from enrich_ro_directories import (  # noqa: E402
    COLDMAIL_COLUMNS,
    INVALID_EXTS,
    clean_company_for_match,
    clean_email,
    clean_text,
    collect_prioritized_subpages_ro,
    ensure_phone_quote,
    extract_emails_from_html,
    fetch_html_fast,
    is_blacklisted_company,
    is_facebook_url,
    is_valid_website,
    normalize_ro_phones,
    normalize_website_url,
    score_email_b2b_ro,
    select_best_email,
    strip_diacritics,
)

INPUT_DIR0_1ENR = ROOT_DIR / "RO_AGCY_DIR0_1ENR.csv"
INPUT_DIR0_FALLBACK = RO_DIR / "RO_AGCY_DIR0_1ENR.csv"
BACKUP_DIR0_1ENR = RO_DIR / "backup_RO_AGCY_DIR0_1ENR.csv"
CACHE_FILE = SCRIPT_DIR / "cache_enrich_maps_ro_agcy.json"

OUTPUT_1ENR_PATH = ROOT_DIR / "RO_AGCY_GMAP_1ENR.csv"
OUTPUT_2COL_PATH = ROOT_DIR / "RO_AGCY_GMAP_2COL.csv"
OUTPUT_READY_PATH = ROOT_DIR / "RO_AGCY_GMAP_ONLY_EMAILS_READY.csv"

UA_STRING = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

INACTIVE_ANAF_RE = re.compile(r"RADIER|DIZOLV|FALIMENT|INACTIV|SUSPENDAT|INSOLV", re.I)

LOCATION_SUFFIX_TOKENS = {"romania", "ro", "bucuresti", "bucharest"}

MAPS_TIMEOUT_MS = 22000
WEB_TIMEOUT_MS = 12000
DELAY_AFTER_SEARCH = 2.0
DELAY_AFTER_CLICK = 1.4


def extract_clean_city_ro(city_raw: str, judet_raw: str = "", addr_raw: str = "") -> str:
    """Clean administrative prefixes ('Mun. ', 'Ors. ', 'Sectorul X') into searchable Romanian city."""
    c = strip_diacritics(city_raw or "")
    c = re.sub(r"\b(?:mun\.?|municipiul|ors\.?|orasul|oras|com\.?|comuna|sat|loc\.?)\b", " ", c)
    if "bucuresti" in c or "bucharest" in c:
        return "Bucuresti"
    c = re.sub(r"\bsector(?:ul)?\s*\d+\b", " ", c)
    c = re.sub(r"\s+", " ", c).strip(" ,.-")
    if c:
        return c.title()

    j = strip_diacritics(judet_raw or "")
    j = re.sub(r"\bjud(?:etul)?\.?\b", " ", j)
    j = re.sub(r"\s+", " ", j).strip(" ,.-")
    if "bucuresti" in j:
        return "Bucuresti"
    if j:
        return j.title()

    m_city = re.search(r"(?:MUN\.?|OR[SŞ]\.?|LOC\.?)\s*([A-ZĂÂÎȘŢA-Za-z\-\s]{3,30})", addr_raw or "", re.I)
    if m_city:
        return clean_text(m_city.group(1)).split(",")[0].strip().title()
    return ""


def _norm_for_strict_match(name: str) -> str:
    """Normalize quotes, punctuation, '&', and Romanian diacritics cleanly."""
    s = strip_diacritics(name or "")
    s = re.sub(r'["\'`„“”«»]', " ", s)
    s = s.replace("&", " and ")
    s = re.sub(r"\s+", " ", s).strip(" ,.-")
    return s


def _strip_brackets(text: str) -> str:
    """Remove Google Maps auto-translated / explanatory (...) or [...] tags."""
    out = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", text or "")
    return re.sub(r"\s+", " ", out).strip(" ,.-")


def is_valid_name_match_ro_maps(
    query_names: list[str],
    candidate_name: str,
    city: str = "",
    judet: str = "",
) -> tuple[bool, str]:
    """
    Smart & Strict Delimiter-Aware Matching for Romanian Google Maps results.
    Supports exact match, NFKD diacritic folding, legal-suffix cleaning,
    bracket note stripping, delimiter splitting, and safe city/location suffixing.
    """
    if not candidate_name or not query_names:
        return False, "EMPTY"

    c_norm = _norm_for_strict_match(candidate_name)
    c_nobrk = _strip_brackets(c_norm)
    c_core = clean_company_for_match(c_nobrk)

    loc_tokens = set(LOCATION_SUFFIX_TOKENS)
    for tok in (strip_diacritics(city) + " " + strip_diacritics(judet)).split():
        clean_tok = re.sub(r"[^a-z0-9]", "", tok)
        if len(clean_tok) >= 2:
            loc_tokens.add(clean_tok)

    for raw_q in query_names:
        if not raw_q:
            continue
        q_norm = _norm_for_strict_match(raw_q)
        q_core = clean_company_for_match(_strip_brackets(q_norm))
        if not q_core and not q_norm:
            continue

        if q_norm and q_norm == c_norm:
            return True, "EXACT"
        if q_core and q_core == c_core:
            return True, "LEGAL_EXACT"
        if q_norm and c_nobrk and q_norm == c_nobrk:
            return True, "BRACKET_MATCH"
        if q_core and c_core and q_core == clean_company_for_match(c_nobrk):
            return True, "BRACKET_LEGAL"

        # Delimiter-separated variant matching (e.g. "Randstad - Bucuresti", "Lugera | Recrutare")
        for delim_src in (c_norm, c_nobrk):
            parts = [p.strip(" ,.-") for p in re.split(r"[-–—|/:,]", delim_src) if p.strip(" ,.-")]
            for p in parts:
                p_core = clean_company_for_match(p)
                if (q_norm and p == q_norm) or (q_core and len(q_core) >= 4 and p_core == q_core):
                    return True, "DELIMITER_MATCH"

        # Safe trailing location / country suffix match (e.g. "Lugera Romania", "Randstad Bucuresti")
        if q_core and len(q_core) >= 5 and c_core.startswith(q_core + " "):
            rem_tokens = [t for t in c_core[len(q_core) :].strip().split() if t]
            if rem_tokens and all(t in loc_tokens for t in rem_tokens):
                return True, "LOCATION_SUFFIX_MATCH"

    return False, "NO_MATCH"


def build_query_candidates(row: pd.Series) -> list[str]:
    """Return legal + alternate trade names from row for search & strict matching."""
    names: list[str] = []
    main_name = clean_text(row.get("Cong_Ty", ""))
    if main_name:
        names.append(main_name)
    alt = clean_text(row.get("Ten_Khac_Hoac_Cu", ""))
    if alt:
        for piece in re.split(r"[;|]", alt):
            p = clean_text(piece)
            if p and p not in names:
                names.append(p)
    return names


def build_maps_search_query(row: pd.Series) -> tuple[str, str]:
    """Construct clean Maps search string (<Core Name> <City/Judet> Romania)."""
    names = build_query_candidates(row)
    raw_name = names[0] if names else ""
    core = clean_company_for_match(raw_name)
    # Keep full name when cleaned core becomes too short/ambiguous (<= 3 chars)
    search_comp = raw_name if len(core) <= 3 else core.title()
    city = extract_clean_city_ro(row.get("City", ""), row.get("Judet", ""), row.get("Dia_Chi", ""))
    loc_label = f"{city} Romania" if city else "Romania"
    return f"{search_comp} {loc_label}".strip(), city or "Romania"


async def fetch_html_playwright(pw_page, url: str, timeout: int = WEB_TIMEOUT_MS) -> str:
    """Render page with Chromium for JS-heavy corporate / Facebook pages."""
    if not url or not pw_page:
        return ""
    try:
        resp = await pw_page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        if resp and resp.status >= 400:
            return ""
        await asyncio.sleep(1.5)
        return await pw_page.content()
    except Exception:
        return ""


async def crawl_website_pw_and_http(web_url: str, existing_fb: str = "", pw_page=None) -> tuple[str, str, str]:
    """
    Hybrid email extraction:
      1) Fast curl_cffi HTTP crawl with non-www + SSL fallbacks + Priority-10 DOM links
      2) Playwright Chromium JS-render fallback on homepage & top contact pages
      3) Facebook Fanpage /about fallback
    """
    found_emails: set[str] = set()
    fb_candidates: list[str] = []
    if existing_fb and is_facebook_url(existing_fb):
        fb_candidates.append(existing_fb)

    working_url = normalize_website_url(web_url)
    root = ""
    if working_url:
        parsed = urllib.parse.urlparse(working_url)
        host = parsed.netloc
        bare = host[4:] if host.lower().startswith("www.") else host
        root = f"{parsed.scheme}://{host}"

        home_html = ""
        for cand in dict.fromkeys([working_url, f"https://{bare}", f"http://{host}", f"http://{bare}"]):
            home_html = fetch_html_fast(cand, timeout=6.0, allow_insecure=True)
            if home_html:
                working_url = cand
                p_ok = urllib.parse.urlparse(working_url)
                root = f"{p_ok.scheme}://{p_ok.netloc}"
                break

        if not home_html and pw_page:
            home_html = await fetch_html_playwright(pw_page, working_url)
            if not home_html and bare != host:
                home_html = await fetch_html_playwright(pw_page, f"https://{bare}")
                if home_html:
                    working_url = f"https://{bare}"
                    root = working_url

        if home_html:
            found_emails |= extract_emails_from_html(home_html)
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(home_html, "html.parser")
                for a in soup.find_all("a", href=True):
                    if is_facebook_url(a["href"]):
                        fb = a["href"].split("?")[0]
                        if fb not in fb_candidates:
                            fb_candidates.append(fb)
            except Exception:
                pass

            best = select_best_email(found_emails, root)
            if best and score_email_b2b_ro(best, root) >= 95:
                return best, (fb_candidates[0] if fb_candidates else ""), "Website"

            subpages = collect_prioritized_subpages_ro(home_html, working_url)[:8]
            used_pw_fallback = False
            for sub_url in subpages:
                sub_html = fetch_html_fast(sub_url, timeout=5.0, allow_insecure=True)
                if not sub_html and pw_page and not used_pw_fallback:
                    sub_html = await fetch_html_playwright(pw_page, sub_url)
                    used_pw_fallback = True
                if not sub_html:
                    continue
                found_emails |= extract_emails_from_html(sub_html)
                best = select_best_email(found_emails, root)
                if best and score_email_b2b_ro(best, root) >= 95:
                    return best, (fb_candidates[0] if fb_candidates else ""), "Website"

            # If homepage + HTTP subpages yielded nothing (e.g. React/SPA contact page), try JS render on top 3 contact links
            if not select_best_email(found_emails, root) and pw_page:
                js_targets = [working_url] + subpages[:3]
                for ju in dict.fromkeys(js_targets):
                    jhtml = await fetch_html_playwright(pw_page, ju, timeout=9000)
                    if not jhtml:
                        continue
                    found_emails |= extract_emails_from_html(jhtml)
                    best = select_best_email(found_emails, root)
                    if best and score_email_b2b_ro(best, root) >= 95:
                        return best, (fb_candidates[0] if fb_candidates else ""), "Website"

            best = select_best_email(found_emails, root)
            if best:
                return best, (fb_candidates[0] if fb_candidates else ""), "Website"

    best_fb = fb_candidates[0] if fb_candidates else ""
    if best_fb:
        for fb_url in (best_fb.rstrip("/") + "/about", best_fb):
            fb_html = fetch_html_fast(fb_url, timeout=5.0, allow_insecure=True)
            if not fb_html and pw_page:
                fb_html = await fetch_html_playwright(pw_page, fb_url, timeout=11000)
            if fb_html:
                fb_best = select_best_email(extract_emails_from_html(fb_html), root)
                if fb_best:
                    return fb_best, best_fb, "Facebook"

    return "", best_fb, ""


def make_cache_key(row: pd.Series) -> str:
    """Stable deterministic checkpoint key by CUI or normalized company name."""
    cui = re.sub(r"\D", "", clean_text(row.get("Ma_Dinh_Danh_CUI", "")))
    if cui:
        return f"CUI:{cui}"
    return f"NAME:{strip_diacritics(row.get('Cong_Ty', ''))}"


def load_cache() -> dict:
    """Load Maps enrichment checkpoint cache JSON."""
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            pass
    return {}


def save_cache(cache: dict) -> None:
    """Atomic JSON cache save to protect progress on interruption."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CACHE_FILE)


def load_source_dataset() -> pd.DataFrame | None:
    """Load RO_AGCY_DIR0_1ENR.csv (preferred) or backup copy."""
    for cand in (INPUT_DIR0_1ENR, INPUT_DIR0_FALLBACK):
        if cand.exists():
            df = pd.read_csv(cand, encoding="utf-8-sig", dtype=str).fillna("")
            df = df[~df["Cong_Ty"].apply(is_blacklisted_company)].reset_index(drop=True)
            for col in ("Maps_Match", "Maps_Status", "Maps_URL", "Maps_Category", "Facebook_URL", "Email_Source"):
                if col not in df.columns:
                    df[col] = ""
            df["SDT"] = df["SDT"].apply(ensure_phone_quote)
            return df
    return None


def apply_cache_to_df(df: pd.DataFrame, cache: dict) -> None:
    """Merge cached Google Maps & Phase 1 enrichment onto loaded DataFrame."""
    if not cache:
        return
    for idx, row in df.iterrows():
        rec = cache.get(make_cache_key(row))
        if not rec:
            continue
        if rec.get("Website") and not is_valid_website(df.at[idx, "Website"]):
            df.at[idx, "Website"] = normalize_website_url(rec["Website"])
        if rec.get("Facebook_URL") and not clean_text(df.at[idx, "Facebook_URL"]):
            df.at[idx, "Facebook_URL"] = rec["Facebook_URL"]
        if rec.get("SDT") and not clean_text(df.at[idx, "SDT"]):
            df.at[idx, "SDT"] = ensure_phone_quote(rec["SDT"])
        if rec.get("Dia_Chi") and not clean_text(df.at[idx, "Dia_Chi"]):
            df.at[idx, "Dia_Chi"] = rec["Dia_Chi"]
        cand_em = clean_email(rec.get("Email", ""))
        if cand_em and score_email_b2b_ro(cand_em, df.at[idx, "Website"]) > 0:
            if not clean_email(df.at[idx, "Email"]):
                df.at[idx, "Email"] = cand_em
                df.at[idx, "Email_Source"] = rec.get("Email_Source", "")
        for mcol in ("Maps_Match", "Maps_Status", "Maps_URL", "Maps_Category"):
            if rec.get(mcol):
                df.at[idx, mcol] = rec[mcol]


def export_all_csvs(df: pd.DataFrame) -> int:
    """Export RO_AGCY_GMAP_1ENR, 2COL (email-first), ONLY_EMAILS_READY, and ro_romania/ mirrors."""
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
        link = (
            web
            or clean_text(r.get("Maps_URL", ""))
            or clean_text(r.get("CompanyWall_URL", ""))
            or clean_text(r.get("PaginiAurii_URL", ""))
        )
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
        if clean_text(r.get("Maps_Category", "")):
            cat_parts.append(clean_text(r.get("Maps_Category", "")))
        if clean_text(r.get("Maps_Status", "")):
            cat_parts.append(f"Maps: {clean_text(r.get('Maps_Status', ''))}")
        elif clean_text(r.get("Trang_Thai_ANAF", "")):
            cat_parts.append(f"ANAF: {clean_text(r.get('Trang_Thai_ANAF', ''))}")

        coldmail_rows.append(
            {
                "No.": r.get("No.", ""),
                "Công ty": comp,
                "Chức danh": chuc_danh,
                "Người liên hệ": admin,
                "SĐT": phone,
                "Liên Hệ": link,
                "Email": email,
                "Liên Hệ mail": f"mailto:{email}" if email else link,
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


def _ring_captcha_bell() -> None:
    """Beep audibly on Windows + terminal bell so operator spots Captcha immediately."""
    print("\a" * 3, flush=True)
    try:
        import winsound
        winsound.Beep(1200, 350)
        winsound.Beep(900, 350)
    except Exception:
        pass


async def handle_google_captcha_if_present(maps_page, df: pd.DataFrame, cache: dict) -> bool:
    """Save progress immediately and pause cleanly if Google presents Captcha / /sorry."""
    cur_u = maps_page.url.lower()
    page_txt_low = (await maps_page.content()).lower()
    has_recaptcha = await maps_page.query_selector("iframe[src*='recaptcha']")
    if (
        "/sorry/" in cur_u
        or "captcha" in cur_u
        or "unusual traffic" in page_txt_low
        or "trafic neobișnuit" in page_txt_low
        or has_recaptcha
    ):
        save_cache(cache)
        export_all_csvs(df)
        _ring_captcha_bell()
        print("\n[!] GOOGLE CAPTCHA / RATE-LIMIT DETECTED! Progress saved cleanly.")
        print("    Please solve the Captcha directly in Chrome, then press ENTER here to continue...")
        await asyncio.to_thread(input, "")
        return True
    return False


async def extract_maps_place_fields(maps_page) -> dict:
    """Extract Website, Facebook URL, Phone, Address, Category, Closed Status from open Maps panel."""
    out = {"website": "", "fb": "", "phone": "", "addr": "", "category": "", "status": "OPEN"}

    web_btn = await maps_page.query_selector(
        'a[data-item-id="authority"], a[aria-label*="Site web"], a[aria-label*="Website"]'
    )
    if web_btn:
        w_href = (await web_btn.get_attribute("href") or "").strip()
        if is_valid_website(w_href):
            out["website"] = normalize_website_url(w_href)
        elif is_facebook_url(w_href):
            out["fb"] = w_href.split("?")[0]

    phone_btn = await maps_page.query_selector(
        'button[data-item-id^="phone:"], button[aria-label*="Telefon"], button[aria-label*="Phone"]'
    )
    if phone_btn:
        p_attr = await phone_btn.get_attribute("data-item-id") or ""
        raw_ph = p_attr.replace("phone:tel:", "") if p_attr.startswith("phone:tel:") else await phone_btn.inner_text()
        p1, _ = normalize_ro_phones([raw_ph])
        out["phone"] = p1 or ensure_phone_quote(re.sub(r"[^\d+]", "", raw_ph))

    addr_btn = await maps_page.query_selector(
        'button[data-item-id="address"], button[aria-label*="Adresă"], button[aria-label*="Adresa"], button[aria-label*="Address"]'
    )
    if addr_btn:
        raw_a = clean_text(await addr_btn.inner_text())
        out["addr"] = re.sub(r"^(?:Adres[ăa]|Address)\s*:?\s*", "", raw_a, flags=re.I).strip()

    cat_btn = await maps_page.query_selector('button[jsaction*="category"]')
    if cat_btn:
        out["category"] = clean_text(await cat_btn.inner_text())

    body_txt = strip_diacritics(await maps_page.evaluate("() => document.body ? document.body.innerText.slice(0, 3500) : ''"))
    if "inchis definitiv" in body_txt or "permanently closed" in body_txt:
        out["status"] = "PERMANENTLY_CLOSED"
    elif "inchis temporar" in body_txt or "temporarily closed" in body_txt:
        out["status"] = "TEMPORARILY_CLOSED"

    return out


async def run_enrichment(
    headless: bool = False,
    limit: int | None = None,
    skip_phase1: bool = False,
    phase1_only: bool = False,
    force_retry: bool = False,
    include_inactive: bool = False,
    proxy: str = "",
) -> None:
    """Execute Phase 1 JS-rendered web re-crawl + Phase 2 Visual Google Maps enrichment."""
    df = load_source_dataset()
    if df is None:
        print(f"[!] Input CSV not found: {INPUT_DIR0_1ENR.name} or {INPUT_DIR0_FALLBACK}")
        return

    if INPUT_DIR0_1ENR.exists() and not BACKUP_DIR0_1ENR.exists():
        BACKUP_DIR0_1ENR.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(INPUT_DIR0_1ENR, BACKUP_DIR0_1ENR)
        print(f"[+] Created one-time backup: {BACKUP_DIR0_1ENR.relative_to(ROOT_DIR)}")

    cache = {} if force_retry else load_cache()
    apply_cache_to_df(df, cache)

    def _is_eligible(row: pd.Series) -> bool:
        if include_inactive:
            return True
        st = clean_text(row.get("Trang_Thai_ANAF", ""))
        return not bool(st and INACTIVE_ANAF_RE.search(st))

    eligible_mask = df.apply(_is_eligible, axis=1)
    missing_email_idx = [i for i, r in df.iterrows() if eligible_mask.iloc[i] and not clean_email(r["Email"])]
    missing_phone_only_idx = [
        i for i, r in df.iterrows()
        if eligible_mask.iloc[i] and clean_email(r["Email"]) and not clean_text(r["SDT"])
    ]

    print("=" * 82)
    print("GOOGLE MAPS ENRICHMENT - ROMANIAN EMPLOYMENT AGENCIES (RO_AGCY_GMAP)")
    print(f"  Source CSV      : {INPUT_DIR0_1ENR.name} ({len(df):,} total, {int(eligible_mask.sum()):,} eligible)")
    print(f"  Already Email   : {int((df['Email'] != '').sum()):,}")
    print(f"  Pending Email   : {len(missing_email_idx):,}")
    print(f"  Missing Phone   : {len(missing_phone_only_idx):,} (eligible rows with Email)")
    print(f"  Browser Mode    : {'HEADLESS' if headless else 'VISUAL (headless=False, 1280x800)'}")
    if proxy:
        print(f"  Proxy           : {proxy}")
    print("=" * 82 + "\n")

    launch_kwargs: dict = {
        "headless": headless,
        "args": ["--start-maximized", "--no-sandbox"],
    }
    if proxy:
        launch_kwargs["proxy"] = {"server": proxy}

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(channel="chrome", **launch_kwargs)
        except Exception:
            browser = await p.chromium.launch(**launch_kwargs)

        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="ro-RO",
            user_agent=UA_STRING,
        )
        await context.add_cookies(
            [{"name": "SOCS", "value": "CAESEwgDEgk2OTQ0NTgyODQaAmVuIAEaBgiA_LyaBg", "domain": ".google.com", "path": "/"}]
        )
        maps_page = await context.new_page()
        web_page = await context.new_page()

        phase1_found = 0
        newly_email = 0
        newly_phone = 0
        newly_web = 0

        try:
            # PHASE 1: Playwright-backed re-crawl of existing directory Websites without email
            if not skip_phase1:
                p1_targets = [
                    i for i in missing_email_idx
                    if (is_valid_website(df.at[i, "Website"]) or is_facebook_url(df.at[i, "Facebook_URL"]))
                    and (force_retry or not cache.get(make_cache_key(df.loc[i]), {}).get("phase1_done"))
                ]
                if limit:
                    p1_targets = p1_targets[:limit]

                print("-" * 82)
                print(f"  PHASE 1: Playwright + HTTP Re-Crawl of {len(p1_targets):,} Existing Directory Websites")
                print("-" * 82)

                for p1_pos, idx in enumerate(p1_targets, 1):
                    row = df.loc[idx]
                    key = make_cache_key(row)
                    comp = clean_text(row["Cong_Ty"])
                    web_u = clean_text(row["Website"])
                    fb_u = clean_text(row["Facebook_URL"])

                    em_found, fb_found, em_src = await crawl_website_pw_and_http(web_u, existing_fb=fb_u, pw_page=web_page)
                    if fb_found and not df.at[idx, "Facebook_URL"]:
                        df.at[idx, "Facebook_URL"] = fb_found
                    if em_found:
                        df.at[idx, "Email"] = em_found
                        df.at[idx, "Email_Source"] = em_src
                        phase1_found += 1
                        print(f"  [{p1_pos}/{len(p1_targets)}] [+] JS WEB MAIL ({em_src}): {comp} -> {em_found}")
                    else:
                        print(f"  [{p1_pos}/{len(p1_targets)}] [-] Still no public email: {web_u or fb_u}")

                    prev = cache.get(key, {})
                    prev.update(
                        {
                            "Website": df.at[idx, "Website"],
                            "Facebook_URL": df.at[idx, "Facebook_URL"],
                            "Email": df.at[idx, "Email"],
                            "Email_Source": df.at[idx, "Email_Source"],
                            "SDT": ensure_phone_quote(df.at[idx, "SDT"]),
                            "Dia_Chi": df.at[idx, "Dia_Chi"],
                            "phase1_done": True,
                        }
                    )
                    cache[key] = prev
                    save_cache(cache)

                cur_em = export_all_csvs(df)
                print(f"[*] Phase 1 completed: +{phase1_found} email(s) (Total ready: {cur_em:,})\n")
                if phase1_only:
                    return

            # PHASE 2: Visual Google Maps Enrichment
            all_pending = [
                i for i, r in df.iterrows()
                if eligible_mask.iloc[i]
                and (not clean_email(r["Email"]) or not clean_text(r["SDT"]))
            ]
            if not force_retry:
                pending = [i for i in all_pending if not cache.get(make_cache_key(df.loc[i]), {}).get("maps_done")]
            else:
                pending = all_pending

            if limit:
                pending = pending[:limit]

            print("-" * 82)
            print(f"  PHASE 2: Visual Google Maps Enrichment - Pending: {len(pending):,}")
            print("-" * 82)

            if not pending:
                cur_em = export_all_csvs(df)
                print(f"[+] No pending agencies left! Total ready with Email: {cur_em:,}")
                return

            processed = 0
            for idx in pending:
                row = df.loc[idx]
                key = make_cache_key(row)
                comp = clean_text(row["Cong_Ty"])
                query_names = build_query_candidates(row)
                maps_query, city_clean = build_maps_search_query(row)
                judet = clean_text(row.get("Judet", ""))
                maps_url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(maps_query)}?hl=ro"

                processed += 1
                print(f"[{processed}/{len(pending)}] Searching: {maps_query}")

                m_info = {"website": "", "fb": "", "phone": "", "addr": "", "category": "", "status": ""}
                matched = False
                match_reason = "NO_MATCH"
                found_email = ""
                email_src = ""
                place_url = ""

                try:
                    await maps_page.goto(maps_url, wait_until="domcontentloaded", timeout=MAPS_TIMEOUT_MS)
                    await asyncio.sleep(DELAY_AFTER_SEARCH + random.uniform(0.1, 0.5))

                    if "consent.google.com" in maps_page.url.lower():
                        c_btn = await maps_page.query_selector(
                            'button:has-text("Acceptă tot"), button:has-text("Accept all"), form[action*="consent"] button'
                        )
                        if c_btn:
                            await c_btn.click()
                            await asyncio.sleep(2.2)

                    await handle_google_captcha_if_present(maps_page, df, cache)

                    try:
                        await maps_page.wait_for_selector(
                            'h1.DUwDvf, div[role="feed"] a.hfpxzc[href*="/maps/place/"]',
                            timeout=7000,
                        )
                        await asyncio.sleep(0.8)
                    except Exception:
                        pass

                    h1 = await maps_page.query_selector("h1.DUwDvf")
                    h1_name = clean_text(await h1.inner_text()) if h1 else ""
                    if h1_name:
                        h1_ok, h1_reason = is_valid_name_match_ro_maps(query_names, h1_name, city_clean, judet)
                        if h1_ok:
                            matched, match_reason = True, h1_reason

                    if not matched:
                        cards = await maps_page.query_selector_all(
                            'div[role="feed"] a.hfpxzc[href*="/maps/place/"]'
                        )
                        best_card = None
                        best_reason = "NO_MATCH"
                        for card in cards[:6]:
                            cand_name = clean_text(await card.get_attribute("aria-label") or await card.inner_text())
                            ok, reason = is_valid_name_match_ro_maps(query_names, cand_name, city_clean, judet)
                            if ok:
                                best_card = card
                                best_reason = reason
                                break
                        if best_card is not None:
                            matched = True
                            match_reason = best_reason
                            await best_card.click()
                            try:
                                await maps_page.wait_for_selector("h1.DUwDvf", timeout=5000)
                            except Exception:
                                pass
                            await asyncio.sleep(DELAY_AFTER_CLICK)

                    if matched:
                        place_url = maps_page.url.split("&entry=")[0]
                        m_info = await extract_maps_place_fields(maps_page)
                        target_web = m_info["website"] or (
                            df.at[idx, "Website"] if is_valid_website(df.at[idx, "Website"]) else ""
                        )
                        target_fb = m_info["fb"] or clean_text(df.at[idx, "Facebook_URL"])

                        if not clean_email(df.at[idx, "Email"]) and (target_web or target_fb):
                            found_email, fb_from_site, email_src = await crawl_website_pw_and_http(
                                target_web, existing_fb=target_fb, pw_page=web_page
                            )
                            if fb_from_site and not m_info["fb"]:
                                m_info["fb"] = fb_from_site

                        if not clean_email(df.at[idx, "Email"]) and not found_email:
                            panel_best = select_best_email(extract_emails_from_html(await maps_page.content()), target_web)
                            if panel_best:
                                found_email = panel_best
                                email_src = "GoogleMaps"
                except Exception as err:
                    print(f"    [!] Maps lookup error: {err}")

                if m_info["website"] and not is_valid_website(df.at[idx, "Website"]):
                    df.at[idx, "Website"] = m_info["website"]
                    newly_web += 1
                if m_info["fb"] and not clean_text(df.at[idx, "Facebook_URL"]):
                    df.at[idx, "Facebook_URL"] = m_info["fb"]
                if m_info["phone"] and not clean_text(df.at[idx, "SDT"]):
                    df.at[idx, "SDT"] = ensure_phone_quote(m_info["phone"])
                    newly_phone += 1
                if m_info["addr"] and not clean_text(df.at[idx, "Dia_Chi"]):
                    df.at[idx, "Dia_Chi"] = m_info["addr"]
                if found_email and not clean_email(df.at[idx, "Email"]):
                    df.at[idx, "Email"] = found_email
                    df.at[idx, "Email_Source"] = email_src
                    newly_email += 1

                if matched:
                    df.at[idx, "Maps_Match"] = match_reason
                    df.at[idx, "Maps_Status"] = m_info["status"]
                    df.at[idx, "Maps_URL"] = place_url
                    if m_info["category"]:
                        df.at[idx, "Maps_Category"] = m_info["category"]

                if found_email:
                    print(
                        f"    [+] EMAIL ({email_src} | {match_reason}): {found_email} | "
                        f"Web: {m_info['website'] or df.at[idx, 'Website'] or '-'} | "
                        f"Phone: {m_info['phone'] or df.at[idx, 'SDT'] or '-'}"
                    )
                elif matched and (m_info["website"] or m_info["phone"] or m_info["status"] != "OPEN"):
                    print(
                        f"    [~] MAPS MATCH ({match_reason} | {m_info['status']}): "
                        f"Web: {m_info['website'] or '-'} | Phone: {m_info['phone'] or '-'}"
                    )
                else:
                    print(f"    [-] No strict Maps match ({match_reason}).")

                cache[key] = {
                    "Website": df.at[idx, "Website"],
                    "Facebook_URL": df.at[idx, "Facebook_URL"],
                    "SDT": ensure_phone_quote(df.at[idx, "SDT"]),
                    "Dia_Chi": df.at[idx, "Dia_Chi"],
                    "Email": df.at[idx, "Email"],
                    "Email_Source": df.at[idx, "Email_Source"],
                    "Maps_Match": df.at[idx, "Maps_Match"],
                    "Maps_Status": df.at[idx, "Maps_Status"],
                    "Maps_URL": df.at[idx, "Maps_URL"],
                    "Maps_Category": df.at[idx, "Maps_Category"],
                    "phase1_done": True,
                    "maps_done": True,
                }
                save_cache(cache)

                if processed % 5 == 0:
                    cur_em = export_all_csvs(df)
                    print(
                        f"    [*] Checkpoint CSV ({processed}/{len(pending)} | Total Emails: {cur_em:,} | "
                        f"+{newly_email} email, +{newly_phone} phone, +{newly_web} web)"
                    )

                await asyncio.sleep(random.uniform(0.7, 1.3))
        finally:
            save_cache(cache)
            cur_em = export_all_csvs(df)
            await browser.close()

    print("\n" + "=" * 82)
    print("GOOGLE MAPS ENRICHMENT COMPLETED - ROMANIAN AGENCIES (RO_AGCY_GMAP)")
    print(f"  Total Agencies   : {len(df):,}")
    print(f"  B2B Emails Ready : {cur_em:,}")
    print(f"  Total Phones     : {(df['SDT'] != '').sum():,} (+{newly_phone} new this run)")
    print(f"  Websites Found   : {(df['Website'] != '').sum():,} (+{newly_web} new this run)")
    print(f"  Added Emails     : +{phase1_found + newly_email} this run")
    print(f"  Outputs          : {OUTPUT_1ENR_PATH.name} | {OUTPUT_2COL_PATH.name} | {OUTPUT_READY_PATH.name}")
    print("=" * 82)


def main() -> None:
    parser = argparse.ArgumentParser(description="Google Maps Enrichment for RO_AGCY_DIR0_1ENR.csv")
    parser.add_argument("--headless", action="store_true", help="Run headless Chromium (default: visible Chrome)")
    parser.add_argument("--limit", type=int, default=None, help="Only process first N pending companies")
    parser.add_argument("--skip-phase1", action="store_true", help="Skip Playwright re-crawl on existing websites")
    parser.add_argument("--phase1-only", action="store_true", help="Only run Phase 1 website JS re-crawl")
    parser.add_argument("--force-retry", action="store_true", help="Ignore Maps cache and retry from start")
    parser.add_argument("--include-inactive", action="store_true", help="Also query ANAF-inactive/dissolved companies")
    parser.add_argument("--proxy", type=str, default="", help="Optional Chromium proxy URL (e.g. http://ip:port)")
    parser.add_argument("--re-export", action="store_true", help="Only re-export CSV outputs from existing cache")
    args = parser.parse_args()

    if args.re_export:
        df = load_source_dataset()
        if df is not None:
            apply_cache_to_df(df, load_cache())
            cnt = export_all_csvs(df)
            print(f"[RE-EXPORT] Exported {len(df):,} rows ({cnt:,} with clean B2B Email)")
        return

    asyncio.run(
        run_enrichment(
            headless=args.headless,
            limit=args.limit,
            skip_phase1=args.skip_phase1,
            phase1_only=args.phase1_only,
            force_retry=args.force_retry,
            include_inactive=args.include_inactive,
            proxy=args.proxy,
        )
    )


if __name__ == "__main__":
    main()
