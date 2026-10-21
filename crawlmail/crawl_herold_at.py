#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Crawl Austrian Employment & Staffing Agencies from Herold.at
Dynamic paths, resilient pagination checklist, incremental checkpointing.
"""

import os
import sys
import json
import re
import time
from pathlib import Path
from bs4 import BeautifulSoup
from curl_cffi import requests

# Base directory relative to this script
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_RAW_DIR = BASE_DIR / "data"
OUTPUT_RAW_DIR.mkdir(parents=True, exist_ok=True)

RAW_CSV = OUTPUT_RAW_DIR / "AT_AGCY_HERO_0RAW.csv"
RAW_JSON = OUTPUT_RAW_DIR / "AT_AGCY_HERO_0RAW.json"
CHECKLIST_FILE = OUTPUT_RAW_DIR / "checklist_at_agcy.json"

TARGET_URLS = [
    {
        "id": "herold_tirol_vermittlung",
        "url": "https://www.herold.at/gelbe-seiten/tirol/arbeitsvermittlung/",
        "region": "Tirol",
        "category": "Arbeitsvermittlung"
    },
    {
        "id": "herold_steiermark_vermittlung",
        "url": "https://www.herold.at/gelbe-seiten/steiermark/arbeitsvermittlung/",
        "region": "Steiermark",
        "category": "Arbeitsvermittlung"
    },
    {
        "id": "herold_linz_bereitstellung",
        "url": "https://www.herold.at/gelbe-seiten/linz-stadt/personalbereitstellung/",
        "region": "Linz-Stadt",
        "category": "Personalbereitstellung"
    },
    {
        "id": "herold_wien_vermittlung",
        "url": "https://www.herold.at/gelbe-seiten/wien/arbeitsvermittlung/",
        "region": "Wien",
        "category": "Arbeitsvermittlung"
    },
    {
        "id": "herold_noe_vermittlung",
        "url": "https://www.herold.at/gelbe-seiten/nieder%C3%B6sterreich/arbeitsvermittlung/",
        "region": "Niederösterreich",
        "category": "Arbeitsvermittlung"
    },
    {
        "id": "herold_wien_bereitstellung",
        "url": "https://www.herold.at/gelbe-seiten/wien/personalbereitstellung/",
        "region": "Wien",
        "category": "Personalbereitstellung"
    }
]

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
            # Ensure phone has single quote
            phone = str(row["phone"]).strip()
            if phone and not phone.startswith("'"):
                row["phone"] = f"'{phone}"
            writer.writerow(row)

def clean_email(email_str):
    if not email_str:
        return ""
    email_str = email_str.replace("mailto:", "").split("?")[0].strip()
    email_str = email_str.replace("%20", "").strip()
    # Basic validation
    if "@" in email_str and "." in email_str.split("@")[-1]:
        return email_str
    return ""

def clean_phone(phone_str):
    if not phone_str:
        return ""
    phone_str = phone_str.replace("tel:", "").strip()
    phone_str = re.sub(r"[^\d+/\s\-()]", "", phone_str).strip()
    return phone_str

def parse_herold_page(html, target_info):
    soup = BeautifulSoup(html, "html.parser")
    results = []
    
    # Check total pages from title or pagination
    # e.g., Title: "Personalbereitstellung in Linz (Stadt)... - Seite 1/3 - herold.at"
    total_pages = 1
    title = soup.title.string if soup.title else ""
    page_match = re.search(r"Seite\s+\d+/(\d+)", title)
    if page_match:
        total_pages = int(page_match.group(1))
    else:
        # Search in pagination links
        pag_links = soup.find_all("a", href=lambda h: h and "/seite/" in h)
        for pl in pag_links:
            m = re.search(r"/seite/(\d+)/", pl.get("href", ""))
            if m:
                total_pages = max(total_pages, int(m.group(1)))
                
    # Extract company cards from li.location-search-result or article
    items = soup.select("li.location-search-result")
    if not items:
        items = soup.find_all("article")
        
    for it in items:
        # Find detail link to company profile
        # e.g. /gelbe-seiten/linz/GCq6z/jobfactory-personalservice-gmbh/
        comp_link = None
        for a in it.find_all("a"):
            href = a.get("href", "").strip()
            if "/gelbe-seiten/" in href:
                parts = href.strip("/").split("/")
                if len(parts) >= 4 and parts[0] == "gelbe-seiten" and len(parts[2]) == 5:
                    comp_link = a
                    break
                    
        if not comp_link:
            continue
            
        href = comp_link.get("href", "").strip()
        
        # Company name from detail link text or heading
        name = ""
        for a in it.find_all("a", href=href):
            txt = a.get_text(strip=True)
            if txt and txt.lower() not in ["mehr details", "termin buchen", "bewerten"]:
                name = txt
                break
                
        if not name:
            h = it.find(["h2", "h3", "h4"])
            if h:
                name = h.get_text(strip=True)
                
        if not name or "Firmeneintrag" in name or "Kostenlosen" in name or len(name) < 2:
            continue
            
        # Phone
        phone = ""
        phone_el = it.find("a", href=lambda h: h and "tel:" in h)
        if phone_el:
            phone = clean_phone(phone_el.get("href", "") or phone_el.get_text(strip=True))
            
        # Email
        email = ""
        email_el = it.find("a", href=lambda h: h and "mailto:" in h)
        if email_el:
            email = clean_email(email_el.get("href", "") or email_el.get_text(strip=True))
            
        # Website
        website = ""
        for a_web in it.find_all("a"):
            w_href = a_web.get("href", "").strip()
            if w_href.startswith("http") and "herold.at" not in w_href and "facebook" not in w_href and "google" not in w_href and "instagram" not in w_href:
                website = w_href
                break
                
        # Address parsing from text
        postal_code = ""
        city = ""
        street = ""
        
        it_text = it.get_text(" | ", strip=True)
        plz_match = re.search(r"\b(\d{4})\s+([A-Za-zäöüÄÖÜß\-\s]+?)(?:\s*\||$)", it_text)
        if plz_match:
            postal_code = plz_match.group(1).strip()
            city = plz_match.group(2).strip()
            
        full_detail_url = f"https://www.herold.at{href}" if href.startswith("/") else href
        
        results.append({
            "source": "Herold.at",
            "region": target_info["region"],
            "category": target_info["category"],
            "name": name,
            "street": street,
            "postal_code": postal_code,
            "city": city,
            "phone": phone,
            "email": email,
            "website": website,
            "detail_url": full_detail_url
        })
        
    return results, total_pages

def crawl_herold():
    checklist = load_checklist()
    existing_results = load_existing_results()
    seen_keys = { (r["name"].lower().strip(), r.get("detail_url", "").lower().strip()) for r in existing_results }
    all_results = list(existing_results)
    
    print("\n" + "=" * 75)
    print("🚀 BẮT ĐẦU CÀO HEROLD.AT (AUSTRIA AGENCY)")
    print(f"📁 Dữ liệu lưu tại: {RAW_CSV}")
    print(f"📋 Checklist file: {CHECKLIST_FILE}")
    print("=" * 75)
    
    session = requests.Session()
    
    for t_idx, target in enumerate(TARGET_URLS, 1):
        t_id = target["id"]
        base_url = target["url"]
        
        if t_id not in checklist:
            checklist[t_id] = {
                "portal": "Herold",
                "region": target["region"],
                "category": target["category"],
                "base_url": base_url,
                "total_pages": None,
                "scraped_pages": [],
                "status": "PENDING",
                "items_count": 0
            }
            save_checklist(checklist)
            
        entry = checklist[t_id]
        if entry.get("status") == "COMPLETED":
            print(f"[{t_idx}/{len(TARGET_URLS)}] ⏭️ Bỏ qua {t_id} (Đã hoàn thành trước đó với {entry.get('items_count', 0)} mục)")
            continue
            
        print(f"\n[{t_idx}/{len(TARGET_URLS)}] 🔍 Đang xử lý: {target['region']} - {target['category']}")
        print(f"🔗 Base URL: {base_url}")
        
        page_num = 1
        total_pages = entry.get("total_pages") or 1
        
        while page_num <= total_pages:
            if page_num in entry.get("scraped_pages", []):
                print(f"  ⏭️ Trang {page_num} đã cào -> Bỏ qua")
                page_num += 1
                continue
                
            page_url = base_url if page_num == 1 else f"{base_url.rstrip('/')}/seite/{page_num}/"
            print(f"  📄 Đang tải trang {page_num}/{total_pages}: {page_url} ...")
            
            try:
                resp = session.get(page_url, impersonate="chrome120", timeout=20)
                if resp.status_code != 200:
                    print(f"  ⚠️ HTTP {resp.status_code} khi tải {page_url}")
                    break
                    
                items, detected_total = parse_herold_page(resp.text, target)
                if detected_total > total_pages:
                    total_pages = detected_total
                    entry["total_pages"] = total_pages
                    
                new_items = 0
                for it in items:
                    key = (it["name"].lower().strip(), it["detail_url"].lower().strip())
                    if key not in seen_keys:
                        seen_keys.add(key)
                        all_results.append(it)
                        new_items += 1
                        
                entry["scraped_pages"].append(page_num)
                entry["items_count"] = entry.get("items_count", 0) + new_items
                save_checklist(checklist)
                save_results(all_results)
                
                print(f"  ✅ Trang {page_num}/{total_pages}: Trích xuất được {len(items)} cty (+{new_items} mới) | Tổng: {len(all_results)}")
                
            except Exception as e:
                print(f"  ❌ Lỗi khi tải trang {page_num}: {e}")
                time.sleep(2)
                
            page_num += 1
            time.sleep(1.0)
            
        entry["status"] = "COMPLETED"
        save_checklist(checklist)
        print(f"🎉 Hoàn thành mục {t_id}! Tổng công ty hiện có: {len(all_results)}")
        
    print("\n" + "=" * 75)
    print(f"🏁 ĐÃ HOÀN TẤT TOÀN BỘ HEROLD.AT!")
    print(f"📊 Tổng cộng: {len(all_results)} công ty")
    print(f"💾 File kết quả: {RAW_CSV}")
    print("=" * 75)

if __name__ == "__main__":
    crawl_herold()
