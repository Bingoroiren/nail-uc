#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HỆ THỐNG CÀO DỮ LIỆU XƯỞNG CHẾ BIẾN GÀ & THỊT LITVA (LITHUANIA POULTRY & MEAT PROCESSING)
Bộ cào đa nguồn:
1. https://www.info.lt/rubrika/M%C4%97sa-m%C4%97sos-gaminiai/100209597
2. https://ensun.io/search?threshold=BALANCED&q=Poultry%20And%20Meat%20Processing&locations=Lithuania%2Cnull%2Cnull
3. https://rekvizitai.vz.lt/imones/gyvuliai_zverys_pauksciai_ir_ju_veisimas/
4. https://rekvizitai.vz.lt/imones/mesa_mesos_produktai/
5. https://rekvizitai.vz.lt/paieskos-frazes/paukstiena+didmenine+prekyba/
6. https://rekvizitai.vz.lt/paieskos-frazes/Paukst/

Đặc tính kỹ thuật:
- Chế độ trực quan (headless=False) với cửa sổ Chrome thật 1280x800.
- Profile lưu vĩnh viễn (chrome_user_data/lt_poultry_profile) giữ cookies & cf_clearance.
- Tự động bắt Turnstile, Captcha Rekvizitai, Vercel Security Checkpoint, chuông báo \a.
- Bộ lọc Danh sách đen cố định (Rule #12): Scandi Standard, Biliarta, Daigre.
- Lưu tăng dần từng dòng (mode='a', flush()) và checkpoint JSON (checklist_lt_poultry.json).
- Xuất file chuẩn 17 ký tự: LT_POUL_WEBD_0RAW.csv.
"""

import os
import sys
import re
import csv
import json
import time
import base64
import asyncio
import unicodedata
import urllib.parse
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

# ----------------------------------------------------------------------
# ĐƯỜNG DẪN & CẤU HÌNH ĐỘNG
# ----------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_RAW = BASE_DIR / "LT_POUL_WEBD_0RAW.csv"
CHECKLIST_FILE = BASE_DIR / "crawlmail" / "checklist_lt_poultry.json"
USER_DATA_DIR = BASE_DIR / "chrome_user_data" / "lt_poultry_profile"

RAW_COLUMNS = [
    "No.", "Công ty", "IČO", "SĐT", "Web", "Email", "Địa chỉ", "Thành phố",
    "Direktorius", "Nhân sự", "Category", "Source", "Source_URL"
]

# ----------------------------------------------------------------------
# RULE #12: PERMANENT BLACKLIST
# ----------------------------------------------------------------------
PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre', 'daigre'
]

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

# ----------------------------------------------------------------------
# TIỆN ÍCH CHUẨN HÓA SĐT & EMAIL
# ----------------------------------------------------------------------
def clean_phone_lt(raw):
    if not raw:
        return ""
    p = re.sub(r"[^\d+]", "", str(raw).strip())
    if not p:
        return ""
    if p.startswith("8") and len(p) == 9:
        p = "+370" + p[1:]
    elif p.startswith("0") and (len(p) == 9 or len(p) == 10):
        p = "+370" + p[1:]
    elif not p.startswith("+") and len(p) == 8:
        p = "+370" + p
    return f"'{p}" if not p.startswith("'") else p

def decode_infolt_email(raw_b64):
    if not raw_b64:
        return ""
    try:
        raw = base64.b64decode(raw_b64).decode("utf-8").split(",")
        key = int(raw[0])
        decoded = "".join(chr(int(x) ^ key) for x in raw[1:])
        return decoded.replace("mailto:", "").strip().lower()
    except Exception:
        return ""

def decode_cf(hex_str):
    try:
        r = int(hex_str[:2], 16)
        email = "".join([chr(int(hex_str[i:i+2], 16) ^ r) for i in range(2, len(hex_str), 2)])
        return email.lower().strip()
    except Exception:
        return ""

# ----------------------------------------------------------------------
# XỬ LÝ CAPTCHA & SECURITY CHECKPOINTS
# ----------------------------------------------------------------------
async def handle_security_challenges(page, context_label="", max_wait_seconds=60):
    """
    Tự động kiểm tra và chờ người dùng giải quyết Captcha thủ công nếu có:
    - Cloudflare Turnstile / Just a moment
    - Vercel Security Checkpoint
    - Rekvizitai 3-char code verification
    """
    start_t = time.time()
    alerted = False
    while True:
        try:
            if page.is_closed():
                return False
            if time.time() - start_t > max_wait_seconds:
                if alerted:
                    print(f"[!] [TIMEOUT] Qua thoi gian cho ({max_wait_seconds}s) tai {context_label}. Bo qua checkpoint.")
                return False

            title = await page.title()
            content = await page.content()
            
            # 1. Rekvizitai 3-character security code
            has_rekv_captcha = await page.query_selector("#formFirmsCaptcha, input#security_code") is not None
            if has_rekv_captcha:
                if not alerted:
                    print("\a\n" + "!" * 75)
                    print(f"[!] [CAPTCHA REKVIZITAI] {context_label}: PHAT HIEN MA 3 KY TU TRONG ANH!")
                    print("    Vui long nhin vao man hinh Chrome, nhap 3 ky tu va an Tiep tuc (Continue)...")
                    print("!" * 75 + "\n")
                    alerted = True
                await asyncio.sleep(2.0)
                continue

            # 2. Vercel Security Checkpoint (ensun.io)
            is_vercel = "Vercel Security Checkpoint" in title or "checkpoint" in content.lower()
            if is_vercel:
                if not alerted:
                    print("\a\n" + "!" * 75)
                    print(f"[!] [VERCEL CHECKPOINT] {context_label}: XAC THUC AN TOAN VERCEL / ENSUN.IO!")
                    print("    Vui long nhin vao man hinh Chrome va tich vao o xac thuc / lam theo huong dan...")
                    print("!" * 75 + "\n")
                    alerted = True
                # Thu click nut checkbox neu tim thay
                for frame in page.frames:
                    try:
                        btn = await frame.query_selector("input[type='checkbox'], #challenge-stage, .cb-lb")
                        if btn:
                            await btn.click()
                    except Exception:
                        pass
                await asyncio.sleep(2.5)
                continue

            # 3. Cloudflare Turnstile / Challenge
            is_cf = (
                "Just a moment" in title 
                or "Luktelėkite" in title 
                or "DDoS protection" in content 
                or "cf-turnstile" in content
                or "challenges.cloudflare.com" in content
            )
            if is_cf:
                if not alerted:
                    print("\a\n" + "!" * 75)
                    print(f"[!] [CLOUDFLARE TURNSTILE] {context_label}: PHAT HIEN XAC THUC CLOUDFLARE!")
                    print("    Vui long tich vao o xac nhan tren cua so Chrome...")
                    print("!" * 75 + "\n")
                    alerted = True
                for frame in page.frames:
                    try:
                        if "cloudflare" in frame.url or "challenge" in frame.url:
                            chk = await frame.query_selector("input[type='checkbox'], .cb-lb, #challenge-stage")
                            if chk:
                                await chk.click()
                    except Exception:
                        pass
                await asyncio.sleep(2.5)
                continue

            # Neu khong con bat ky checkpoint nao
            if alerted:
                print(f"[+] Da vuot qua bao mat thanh cong tai {context_label}! Tiep tuc cao du lieu...\n")
            return True

        except Exception as e:
            await asyncio.sleep(2.0)

# ----------------------------------------------------------------------
# CHECKLIST & STATE MANAGER
# ----------------------------------------------------------------------
def load_checklist():
    if CHECKLIST_FILE.exists():
        try:
            with open(CHECKLIST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "info_lt": {"done_pages": [], "completed": False},
        "ensun_io": {"completed": False},
        "rekvizitai_breeding": {"done_pages": [], "completed": False},
        "rekvizitai_meat": {"done_pages": [], "completed": False},
        "rekvizitai_phrase_poultry": {"done_pages": [], "completed": False},
        "rekvizitai_phrase_paukst": {"done_pages": [], "completed": False}
    }

def save_checklist(checklist):
    try:
        CHECKLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CHECKLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(checklist, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[!] Warning saving checklist: {e}")

# ----------------------------------------------------------------------
# BỘ CÀO NGUỒN 1: INFO.LT (MEAT & POULTRY PRODUCTS)
# ----------------------------------------------------------------------
async def crawl_infolt(page, checklist, seen_keys, raw_file_writer, csv_file):
    print("\n" + "=" * 70)
    print(" [NGUỒN 1/6] CÀO INFO.LT: Mėsa, mėsos gaminiai")
    print("=" * 70)
    
    cat_cfg = checklist.get("info_lt", {"done_pages": [], "completed": False})
    if cat_cfg.get("completed"):
        print("[*] Nguon info.lt da hoan thanh truoc do. Bo qua.")
        return

    base_url = "https://www.info.lt/rubrika/M%C4%97sa-m%C4%97sos-gaminiai/100209597"
    
    try:
        await page.goto(base_url, wait_until="domcontentloaded", timeout=25000)
        await handle_security_challenges(page, "info.lt initial")
        await asyncio.sleep(2.0)
    except Exception as e:
        print(f"[!] Loi truy cap trang chu info.lt: {e}")
        return

    # Lay tong so trang / max offset
    content = await page.content()
    soup = BeautifulSoup(content, "html.parser")
    offsets = [0]
    for a in soup.find_all("a", href=True):
        m = re.search(r"/(\d+)-20$", a["href"])
        if m:
            offsets.append(int(m.group(1)))
    max_offset = max(offsets) if offsets else 0
    all_offsets = list(range(0, max_offset + 1, 20))
    print(f"[*] Tim thay tong cong {len(all_offsets)} trang tren info.lt (Max offset: {max_offset}).")

    for offset in all_offsets:
        if offset in cat_cfg.get("done_pages", []):
            continue
        
        page_url = base_url if offset == 0 else f"{base_url}/{offset}-20"
        print(f"\n[+] Dang cao info.lt trang offset {offset}/{max_offset} -> {page_url}")
        
        try:
            await page.goto(page_url, wait_until="domcontentloaded", timeout=25000)
            await handle_security_challenges(page, f"info.lt offset {offset}")
            await asyncio.sleep(1.5)
            
            p_content = await page.content()
            p_soup = BeautifulSoup(p_content, "html.parser")
            
            # Lay danh sach link chi tiet cong ty (URL tren info.lt co dang /imones/Ten-Cong-Ty/id)
            firm_links = []
            for a in p_soup.find_all("a", href=True):
                href = a["href"]
                if "/imones/" in href:
                    if not any(k in href for k in ["/mano-imones", "/imonems/", "/shop", "/sodra", "#", "javascript", "skelbimai"]):
                        full_u = urllib.parse.urljoin("https://www.info.lt", href)
                        if full_u not in firm_links:
                            firm_links.append(full_u)
            
            print(f"    -> Tim thay {len(firm_links)} doanh nghiep tren trang nay.")
            
            for f_url in firm_links:
                try:
                    await page.goto(f_url, wait_until="domcontentloaded", timeout=20000)
                    await handle_security_challenges(page, "info.lt detail")
                    await asyncio.sleep(0.8)
                    
                    d_content = await page.content()
                    d_soup = BeautifulSoup(d_content, "html.parser")
                    
                    # 1. Ten cong ty
                    h1 = d_soup.find("h1")
                    comp_name = h1.get_text(strip=True) if h1 else ""
                    if not comp_name:
                        continue
                    
                    if is_blacklisted_company(comp_name):
                        print(f"    [-] [BLACKLIST BO QUA] {comp_name}")
                        continue
                        
                    key = comp_name.lower().strip()
                    if key in seen_keys:
                        continue
                    
                    full_text = d_soup.get_text(" ", strip=True)

                    # 2. Email (Uu tien XOR data-text-ob / data-link-ob, fallback mailto:)
                    email = ""
                    em_el = d_soup.select_one("[data-text-ob], [data-link-ob]")
                    if em_el:
                        raw_ob = em_el.get("data-text-ob") or em_el.get("data-link-ob")
                        email = decode_infolt_email(raw_ob)
                    if not email:
                        for a in d_soup.find_all("a", href=True):
                            if a["href"].startswith("mailto:"):
                                email = a["href"].replace("mailto:", "").split("?")[0].strip().lower()
                                break
                    if not email:
                        m_em = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", full_text)
                        if m_em and not any(ex in m_em.group(0).lower() for ex in ["info.lt", "saulesspektras"]):
                            email = m_em.group(0).lower()

                    # 3. IČO
                    ico = ""
                    m_ico = re.search(r"Įmonės kodas\s*[:\s]*(\d{7,10})", full_text)
                    if m_ico:
                        ico = m_ico.group(1).strip()
                        
                    # 4. Director
                    director = ""
                    m_dir = re.search(r"(?:Direktorius|Vadovas|Generalinis direktorius)\s*[:\s]*([A-ZĄČĘĖĮŠŲŪŽ][a-ząčęėįšųūž]+\s+[A-ZĄČĘĖĮŠŲŪŽ][a-ząčęėįšųūž]+)", full_text)
                    if m_dir:
                        director = m_dir.group(1).strip()
                        
                    # 5. Employees
                    employees = ""
                    m_emp = re.search(r"Darbuotojai\s*[:\s]*(\d+\s*darbuotojai?[^\n,]*)", full_text, re.IGNORECASE)
                    if m_emp:
                        employees = m_emp.group(1).strip()
                        
                    # 6. Phone (Tel a hoac text Telefonas / Mob.)
                    phone = ""
                    tel_a = d_soup.find("a", href=lambda h: h and h.startswith("tel:"))
                    if tel_a:
                        phone = clean_phone_lt(tel_a.get_text(strip=True) or tel_a["href"])
                    if not phone:
                        m_tel = re.search(r"(?:Telefonas|Mob\.\s*telefonas|Tel\.)\s*[:\s]*([+0-9\s()/-]{7,25})", full_text, re.I)
                        if m_tel:
                            phone = clean_phone_lt(m_tel.group(1))
                        
                    # 7. Website chinh thuc (Loc bo mang xa hoi & platform noi bo)
                    web = ""
                    for a in d_soup.find_all("a", href=True):
                        h = a["href"]
                        t = a.get_text(strip=True).lower()
                        if h.startswith("http") and not any(x in h.lower() for x in [
                            "info.lt", "saulesspektras.lt", "facebook", "linkedin", "waze", "google.com",
                            "apple.com", "maps", "statyba.lt", "medicina.lt", "auto.lt", "turizmas.lt", "balticexport.com", "zl.lv"
                        ]):
                            if "tinklalapis" in t or "." in t or "www." in h:
                                web = h
                                break
                                
                    # 8. Dia chi & Thanh pho
                    addr = ""
                    city = ""
                    h1_div = d_soup.find("div", class_=lambda c: c and "h1_div" in c)
                    if h1_div:
                        for child in h1_div.find_all(["div", "p"]):
                            txt = child.get_text(strip=True)
                            if txt and txt != comp_name and (any(k in txt for k in ["g.", "pl.", "pr.", "al.", "kel.", "k.", "Raj.", "raj."]) or any(c.isdigit() for c in txt)):
                                addr = txt
                                break
                    if not addr:
                        addr_el = d_soup.select_one('[itemprop="streetAddress"]')
                        if addr_el and addr_el.get_text(strip=True):
                            addr = addr_el.get_text(strip=True)
                    if not addr:
                        m_addr = re.search(r"Adresas\s*[:\s]*([^,\n]+(?:g\.|pl\.|al\.|k\.|pr\.)[^,\n]+,\s*[0-9]{4,5}\s*[^,\n]+)", full_text, re.I)
                        if m_addr:
                            addr = m_addr.group(1).strip()

                    # Lam sach danh gia / atsiliepimai o cuoi dia chi
                    if addr:
                        addr = re.sub(r"\d*\s*atsiliepim.*$", "", addr, flags=re.I).strip()
                        parts = [p.strip() for p in addr.split(",") if p.strip()]
                        if len(parts) >= 2:
                            city = re.sub(r"^\d{4,5}\s*", "", parts[-1]).strip()

                    row = {
                        "No.": len(seen_keys) + 1,
                        "Công ty": comp_name,
                        "IČO": ico,
                        "SĐT": phone,
                        "Web": web,
                        "Email": email,
                        "Địa chỉ": addr,
                        "Thành phố": city,
                        "Direktorius": director,
                        "Nhân sự": employees,
                        "Category": "Mėsa, mėsos gaminiai",
                        "Source": "info.lt",
                        "Source_URL": f_url
                    }
                    
                    seen_keys.add(key)
                    raw_file_writer.writerow(row)
                    csv_file.flush()
                    print(f"    [+] [{len(seen_keys)}] {comp_name} | Tel: {phone} | Mail: {email} | Web: {web}")
                    
                except Exception as ex_item:
                    print(f"    [!] Loi doc cong ty {f_url}: {ex_item}")
                    
            cat_cfg.setdefault("done_pages", []).append(offset)
            checklist["info_lt"] = cat_cfg
            save_checklist(checklist)
            
        except Exception as ex_page:
            print(f"[!] Loi cao offset {offset}: {ex_page}")
            
    cat_cfg["completed"] = True
    checklist["info_lt"] = cat_cfg
    save_checklist(checklist)
    print("[*] Hoan thanh 100% nguon info.lt!")

# ----------------------------------------------------------------------
# BỘ CÀO NGUỒN 2: ENSUN.IO (POULTRY & MEAT PROCESSING LITHUANIA)
# ----------------------------------------------------------------------
async def crawl_ensun(page, checklist, seen_keys, raw_file_writer, csv_file):
    print("\n" + "=" * 70)
    print(" [NGUỒN 2/6] CÀO ENSUN.IO: Poultry And Meat Processing in Lithuania")
    print("=" * 70)
    
    cfg = checklist.get("ensun_io", {"completed": False})
    if cfg.get("completed"):
        print("[*] Nguon ensun.io da hoan thanh truoc do. Bo qua.")
        return

    url = "https://ensun.io/search?threshold=BALANCED&q=Poultry%20And%20Meat%20Processing&locations=Lithuania%2Cnull%2Cnull"
    
    try:
        print("[*] Dang mo ensun.io tren trinh duyet Chrome...")
        await page.goto(url, wait_until="domcontentloaded", timeout=35000)
        await handle_security_challenges(page, "ensun.io Search")
        await asyncio.sleep(4.0)
        
        # Cho cho ket qua load
        for _ in range(15):
            content = await page.content()
            if "Poultry" in content or "Processing" in content or "company" in content.lower():
                break
            await asyncio.sleep(1.5)
            
        content = await page.content()
        soup = BeautifulSoup(content, "html.parser")
        
        # Bóc tách các thẻ công ty trên ensun.io
        cards = soup.select("article, .company-card, [data-testid*='company'], .search-result-item, a[href*='/company/']")
        print(f"[*] Tim thay {len(cards)} phan tu doanh nghiep tren ensun.io.")
        
        added_count = 0
        for card in cards:
            title_el = card.find(["h2", "h3", "h4", "strong"])
            comp_name = title_el.get_text(strip=True) if title_el else ""
            if not comp_name and card.name == 'a':
                comp_name = card.get_text(strip=True)
            if not comp_name or len(comp_name) < 3:
                continue
                
            if is_blacklisted_company(comp_name):
                print(f"    [-] [BLACKLIST BO QUA] {comp_name}")
                continue
                
            key = comp_name.lower().strip()
            if key in seen_keys:
                continue
                
            # Website hoac ensun detail link
            web = ""
            detail_link = ""
            for a in card.find_all("a", href=True):
                h = a["href"]
                if "/company/" in h:
                    detail_link = urllib.parse.urljoin("https://ensun.io", h)
                elif h.startswith("http") and not any(x in h for x in ["ensun.io", "linkedin", "google", "twitter"]):
                    web = h
                    
            desc = card.get_text(" ", strip=True)
            
            row = {
                "No.": len(seen_keys) + 1,
                "Công ty": comp_name,
                "IČO": "",
                "SĐT": "",
                "Web": web,
                "Email": "",
                "Địa chỉ": "Lithuania",
                "Thành phố": "",
                "Direktorius": "",
                "Nhân sự": "",
                "Category": "Poultry & Meat Processing (ensun.io)",
                "Source": "ensun.io",
                "Source_URL": detail_link or url
            }
            
            seen_keys.add(key)
            raw_file_writer.writerow(row)
            csv_file.flush()
            added_count += 1
            print(f"    [+] [{len(seen_keys)}] {comp_name} | Web: {web} | Source: ensun.io")
            
        print(f"[*] Da trich xuat duoc {added_count} cong ty tu ensun.io.")
        cfg["completed"] = True
        checklist["ensun_io"] = cfg
        save_checklist(checklist)
        
    except Exception as e:
        print(f"[!] Loi cao ensun.io: {e}")

# ----------------------------------------------------------------------
# BỘ CÀO NGUỒN 3 - 6: REKVIZITAI.VZ.LT (CATEGORIES & PHRASE SEARCHES)
# ----------------------------------------------------------------------
async def crawl_rekvizitai_target(page, target_key, base_url, category_name, checklist, seen_keys, raw_file_writer, csv_file, max_pages=50):
    print("\n" + "=" * 70)
    print(f" CÀO REKVIZITAI: {category_name}")
    print(f" URL: {base_url}")
    print("=" * 70)
    
    cfg = checklist.get(target_key, {"done_pages": [], "completed": False})
    if cfg.get("completed"):
        print(f"[*] Muc {target_key} da hoan thanh truoc do. Bo qua.")
        return

    try:
        await page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
        await handle_security_challenges(page, f"Rekvizitai {category_name} init")
        await asyncio.sleep(2.0)
    except Exception as e:
        print(f"[!] Loi truy cap {base_url}: {e}")
        return

    # Xác định tổng số trang từ pagination nếu có
    content = await page.content()
    soup = BeautifulSoup(content, "html.parser")
    page_numbers = [1]
    for a in soup.select("div.paging a, .pagination a, a[href*='rekvizitai.vz.lt']"):
        m = re.search(r"/(\d+)/?$", a.get("href", ""))
        if m:
            page_numbers.append(int(m.group(1)))
    detected_max = min(max(page_numbers), max_pages) if page_numbers else 1
    print(f"[*] Phat hien khoang {detected_max} trang can quet.")

    for p_num in range(1, detected_max + 1):
        if p_num in cfg.get("done_pages", []):
            continue

        p_url = base_url if p_num == 1 else f"{base_url.rstrip('/')}/{p_num}/"
        print(f"\n[+] Dang cao Rekvizitai trang {p_num}/{detected_max} -> {p_url}")
        
        try:
            await page.goto(p_url, wait_until="domcontentloaded", timeout=25000)
            await handle_security_challenges(page, f"Rekvizitai trang {p_num}")
            await asyncio.sleep(1.5)
            
            p_content = await page.content()
            p_soup = BeautifulSoup(p_content, "html.parser")
            
            # Thu thap link cong ty
            company_links = []
            for a in p_soup.find_all("a", href=True):
                h = a["href"]
                if "/imone/" in h and h not in company_links:
                    if not any(k in h for k in ["#", "javascript", "skelbimai", "atsiliepimai"]):
                        company_links.append(urllib.parse.urljoin("https://rekvizitai.vz.lt", h))
                        
            print(f"    -> Tim thay {len(company_links)} doanh nghiep tren trang {p_num}.")
            
            for c_url in company_links:
                try:
                    await page.goto(c_url, wait_until="domcontentloaded", timeout=20000)
                    await handle_security_challenges(page, "Rekvizitai detail")
                    await asyncio.sleep(0.8)
                    
                    d_content = await page.content()
                    d_soup = BeautifulSoup(d_content, "html.parser")
                    
                    h1 = d_soup.find("h1")
                    comp_name = h1.get_text(strip=True) if h1 else ""
                    if not comp_name:
                        continue
                        
                    if is_blacklisted_company(comp_name):
                        print(f"    [-] [BLACKLIST BO QUA] {comp_name}")
                        continue
                        
                    key = comp_name.lower().strip()
                    if key in seen_keys:
                        continue
                        
                    full_text = d_soup.get_text(" ", strip=True)
                    
                    # IČO
                    ico = ""
                    m_ico = re.search(r"(?:Įmonės kodas|Registration code)[:\s]*(\d{7,10})", full_text)
                    if m_ico:
                        ico = m_ico.group(1).strip()
                        
                    # Phone
                    phone = ""
                    for a in d_soup.find_all("a", href=True):
                        if a["href"].startswith("tel:"):
                            phone = clean_phone_lt(a.get_text(strip=True))
                            break
                            
                    # Email
                    email = ""
                    for a in d_soup.find_all("a", href=True):
                        if a["href"].startswith("mailto:"):
                            email = a.get_text(strip=True).replace("mailto:", "").strip().lower()
                            break
                            
                    # Website
                    web = ""
                    for a in d_soup.find_all("a", href=True):
                        h = a["href"]
                        t = a.get_text(strip=True).lower()
                        if h.startswith("http") and not any(x in h for x in ["rekvizitai.vz.lt", "vz.lt", "facebook", "linkedin", "google.com", "cvbankas"]):
                            if "tinklalapis" in t or "website" in t or "." in t:
                                web = h
                                break
                                
                    # Address & City
                    addr = ""
                    city = ""
                    addr_el = d_soup.select_one(".address, [itemprop='streetAddress'], td:contains('Adresas') + td")
                    if addr_el:
                        addr = addr_el.get_text(strip=True)
                        
                    loc_el = d_soup.select_one(".city, [itemprop='addressLocality']")
                    if loc_el:
                        city = loc_el.get_text(strip=True)
                        
                    # Director
                    director = ""
                    m_dir = re.search(r"(?:Vadovas|Direktorius|Manager)[:\s]*([A-ZĄČĘĖĮŠŲŪŽ][a-ząčęėįšųūž]+\s+[A-ZĄČĘĖĮŠŲŪŽ][a-ząčęėįšųūž]+)", full_text)
                    if m_dir:
                        director = m_dir.group(1).strip()
                        
                    # Employees
                    emp = ""
                    m_emp = re.search(r"(?:Apdraustieji|Darbuotojai|Employees)[:\s]*(\d+)", full_text)
                    if m_emp:
                        emp = f"{m_emp.group(1)} darbuotojai"

                    row = {
                        "No.": len(seen_keys) + 1,
                        "Công ty": comp_name,
                        "IČO": ico,
                        "SĐT": phone,
                        "Web": web,
                        "Email": email,
                        "Địa chỉ": addr,
                        "Thành phố": city,
                        "Direktorius": director,
                        "Nhân sự": emp,
                        "Category": category_name,
                        "Source": "rekvizitai.vz.lt",
                        "Source_URL": c_url
                    }
                    
                    seen_keys.add(key)
                    raw_file_writer.writerow(row)
                    csv_file.flush()
                    print(f"    [+] [{len(seen_keys)}] {comp_name} | Tel: {phone} | Mail: {email} | Web: {web}")
                    
                except Exception as ex_item:
                    print(f"    [!] Loi doc cong ty {c_url}: {ex_item}")
                    
            cfg.setdefault("done_pages", []).append(p_num)
            checklist[target_key] = cfg
            save_checklist(checklist)
            
        except Exception as ex_p:
            print(f"[!] Loi cao trang {p_num} tai {target_key}: {ex_p}")

    cfg["completed"] = True
    checklist[target_key] = cfg
    save_checklist(checklist)
    print(f"[*] Hoan thanh 100% muc {category_name} tren Rekvizitai!")

# ----------------------------------------------------------------------
# CHƯƠNG TRÌNH CHÍNH TỔNG HỢP 6 NGUỒN CÀO
# ----------------------------------------------------------------------
async def main():
    print("=" * 80)
    print(" HỆ THỐNG CÀO DỮ LIỆU XƯỞNG GÀ & THỊT LITVA (LT_POUL_WEBD_0RAW)")
    print(f" Output Raw : {OUTPUT_RAW}")
    print(f" Checklist  : {CHECKLIST_FILE}")
    print(f" Profile Dir: {USER_DATA_DIR}")
    print("=" * 80)

    # 1. Khoi tao checkpoint va tap da cao
    seen_keys = set()
    file_exists = OUTPUT_RAW.exists()
    
    if file_exists:
        try:
            with open(OUTPUT_RAW, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    name = r.get("Công ty", "").strip().lower()
                    if name:
                        seen_keys.add(name)
            print(f"[*] Da khoi phuc {len(seen_keys)} ban ghi da cao tu {OUTPUT_RAW.name}.")
        except Exception as e:
            print(f"[!] Chu y khi doc file ton tai: {e}")

    checklist = load_checklist()

    # 2. Khoi chay Playwright Persistent Context
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    async with async_playwright() as p:
        print("[*] Dang khoi dong Google Chrome (headless=False) voi profile rieng biet...")
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            viewport={"width": 1280, "height": 800},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized"
            ]
        )
        
        page = context.pages[0] if context.pages else await context.new_page()

        # Mo file CSV o che do append lien tuc
        with open(OUTPUT_RAW, mode="a", encoding="utf-8-sig", newline="") as csv_f:
            writer = csv.DictWriter(csv_f, fieldnames=RAW_COLUMNS)
            if not file_exists or os.path.getsize(OUTPUT_RAW) == 0:
                writer.writeheader()
                csv_f.flush()

            # ----------------------------------------------------------
            # NGUON 1: Info.lt (Meat & Meat products)
            # ----------------------------------------------------------
            await crawl_infolt(page, checklist, seen_keys, writer, csv_f)

            # ----------------------------------------------------------
            # NGUON 2: Ensun.io (Poultry & Meat Processing)
            # ----------------------------------------------------------
            await crawl_ensun(page, checklist, seen_keys, writer, csv_f)

            # ----------------------------------------------------------
            # NGUON 3: Rekvizitai - gyvuliai_zverys_pauksciai_ir_ju_veisimas
            # ----------------------------------------------------------
            await crawl_rekvizitai_target(
                page=page,
                target_key="rekvizitai_breeding",
                base_url="https://rekvizitai.vz.lt/imones/gyvuliai_zverys_pauksciai_ir_ju_veisimas/",
                category_name="Gyvuliai, žvėrys, paukščiai ir jų veisimas (Breeding)",
                checklist=checklist,
                seen_keys=seen_keys,
                raw_file_writer=writer,
                csv_file=csv_f,
                max_pages=30
            )

            # ----------------------------------------------------------
            # NGUON 4: Rekvizitai - mesa_mesos_produktai
            # ----------------------------------------------------------
            await crawl_rekvizitai_target(
                page=page,
                target_key="rekvizitai_meat",
                base_url="https://rekvizitai.vz.lt/imones/mesa_mesos_produktai/",
                category_name="Mėsa, mėsos produktai (Meat products)",
                checklist=checklist,
                seen_keys=seen_keys,
                raw_file_writer=writer,
                csv_file=csv_f,
                max_pages=30
            )

            # ----------------------------------------------------------
            # NGUON 5: Rekvizitai Phrase - paukstiena didmenine prekyba
            # ----------------------------------------------------------
            await crawl_rekvizitai_target(
                page=page,
                target_key="rekvizitai_phrase_poultry",
                base_url="https://rekvizitai.vz.lt/paieskos-frazes/paukstiena+didmenine+prekyba/",
                category_name="Paukštiena didmeninė prekyba (Poultry wholesale)",
                checklist=checklist,
                seen_keys=seen_keys,
                raw_file_writer=writer,
                csv_file=csv_f,
                max_pages=20
            )

            # ----------------------------------------------------------
            # NGUON 6: Rekvizitai Phrase - Paukst
            # ----------------------------------------------------------
            await crawl_rekvizitai_target(
                page=page,
                target_key="rekvizitai_phrase_paukst",
                base_url="https://rekvizitai.vz.lt/paieskos-frazes/Paukst/",
                category_name="Paukšt (Poultry & Birds)",
                checklist=checklist,
                seen_keys=seen_keys,
                raw_file_writer=writer,
                csv_file=csv_f,
                max_pages=20
            )

        print("\n" + "=" * 80)
        print(f"[*] DA HOAN THANH QUET TOAN BO 6 NGUON CÀO XƯỞNG GÀ LITVA!")
        print(f"[*] Tong so doanh nghiep da thu thap: {len(seen_keys)}")
        print(f"[*] File ket qua tho: {OUTPUT_RAW}")
        print("=" * 80)
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
