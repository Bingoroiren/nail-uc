import os
import sys
import csv
import html
import requests
from bs4 import BeautifulSoup

# Ensure UTF-8 output on Windows console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

URL = "https://nyidanmark.dk/en-GB/Words-and-concepts/SIRI/Certified-companies"
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if "crawlmail" in os.path.dirname(os.path.abspath(__file__)) else os.path.dirname(os.path.abspath(__file__))

TARGET_CSV_STANDARD = os.path.join(WORKSPACE_DIR, "(11_9) SIRI Certified companies Denmark - Trang tính1.csv")
TARGET_CSV_CLEAN = os.path.join(WORKSPACE_DIR, "siri_certified_companies_denmark.csv")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-GB,en;q=0.9,da;q=0.8',
}

def fetch_html():
    print(f"[*] Dang tai du lieu truc tiep tu: {URL} ...")
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=20)
        if resp.status_code == 200:
            print("[+] Tai du lieu thanh cong qua HTTP Requests.")
            return resp.text
    except Exception as e:
        print(f"[-] Loi ket noi HTTP: {e}")

    # Fallback to local cache if available
    local_cache = r"C:\Users\Admin\.gemini\antigravity-ide\brain\ef352db8-03a5-4dae-92ec-f1a2c452d11e\.system_generated\steps\135\content.md"
    if os.path.exists(local_cache):
        print(f"[*] Doc du lieu du phong tu cache cuc bo: {local_cache} ...")
        with open(local_cache, "r", encoding="utf-8") as f:
            return f.read()

    raise RuntimeError("Khong the lay du lieu trang web!")

def parse_companies(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        raise ValueError("Khong tim thay bang du lieu tren trang web!")

    table = tables[0]
    rows = table.find_all("tr")
    print(f"[*] Tim thay {len(rows)} the <tr> trong bang.")

    companies = []
    for idx, r in enumerate(rows[1:], 1):
        tds = r.find_all(["td", "th"])
        if len(tds) < 2:
            continue
        raw_name = tds[0].get_text().replace('\xa0', ' ').strip()
        raw_cvr = tds[1].get_text().replace('\xa0', ' ').strip()

        name = html.unescape(raw_name).strip()
        cvr = html.unescape(raw_cvr).strip()

        if not name and not cvr:
            continue

        companies.append({
            "no": str(idx),
            "company_name": name,
            "cvr": cvr,
            "cvr_quoted": f"'{cvr}" if cvr else "",
        })

    return companies

def export_to_csv(companies):
    # 1. Export Standard Template CSV for Google Sheets
    standard_headers = [
        "No.", "Cong ty", "CVR no.", "Chuc danh", "Nguoi lien he",
        "SDT", "Lien He", "Email", "Lien He mail", "Dia chi",
        "Luong", "Ngay dang", "Han tuyen", "Check gui",
        "Last Subject", "Last Body HTML", "Trang thai Reply",
        "Lan Follow-up", "Ngay Follow-up gan nhat", "Mailbox da dung", "Category"
    ]

    print(f"[*] Dang xuat file chuan Google Sheets: {TARGET_CSV_STANDARD} ...")
    with open(TARGET_CSV_STANDARD, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(standard_headers)
        for c in companies:
            writer.writerow([
                c["no"],
                c["company_name"],
                c["cvr_quoted"],
                "",  # Chuc danh
                "",  # Nguoi lien he
                "",  # SDT
                URL,  # Lien He (nguon SIRI)
                "",  # Email
                "",  # Lien He mail
                "",  # Dia chi
                "",  # Luong
                "",  # Ngay dang
                "",  # Han tuyen
                "",  # Check gui
                "",  # Last Subject
                "",  # Last Body HTML
                "",  # Trang thai Reply
                "0",  # Lan Follow-up
                "",  # Ngay Follow-up gan nhat
                "",  # Mailbox da dung
                "Doanh nghiệp chứng nhận SIRI (Fast-track Denmark)"  # Category
            ])

    # 2. Export Clean Direct CSV
    clean_headers = ["No.", "Name of company", "CVR no.", "Source"]
    print(f"[*] Dang xuat file danh sach gon: {TARGET_CSV_CLEAN} ...")
    with open(TARGET_CSV_CLEAN, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(clean_headers)
        for c in companies:
            writer.writerow([
                c["no"],
                c["company_name"],
                c["cvr_quoted"],
                URL
            ])

    print("=" * 68)
    print(" [KET QUA CAO DANH SACH SIRI CERTIFIED COMPANIES]")
    print(f"  - Tong so cong ty cao duoc: {len(companies)}")
    print(f"  - File chuan Google Sheets: {TARGET_CSV_STANDARD}")
    print(f"  - File rut gon: {TARGET_CSV_CLEAN}")
    print("=" * 68)

def main():
    html_content = fetch_html()
    companies = parse_companies(html_content)
    export_to_csv(companies)

if __name__ == "__main__":
    main()
