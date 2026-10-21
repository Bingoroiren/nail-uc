# -*- coding: utf-8 -*-
"""
Hệ thống cào tuyển dụng Thợ hàn đóng tàu (Visa E-7-3) từ 3 nguồn cốt lõi:
1. Work24 (Cổng việc làm Quốc gia work24.go.kr - Bắt buộc tuyển nội địa trước khi xin Quota E-7-3)
2. Saramin (saramin.co.kr - Chuyên sâu thầu phụ đóng tàu)
3. JobKorea (jobkorea.co.kr - Nhà thầu phụ HD Hyundai, Samsung, Hanwha)

Xuất ra: KR_WELD_E703_0RAW.csv (20 cột chuẩn Cold Mail UTF-8 with BOM)
"""

import sys
import os
import re
import csv
import time
import urllib.parse
from pathlib import Path
from bs4 import BeautifulSoup

try:
    from curl_cffi import requests
    HAS_CURL_CFFI = True
except ImportError:
    import urllib.request as requests
    HAS_CURL_CFFI = False

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_CSV = str(ROOT_DIR / "KR_WELD_E703_0RAW.csv")

HEADERS = [
    'No.', 'Cong ty', 'Chuc danh', 'Nguoi lien he', 'SDT', 
    'Lien He', 'Email', 'Lien He mail', 'Dia chi', 'Luong', 
    'Ngay dang', 'Han tuyen', 'Check gui', 'Last Subject', 
    'Last Body HTML', 'Trang thai Reply', 'Lan Follow-up', 
    'Ngay Follow-up gan nhat', 'Mailbox da dung', 'Category'
]

SEARCH_KEYWORDS = [
    "선박 용접",        # Hàn tàu biển
    "사내협력사 용접",  # Hàn tại công ty thầu phụ
    "조선소 용접",      # Hàn xưởng đóng tàu
    "선박 취부",        # Thợ lắp ráp kết cấu vỏ tàu
    "선박 배관 용접",   # Hàn đường ống tàu biển
]

def clean_company_name(name):
    if not name:
        return ""
    name = re.sub(r'[\r\n\t]+', ' ', name).strip()
    name = re.sub(r'\s+', ' ', name)
    return name

def get_session():
    if HAS_CURL_CFFI:
        return requests.Session(impersonate="chrome120")
    return None

# ==============================================================================
# 1. CÀO TỪ SARAMIN (saramin.co.kr)
# ==============================================================================
def scrape_saramin(session, keywords, max_pages=3):
    print("\n" + "=" * 60)
    print(" [1/3] ĐANG CÀO DỮ LIỆU TỪ SARAMIN (saramin.co.kr)...")
    print("=" * 60)
    
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    for kw in keywords:
        print(f"\n[*] Saramin - Từ khóa: [{kw}]")
        for page in range(1, max_pages + 1):
            encoded_kw = urllib.parse.quote(kw)
            url = f"https://www.saramin.co.kr/zf_user/search/recruit?searchword={encoded_kw}&recruitPage={page}"
            try:
                r = session.get(url, headers=headers, timeout=12)
                if r.status_code != 200:
                    print(f" -> Trang {page} lỗi HTTP {r.status_code}")
                    break
                
                soup = BeautifulSoup(r.text, "html.parser")
                items = soup.select("div.item_recruit")
                if not items:
                    print(f" -> Hết dữ liệu ở trang {page}")
                    break
                
                print(f" -> Trang {page}: Tìm thấy {len(items)} tin tuyển dụng")
                for it in items:
                    corp_el = it.select_one("strong.corp_name a") or it.select_one("strong.corp_name")
                    if not corp_el:
                        continue
                    corp_name = clean_company_name(corp_el.text)
                    if not corp_name:
                        continue
                        
                    tit_el = it.select_one("h2.job_tit a")
                    job_title = tit_el.text.strip() if tit_el else ""
                    job_href = "https://www.saramin.co.kr" + tit_el.get("href") if tit_el and tit_el.get("href") else ""
                    
                    conditions = [s.text.strip() for s in it.select("div.job_condition span")]
                    loc_text = conditions[0] if conditions else ""
                    
                    date_el = it.select_one("span.date")
                    due_date = date_el.text.strip() if date_el else ""

                    results.append({
                        "Cong ty": corp_name,
                        "Chuc danh": f"[Thợ hàn/kỹ thuật] {job_title}",
                        "Nguoi lien he": "Phòng Nhân Sự / Tuyển Dụng",
                        "SDT": "",
                        "Lien He": job_href,
                        "Email": "",
                        "Lien He mail": job_href,
                        "Dia chi": loc_text,
                        "Luong": "Thỏa thuận theo bậc tay nghề E-7-3",
                        "Ngay dang": "2026-10-06",
                        "Han tuyen": due_date,
                        "Category": f"Tuyển thợ hàn đóng tàu (Saramin - {kw})"
                    })
                time.sleep(0.5)
            except Exception as e:
                print(f" -> Lỗi cào Saramin trang {page}: {e}")
                break
                
    print(f"\n[+] Tổng số tin thu thập từ Saramin: {len(results)}")
    return results

