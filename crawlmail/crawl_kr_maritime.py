"""
Crawl toan bo 4 danh muc tu MaritimePress (http://www.maritimepress.co.kr/corp/searchCorp.html):
1. 외항해운선사 (Ocean-going Shipping Companies): 157 cong ty -> Tàu to
2. 지방해운대리점 (Regional Shipping Agency): 47 cong ty -> Tàu to
3. 내항여객선사 (Domestic Passenger Ship): 37 cong ty -> Tàu to (Tàu khách)
4. 조선기자재 (Shipbuilding Equipment & Materials): 316 cong ty -> Thiết bị đóng tàu

Thu thap chi tiet: SĐT, Fax, Email, Website, Nguoi dai dien, Dia chi tu ca trang danh sach va popup info.php.
Ket hop cung du lieu 25 cong ty tu DSTUG.ORG (Cảng Daesan: Tau to va Tau dat) de ghi vao:
- KR_SHIP_DSTU_0RAW.csv
- KR_SHIP_DSTU_2COL.csv
"""

import os
import re
import sys
import csv
import time
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout.reconfigure(encoding='utf-8')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

CATEGORIES = [
    {
        "id": "Zero2N1",
        "name_kr": "외항해운선사",
        "name_vi": "Tàu to (외항해운선사 - Hãng tàu viễn dương)",
        "cat_type": "Tàu to",
        "cateno": "Zero2",
        "subCateno": "Zero2N1",
        "pages": 16,
    },
    {
        "id": "Zero2N4",
        "name_kr": "지방해운대리점",
        "name_vi": "Tàu to (지방해운대리점 - Đại lý tàu biển địa phương)",
        "cat_type": "Tàu to",
        "cateno": "Zero2",
        "subCateno": "Zero2N4",
        "pages": 5,
    },
    {
        "id": "Zero2N8",
        "name_kr": "내항여객선사",
        "name_vi": "Tàu to (내항여객선사 - Hãng tàu khách)",
        "cat_type": "Tàu to",
        "cateno": "Zero3",
        "subCateno": "Zero2N8",
        "pages": 4,
    },
    {
        "id": "Zero6",
        "name_kr": "조선기자재",
        "name_vi": "Thiết bị đóng tàu (조선기자재 - Vật tư & phụ tùng hàng hải)",
        "cat_type": "Thiết bị đóng tàu",
        "cateno": "Zero6",
        "subCateno": "",
        "pages": 32,
    },
]

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
    # Check invalid placeholder emails
    invalid = ["test@test.com", "email@email.com", "example@example.com", "none@none.com"]
    if e in invalid or "@" not in e:
        return ""
    return e

def clean_website(w):
    if not w:
        return ""
    w = w.strip().replace(" ", "")
    if w and not w.startswith("http://") and not w.startswith("https://"):
        if "." in w and not "@" in w:
            w = f"http://{w}"
        elif "@" in w:
            return "" # Sometimes email is typed into website field
    return w

def scrape_search_page(cat, page_num):
    url = f"http://www.maritimepress.co.kr/corp/searchCorp.html?page={page_num}&cateno={cat['cateno']}&subCateno={cat['subCateno']}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        r.encoding = 'utf-8'
        soup = BeautifulSoup(r.text, 'html.parser')
        table = soup.find('table')
        if not table:
            return []
        rows = table.find_all('tr')[1:]
        results = []
        for tr in rows:
            tds = tr.find_all('td')
            if len(tds) >= 5:
                company = tds[0].get_text(strip=True)
                industry = tds[1].get_text(strip=True)
                rep = tds[2].get_text(strip=True)
                addr = tds[3].get_text(strip=True)
                phone = tds[4].get_text(strip=True)

                idxno = None
                for a in tds[0].find_all('a'):
                    m = re.search(r'idxno=(\d+)', a.get('href', ''))
                    if m:
                        idxno = m.group(1)
                        break

                results.append({
                    "company": company,
                    "industry": industry,
                    "rep": rep,
                    "addr": addr,
                    "phone": phone,
                    "idxno": idxno,
                    "cat_id": cat["id"],
                    "name_kr": cat["name_kr"],
                    "name_vi": cat["name_vi"],
                    "cat_type": cat["cat_type"]
                })
        return results
    except Exception as e:
        print(f" [!] Loi page {page_num} ({cat['name_kr']}): {e}")
        return []

def scrape_popup_detail(idxno):
    url = f"http://www.maritimepress.co.kr/corp/info.php?idxno={idxno}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.encoding = 'utf-8'
        soup = BeautifulSoup(r.text, 'html.parser')
        info = {}
        for tr in soup.find_all('tr'):
            th = tr.find(['th', 'td'])
            tds = tr.find_all('td')
            if th and len(tds) >= 1:
                key = th.get_text(strip=True)
                val = tds[-1].get_text(strip=True)
                info[key] = val
        return idxno, info
    except Exception as e:
        return idxno, {}

