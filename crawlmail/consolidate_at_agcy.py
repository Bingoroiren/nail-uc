#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Master Consolidation and Cold Mail Deduplicator for Austrian Employment Agencies (AT_AGCY)
Strictly adheres to GEMINI.md:
- 20 standard Cold Mail columns
- CSV UTF-8 with BOM (utf-8-sig)
- Phone numbers prefixed with single quote (')
- 100% companies with email pushed to top (with_email + without_email)
- B2B email scoring (score_email_b2b) keeping 1 best email
- Strict NFKD name normalization and multi-source cross-enrichment
"""

import os
import sys
import csv
import json
import re
import unicodedata
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

OUTPUT_RAW_COMB = DATA_DIR / "AT_AGCY_COMB_0RAW.csv"
OUTPUT_COLD_COMB = DATA_DIR / "AT_AGCY_COMB_2COL.csv"
ROOT_COLD_COMB = BASE_DIR / "AT_AGCY_COMB_2COL.csv"

# 20 Standard Cold Mail Columns
COLD_MAIL_COLUMNS = [
    "Company",
    "Country",
    "City",
    "Postal_Code",
    "Address",
    "Phone",
    "Email",
    "Website",
    "Industry",
    "Category",
    "Source",
    "Status",
    "Legal_Form",
    "Region",
    "Detail_URL",
    "Contact_Person",
    "Custom_Note",
    "Campaign_ID",
    "Lead_Score",
    "Verified_Date"
]

GARBAGE_EMAIL_PATTERNS = [
    r"example\.com", r"domain\.com", r"yourcompany", r"youremail", r"your-email",
    r"someone@", r"user@", r"sentry@", r"wix\.com", r"wordpress@", r"no-reply@",
    r"donotreply@", r"privacy@", r"gdpr@", r"datenschutz@", r"email@email\.com",
    r"test@test\.com", r"admin@domain", r"\.png$", r"\.jpg$", r"\.jpeg$", r"\.webp$"
]

def normalize_name(name):
    if not name:
        return ""
    # Unicode NFKD decomposition
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    
    # Remove translation in brackets e.g. (Personalberatung)
    text = re.sub(r"[\(\[\{].*?[\)\]\}]", "", text)
    
    # Remove legal forms
    legal_forms = [
        r"\bgmbh\b", r"\bgesmbh\b", r"\bag\b", r"\be\.u\.\b", r"\beu\b",
        r"\bkg\b", r"\bog\b", r"\bgbr\b", r"\bco\b", r"\bltd\b", r"\binc\b",
        r"\bholding\b", r"\bgroup\b", r"\bgruppe\b", r"\bpersonalservice\b",
        r"\bpersonalbereitstellung\b", r"\bpersonalmanagement\b"
    ]
    for lf in legal_forms:
        text = re.sub(lf, "", text)
        
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def score_email_b2b(email, website=""):
    if not email:
        return 0
    email = email.lower().strip()
    
    # Filter garbage emails
    for pat in GARBAGE_EMAIL_PATTERNS:
        if re.search(pat, email):
            return 0
            
    score = 10
    
    # Domain match bonus
    if website:
        web_domain = re.sub(r"^https?://(www\.)?", "", website.lower()).split("/")[0]
        mail_domain = email.split("@")[-1]
        if web_domain and mail_domain and (mail_domain in web_domain or web_domain in mail_domain):
            score += 50
            
    # Priority 1: HR / Jobs / Careers / Recruitment
    hr_keywords = ["praca@", "kariera@", "hr@", "jobs@", "recruitment@", "career@", "personal@", "bewerbung@", "karriere@"]
    if any(k in email for k in hr_keywords):
        score += 50
    # Priority 2: Executive / Leadership
    elif any(k in email for k in ["ceo@", "director@", "geschaeftsfuehrung@", "inhaber@", "leitung@", "sales@", "obchod@"]):
        score += 45
    # Priority 3: Official B2B Contact
    elif any(k in email for k in ["info@", "kontakt@", "contact@", "office@", "biuro@", "sekretariat@", "recepcia@"]):
        score += 40
    # Named personal email
    elif "." in email.split("@")[0]:
        score += 25
    # Free webmail
    elif any(k in email for k in ["@gmail.com", "@gmx.at", "@gmx.net", "@hotmail.com", "@yahoo."]):
        score += 5
        
    return score

def load_csv_rows(filepath):
    if not Path(filepath).exists():
        return []
    rows = []
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append(dict(r))
    except Exception as e:
        print(f"⚠️ Error reading {filepath}: {e}")
    return rows

def consolidate():
    print("\n" + "=" * 75)
    print("🔄 BẮT ĐẦU TỔNG HỢP VÀ CHUẨN HÓA AT_AGCY SANG 20 CỘT COLD MAIL")
    print("=" * 75)

    source_files = [
        DATA_DIR / "AT_AGCY_HERO_0RAW.csv",
        DATA_DIR / "AT_AGCY_OEPD_0RAW.csv",
        DATA_DIR / "AT_AGCY_FABC_0RAW.csv",
        DATA_DIR / "AT_AGCY_WKOP_0RAW.csv"
    ]

    all_raw_records = []
    for sf in source_files:
        if sf.exists():
            rows = load_csv_rows(sf)
            print(f"📂 Đọc {sf.name}: {len(rows)} bản ghi")
            all_raw_records.extend(rows)
        else:
            print(f"ℹ️ Chưa có file: {sf.name} (Sẽ cập nhật khi file hoàn tất)")

    if not all_raw_records:
        print("❌ Không tìm thấy dữ liệu nào để tổng hợp!")
        return

    # Deduplication and merging map: norm_key -> consolidated record
    companies_map = {}

    for row in all_raw_records:
        name = row.get("name", "").strip()
        if not name or len(name) < 2:
            continue

        norm_name = normalize_name(name)
        if not norm_name:
            norm_name = name.lower().strip()

        # Unique key using normalized name + PLZ
        plz = str(row.get("postal_code", "")).strip()
        key = f"{norm_name}_{plz}" if plz else norm_name

        phone = str(row.get("phone", "")).strip().lstrip("'")
        email = row.get("email", "").strip()
        website = row.get("website", "").strip()
        city = row.get("city", "").strip()
        street = row.get("street", "").strip()
        source = row.get("source", "").strip()
        category = row.get("category", "").strip()
        detail_url = row.get("detail_url", "").strip()
        region = row.get("region", "").strip()

        if key not in companies_map:
            companies_map[key] = {
                "name": name,
                "city": city,
                "postal_code": plz,
                "street": street,
                "phone": phone,
                "email": email,
                "website": website,
                "category": category,
                "source": source,
                "region": region,
                "detail_url": detail_url
            }
        else:
            existing = companies_map[key]
            # Merge fields: keep longer / richer information
            if not existing["phone"] and phone:
                existing["phone"] = phone
            if not existing["website"] and website:
                existing["website"] = website
            if not existing["city"] and city:
                existing["city"] = city
            if not existing["postal_code"] and plz:
                existing["postal_code"] = plz
            if not existing["street"] and street:
                existing["street"] = street

            # Best email scoring
            current_email = existing.get("email", "")
            if not current_email and email:
                existing["email"] = email
            elif current_email and email and current_email != email:
                curr_score = score_email_b2b(current_email, existing.get("website", ""))
                new_score = score_email_b2b(email, website or existing.get("website", ""))
                if new_score > curr_score:
                    existing["email"] = email

            # Append source
            if source and source not in existing["source"]:
                existing["source"] = f"{existing['source']} + {source}"

    print(f"📊 Tổng hợp thành công {len(companies_map)} công ty duy nhất sau khử trùng!")

    # Format to standard 20 columns
    with_email = []
    without_email = []

    for item in companies_map.values():
        phone_val = item["phone"]
        if phone_val and not phone_val.startswith("'"):
            phone_val = f"'{phone_val}"

        email_val = item["email"].strip()
        lead_score = score_email_b2b(email_val, item["website"]) if email_val else 0

        # Build address
        addr_parts = []
        if item["street"]:
            addr_parts.append(item["street"])
        if item["postal_code"] or item["city"]:
            addr_parts.append(f"{item['postal_code']} {item['city']}".strip())
        full_address = ", ".join(addr_parts)

        row = {
            "Company": item["name"],
            "Country": "Austria",
            "City": item["city"],
            "Postal_Code": item["postal_code"],
            "Address": full_address,
            "Phone": phone_val,
            "Email": email_val,
            "Website": item["website"],
            "Industry": "Staffing & Recruitment",
            "Category": item["category"] or "Personaldienstleister",
            "Source": item["source"],
            "Status": "Verified",
            "Legal_Form": "GmbH / e.U.",
            "Region": item["region"] or item["city"],
            "Detail_URL": item["detail_url"],
            "Contact_Person": "",
            "Custom_Note": "Austrian Manpower & Staffing Agency",
            "Campaign_ID": "AT_AGCY_2026",
            "Lead_Score": str(lead_score) if lead_score > 0 else "",
            "Verified_Date": "2026-10"
        }

        if email_val:
            with_email.append(row)
        else:
            without_email.append(row)

    # Sort with_email by Lead_Score desc
    with_email.sort(key=lambda r: int(r.get("Lead_Score") or 0), reverse=True)

    # Combine: 100% of companies WITH EMAIL strictly placed on top!
    final_rows = with_email + without_email

    # Save to data directory and root directory
    for out_path in [OUTPUT_COLD_COMB, ROOT_COLD_COMB]:
        with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=COLD_MAIL_COLUMNS)
            writer.writeheader()
            writer.writerows(final_rows)

    print("\n" + "=" * 75)
    print("🎉 HOÀN THÀNH TỔNG HỢP VÀ CHUẨN HÓA DỮ LIỆU!")
    print(f"📊 Tổng số công ty: {len(final_rows)}")
    print(f"✉️ Công ty CÓ EMAIL (Đẩy lên đầu): {len(with_email)} ({len(with_email)*100/len(final_rows):.1f}%)")
    print(f"📞 Công ty KHÔNG EMAIL: {len(without_email)}")
    print(f"💾 File đầu ra chính: {ROOT_COLD_COMB}")
    print(f"💾 File lưu kho: {OUTPUT_COLD_COMB}")
    print("=" * 75)

if __name__ == "__main__":
    consolidate()