# ==============================================================================
# 2. CÀO TỪ WORK24 (work24.go.kr - Cổng việc làm Quốc gia Hàn Quốc)
# ==============================================================================
def scrape_work24(session, keywords, max_pages=3):
    print("\n" + "=" * 60)
    print(" [2/3] ĐANG CÀO DỮ LIỆU TỪ WORK24 (work24.go.kr - Cổng QG)...")
    print("=" * 60)
    
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    for kw in keywords:
        print(f"\n[*] Work24 - Từ khóa: [{kw}]")
        for page in range(1, max_pages + 1):
            encoded_kw = urllib.parse.quote(kw)
            url = f"https://www.work24.go.kr/wk/a/b/1200/retriveDtlEmpSrchList.do?srcKeyword={encoded_kw}&pageIndex={page}"
            try:
                r = session.get(url, headers=headers, timeout=12)
                if r.status_code != 200:
                    print(f" -> Trang {page} lỗi HTTP {r.status_code}")
                    break
                
                soup = BeautifulSoup(r.text, "html.parser")
                tables = soup.find_all("table")
                job_table = None
                for t in tables:
                    th_text = t.text
                    if "회사명" in th_text or "채용공고명" in th_text:
                        job_table = t
                        break
                        
                if not job_table:
                    # Thử lấy bảng cuối cùng
                    if tables:
                        job_table = tables[-1]

                if not job_table:
                    print(f" -> Không tìm thấy bảng việc làm Work24 ở trang {page}")
                    break

                trs = job_table.find_all("tr")
                found_in_page = 0
                for tr in trs:
                    tds = tr.find_all("td")
                    if len(tds) < 3:
                        continue
                    
                    # Col 0: Tên công ty + Tiêu đề
                    col0 = tds[0]
                    # Tìm link chi tiết
                    a_link = col0.find("a")
                    job_href = ""
                    job_title = ""
                    if a_link:
                        job_href = "https://www.work24.go.kr" + a_link.get("href") if a_link.get("href") else ""
                        job_title = a_link.text.strip()
                    
                    corp_div = col0.find("div", class_="cp-info") or col0.find("strong") or col0.find("a")
                    # Tách tên công ty
                    lines = [l.strip() for l in col0.text.split("\n") if l.strip()]
                    corp_name = lines[0] if lines else ""
                    if corp_name == job_title and len(lines) > 1:
                        corp_name = lines[1]
                    corp_name = clean_company_name(corp_name)
                    if not corp_name or len(corp_name) < 2:
                        continue

                    # Col 1: Lương & Điều kiện
                    col1_text = tds[1].text.strip().replace("\n", " ") if len(tds) > 1 else ""
                    
                    # Col 2: Hạn nộp & Địa điểm
                    col2_text = tds[2].text.strip().replace("\n", " ") if len(tds) > 2 else ""

                    # Phân tích hạn nộp
                    due_m = re.search(r'마감일\s*:\s*([0-9\-\.]+)', col2_text)
                    reg_m = re.search(r'등록일\s*:\s*([0-9\-\.]+)', col2_text)
                    due_date = due_m.group(1) if due_m else ""
                    reg_date = reg_m.group(1) if reg_m else "2026-10-06"

                    results.append({
                        "Cong ty": corp_name,
                        "Chuc danh": f"[Work24 QG] {job_title if job_title else 'Tuyển thợ hàn/thợ phụ đóng tàu'}",
                        "Nguoi lien he": "Phòng Tuyển Dụng / Nhân Sự",
                        "SDT": "",
                        "Lien He": job_href if job_href else url,
                        "Email": "",
                        "Lien He mail": job_href if job_href else url,
                        "Dia chi": "Hàn Quốc (Xưởng đóng tàu thầu phụ)",
                        "Luong": col1_text[:60] if col1_text else "Theo bậc thợ hàn E-7-3",
                        "Ngay dang": reg_date,
                        "Han tuyen": due_date,
                        "Category": f"Work24 Cổng QG - Đang tuyển thợ hàn ({kw})"
                    })
                    found_in_page += 1

                print(f" -> Trang {page}: Tìm thấy {found_in_page} tin tuyển dụng trên Work24")
                if found_in_page == 0:
                    break
                time.sleep(0.5)
            except Exception as e:
                print(f" -> Lỗi cào Work24 trang {page}: {e}")
                break

    print(f"\n[+] Tổng số tin thu thập từ Work24: {len(results)}")
    return results

