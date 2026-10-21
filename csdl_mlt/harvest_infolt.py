# -*- coding: utf-8 -*-
"""
Harvest Lithuania Meat and Fish Directories from Info.lt
Target Categories:
- https://www.info.lt/rubrika/M%C4%97sa-m%C4%97sos-gaminiai/100209597 (Meat & meat products)
- https://www.info.lt/rubrika/%C5%BDuvis-%C5%BEuvies-produktai/100209695 (Fish & fish products)

Outputs: csdl_mlt/infolt_database.csv
"""

import sys
import os
import re
import csv
import time
import base64
from bs4 import BeautifulSoup
from curl_cffi import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

OUT_DIR = os.path.join(os.path.dirname(__file__))
OUT_CSV = os.path.join(OUT_DIR, "infolt_database.csv")

TARGET_CATEGORIES = [
    {
        "url": "https://www.info.lt/rubrika/M%C4%97sa-m%C4%97sos-gaminiai/100209597",
        "category_name": "Mėsa, mėsos gaminiai (Meat and meat products)",
    },
    {
        "url": "https://www.info.lt/rubrika/%C5%BDuvis-%C5%BEuvies-produktai/100209695",
        "category_name": "Žuvis, žuvies produktai (Fish and fish products)",
    },
]

HEADERS = [
    "Công ty",
    "IČO",  # Įmonės kodas
    "SĐT",
    "Web",
    "Email",
    "Địa chỉ",
    "Thành phố",
    "Direktorius",
    "Nhân sự",
    "Category",
    "Source",
    "Source_URL",
]


def decode_infolt_email(link_el):
    """Decode info.lt XOR obfuscated email string"""
    if not link_el:
        return ""
    try:
        raw_b64 = link_el.get("data-text-ob") or link_el.get("data-link-ob")
        if not raw_b64:
            return ""
        raw = base64.b64decode(raw_b64).decode("utf-8").split(",")
        key = int(raw[0])
        decoded = "".join(chr(int(x) ^ key) for x in raw[1:])
        return decoded.replace("mailto:", "").strip()
    except Exception:
        return ""


def clean_phone(raw):
    """Normalize Lithuanian phone numbers and ensure leading single quote"""
    if not raw:
        return ""
    p = re.sub(r"[^\d+]", "", str(raw).strip())
    if p.startswith("8") and len(p) == 9:
        p = "+370" + p[1:]
    elif p.startswith("0") and len(p) == 10:
        p = "+370" + p[1:]
    elif not p.startswith("+") and len(p) == 8:
        p = "+370" + p
    return f"'{p}" if not p.startswith("'") else p


def fetch_detail_info(detail_url):
    """Fetch detail page on info.lt for Company Code, decoded Email, Director, Employees"""
    res = {
        "ico": "",
        "email": "",
        "director": "",
        "employees": "",
        "phone": "",
        "web": "",
        "address": "",
        "city": "",
    }
    if not detail_url:
        return res

    try:
        r = requests.get(detail_url, impersonate="chrome120", timeout=12)
        if r.status_code != 200:
            return res

        soup = BeautifulSoup(r.text, "html.parser")

        # Email decode
        em_el = soup.select_one("[data-text-ob], [data-link-ob]")
        if em_el:
            res["email"] = decode_infolt_email(em_el)

        # Contacts block text
        full_text = soup.get_text(" ", strip=True)

        # Company code
        m_ico = re.search(r"Įmonės kodas\s*[:\s]*(\d{7,10})", full_text)
        if m_ico:
            res["ico"] = m_ico.group(1).strip()

        # Director
        m_dir = re.search(r"(?:Direktorius|Vadovas|Generalinis direktorius)\s*[:\s]*([A-ZĄČĘĖĮŠŲŪŽ][a-ząčęėįšųūž]+\s+[A-ZĄČĘĖĮŠŲŪŽ][a-ząčęėįšųūž]+)", full_text)
        if m_dir:
            res["director"] = m_dir.group(1).strip()

        # Employees
        m_emp = re.search(r"Darbuotojai\s*[:\s]*(\d+\s*darbuotojai?[^\n,]*)", full_text, re.IGNORECASE)
        if m_emp:
            res["employees"] = m_emp.group(1).strip()

        # Phone
        tel_a = soup.select_one('a[href^="tel:"]')
        if tel_a:
            res["phone"] = clean_phone(tel_a.get_text(strip=True))

        # Website
        for a in soup.find_all("a", href=True):
            href = a["href"]
            txt = a.get_text(strip=True).lower()
            if href.startswith("http") and not any(x in href for x in ["info.lt", "facebook", "linkedin", "waze", "apple.com", "google.com"]):
                if "tinklalapis" in txt or "." in txt:
                    res["web"] = href
                    break

        # Address & City
        addr_el = soup.select_one('[itemprop="streetAddress"]')
        loc_el = soup.select_one('[itemprop="addressLocality"]')
        if addr_el and addr_el.get_text(strip=True):
            res["address"] = addr_el.get_text(strip=True)
        if loc_el and loc_el.get_text(strip=True):
            res["city"] = loc_el.get_text(strip=True)
            if res["address"]:
                res["address"] = f"{res['address']}, {res['city']}"
            else:
                res["address"] = res["city"]

    except Exception:
        pass

    return res


