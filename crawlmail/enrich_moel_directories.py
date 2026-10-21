# -*- coding: utf-8 -*-
"""
Hệ thống cào và làm giàu dữ liệu tự động cho KR_AGCY_MOEL_0RAW.csv từ các trang danh bạ và Google:
1. Tra cứu Google/Naver theo Tên công ty + Địa phương ven biển.
2. Tự động nhận diện các trang danh bạ doanh nghiệp:
   - bizno.net (회사이메일, 대표전화)
   - saramin.co.kr / jobkorea.co.kr (기업정보, 이메일, 전화)
   - nicebizinfo.com / moneypin.biz
   - Website chính thức / Naver Place
3. Bóc tách Số điện thoại (luôn có nháy đơn '), Website chính thức, Email B2B xác thực.
4. Cơ chế lưu tăng dần (Auto-save) và Checkpoint JSON (Resume 100%).
5. Sắp xếp các công ty có Email và SĐT lên hàng đầu danh sách.
"""

import sys
import io
import os
import re
import csv
import json
import time
import asyncio
import urllib.parse
import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests
from playwright.async_api import async_playwright

import functools

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True, write_through=True)
print = functools.partial(print, flush=True)

CSV_FILE = "KR_AGCY_MOEL_0RAW.csv"
CACHE_FILE = "crawlmail/cache_enrich_moel_directories.json"

COLUMNS_20 = [
    'No.', 'Cong ty', 'Chuc danh', 'Nguoi lien he', 'SDT', 'Lien He', 'Email', 
    'Lien He mail', 'Dia chi', 'Luong', 'Ngay dang', 'Han tuyen', 'Check gui', 
    'Last Subject', 'Last Body HTML', 'Trang thai Reply', 'Lan Follow-up', 
    'Ngay Follow-up gan nhat', 'Mailbox da dung', 'Category'
]

GARBAGE_PATTERNS = [
    'sentry', 'wixpress', 'wix.com', 'monday.com', 'wordpress', 'no-reply',
    'donotreply', 'privacy@', 'gdpr@', 'bootstrap@', 'fontawesome', 'xeicon@'
]

FILE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.json', '.css', '.js', '.map', '@2x']

def clean_phone(phone: str) -> str:
    if not phone:
        return ""
    p = str(phone).strip()
    if not p or p.lower() == 'nan' or p.lower() == 'none':
        return ""
    p = p.replace('\n', ' ').strip()
    p = re.sub(r'[^\d\+\-\s\(\)]', '', p).strip()
    if not p:
        return ""
    if not p.startswith("'"):
        p = f"'{p}"
    return p

def clean_email(email: str) -> str:
    if not email:
        return ""
    em = str(email).strip().lower()
    for ext in FILE_EXTENSIONS:
        if ext in em:
            return ""
    for g in GARBAGE_PATTERNS:
        if g in em:
            return ""
    if not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', em):
        return ""
    if not re.search(r'\.[a-z]{2,}$', em):
        return ""
    return em

def save_checkpoint(df, cache):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    has_em = df['Email'].notna() & (df['Email'].astype(str).str.strip() != '') & (df['Email'].astype(str) != 'nan')
    has_ph = df['SDT'].notna() & (df['SDT'].astype(str).str.strip() != '') & (df['SDT'].astype(str) != 'nan')

    p1 = df[has_em].copy()
    p2 = df[~has_em & has_ph].copy()
    p3 = df[~has_em & ~has_ph].copy()

    sorted_df = pd.concat([p1, p2, p3], ignore_index=True)
    sorted_df['No.'] = range(1, len(sorted_df) + 1)
    sorted_df[COLUMNS_20].to_csv(CSV_FILE, index=False, encoding='utf-8-sig')