# ==============================================================================
# 3. CÀO TỪ JOBKOREA (jobkorea.co.kr)
# ==============================================================================
def scrape_jobkorea(session, keywords, max_pages=3):
    print("\n" + "=" * 60)
    print(" [3/3] ĐANG CÀO DỮ LIỆU TỪ JOBKOREA (jobkorea.co.kr)...")
    print("=" * 60)
    
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    for kw in keywords:
        print(f"\n[*] JobKorea - Từ khóa: [{kw}]")
        for page in range(1, max_pages + 1):
            encoded_kw = urllib.parse.quote(kw)
            url = f"https://www.jobkorea.co.kr/Search/?stext={encoded_kw}&tabType=recruit&Page_No={page}"
            try:
                r = session.get(url, headers=headers, timeout=12)
                if r.status_code != 200:
                    print(f" -> Trang {page} lỗi HTTP {r.status_code}")
                    break
                
                soup = BeautifulSoup(r.text, "html.parser")
                # Tìm các liên kết bài đăng tuyển /Recruit/GI_Read/
                gi_links = soup.find_all("a", href=re.compile(r'/Recruit/GI_Read/'))
                
                page_jobs = {}
                for a in gi_links:
                    href = a.get("href")
                    if not href:
                        continue
                    full_href = href if href.startswith("http") else "https://www.jobkorea.co.kr" + href
                    clean_url = full_href.split("?")[0]
                    text = clean_company_name(a.text)
                    if not text:
                        continue
                    
                    if clean_url not in page_jobs:
                        page_jobs[clean_url] = {"href": full_href, "texts": []}
                    page_jobs[clean_url]["texts"].append(text)

                found_in_page = 0
                for curl, data in page_jobs.items():
                    texts = [t for t in data["texts"] if t]
                    if not texts:
                        continue
                    
                    # Xác định tên công ty và tiêu đề
                    corp_name = ""
                    job_title = ""
                    for t in texts:
                        if any(ext in t for ext in ["(주)", "주식회사", "㈜", "기업", "중공업", "조선", "이엔지", "ENG", "테크", "산업"]):
                            corp_name = t
                            break
                    if not corp_name:
                        corp_name = texts[-1]
                        
                    for t in texts:
                        if t != corp_name:
                            job_title = t
                            break
                    if not job_title:
                        job_title = "Tuyển thợ hàn/thợ đóng tàu xưởng Hyundai/Samsung/Hanwha"

                    corp_name = clean_company_name(corp_name)
                    if not corp_name or len(corp_name) < 2:
                        continue

                    results.append({
                        "Cong ty": corp_name,
                        "Chuc danh": f"[JobKorea] {job_title}",
                        "Nguoi lien he": "Phòng Tuyển Dụng / Nhân Sự",
                        "SDT": "",
                        "Lien He": data["href"],
                        "Email": "",
                        "Lien He mail": data["href"],
                        "Dia chi": "Hàn Quốc (Cụm xưởng Ulsan, Geoje, Yeongam, Busan)",
                        "Luong": "Theo thỏa thuận thợ hàn E-7-3",
                        "Ngay dang": "2026-10-06",
                        "Han tuyen": "Thường xuyên",
                        "Category": f"JobKorea - Tuyển thợ hàn xưởng tàu ({kw})"
                    })
                    found_in_page += 1

                print(f" -> Trang {page}: Tìm thấy {found_in_page} tin tuyển dụng trên JobKorea")
                if found_in_page == 0:
                    break
                time.sleep(0.5)
            except Exception as e:
                print(f" -> Lỗi cào JobKorea trang {page}: {e}")
                break

    print(f"\n[+] Tổng số tin thu thập từ JobKorea: {len(results)}")
    return results

