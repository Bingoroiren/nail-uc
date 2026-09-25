# -*- coding: utf-8 -*-
"""
HỆ THỐNG CÀO DỮ LIỆU NHÀ MÁY ĐIỆN TỬ ĐÀI LOAN - HIỆP HỘI TEEMA (b2b.teema.org.tw)
PHIÊN BẢN TĂNG TỐC ĐA LUỒNG (HIGH-SPEED ASYNC WORKERS - GẤP 15-20 LẦN):
1. Tải danh sách 2.505 công ty từ Checkpoint đã thu thập.
2. Dùng 10 Worker bất đồng bộ (aiohttp) cào song song cực nhanh.
3. Bóc tách toàn bộ: Số lao động (Employees), Vốn (Capital), SĐT (có nháy '), Web, Mail...
4. Tự động sắp xếp giảm dần theo quy mô lao động & vốn ngay khi hoàn tất.
"""

import sys
import os
import re
import csv
import json
import time
import asyncio
import urllib.parse
from pathlib import Path
from bs4 import BeautifulSoup
import aiohttp

# Đảm bảo UTF-8 cho Windows Console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_CSV = str(ROOT_DIR / "data" / "raw" / "teema_taiwan_electronics_factories.csv")
SORTED_CSV = str(ROOT_DIR / "data" / "formatted" / "teema_taiwan_electronics_factories_sorted.csv")
PROGRESS_FILE = str(ROOT_DIR / "progress" / "progress_teema_b2b.json")

os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
os.makedirs(os.path.dirname(SORTED_CSV), exist_ok=True)
os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)

# Số luồng cào song song tối ưu tốc độ và an toàn
CONCURRENCY = 10

FIELDNAMES = [
    "Company_ID",
    "Company_Name",
    "Member_Class",
    "Tax_ID",
    "Chairman",
    "Oversea_Sales_Contact",
    "Employees",
    "Capital",
    "Phone",
    "Fax",
    "Address",
    "Website",
    "Email",
    "Email_Source",
    "Plant_Products",
    "Keyword_Groups",
    "Matched_Keywords",
    "TEEMA_URL"
]

def format_phone_with_quote(phone_str):
    """Chuẩn hóa số điện thoại, luôn thêm dấu nháy đơn ' ở đầu."""
    if not phone_str:
        return ""
    clean = str(phone_str).strip()
    if clean and not clean.startswith("'"):
        clean = f"'{clean}"
    return clean

