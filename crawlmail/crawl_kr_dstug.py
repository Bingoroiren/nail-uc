"""
Crawl 2 danh sach tu http://www.dstug.org/19:
1. Danh sach 1: 선박대리점 (Shipping Agent) -> Đánh dấu: Tàu to (Đại lý tàu buôn / tàu chở hàng)
2. Danh sach 2: 예선사 (Tugboat Company) -> Đánh dấu: Tàu dắt (Công ty tàu lai dắt / tàu kéo)

Kèm theo thông tin Người đại diện (대표자명) và Địa chỉ trụ sở (소재지) từ trang hội viên http://www.dstug.org/17.
Xuất ra 2 file theo chuẩn workspace:
- KR_SHIP_DSTU_0RAW.csv (Chi tiết tất cả trường: Tên, Phân loại VN & KR, SĐT, Fax, Email, Người đại diện, Địa chỉ)
- KR_SHIP_DSTU_2COL.csv (Chuẩn 20 cột Cold Mail B2B, email lên đầu, nháy đơn SĐT)
"""

import os
import sys
import csv
import urllib.request
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

BASE_URL_19 = "http://www.dstug.org/19"
BASE_URL_17 = "http://www.dstug.org/17"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def clean_phone(p):
    if not p:
        return ""
    p = p.strip()
    if p and not p.startswith("'"):
        p = f"'{p}"
    return p

def clean_email(e):
    if not e:
        return ""
    e = e.strip().replace("%20", "").lower()
    return e