def harvest_infolt():
    print("=" * 70)
    print(" HARVESTING INFO.LT (Meat and Fish Categories)")
    print(f" Output File: {OUT_CSV}")
    print("=" * 70)

    os.makedirs(OUT_DIR, exist_ok=True)
    seen_companies = set()
    rows = []

    # Resume from existing if present
    if os.path.exists(OUT_CSV):
        try:
            with open(OUT_CSV, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    key = r.get("Công ty", "").strip().lower()
                    if key:
                        seen_companies.add(key)
                        rows.append(r)
            print(f"[*] Resumed: loaded {len(seen_companies)} existing records from CSV.")
        except Exception as e:
            print(f"[!] Warning reading existing CSV: {e}")

    for cat in TARGET_CATEGORIES:
        base_url = cat["url"]
        cat_name = cat["category_name"]
        print(f"\n[+] Category: {cat_name}")
        print(f"    URL: {base_url}")

        # Determine max offset
        max_offset = 0
        try:
            r_init = requests.get(base_url, impersonate="chrome120", timeout=15)
            if r_init.status_code == 200:
                soup_init = BeautifulSoup(r_init.text, "html.parser")
                offsets = [0]
                for a in soup_init.find_all("a", href=True):
                    m = re.search(r"/(\d+)-20$", a["href"])
                    if m:
                        offsets.append(int(m.group(1)))
                max_offset = max(offsets)
        except Exception as e:
            print(f"    [!] Error detecting max offset: {e}")

        total_pages = (max_offset // 20) + 1
        print(f"    Total pages detected: {total_pages} (Max offset: {max_offset})")

        for page_idx in range(total_pages):
            offset = page_idx * 20
            page_url = base_url if offset == 0 else f"{base_url}/{offset}-20"

            try:
                r = requests.get(page_url, impersonate="chrome120", timeout=20)
                if r.status_code != 200:
                    print(f"    [!] Page {page_idx + 1} status {r.status_code}, skipping...")
                    continue

                soup = BeautifulSoup(r.text, "html.parser")
                cards = []
                for h in soup.find_all(["h2", "h3"]):
                    a = h.find("a", href=re.compile(r"/imones/[^/]+/\d+"))
                    if a:
                        comp_name = a.get_text(strip=True)
                        detail_href = a["href"]
                        if not detail_href.startswith("http"):
                            detail_href = f"https://www.info.lt{detail_href}"
                        cards.append((comp_name, detail_href))

                new_in_page = 0
                for comp_name, detail_href in cards:
                    key = comp_name.lower()
                    if key in seen_companies:
                        continue

                    # Fetch detail info
                    det = fetch_detail_info(detail_href)
                    time.sleep(0.15)

                    record = {
                        "Công ty": comp_name,
                        "IČO": det["ico"],
                        "SĐT": det["phone"],
                        "Web": det["web"],
                        "Email": det["email"],
                        "Địa chỉ": det["address"],
                        "Thành phố": det["city"],
                        "Direktorius": det["director"],
                        "Nhân sự": det["employees"],
                        "Category": cat_name,
                        "Source": "info.lt",
                        "Source_URL": detail_href,
                    }

                    seen_companies.add(key)
                    rows.append(record)
                    new_in_page += 1

                print(f"    [+] Page {page_idx + 1}/{total_pages}: +{new_in_page} companies (Total: {len(rows)})")

                # Incremental auto-save
                with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=HEADERS)
                    writer.writeheader()
                    writer.writerows(rows)

                time.sleep(0.3)
            except Exception as ex:
                print(f"    [!] Error on page {page_idx + 1}: {ex}")

    print(f"\n[V] Completed Info.lt harvest! Total records: {len(rows):,} saved to {OUT_CSV}")


if __name__ == "__main__":
    harvest_infolt()
