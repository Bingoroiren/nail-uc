#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Crawl Austrian Federation of Staffing Agencies: Personaldienstleister.at
Dynamic paths, Playwright / curl_cffi DOM parsing, incremental auto-save.
"""

import os
import sys
import json
import re
import time
import asyncio
from pathlib import Path
from bs4 import BeautifulSoup
from curl_cffi import requests

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass

# Base directory relative to this script
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_RAW_DIR = BASE_DIR / "data"
OUTPUT_RAW_DIR.mkdir(parents=True, exist_ok=True)

RAW_CSV = OUTPUT_RAW_DIR / "AT_AGCY_OEPD_0RAW.csv"
RAW_JSON = OUTPUT_RAW_DIR / "AT_AGCY_OEPD_0RAW.json"
CHECKLIST_FILE = OUTPUT_RAW_DIR / "checklist_at_agcy.json"

TARGET_URL = "https://www.personaldienstleister.at/verband-mitglieder/mitglieder/#/unsere-mitglieder"

def load_checklist():
    if CHECKLIST_FILE.exists():
        try:
            with open(CHECKLIST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_checklist(checklist):
    try:
        with open(CHECKLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(checklist, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Error saving checklist: {e}")

def load_existing_results():
    if RAW_JSON.exists():
        try:
            with open(RAW_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_results(results):
    if not results:
        return
    with open(RAW_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    # Save CSV with BOM
    fieldnames = [
        "source", "region", "category", "name", "street", "postal_code",
        "city", "phone", "email", "website", "detail_url"
    ]
    import csv
    with open(RAW_CSV, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            row = {k: r.get(k, "") for k in fieldnames}
            phone = str(row["phone"]).strip()
            if phone and not phone.startswith("'"):
                row["phone"] = f"'{phone}"
            writer.writerow(row)

def clean_phone(phone_str):
    if not phone_str:
        return ""
    phone_str = phone_str.replace("tel:", "").strip()
    phone_str = phone_str.replace("0043+43", "+43").replace("0043", "+43")
    phone_str = re.sub(r"[^\d+/\s\-()]", "", phone_str).strip()
    return phone_str

def clean_email(email_str):
    if not email_str:
        return ""
    email_str = email_str.replace("mailto:", "").split("?")[0].strip()
    email_str = email_str.replace("%20", "").strip()
    if "@" in email_str and "." in email_str.split("@")[-1]:
        return email_str
    return ""

async def fetch_page_html():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        print(f"🌐 Đang truy cập Personaldienstleister: {TARGET_URL}")
        await page.goto(TARGET_URL, wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(3000)
        html = await page.content()
        await browser.close()
        return html

def parse_members_html(html):
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".card.card--locations, .map__item")
    if not cards:
        cards = soup.select(".card--locations")
    print(f"📦 Tìm thấy {len(cards)} thẻ thành viên trên trang!")
    
    results = []
    seen = set()
    
    for c in cards:
        # Extract title/name
        # Usually first strong or heading or text
        h_el = c.find(["h3", "h4", "h5", "strong"])
        raw_text_lines = [l.strip() for l in c.get_text("\n", strip=True).split("\n") if l.strip()]
        
        name = ""
        if h_el and len(h_el.get_text(strip=True)) > 2:
            name = h_el.get_text(strip=True)
        elif raw_text_lines:
            name = raw_text_lines[0]
            
        if not name or "Alle Mitglieder" in name or len(name) < 3:
            continue
            
        # Detail url
        detail_link = c.find("a", href=lambda h: h and "/mitglieder/" in h)
        detail_url = ""
        if detail_link:
            href = detail_link.get("href", "").strip().lstrip("-")
            detail_url = f"https://www.personaldienstleister.at{href}" if href.startswith("/") else href
            
        # Phone
        phone = ""
        phone_el = c.find("a", href=lambda h: h and "tel:" in h)
        if phone_el:
            phone = clean_phone(phone_el.get("href", "") or phone_el.get_text(strip=True))
            
        # Email
        email = ""
        email_el = c.find("a", href=lambda h: h and "mailto:" in h)
        if email_el:
            email = clean_email(email_el.get("href", "") or email_el.get_text(strip=True))
            
        # Address
        street = ""
        postal_code = ""
        city = ""
        
        # In card text lines, search for PLZ (4 digits)
        full_text = " | ".join(raw_text_lines)
        plz_match = re.search(r"\b(\d{4})\s*\|\s*([A-Za-zäöüÄÖÜß\-\s]+?)(?:\s*\||$)", full_text)
        if plz_match:
            postal_code = plz_match.group(1).strip()
            city = plz_match.group(2).strip()
            
        # Street is usually the line preceding PLZ
        for idx, line in enumerate(raw_text_lines):
            if postal_code and postal_code in line:
                if idx > 0:
                    prev_line = raw_text_lines[idx - 1]
                    if any(x in prev_line.lower() for x in ["straße", "strasse", "gasse", "weg", "platz", "str."]):
                        street = prev_line
                break
                
        key = (name.lower().strip(), postal_code, city.lower().strip())
        if key in seen:
            continue
        seen.add(key)
        
        results.append({
            "source": "Personaldienstleister.at",
            "region": city if city else "Österreich",
            "category": "Personaldienstleister Verband",
            "name": name,
            "street": street,
            "postal_code": postal_code,
            "city": city,
            "phone": phone,
            "email": email,
            "website": "",
            "detail_url": detail_url
        })
        
    return results

def crawl_personaldienstleister():
    checklist = load_checklist()
    t_id = "personaldienstleister_verband"
    
    if t_id not in checklist:
        checklist[t_id] = {
            "portal": "Personaldienstleister.at",
            "region": "Österreich",
            "category": "Verband Mitglieder",
            "base_url": TARGET_URL,
            "total_pages": 1,
            "scraped_pages": [],
            "status": "PENDING",
            "items_count": 0
        }
        save_checklist(checklist)
        
    entry = checklist[t_id]
    if entry.get("status") == "COMPLETED":
        print(f"⏭️ Bỏ qua {t_id} (Đã hoàn thành trước đó với {entry.get('items_count', 0)} mục)")
        return
        
    print("\n" + "=" * 75)
    print("🚀 BẮT ĐẦU CÀO PERSONALDIENSTLEISTER.AT (VERBAND)")
    print(f"🔗 Target: {TARGET_URL}")
    print("=" * 75)
    
    html = asyncio.run(fetch_page_html())
    items = parse_members_html(html)
    
    entry["scraped_pages"] = [1]
    entry["items_count"] = len(items)
    entry["status"] = "COMPLETED"
    save_checklist(checklist)
    save_results(items)
    
    print("\n" + "=" * 75)
    print(f"🏁 ĐÃ HOÀN TẤT PERSONALDIENSTLEISTER.AT!")
    print(f"📊 Thu thập được: {len(items)} thành viên chính thức")
    print(f"💾 File kết quả: {RAW_CSV}")
    print("=" * 75)

if __name__ == "__main__":
    crawl_personaldienstleister()
