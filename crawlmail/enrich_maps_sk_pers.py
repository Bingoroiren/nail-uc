#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Maps Enrichment for Slovakia Employment Agencies (from personalneagentury.sk)
Input : SK_AGCY_PERS_0RAW.csv
Output: SK_AGCY_PERS_1ENR.csv, SK_AGCY_PERS_2COL.csv
Strictly adheres to GEMINI.md:
- headless=False with Chrome persistent context
- Single quote on phone numbers (')
- B2B email scoring, 100% emails on top
- Incremental auto-save and cache checkpoint
"""

import os
import sys
import re
import json
import time
import asyncio
import urllib.parse
from pathlib import Path
import pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = BASE_DIR / "SK_AGCY_PERS_0RAW.csv"
OUTPUT_1ENR = BASE_DIR / "SK_AGCY_PERS_1ENR.csv"
OUTPUT_2COL = BASE_DIR / "SK_AGCY_PERS_2COL.csv"
CACHE_FILE = BASE_DIR / "crawlmail" / "cache_enrich_sk_pers.json"
PROFILE_DIR = BASE_DIR / "chrome_user_data" / "sk_pers_profile"

COLDMAIL_COLUMNS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

BLACKLIST_DOMAINS = [
    'facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'twitter.com', 'x.com',
    'google.com', 'maps.google.com', 'yellowpages', 'zlatestranky.sk', 'finstat.sk',
    'orsr.sk', 'transparex.sk', 'personalneagentury.sk', 'slovakdata.sk', 'profesia.sk'
]

def clean_phone_sk(phone):
    if not phone or not isinstance(phone, str):
        return ""
    p = re.sub(r"[^\d+]", "", phone.strip().lstrip("'"))
    if not p:
        return ""
    if p.startswith("0") and len(p) == 10:
        p = "+421" + p[1:]
    elif not p.startswith("+") and len(p) == 9:
        p = "+421" + p
    return f"'{p}" if not p.startswith("'") else p

def clean_email(email):
    if not email or not isinstance(email, str):
        return ""
    e = email.replace("mailto:", "").split("?")[0].replace("%20", "").strip().lower()
    if "@" in e and "." in e.split("@")[-1] and not any(bad in e for bad in ["example", "sentry", "wix", "wordpress"]):
        return e
    return ""

async def crawl_email_from_website(page, website):
    if not website or not website.startswith("http"):
        return ""
    emails = set()
    try:
        await page.goto(website, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(1.0)
        content = await page.content()
        # Find mailto links
        for m in re.findall(r'href=["\']mailto:([^"?\'>\s]+)', content, re.I):
            ce = clean_email(m)
            if ce:
                emails.add(ce)
        # Find email regex
        for em in re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b', content):
            ce = clean_email(em)
            if ce:
                emails.add(ce)
                
        # If no email on homepage, check kontakt subpage
        if not emails:
            for sub in ["/kontakt", "/kontakt.html", "/contact", "/o-nas"]:
                try:
                    sub_url = urllib.parse.urljoin(website, sub)
                    await page.goto(sub_url, wait_until="domcontentloaded", timeout=10000)
                    await asyncio.sleep(0.8)
                    sub_content = await page.content()
                    for m in re.findall(r'href=["\']mailto:([^"?\'>\s]+)', sub_content, re.I):
                        ce = clean_email(m)
                        if ce:
                            emails.add(ce)
                    if emails:
                        break
                except Exception:
                    pass
    except Exception:
        pass

    if not emails:
        return ""
    # Select best email
    return sorted(list(emails), key=lambda x: (
        0 if any(k in x for k in ["praca@", "kariera@", "hr@", "jobs@"]) else
        1 if any(k in x for k in ["vedenie@", "riaditel@", "ceo@"]) else
        2 if any(k in x for k in ["info@", "kontakt@", "office@"]) else 3
    ))[0]

def save_checkpoint(df):
    df_out = df.copy()
    if 'SĐT' in df_out.columns:
        df_out['SĐT'] = df_out['SĐT'].apply(clean_phone_sk)
        
    has_em = df_out[df_out['Email'].notna() & (df_out['Email'].astype(str).str.strip() != '') & (df_out['Email'].astype(str).str.strip() != 'nan')].copy()
    no_em = df_out[df_out['Email'].isna() | (df_out['Email'].astype(str).str.strip() == '') | (df_out['Email'].astype(str).str.strip() == 'nan')].copy()
    df_sorted = pd.concat([has_em, no_em], ignore_index=True)
    df_sorted['No.'] = range(1, len(df_sorted) + 1)
    
    # Save 1ENR
    df_sorted.to_csv(OUTPUT_1ENR, index=False, encoding='utf-8-sig')
    
    # Format 2COL
    cold_rows = []
    for _, r in df_sorted.iterrows():
        cold_rows.append({
            'No.': r.get('No.', ''),
            'Công ty': r.get('Name', r.get('Công ty', '')),
            'Chức danh': 'Vadovas / Konateľ',
            'Người liên hệ': '',
            'SĐT': clean_phone_sk(r.get('Phone', r.get('SĐT', ''))),
            'Liên Hệ': r.get('Web', r.get('Liên Hệ', '')),
            'Email': r.get('Email', ''),
            'Liên Hệ mail': f"mailto:{r.get('Email', '')}" if r.get('Email') else '',
            'Địa chỉ': r.get('Address', r.get('Địa chỉ', '')),
            'Lương': '', 'Ngày đăng': '', 'Hạn tuyển': '',
            'Check gửi': 'Chưa gửi',
            'Last Subject': '', 'Last Body HTML': '', 'Trạng thái Reply': '',
            'Lần Follow-up': '0', 'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': r.get('NACE', 'Agentúry sprostredkujúce zamestnanie')
        })
    df_cold = pd.DataFrame(cold_rows)
    df_cold.to_csv(OUTPUT_2COL, index=False, encoding='utf-8-sig')
    return len(has_em)

async def main():
    print("=" * 75)
    print("🚀 LÀM GIÀU DỮ LIỆU GOOGLE MAPS - SLOVAKIA PERSONALNE AGENTURY")
    print(f"📁 Tệp đầu vào: {INPUT_CSV}")
    print(f"📁 Tệp xuất: {OUTPUT_2COL}")
    print("=" * 75)

    if not INPUT_CSV.exists():
        print(f"❌ Không tìm thấy tệp {INPUT_CSV}")
        return

    df = pd.read_csv(INPUT_CSV, encoding='utf-8-sig', dtype=str).fillna('')
    total = len(df)
    print(f"[*] Tổng số doanh nghiệp cần kiểm tra: {total}")

    cache = {}
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
            print(f"[*] Đã nạp Cache: {len(cache)} công ty đã kiểm tra từ trước.")
        except Exception:
            pass

    # Apply cache to df
    for idx in df.index:
        name_k = str(df.at[idx, 'Name']).strip().lower()
        if name_k in cache:
            item = cache[name_k]
            if item.get('email') and not df.at[idx, 'Email']:
                df.at[idx, 'Email'] = item['email']
            if item.get('web') and not df.at[idx, 'Web']:
                df.at[idx, 'Web'] = item['web']
            if item.get('phone') and not df.at[idx, 'Phone']:
                df.at[idx, 'Phone'] = item['phone']

    unprocessed = [idx for idx in df.index if not df.at[idx, 'Email'] and str(df.at[idx, 'Name']).strip().lower() not in cache]
    print(f"[*] Số công ty cần làm giàu Google Maps: {len(unprocessed)}")

    if not unprocessed:
        print("✅ Toàn bộ công ty đã có dữ liệu hoặc đã nằm trong cache!")
        save_checkpoint(df)
        return

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={'width': 1280, 'height': 800},
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()

        processed = 0
        for idx in unprocessed:
            comp_name = str(df.at[idx, 'Name']).strip()
            city = str(df.at[idx, 'City']).strip()
            cache_k = comp_name.lower()

            print(f"[{processed+1:04d}/{len(unprocessed):04d}] {comp_name[:35]:<35} | ", end="", flush=True)

            query = f"{comp_name} {city} Slovensko" if city else f"{comp_name} Slovensko"
            url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(query)}"

            found_web = ""
            found_phone = ""
            found_email = ""

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=18000)
                await asyncio.sleep(1.0)

                # Cookie accept
                try:
                    btn = await page.query_selector('button:has-text("Accept all"), button:has-text("Prijať všetko")')
                    if btn:
                        await btn.click()
                        await asyncio.sleep(0.5)
                except Exception:
                    pass

                # Extract Website and Phone from Google Maps place card
                web_el = await page.query_selector('a[data-item-id="authority"]')
                if web_el:
                    w = await web_el.get_attribute("href")
                    if w and not any(bad in w for bad in BLACKLIST_DOMAINS):
                        found_web = w.strip()

                phone_el = await page.query_selector('button[data-item-id^="phone:"]')
                if phone_el:
                    ph = await phone_el.get_attribute("data-item-id")
                    if ph:
                        found_phone = clean_phone_sk(ph.replace("phone:tel:", ""))

                if found_web:
                    found_email = await crawl_email_from_website(page, found_web)
                    print(f"GMAP->WEB: {found_web[:22]:<22} | EMAIL: {found_email if found_email else '(Chưa thấy mail)'}")
                elif found_phone:
                    print(f"GMAP: {found_phone:<18} | (Khớp Maps - Có SĐT)")
                else:
                    print(f"No match | (Không tìm thấy trên Maps)")

            except Exception as e:
                print(f"Error: {e}")

            if found_web:
                df.at[idx, 'Web'] = found_web
            if found_phone:
                df.at[idx, 'Phone'] = found_phone
            if found_email:
                df.at[idx, 'Email'] = found_email

            cache[cache_k] = {
                'web': found_web,
                'phone': found_phone,
                'email': found_email,
                'time': time.strftime("%Y-%m-%d %H:%M:%S")
            }

            processed += 1

            if processed % 10 == 0:
                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(cache, f, ensure_ascii=False, indent=2)
                cur_emails = save_checkpoint(df)
                print(f"  --> [CHECKPOINT] Đã lưu tăng dần! Hiện có {cur_emails} công ty có Email.")

        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        final_em = save_checkpoint(df)
        print("\n" + "=" * 75)
        print(f"🎉 HOÀN THÀNH LÀM GIÀU DỮ LIỆU! Tổng có Email: {final_em}")
        print("=" * 75)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