def main():
    print("=" * 65)
    print(" CRAWLER TOAN DIEN MARITIMEPRESS & HOAN THIEN KR_SHIP_DSTU_0RAW.csv")
    print("=" * 65)

    # 1. Scraping search pages
    print("\n[BƯỚC 1/4] Đang quét 57 trang danh mục từ maritimepress.co.kr...")
    t0 = time.time()
    maritime_records = []
    page_tasks = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        for cat in CATEGORIES:
            for p in range(1, cat["pages"] + 1):
                page_tasks.append(executor.submit(scrape_search_page, cat, p))

        for f in as_completed(page_tasks):
            items = f.result()
            maritime_records.extend(items)

    print(f" -> Thu thập được {len(maritime_records)} công ty từ danh mục trong {time.time()-t0:.2f}s.")

    # 2. Scraping popup details
    unique_idxnos = list({r["idxno"] for r in maritime_records if r["idxno"]})
    print(f"\n[BƯỚC 2/4] Đang cào chi tiết (Fax, Email, Website) cho {len(unique_idxnos)} popup công ty...")
    t1 = time.time()
    popup_data = {}
    done_count = 0

    with ThreadPoolExecutor(max_workers=15) as executor:
        future_to_idx = {executor.submit(scrape_popup_detail, idx): idx for idx in unique_idxnos}
        for f in as_completed(future_to_idx):
            idx, info = f.result()
            popup_data[idx] = info
            done_count += 1
            if done_count % 100 == 0 or done_count == len(unique_idxnos):
                print(f"    - Tiến độ popup: {done_count}/{len(unique_idxnos)} ({done_count/len(unique_idxnos)*100:.1f}%)")

    print(f" -> Đã cào xong {len(popup_data)} popup chi tiết trong {time.time()-t1:.2f}s.")

    # Gộp thông tin chi tiết vào danh sách maritime
    for r in maritime_records:
        idx = r.get("idxno")
        dt = popup_data.get(idx, {})
        r["fax"] = dt.get("팩스번호", "")
        r["email"] = dt.get("이메일", "")
        r["website"] = dt.get("홈페이지", "")
        # Nếu popup có thông tin đại diện/địa chỉ chi tiết hơn
        if dt.get("대표") and not r.get("rep"):
            r["rep"] = dt.get("대표")
        if dt.get("주소") and not r.get("addr"):
            r["addr"] = dt.get("주소")

    # 3. Đọc dữ liệu DSTUG hiện tại (25 bản ghi)
    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    raw_csv_path = os.path.join(workspace_dir, "KR_SHIP_DSTU_0RAW.csv")
    col2_csv_path = os.path.join(workspace_dir, "KR_SHIP_DSTU_2COL.csv")

    existing_dstug_records = []
    if os.path.exists(raw_csv_path):
        with open(raw_csv_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Kiểm tra nếu là bản ghi nguồn DSTUG cũ
                cat_vi = row.get("Phân loại", "")
                if "Shipping Agent" in cat_vi or "Tugboat" in cat_vi or "선박대리점" in str(row) or "예선사" in str(row):
                    existing_dstug_records.append({
                        "company": row.get("Công ty (Hàn)", ""),
                        "type_vi": row.get("Phân loại", ""),
                        "type_kr": row.get("Phân loại (Hàn / Anh)", ""),
                        "category": "Tàu to" if "Tàu to" in cat_vi else "Tàu dắt",
                        "phone": row.get("SĐT", ""),
                        "fax": row.get("Số Fax", ""),
                        "email": row.get("Email", ""),
                        "rep": row.get("Người đại diện", ""),
                        "addr": row.get("Địa chỉ trụ sở", ""),
                        "website": row.get("Website", "")
                    })

    print(f"\n[BƯỚC 3/4] Tích hợp dữ liệu: {len(existing_dstug_records)} bản ghi từ DSTUG + {len(maritime_records)} bản ghi từ MaritimePress...")

    all_combined = []
    # Thêm các bản ghi DSTUG trước
    for rec in existing_dstug_records:
        all_combined.append(rec)

    # Thêm các bản ghi MaritimePress
    for r in maritime_records:
        all_combined.append({
            "company": r["company"],
            "type_vi": r["name_vi"],
            "type_kr": f"{r['industry']} ({r['name_kr']})",
            "category": r["cat_type"],
            "phone": clean_phone(r["phone"]),
            "fax": clean_phone(r["fax"]),
            "email": clean_email(r["email"]),
            "rep": r["rep"],
            "addr": r["addr"],
            "website": clean_website(r["website"])
        })

    # 4. Xuất file thô KR_SHIP_DSTU_0RAW.csv
    print(f"\n[BƯỚC 4/4] Đang ghi file KR_SHIP_DSTU_0RAW.csv...")
    raw_headers = [
        "STT", "Công ty (Hàn)", "Phân loại", "Phân loại (Hàn / Anh)", 
        "SĐT", "Số Fax", "Email", "Người đại diện", "Địa chỉ trụ sở", "Website"
    ]
    with open(raw_csv_path, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(raw_headers)
        for idx, rec in enumerate(all_combined, 1):
            writer.writerow([
                idx,
                rec["company"],
                rec["type_vi"],
                rec["type_kr"],
                rec["phone"],
                rec["fax"],
                rec["email"],
                rec["rep"],
                rec["addr"],
                rec["website"]
            ])
    print(f" -> Đã lưu thành công {len(all_combined)} dòng vào {raw_csv_path}")

    # Đồng bộ cập nhật luôn KR_SHIP_DSTU_2COL.csv (đẩy email lên đầu danh sách)
    print(" -> Đang đồng bộ cập nhật KR_SHIP_DSTU_2COL.csv...")
    with_email = [r for r in all_combined if r["email"]]
    without_email = [r for r in all_combined if not r["email"]]
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
                rec["category"],           # Chức danh / Phân loại
                rec["rep"],                # Người liên hệ
                rec["phone"],              # SĐT
                rec["website"],            # Liên Hệ (Website)
                rec["email"],              # Email
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
                category_str               # Category
            ])
    print(f" -> Đã lưu thành công {len(sorted_records)} dòng vào {col2_csv_path} (Có Email: {len(with_email)} | Không Email: {len(without_email)})")
    print("\n[V] HOÀN TẤT XỬ LÝ TOÀN BỘ YÊU CẦU!")

if __name__ == "__main__":
    main()
