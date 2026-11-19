# -*- coding: utf-8 -*-
"""
PARSER BÓC TÁCH DỮ LIỆU PAGESJAUNES TỪ FILE HTML (LƯU TRỰC TIẾP TỪ TRÌNH DUYỆT)
Xử lý dữ liệu từ 2 danh mục:
1. Recrutement international (Paris)
2. Agences d'interim (Paris)
Gộp chung vào 1 file CSV chuẩn 17 ký tự: FR_AGCY_PJAU_0RAW.csv và FR_AGCY_PJAU_2COL.csv
"""

import os
import re
import csv
import glob
import unicodedata
from pathlib import Path
from bs4 import BeautifulSoup

PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

def format_french_phone(phone_raw):
    if not phone_raw:
        return ""
    # Loại bỏ khoảng trắng và ký tự không phải số/+
    clean = re.sub(r"[^\d+]", "", phone_raw.strip())
    # Nếu là dạng 01 23 45 67 89 -> chuyển thành +33 1 23 45 67 89 hoặc giữ format
    if clean.startswith("0") and len(clean) == 10:
        clean = "+33" + clean[1:]
    elif clean.startswith("0033"):
        clean = "+33" + clean[4:]
    return f"'{clean}" if clean and not clean.startswith("'") else clean

def parse_pj_html_content(html_content, source_tag="PagesJaunes"):
    soup = BeautifulSoup(html_content, "html.parser")
    records = []
    
    # Tìm các thẻ chứa doanh nghiệp
    # PagesJaunes thường dùng article.bi-bloc, li.bi-bloc, .bi-bloc, div.bi
    cards = soup.select("article.bi-bloc, li.bi-bloc, .bi-bloc, article.bi, .bi-listing-item")
    if not cards:
        # Fallback thử tìm các container có data-pj-analytics hoặc class chứa 'bi'
        cards = soup.select("[data-pj-analytics], [id^='bi-']")
    
    for card in cards:
        # 1. Tên công ty
        name_el = card.select_one(".denomination-links, .company-name, h3, .giz-__title, a.bi-denomination")
        name = name_el.get_text(strip=True) if name_el else ""
        if not name or len(name) < 2 or is_blacklisted_company(name):
            continue
            
        # 2. Hoạt động / Ngành
        act_el = card.select_one(".activite, .bi-activity, .bi-activite, .bi-tag")
        activity = act_el.get_text(strip=True) if act_el else source_tag
        
        # 3. Địa chỉ & Mã bưu chính
        addr_el = card.select_one(".adresse-bloc, .bi-address, .address, .bi-adresse")
        address = addr_el.get_text(" ", strip=True) if addr_el else ""
        postal_code = ""
        pc_match = re.search(r"\b(75\d{3})\b", address)
        if pc_match:
            postal_code = pc_match.group(1)
            
        # 4. Số điện thoại
        phone_el = card.select_one(".bi-contact-tel, span[itemprop='telephone'], .coord-numero, [data-pj-analytics*='telephone']")
        phone = ""
        if phone_el:
            phone_text = phone_el.get_text(strip=True)
            phone = format_french_phone(phone_text)
            
        # 5. Website
        web_el = card.select_one("a[data-pj-analytics*='site_internet'], .bi-site-web a, a.bi-links, a[href^='http']:not([href*='pagesjaunes.fr'])")
        website = ""
        if web_el and web_el.get("href"):
            w_href = web_el.get("href")
            # PagesJaunes redirect tracking url
            if "urldirecte=" in w_href:
                m = re.search(r"urldirecte=([^&]+)", w_href)
                if m:
                    import urllib.parse
                    website = urllib.parse.unquote(m.group(1))
            elif not "pagesjaunes.fr" in w_href:
                website = w_href
                
        # 6. Profile URL trên PagesJaunes
        pj_link = ""
        if name_el and name_el.name == "a" and name_el.get("href"):
            pj_link = "https://www.pagesjaunes.fr" + name_el.get("href") if not name_el.get("href").startswith("http") else name_el.get("href")
            
        records.append({
            "Name": name,
            "Activity": activity,
            "Address": address,
            "Postal_Code": postal_code,
            "City": "Paris",
            "Country": "France",
            "Phone": phone,
            "Website": website,
            "PagesJaunes_URL": pj_link,
            "Category_Source": source_tag
        })
        
    return records

def parse_all_saved_html(input_dir="scratch"):
    files = glob.glob(os.path.join(input_dir, "pj_*.html"))
    all_records = []
    seen = set()
    
    print(f"[*] Tìm thấy {len(files)} file HTML trong thư mục {input_dir}")
    for file_path in files:
        file_name = os.path.basename(file_path).lower()
        tag = "Recrutement International" if "recrutement" in file_name or "inter" in file_name else "Agence Interim"
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            recs = parse_pj_html_content(content, source_tag=tag)
            print(f"    - {os.path.basename(file_path)}: Bóc tách được {len(recs)} doanh nghiệp.")
            for r in recs:
                dedup_key = (r["Name"].lower().strip(), r["Phone"])
                if dedup_key not in seen:
                    seen.add(dedup_key)
                    all_records.append(r)
        except Exception as e:
            print(f"[!] Lỗi đọc file {file_path}: {e}")
            
    print(f"\n[+] Tổng số doanh nghiệp bóc tách thành công (đã khử trùng lặp): {len(all_records)}")
    
    if all_records:
        out_raw = "FR_AGCY_PJAU_0RAW.csv"
        with open(out_raw, "w", encoding="utf-8-sig", newline="") as f:
            fieldnames = ["Name", "Activity", "Address", "Postal_Code", "City", "Country", "Phone", "Website", "PagesJaunes_URL", "Category_Source"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_records)
        print(f"✅ Đã xuất file thô: {out_raw} ({len(all_records)} dòng)")
        
    return all_records

if __name__ == "__main__":
    parse_all_saved_html()