def clean_email_string(email_str):
    """Làm sạch email, loại bỏ %20 và ký tự rác."""
    if not email_str:
        return ""
    em = urllib.parse.unquote(str(email_str)).replace('%20', '').strip().lower().rstrip('.,;:')
    if any(em.endswith(ext) for ext in ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf', '.css', '.js')):
        return ""
    if '@' not in em or len(em) < 6:
        return ""
    return em

def parse_number(val):
    """Chuyển chuỗi số có dấu phẩy thành số nguyên để sắp xếp."""
    if not val:
        return 0
    clean = re.sub(r'[^\d]', '', str(val))
    return int(clean) if clean else 0

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {"completed_accounts": [], "harvested_companies": {}}

def save_progress(progress_data):
    try:
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

# Khóa luồng an toàn khi ghi file CSV
csv_lock = asyncio.Lock()

async def append_to_csv(row_dict):
    async with csv_lock:
        file_exists = os.path.isfile(OUTPUT_CSV)
        try:
            with open(OUTPUT_CSV, mode='a', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(row_dict)
                f.flush()
        except Exception as e:
            print(f"[-] Lỗi ghi CSV: {e}")

async def fetch_company_detail_async(session, account_id, meta_info, semaphore):
    """Tải và phân tích trang chi tiết nhà máy siêu tốc bằng aiohttp."""
    detail_url = f"https://b2b.teema.org.tw/CompanyDetail_en.aspx?companyAccount={account_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    async with semaphore:
        html_text = ""
        for attempt in range(3):
            try:
                async with session.get(detail_url, headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                    if resp.status == 200:
                        html_text = await resp.text()
                        break
            except Exception:
                await asyncio.sleep(0.5)

        if not html_text:
            return None

        # Phân tích DOM cực nhanh bằng BeautifulSoup
        soup = BeautifulSoup(html_text, 'html.parser')

        def get_val(elem_id):
            elem = soup.find(id=elem_id)
            return elem.get_text(strip=True) if elem else ""

        comp_id = get_val("ContentPlaceHolder1_lblCompanyID") or account_id
        comp_name = get_val("ContentPlaceHolder1_lblCompanyName") or meta_info.get("company_name", "")
        member_class = get_val("ContentPlaceHolder1_lblMemberClass")
        tax_id = get_val("ContentPlaceHolder1_lblTaxID")
        chairman = get_val("ContentPlaceHolder1_lblPresident")
        oversea_contact = get_val("ContentPlaceHolder1_lblExportPresident")
        email_profile = get_val("ContentPlaceHolder1_lblEmail")
        employees = get_val("ContentPlaceHolder1_lblEmployeeCount")
        capital = get_val("ContentPlaceHolder1_lblCapital")
        phone = get_val("ContentPlaceHolder1_lblTel")
        fax = get_val("ContentPlaceHolder1_lblFax")
        address = get_val("ContentPlaceHolder1_lblAddress")

        website = ""
        web_elem = soup.find(id="ContentPlaceHolder1_lnkLink")
        if web_elem:
            website = (web_elem.get("href") or "").strip()

        plant_products = get_val("ContentPlaceHolder1_lblMainProduct")

        phone_formatted = format_phone_with_quote(phone)
        fax_formatted = format_phone_with_quote(fax)
        final_email = clean_email_string(email_profile)

        record = {
            "Company_ID": comp_id,
            "Company_Name": comp_name,
            "Member_Class": member_class,
            "Tax_ID": tax_id,
            "Chairman": chairman,
            "Oversea_Sales_Contact": oversea_contact,
            "Employees": employees,
            "Capital": capital,
            "Phone": phone_formatted,
            "Fax": fax_formatted,
            "Address": address,
            "Website": website,
            "Email": final_email,
            "Email_Source": "TEEMA Profile" if final_email else "",
            "Plant_Products": plant_products,
            "Keyword_Groups": "; ".join(meta_info.get("groups", [])),
            "Matched_Keywords": "; ".join(meta_info.get("keywords", [])),
            "TEEMA_URL": detail_url
        }
        return record

def sort_teema_data():
    """Tự động sắp xếp dữ liệu giảm dần theo quy mô Lao động & Vốn."""
    if not os.path.exists(OUTPUT_CSV):
        return
    with open(OUTPUT_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    if not rows:
        return

    print(f"\n[*] Đang tự động sắp xếp {len(rows)} nhà máy theo quy mô Lao động & Vốn...")
    sorted_rows = sorted(
        rows,
        key=lambda r: (parse_number(r.get("Employees", 0)), parse_number(r.get("Capital", 0))),
        reverse=True
    )

    with open(SORTED_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sorted_rows)

    print(f"[✓] ĐÃ XUẤT FILE XẾP HẠNG QUY MÔ THÀNH CÔNG: {SORTED_CSV}")
    print("\n" + "=" * 75)
    print("   TOP 10 NHÀ MÁY ĐIỆN TỬ LỚN NHẤT ĐÀI LOAN (TEEMA)")
    print("=" * 75)
    for idx, r in enumerate(sorted_rows[:10], 1):
        emp = r.get("Employees") or "N/A"
        cap = r.get("Capital") or "N/A"
        print(f" {idx:2d}. {r.get('Company_Name')}")
        print(f"     👥 Lao động: {emp:>6} người | 💰 Vốn: {cap:>15} NTD | 📞 SĐT: {r.get('Phone')}")

async def main():
    print("=" * 75)
    print("   HỆ THỐNG CÀO DỮ LIỆU TEEMA B2B (PHIÊN BẢN TĂNG TỐC ĐA LUỒNG X15)")
    print(f"   Số luồng song song: {CONCURRENCY} Workers")
    print("=" * 75)

    progress = load_progress()
    harvested = progress.get("harvested_companies", {})
    completed = set(progress.get("completed_accounts", []))

    if not harvested:
        print("[-] Chưa có danh sách thu thập trong Checkpoint. Vui lòng chạy lần đầu để gom ID.")
        return

    to_scrape = [acc for acc in harvested.keys() if acc not in completed]
    total_harvested = len(harvested)
    already_done = len(completed)
    remaining = len(to_scrape)

    print(f"[*] Tổng số nhà máy đã thu thập: {total_harvested}")
    print(f"[*] Đã cào chi tiết trước đó: {already_done}")
    print(f"[*] Còn lại cần cào siêu tốc: {remaining}")

    if remaining == 0:
        print("[+] Toàn bộ nhà máy đã được bóc tách đầy đủ!")
        sort_teema_data()
        return

    semaphore = asyncio.Semaphore(CONCURRENCY)
    connector = aiohttp.TCPConnector(limit=CONCURRENCY * 2, ssl=False)

    start_time = time.time()
    processed_count = 0

    async with aiohttp.ClientSession(connector=connector) as session:
        # Xử lý theo từng lô (batch) 30 nhà máy
        batch_size = 30
        for i in range(0, remaining, batch_size):
            batch = to_scrape[i:i + batch_size]
            tasks = []
            for acc_id in batch:
                meta = harvested[acc_id]
                tasks.append(fetch_company_detail_async(session, acc_id, meta, semaphore))

            results = await asyncio.gather(*tasks)

            for acc_id, record in zip(batch, results):
                if record:
                    await append_to_csv(record)
                    completed.add(acc_id)
                processed_count += 1

            # Lưu tiến độ định kỳ
            progress["completed_accounts"] = list(completed)
            save_progress(progress)

            elapsed = time.time() - start_time
            speed = processed_count / elapsed if elapsed > 0 else 0
            pct = ((already_done + processed_count) / total_harvested) * 100
            print(f"[+] Tiến độ: {already_done + processed_count}/{total_harvested} ({pct:.1f}%) | Tốc độ: ~{speed:.1f} cty/giây | Đang xử lý mượt mà...")

    # Tự động sắp xếp sau khi cào xong
    sort_teema_data()

    print("\n" + "=" * 75)
    print("   HOÀN TẤT CÀO DỮ LIỆU TOÀN BỘ 2.505 NHÀ MÁY TEEMA THÀNH CÔNG!")
    print(f"   Thời gian thực thi: {time.time() - start_time:.1f} giây")
    print(f"   File gốc: {OUTPUT_CSV}")
    print(f"   File đã xếp hạng: {SORTED_CSV}")
    print("=" * 75)

if __name__ == "__main__":
    asyncio.run(main())