def fetch_page(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode('utf-8', errors='ignore')

def main():
    print("[1/4] Dang tai du lieu tu http://www.dstug.org/17 (Thong tin bo sung Dai dien & Dia chi)...")
    extra_info = {}
    try:
        html_17 = fetch_page(BASE_URL_17)
        soup_17 = BeautifulSoup(html_17, "html.parser")
        tables_17 = soup_17.find_all("table")
        if tables_17:
            # Table 0: 업체명 | 대표자명 | 소재지 | 전화
            for tr in tables_17[0].find_all("tr")[1:]:
                tds = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if len(tds) >= 4:
                    company = tds[0]
                    rep = tds[1]
                    addr = tds[2]
                    phone = tds[3]
                    extra_info[company] = {
                        "rep": rep,
                        "addr": addr,
                        "phone": phone
                    }
        print(f" -> Da thu thap thong tin bo sung cho {len(extra_info)} cong ty tu trang 17.")
    except Exception as ex:
        print(f" [!] Khong the lay trang 17: {ex}")

    print("\n[2/4] Dang cao 2 danh sach tu http://www.dstug.org/19...")
    html_19 = fetch_page(BASE_URL_19)
    soup_19 = BeautifulSoup(html_19, "html.parser")
    tables_19 = soup_19.find_all("table")

    raw_records = []

    # Table 0: 선박대리점 (Shipping Agent) - Tàu to
    if len(tables_19) > 0:
        t0 = tables_19[0]
        rows = t0.find_all("tr")[1:]
        print(f" -> Bang 1: 선박대리점 (Shipping Agent - Tàu to): {len(rows)} cong ty")
        for r in rows:
            tds = [td.get_text(strip=True) for td in r.find_all(["td", "th"])]
            if len(tds) >= 4:
                company = tds[0]
                phone = tds[1]
                fax = tds[2]
                email = tds[3]
                rep = extra_info.get(company, {}).get("rep", "")
                addr = extra_info.get(company, {}).get("addr", "")
                raw_records.append({
                    "company": company,
                    "type_vi": "Tàu to (Đại lý tàu / Shipping Agent)",
                    "type_kr": "선박대리점 (Shipping Agent)",
                    "category": "Tàu to",
                    "phone": clean_phone(phone),
                    "fax": clean_phone(fax),
                    "email": clean_email(email),
                    "rep": rep,
                    "addr": addr
                })

    # Table 1: 예선사 (Tugboat Company) - Tàu dắt
    if len(tables_19) > 1:
        t1 = tables_19[1]
        rows = t1.find_all("tr")[1:]
        print(f" -> Bang 2: 예선사 (Tugboat Company - Tàu dắt): {len(rows)} cong ty")
        for r in rows:
            tds = [td.get_text(strip=True) for td in r.find_all(["td", "th"])]
            if len(tds) >= 4:
                company = tds[0]
                phone = tds[1]
                fax = tds[2]
                email = tds[3]
                rep = extra_info.get(company, {}).get("rep", "")
                addr = extra_info.get(company, {}).get("addr", "")
                raw_records.append({
                    "company": company,
                    "type_vi": "Tàu dắt (Công ty tàu dắt / Tugboat)",
                    "type_kr": "예선사 (Tug Business)",
                    "category": "Tàu dắt",
                    "phone": clean_phone(phone),
                    "fax": clean_phone(fax),
                    "email": clean_email(email),
                    "rep": rep,
                    "addr": addr
                })

    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    raw_csv_path = os.path.join(workspace_dir, "KR_SHIP_DSTU_0RAW.csv")
    col2_csv_path = os.path.join(workspace_dir, "KR_SHIP_DSTU_2COL.csv")

    print("\n[3/4] Dang xuat file thô KR_SHIP_DSTU_0RAW.csv...")
    raw_headers = [
        "STT", "Công ty (Hàn)", "Phân loại", "Phân loại (Hàn / Anh)", 
        "SĐT", "Số Fax", "Email", "Người đại diện", "Địa chỉ trụ sở"
    ]
    with open(raw_csv_path, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(raw_headers)
        for idx, rec in enumerate(raw_records, 1):
            writer.writerow([
                idx,
                rec["company"],
                rec["type_vi"],
                rec["type_kr"],
                rec["phone"],
                rec["fax"],
                rec["email"],
                rec["rep"],
                rec["addr"]
            ])
    print(f" -> Da luu {len(raw_records)} dong vao: {raw_csv_path}")

    print("\n[4/4] Dang chuan hoa va xuat file Cold Mail KR_SHIP_DSTU_2COL.csv (20 cot chuan)...")
    # Rule: Day toan bo cong ty co email len dau danh sach
    with_email = [r for r in raw_records if r["email"]]
    without_email = [r for r in raw_records if not r["email"]]
    sorted_records = with_email + without_email

    col2_headers = [
        "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ", 
        "Email", "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển", 
        "Check gửi", "Last Subject", "Last Body HTML", "Trạng thái Reply", 
        "Lần Follow-up", "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
    ]

    with open(col2_csv_path, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(col2_headers)
        for idx, rec in enumerate(sorted_records, 1):
            category_str = f"{rec['category']} ({rec['type_kr']})"
            writer.writerow([
                idx,
                rec["company"],
                rec["category"],           # Chức danh / Phân loại: Tàu to hoặc Tàu dắt
                rec["rep"],                # Người liên hệ / Đại diện
                rec["phone"],              # SĐT có nháy đơn '
                "",                        # Liên Hệ
                rec["email"],              # Email duy nhất sạch
                "",                        # Liên Hệ mail
                rec["addr"],               # Địa chỉ
                "",                        # Lương
                "",                        # Ngày đăng
                "",                        # Hạn tuyển
                "",                        # Check gửi
                "",                        # Last Subject
                "",                        # Last Body HTML
                "",                        # Trạng thái Reply
                "",                        # Lần Follow-up
                "",                        # Ngày Follow-up gần nhất
                "",                        # Mailbox đã dùng
                category_str               # Category: Tàu to (...) / Tàu dắt (...)
            ])
    print(f" -> Da luu {len(sorted_records)} dong vao: {col2_csv_path} (Co email: {len(with_email)} | Khong email: {len(without_email)})")
    print("\n[V] HOAN TAT! Tat ca file da duoc tao thanh cong!")

if __name__ == "__main__":
    main()
