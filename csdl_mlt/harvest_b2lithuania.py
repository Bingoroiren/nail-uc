# -*- coding: utf-8 -*-
"""
Harvest Lithuania Food / Meat / Fish Exporters Directory from B2Lithuania.com API
Target: https://b2lithuania.com/companies?sector_id=17
API: https://b2lithuania.com/api/api/companies?sector_ids[0]=17

Outputs: csdl_mlt/b2lithuania_database.csv
"""

import sys
import os
import csv
import time
from curl_cffi import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_DIR = os.path.join(os.path.dirname(__file__))
OUT_CSV = os.path.join(OUT_DIR, "b2lithuania_database.csv")

API_BASE = "https://b2lithuania.com/api/api/companies?sector_ids%5B0%5D=17"

HEADERS = [
    "Công ty",
    "IČO",
    "SĐT",
    "Web",
    "Email",
    "Địa chỉ",
    "Thành phố",
    "Doanh thu (EUR)",
    "Nhân sự",
    "Category",
    "Source",
    "Source_URL",
]


def harvest_b2lithuania():
    print("=" * 70)
    print(" HARVESTING B2LITHUANIA.COM (Sector 17: Food Industry)")
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

    # First fetch page 1 to get last_page
    last_page = 1
    try:
        r1 = requests.get(f"{API_BASE}&page=1", impersonate="chrome120", timeout=15)
        if r1.status_code == 200:
            d1 = r1.json()
            last_page = d1.get("last_page", 1)
            total = d1.get("total", 0)
            print(f"[*] Total companies: {total:,} across {last_page} pages.")
    except Exception as e:
        print(f"[-] Error fetching initial page: {e}")
        return

    for page in range(1, last_page + 1):
        url = f"{API_BASE}&page={page}"
        try:
            r = requests.get(url, impersonate="chrome120", timeout=20)
            if r.status_code != 200:
                print(f"    [!] Page {page} status {r.status_code}, skipping...")
                continue

            data = r.json()
            items = data.get("data", [])
            new_in_page = 0

            for it in items:
                comp_name = (it.get("company_name") or it.get("title") or "").strip()
                if not comp_name:
                    continue

                key = comp_name.lower()
                if key in seen_companies:
                    continue

                ico = str(it.get("company_code") or "").strip()
                web = (it.get("website") or "").strip()
                addr = (it.get("address") or "").strip()
                comp_id = it.get("id")
                source_url = f"https://b2lithuania.com/companies/{comp_id}" if comp_id else "https://b2lithuania.com/companies?sector_id=17"

                # Subsectors / Categories
                sub_names = []
                for s in it.get("sectors", []):
                    sub = s.get("subsector", {}).get("subsector")
                    if sub:
                        sub_names.append(sub)
                cat_str = ", ".join(sub_names) if sub_names else "Food industry"

                # Turnover & Employees
                turnover = str(it.get("turnover") or "").strip()
                employees = str(it.get("employees") or "").strip()

                # City from address
                city = ""
                if addr:
                    parts = [p.strip() for p in addr.split(",") if p.strip()]
                    for p in parts:
                        if any(k in p.lower() for k in [" m.", " r.", " k.", "sav."]):
                            city = p
                            break

                record = {
                    "Công ty": comp_name,
                    "IČO": ico,
                    "SĐT": "",
                    "Web": web,
                    "Email": "",
                    "Địa chỉ": addr,
                    "Thành phố": city,
                    "Doanh thu (EUR)": turnover,
                    "Nhân sự": employees,
                    "Category": cat_str,
                    "Source": "b2lithuania.com",
                    "Source_URL": source_url,
                }

                seen_companies.add(key)
                rows.append(record)
                new_in_page += 1

            print(f"    [+] Page {page}/{last_page}: +{new_in_page} companies (Total: {len(rows)})")

            # Incremental auto-save
            with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=HEADERS)
                writer.writeheader()
                writer.writerows(rows)

            time.sleep(0.4)
        except Exception as ex:
            print(f"    [!] Error on page {page}: {ex}")

    print(f"\n[V] Completed B2Lithuania harvest! Total records: {len(rows):,} saved to {OUT_CSV}")


if __name__ == "__main__":
    harvest_b2lithuania()
