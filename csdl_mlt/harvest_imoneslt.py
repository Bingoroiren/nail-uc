# -*- coding: utf-8 -*-
"""
Harvest Lithuania Meat and Fish Directories from Imones.lt
Target Categories:
- https://www.imones.lt/mesa-mesos-gaminiai (Meat & meat products)
- https://www.imones.lt/zuvis-zuvies-produktai (Fish & fish products)

Outputs: csdl_mlt/imoneslt_database.csv
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
OUT_CSV = os.path.join(OUT_DIR, "imoneslt_database.csv")

TARGET_CATEGORIES = [
    {
        "url": "https://www.imones.lt/mesa-mesos-gaminiai",
        "category_name": "Mėsa, mėsos gaminiai (Meat and meat products)",
    },
    {
        "url": "https://www.imones.lt/zuvis-zuvies-produktai",
        "category_name": "Žuvis, žuvies produktai (Fish and fish products)",
    },
]

HEADERS = [
    "Công ty",
    "IČO",
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


def harvest_imoneslt():
    print("=" * 70, flush=True)
    print(" HARVESTING IMONES.LT (Meat and Fish Categories)", flush=True)
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

        # Determine max page
        max_page = 1
        try:
            r_init = requests.get(base_url, impersonate="chrome120", timeout=15)
            if r_init.status_code == 200:
                soup_init = BeautifulSoup(r_init.text, "html.parser")
                pages = [1]
                path = base_url.replace("https://www.imones.lt", "")
                for a in soup_init.find_all("a", href=True):
                    m = re.search(r"/(\d+)$", a["href"])
                    if m and path in a["href"]:
                        pages.append(int(m.group(1)))
                max_page = max(pages)
        except Exception as e:
            print(f"    [!] Error detecting max page: {e}", flush=True)

        print(f"    Total pages detected: {max_page}", flush=True)

        for page in range(1, max_page + 1):
            page_url = base_url if page == 1 else f"{base_url}/{page}"
            try:
                r = requests.get(page_url, impersonate="chrome120", timeout=20)
                if r.status_code != 200:
                    print(f"    [!] Page {page} status {r.status_code}, skipping...", flush=True)
                    continue

                soup = BeautifulSoup(r.text, "html.parser")
                container = soup.select_one(".list-of-items")
                if not container:
                    print(f"    [!] Container .list-of-items not found on page {page}", flush=True)
                    continue

                # Find all company links
                processed_page_hrefs = set()
                new_in_page = 0

                for a in container.find_all("a", href=re.compile(r"^https://www\.imones\.lt/[a-z0-9-]+$")):
                    comp_name = a.get_text(strip=True)
                    detail_href = a["href"]
                    if not comp_name or any(x in detail_href for x in ["/services", "/mesa", "/zuvis", "/apie", "/kontaktai", "/login", "/search"]):
                        continue
                    if detail_href in processed_page_hrefs:
                        continue
                    processed_page_hrefs.add(detail_href)

                    key = comp_name.lower()
                    if key in seen_companies:
                        continue

                    # Card parent
                    card = a.find_parent("div", class_=lambda c: c and any(k in c for k in ["item", "row", "company", "block", "entry"]))
                    if not card:
                        card = a.find_parent("div")
                    card_txt = card.get_text(" | ", strip=True) if card else ""

                    # Phone from card text
                    phone = ""
                    m_tel = re.search(r"Tel\.?\s*([0-9\s()+-]+)", card_txt)
                    if m_tel:
                        phone = clean_phone(m_tel.group(1).strip())

                    # Address from card text
                    addr = ""
                    city = ""
                    parts = [p.strip() for p in card_txt.split("|") if p.strip()]
                    for p in parts:
                        if any(k in p.upper() for k in [" G.", " AL.", " PL.", " K.", " M.", " R."]) and not p.startswith("Tel"):
                            addr = p
                            break

                    # Email from cloudflare in card
                    email = ""
                    if card:
                        for em_a in card.find_all("a", href=True):
                            if "email-protection" in em_a["href"]:
                                cf = em_a.get("data-cfemail") or em_a["href"].split("#")[-1]
                                em = decode_cf(cf)
                                if em and not any(bad in em for bad in ["wedeliver", "imones.lt"]):
                                    email = em
                                    break

                    # Website in card
                    web = ""
                    if card:
                        for w_a in card.find_all("a", href=True):
                            href = w_a["href"]
                            if href.startswith("http") and not any(x in href for x in ["imones.lt", "visalietuva.lt", "wedeliver.lt", "facebook", "linkedin"]):
                                web = href
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
                        "Source": "imones.lt",
                        "Source_URL": detail_href,
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

    print(f"\n[V] Completed Imones.lt harvest! Total records: {len(rows):,} saved to {OUT_CSV}", flush=True)


if __name__ == "__main__":
    harvest_imoneslt()