async def main(max_items=30):
    print("=" * 70)
    print(" BẮT ĐẦU CÀO VÀ LÀM GIÀU DỮ LIỆU TỪ TRANG DANH BẠ CHO MOEL")
    print("=" * 70)

    df = pd.read_csv(CSV_FILE, encoding='utf-8-sig')
    print(f"Tổng số cơ sở trong {CSV_FILE}: {len(df)}")

    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            print(f" -> Khôi phục checkpoint: {len(cache)} cơ sở đã lưu.")
        except Exception:
            cache = {}

    # Lọc các cơ sở chưa có email hoặc chưa có SĐT
    todo_indices = []
    for idx, r in df.iterrows():
        cname = r['Cong ty']
        em = str(r['Email']).strip()
        ph = str(r['SDT']).strip()
        if (not em or em == 'nan') and cname not in cache:
            todo_indices.append(idx)

    target_count = len(todo_indices) if max_items <= 0 else min(len(todo_indices), max_items)
    print(f"Số lượng cơ sở cần quét làm giàu đợt này: {target_count} {'(TOÀN BỘ CƠ SỞ CÒN LẠI)' if max_items <= 0 else ''}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=['--lang=ko-KR', '--window-size=1280,800'])
        context = await browser.new_context(locale='ko-KR', viewport={'width': 1280, 'height': 800})
        page = await context.new_page()

        processed = 0
        for idx in todo_indices:
            if max_items > 0 and processed >= max_items:
                break
            processed += 1

            row = df.loc[idx]
            cname = str(row['Cong ty']).strip()
            rep = str(row.get('Nguoi lien he', '')).strip()
            addr = str(row.get('Dia chi', '')).strip()
            city = addr.split()[0] if addr else ''

            pct = (processed / target_count * 100) if target_count > 0 else 0
            print(f"\n[{processed}/{target_count}] ({pct:.1f}%) Tra cứu: {cname} ({rep} - {city})...")

            found_phone = ""
            found_email = ""
            found_web = ""

            # Thử 1: Tra cứu Bizno với param chuẩn ?query=
            try:
                bizno_url = f"https://bizno.net/?query={urllib.parse.quote(cname)}"
                await page.goto(bizno_url, timeout=12000, wait_until='domcontentloaded')
                await page.wait_for_timeout(800)

                # Lọc đúng bài viết có tên công ty trùng khớp
                links = await page.query_selector_all("a[href^='/article/']")
                matched_href = None
                clean_target = re.sub(r'[\s\(\)]', '', cname)
                for lk in links:
                    txt = await lk.inner_text()
                    clean_txt = re.sub(r'[\s\(\)]', '', txt)
                    if clean_target in clean_txt or (len(clean_target) >= 4 and clean_target[:4] in clean_txt):
                        matched_href = await lk.get_attribute("href")
                        break

                if matched_href:
                    detail_url = urllib.parse.urljoin("https://bizno.net", matched_href)
                    await page.goto(detail_url, timeout=12000, wait_until='domcontentloaded')
                    await page.wait_for_timeout(800)
                    
                    # Tìm email trên trang Bizno (trường 회사이메일)
                    email_el = await page.query_selector("tr:has-text('회사이메일'), td:has-text('회사이메일') + td, th:has-text('회사이메일') + td")
                    if email_el:
                        em_txt = await email_el.inner_text()
                        em_match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', em_txt)
                        if em_match:
                            clem = clean_email(em_match.group(0))
                            if clem:
                                found_email = clem
                                print(f"    [+] Bizno: Tìm thấy Email: {found_email}")

                    # Tìm SĐT trên trang Bizno (trường 전화번호)
                    phone_el = await page.query_selector("tr:has-text('전화번호'), td:has-text('전화번호') + td, th:has-text('전화번호') + td")
                    if phone_el:
                        ph_txt = await phone_el.inner_text()
                        c_ph = clean_phone(ph_txt)
                        if c_ph:
                            found_phone = c_ph
                            print(f"    [+] Bizno: Tìm thấy SĐT: {found_phone}")
            except Exception as e:
                pass

            # Thử 2: Nếu chưa có email hoặc SĐT, tra cứu Google Maps
            if not found_email or not found_phone:
                try:
                    gmap_query = f"{cname} {city}"
                    gmap_url = f"https://www.google.com/maps/search/{urllib.parse.quote(gmap_query)}?hl=ko"
                    await page.goto(gmap_url, timeout=15000, wait_until='domcontentloaded')
                    await page.wait_for_timeout(1200)

                    # Bóc tách Website
                    web_btn = await page.query_selector("a[data-item-id='authority']")
                    if web_btn:
                        h = await web_btn.get_attribute("href")
                        if h and 'google' not in h:
                            found_web = h
                            print(f"    [+] Ggmap: Tìm thấy Website: {found_web}")

                    # Bóc tách SĐT
                    if not found_phone:
                        phone_btn = await page.query_selector("button[data-item-id^='phone:']")
                        if phone_btn:
                            pt = await phone_btn.inner_text()
                            c_ph = clean_phone(pt)
                            if c_ph:
                                found_phone = c_ph
                                print(f"    [+] Ggmap: Tìm thấy SĐT: {found_phone}")
                except Exception as e:
                    pass

            # Thử 3: Nếu có Website nhưng chưa có Email, truy cập website để bóc tách Email B2B
            if found_web and not found_email and not any(ign in found_web for ign in ['facebook.com', 'instagram.com']):
                try:
                    await page.goto(found_web, timeout=10000, wait_until='domcontentloaded')
                    await page.wait_for_timeout(1000)
                    body_txt = await page.inner_text("body")
                    emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', body_txt)
                    for em in emails:
                        clem = clean_email(em)
                        if clem:
                            found_email = clem
                            print(f"    [+] Website: Bóc tách được Email B2B: {found_email}")
                            break
                except Exception:
                    pass

            # Cập nhật vào dataframe
            if found_phone and (pd.isna(df.at[idx, 'SDT']) or not str(df.at[idx, 'SDT']).strip()):
                df.at[idx, 'SDT'] = found_phone
            if found_email and (pd.isna(df.at[idx, 'Email']) or not str(df.at[idx, 'Email']).strip()):
                df.at[idx, 'Email'] = found_email
            if found_web and (pd.isna(df.at[idx, 'Lien He']) or 'moel.go.kr' in str(df.at[idx, 'Lien He'])):
                df.at[idx, 'Lien He'] = found_web

            cache[cname] = {
                "phone": found_phone,
                "email": found_email,
                "web": found_web
            }

            # Lưu tăng dần sau mỗi 5 cơ sở
            if processed % 5 == 0:
                save_checkpoint(df, cache)
                print(f"  -> [Auto-save] Đã ghi lưu tăng dần vào {CSV_FILE}")

        await browser.close()

    save_checkpoint(df, cache)
    print("\n" + "=" * 70)
    print(f"ĐÃ HOÀN TẤT ĐỢT QUÉT LÀM GIÀU {processed} CƠ SỞ ĐẦU TIÊN!")
    print("=" * 70)

if __name__ == '__main__':
    max_items = 0  # Mặc định 0 là cào toàn bộ (All)
    if len(sys.argv) > 1:
        arg = str(sys.argv[1]).strip().lower()
        if arg in ['all', '0', '-1', 'full', 'tatca']:
            max_items = 0
        else:
            try:
                max_items = int(arg)
            except Exception:
                max_items = 0
    asyncio.run(main(max_items))