# ==============================================================================
# HÀM TỔNG HỢP & KHỬ TRÙNG LẶP
# ==============================================================================
def main():
    print("=" * 70)
    print(" HỆ THỐNG CÀO THỢ HÀN ĐÓNG TÀU (E-7-3) TỪ WORK24, SARAMIN, JOBKOREA")
    print("=" * 70)

    session = get_session()
    if not session:
        print("[!] Lỗi không khởi tạo được session curl_cffi!")
        return

    # 1. Cào Saramin
    saramin_data = scrape_saramin(session, SEARCH_KEYWORDS, max_pages=3)

    # 2. Cào Work24
    work24_data = scrape_work24(session, SEARCH_KEYWORDS, max_pages=3)

    # 3. Cào JobKorea
    jobkorea_data = scrape_jobkorea(session, SEARCH_KEYWORDS, max_pages=3)

    all_raw = saramin_data + work24_data + jobkorea_data
    print(f"\n[+] TỔNG SỐ TIN CÀO ĐƯỢC TỪ CẢ 3 CỔNG: {len(all_raw)} tin tuyển dụng")

    # Khử trùng lặp theo Tên công ty (Chuẩn hóa bỏ pháp nhân để so khớp)
    def normalize_key(name):
        n = re.sub(r'[\(\)\[\]주식회사㈜유한회사]+', '', name).strip().lower()
        n = re.sub(r'\s+', '', n)
        return n

    unique_companies = {}
    for item in all_raw:
        cname = item["Cong ty"]
        norm = normalize_key(cname)
        if not norm or len(norm) < 2:
            continue
            
        if norm not in unique_companies:
            unique_companies[norm] = item
        else:
            # Nếu đã có, gộp vị trí tuyển dụng vào để thông tin phong phú hơn
            existing = unique_companies[norm]
            if item["Chuc danh"] not in existing["Chuc danh"]:
                existing["Chuc danh"] += f" | {item['Chuc danh']}"
            # Cập nhật địa chỉ nếu địa chỉ mới chi tiết hơn
            if len(item["Dia chi"]) > len(existing["Dia chi"]):
                existing["Dia chi"] = item["Dia chi"]

    final_list = list(unique_companies.values())
    print(f"[+] SỐ DOANH NGHIỆP ĐÓNG TÀU ĐỘC NHẤT ĐANG TUYỂN DỤNG: {len(final_list)} công ty")

    # Ghi vào CSV chuẩn 20 cột Cold Mail UTF-8 with BOM
    final_rows = []
    for idx, it in enumerate(final_list, 1):
        row = [
            str(idx),
            it["Cong ty"],
            it["Chuc danh"][:200],
            it["Nguoi lien he"],
            it["SDT"],
            it["Lien He"],
            it["Email"],
            it["Lien He mail"],
            it["Dia chi"],
            it["Luong"],
            it["Ngay dang"],
            it["Han tuyen"],
            "", "", "", "", "", "", "",
            it["Category"]
        ]
        final_rows.append(row)

    with open(OUTPUT_CSV, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(HEADERS)
        writer.writerows(final_rows)

    print(f"\n[V] ĐÃ XUẤT THÀNH CÔNG VÀO TỆP:")
    print(f"    -> {OUTPUT_CSV}")
    print(f"    -> Tổng số: {len(final_rows)} công ty xưởng tàu đang khát thợ hàn E-7-3!")

if __name__ == "__main__":
    main()
