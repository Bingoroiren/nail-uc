# -*- coding: utf-8 -*-
"""
Harvest Lithuania Food / Meat / Fish / Dairy Directory from Visalietuva.lt
Target Categories:
- https://www.visalietuva.lt/imones/mesos-imones
- https://www.visalietuva.lt/imones/mesos-gaminiai
- https://www.visalietuva.lt/imones/zuvies-produktai
- https://www.visalietuva.lt/imones/zuvininkyste
- https://www.visalietuva.lt/imones/pieno-gaminiai

Outputs: csdl_mlt/visalietuva_database.csv
"""

import sys
import os
import re
import csv
import time
from bs4 import BeautifulSoup
from curl_cffi import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

OUT_DIR = os.path.join(os.path.dirname(__file__))
OUT_CSV = os.path.join(OUT_DIR, "visalietuva_database.csv")

TARGET_CATEGORIES = [
    {
        "url": "https://www.visalietuva.lt/imones/mesos-imones",
        "category_name": "Mėsos įmonės (Meat companies)",
    },
    {
        "url": "https://www.visalietuva.lt/imones/mesos-gaminiai",
        "category_name": "Mėsos gaminiai (Meat products)",
    },
    {
        "url": "https://www.visalietuva.lt/imones/zuvies-produktai",
        "category_name": "Žuvies produktai (Fish products)",
    },
    {
        "url": "https://www.visalietuva.lt/imones/zuvininkyste",
        "category_name": "Žuvininkystė (Fisheries)",
    },
    {
        "url": "https://www.visalietuva.lt/imones/pieno-gaminiai",
        "category_name": "Pieno gaminiai (Dairy products)",
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
    "Category",
    "Source",
    "Source_URL",
]


def decode_cf(cf_hex):
    """Decode Cloudflare email protection hex string"""
    try:
        r = int(cf_hex[:2], 16)
        return "".join([chr(int(cf_hex[i:i + 2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
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


def harvest_visalietuva():
    print("=" * 70, flush=True)
    print(" HARVESTING VISALIETUVA.LT (Meat, Fish, Dairy Categories)", flush=True)
    print(f" Output File: {OUT_CSV}", flush=True)
    print("=" * 70, flush=True)

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
            print(f"[*] Resumed: loaded {len(seen_companies)} existing records from CSV.", flush=True)
        except Exception as e:
            print(f"[!] Warning reading existing CSV: {e}", flush=True)

    for cat in TARGET_CATEGORIES:
        base_url = cat["url"]
        cat_name = cat["category_name"]
        print(f"\n[+] Category: {cat_name}", flush=True)
        print(f"    URL: {base_url}", flush=True)

        # Determine total pages
        max_page = 1
        try:
            r_init = requests.get(base_url, impersonate="chrome120", timeout=15)
            if r_init.status_code == 200:
                soup_init = BeautifulSoup(r_init.text, "html.parser")
                pages = [1]
                path = base_url.replace("https://www.visalietuva.lt", "")
                for a in soup_init.find_all("a", href=True):
                    m = re.search(r"/(\d+)$", a["href"])
                    if m and path in a["href"]:
                        pages.append(int(m.group(1)))
                max_page = max(pages)
        except Exception as e:
            print(f"    [!] Error checking total pages: {e}", flush=True)

        print(f"    Total pages detected: {max_page}", flush=True)

        for page in range(1, max_page + 1):
            page_url = base_url if page == 1 else f"{base_url}/{page}"
            try:
                r = requests.get(page_url, impersonate="chrome120", timeout=20)
                if r.status_code != 200:
                    print(f"    [!] Page {page} status {r.status_code}, skipping...", flush=True)
                    continue

                soup = BeautifulSoup(r.text, "html.parser")
                items = soup.select(".company_list .item")
                new_in_page = 0

                for it in items:
                    title_el = it.select_one(".company-item-title")
                    comp_name = title_el.get_text(strip=True) if title_el else ""
                    if not comp_name:
                        continue

                    key = comp_name.lower()
                    if key in seen_companies:
                        continue

                    detail_link = title_el["href"] if title_el and title_el.has_attr("href") else ""
                    if detail_link and not detail_link.startswith("http"):
                        detail_link = f"https://www.visalietuva.lt{detail_link}"

                    # Address & City
                    addr = ""
                    city = ""
                    street_span = it.select_one('[itemprop="streetAddress"]')
                    loc_span = it.select_one('[itemprop="addressLocality"]')
                    if street_span and street_span.get_text(strip=True):
                        addr = street_span.get_text(strip=True)
                    if loc_span and loc_span.get_text(strip=True):
                        loc_txt = loc_span.get_text(strip=True)
                        addr = f"{addr}, {loc_txt}".strip(", ") if addr else loc_txt
                        parts = [p.strip() for p in loc_txt.split(",") if p.strip()]
                        if parts:
                            city = parts[-1]

                    if not addr:
                        for d in it.find_all("div"):
                            txt = d.get_text(" ", strip=True)
                            if txt.startswith("Adresas:"):
                                addr = txt.replace("Adresas:", "").strip()
                                break

                    # Phone
                    phone = ""
                    tel_a = it.select_one('a[href^="tel:"]')
                    if tel_a:
                        phone = clean_phone(tel_a.get_text(strip=True))
                    else:
                        for d in it.find_all("div"):
                            txt = d.get_text(" ", strip=True)
                            if txt.startswith("Telefonas:"):
                                phone = clean_phone(txt.replace("Telefonas:", "").strip())
                                break

                    # Email (Cloudflare decode)
                    email = ""
                    cf_el = it.select_one("[data-cfemail]")
                    if cf_el:
                        email = decode_cf(cf_el["data-cfemail"])

                    # Website
                    web = ""
                    for a in it.find_all("a", href=True):
                        txt = a.get_text(strip=True)
                        href = a["href"]
                        if ("www." in txt or txt.endswith(".lt") or txt.endswith(".com")) and not any(x in href for x in ["visalietuva.lt", "facebook", "linkedin"]):
                            web = href if href.startswith("http") else f"http://{txt}"
                            break

                    record = {
                        "Công ty": comp_name,
                        "IČO": "",
                        "SĐT": phone,
                        "Web": web,
                        "Email": email,
                        "Địa chỉ": addr,
                        "Thành phố": city,
                        "Category": cat_name,
                        "Source": "visalietuva.lt",
                        "Source_URL": detail_link or page_url,
                    }

                    seen_companies.add(key)
                    rows.append(record)
                    new_in_page += 1

                print(f"    [+] Page {page}/{max_page}: +{new_in_page} companies (Total: {len(rows)})", flush=True)

                # Incremental auto-save
                with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=HEADERS)
                    writer.writeheader()
                    writer.writerows(rows)

                time.sleep(0.3)
            except Exception as ex:
                print(f"    [!] Error on page {page}: {ex}", flush=True)

    print(f"\n[V] Completed Visalietuva harvest! Total records: {len(rows):,} saved to {OUT_CSV}", flush=True)


if __name__ == "__main__":
    harvest_visalietuva()
