"""
CRAWL TOAN BO SEANET.CO.KR (302 TRANG, 9043 TIN TUYEN DUNG):
1. Quet toan bo 302 trang danh sach job_list.html
2. Khu trung theo Doanh nghiep (Company), gom toan bo cac vi tri tuyen dung (Positions) cua tung cong ty
3. Cao chinh xac muc '기업 정보' cua tung cong ty: SĐT, Fax, Email phong nhan su/hai vu, Nguoi lien he, Dia chi, Luong (loai bo footer website 02-538-5986)
4. Tich hop vao KR_SHIP_DSTU_0RAW.csv (them cot 'Vị trí tuyển dụng' de loc)
5. Dong bo KR_SHIP_DSTU_2COL.csv (chuan 20 cot Cold Mail, day 100% email len dau)
"""

import os
import re
import sys
import csv
import time
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib3

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding='utf-8')

TOTAL_PAGES = 302
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

def clean_phone(p):
    if not p:
        return ""
    p = p.strip()
    # Loai bo SĐT nha phat trien web Deepcircle
    if "02-538-5986" in p or "02-318-0261" in p:
        return ""
    if p and not p.startswith("'"):
        p = f"'{p}"
    return p

def clean_email(e):
    if not e:
        return ""
    e = e.strip().replace("%20", "").lower()
    invalid = ["test@test.com", "email@email.com", "example@example.com", "none@none.com", "info@deepcircle.net"]
    if e in invalid or "@" not in e:
        return ""
    return e

def clean_company_name(name):
    if not name:
        return ""
    return name.strip()

def scrape_list_page(page):
    url = f"https://seanet.co.kr/job/job_list.html?page={page}"
    try:
        r = requests.get(url, headers=HEADERS, verify=False, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        table = soup.find('table')
        if not table:
            return []
        rows = table.find_all('tr')[1:]
        items = []
        for tr in rows:
            onclick = tr.get('onclick', '')
            to_id_m = re.search(r'jobView\((\d+)\)', onclick)
            to_id = to_id_m.group(1) if to_id_m else ''

            tds = tr.find_all('td')
            if len(tds) >= 7:
                no = tds[0].get_text(strip=True)
                title = tds[1].get_text(strip=True)
                company = clean_company_name(tds[2].get_text(strip=True))
                position = tds[3].get_text(strip=True)
                location = tds[4].get_text(strip=True)
                date_deadline = tds[5].get_text(strip=True)

                if company:
                    items.append({
                        "no": no,
                        "to_id": to_id,
                        "title": title,
                        "company": company,
                        "position": position,
                        "location": location,
                        "date_deadline": date_deadline
                    })
        return items
    except Exception as e:
        print(f" [!] Loi doc trang {page}: {e}")
        return []

def scrape_job_detail(to_id):
    if not to_id:
        return to_id, {}
    url = f"https://seanet.co.kr/job/job_view.html?to_id={to_id}"
    try:
        r = requests.get(url, headers=HEADERS, verify=False, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        info = {
            "phone": "",
            "fax": "",
            "email": "",
            "contact_person": "",
            "addr": "",
            "salary": ""
        }
        
        # Lay thong tin luong tu phan mo dau
        text_full = r.text
        m_sal = re.search(r'급여조건\s*[:：]?\s*<[^>]+>([^<]+)<', text_full)
        if m_sal:
            info["salary"] = m_sal.group(1).strip()

        # Dinh vi chinh xac phan '기업 정보' (Company Info) de khong dinh footer Deepcircle
        h_corp = None
        for h in soup.find_all(['h3', 'h4', 'h5', 'div', 'span', 'p']):
            if h.get_text(strip=True) == '기업 정보':
                h_corp = h.parent
                break
        
        if h_corp:
            text_corp = h_corp.get_text(separator=' ', strip=True)
            m_ph = re.search(r'전화\s*[:：]?\s*([0-9-~]+)', text_corp)
            m_fx = re.search(r'팩스\s*[:：]?\s*([0-9-~]+)', text_corp)
            m_em = re.search(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', text_corp)
            m_ct = re.search(r'담당자\s*[:：]?\s*([^\s<,\n]+)', text_corp)
            m_ad = re.search(r'주소\s*[:：]?\s*([^<\n\r]{6,80})', text_corp)

            if m_ph:
                info["phone"] = m_ph.group(1).strip()
            if m_fx:
                info["fax"] = m_fx.group(1).strip()
            if m_em:
                info["email"] = m_em.group(1).strip()
            if m_ct:
                info["contact_person"] = m_ct.group(1).strip()
            if m_ad:
                addr_str = m_ad.group(1).strip()
                if "딥써클" not in addr_str and "삼봉로" not in addr_str:
                    info["addr"] = addr_str

        return to_id, info
    except Exception as e:
        return to_id, {}

def main():
    print("=" * 70)
    print(" CRAWL & KHỬ TRÙNG DOANH NGHIỆP SEANET.CO.KR (GOM VỊ TRÍ TUYỂN DỤNG)")
    print("=" * 70)

    # 1. Quét toàn bộ 302 trang
    print(f"\n[BƯỚC 1/4] Đang quét toàn bộ {TOTAL_PAGES} trang danh sách trên seanet.co.kr...")
    t0 = time.time()
    all_job_items = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(scrape_list_page, p) for p in range(1, TOTAL_PAGES + 1)]
        done = 0
        for f in as_completed(futures):
            res = f.result()
            all_job_items.extend(res)
            done += 1
            if done % 50 == 0 or done == TOTAL_PAGES:
                print(f"    - Tiến độ đọc trang: {done}/{TOTAL_PAGES} trang ({done/TOTAL_PAGES*100:.1f}%)")

    print(f" -> Thu thập được {len(all_job_items)} tin tuyển dụng trong {time.time()-t0:.2f}s!")

    # 2. Gom nhóm theo Doanh nghiệp duy nhất (Khử trùng)
    print("\n[BƯỚC 2/4] Đang khử trùng theo công ty và tổng hợp các vị trí tuyển dụng...")
    company_groups = {}
    for item in all_job_items:
        cname = item["company"]
        if cname not in company_groups:
            company_groups[cname] = {
                "company": cname,
                "positions": set(),
                "titles": [],
                "locations": set(),
                "to_ids": [],
                "latest_to_id": item["to_id"],
                "latest_deadline": item["date_deadline"],
                "total_postings": 0
            }
        g = company_groups[cname]
        g["total_postings"] += 1
        if item["position"]:
            pos_clean = item["position"].strip()
            pos_clean = re.sub(r'[♥★☆■▶]', '', pos_clean).strip()
            if pos_clean:
                g["positions"].add(pos_clean)
        if item["to_id"] and item["to_id"] not in g["to_ids"]:
            g["to_ids"].append(item["to_id"])
        if item["location"]:
            g["locations"].add(item["location"])
        if len(g["titles"]) < 3 and item["title"]:
            g["titles"].append(item["title"])

    print(f" -> Tổng cộng {len(all_job_items)} tin thuộc về {len(company_groups)} DOANH NGHIỆP DUY NHẤT.")

    # 3. Cào thông tin liên hệ chi tiết (Email, SĐT, Người liên hệ, Địa chỉ) cho từng doanh nghiệp
    print(f"\n[BƯỚC 3/4] Đang cào thông tin liên hệ (Email, SĐT, Đại diện, Địa chỉ) cho {len(company_groups)} công ty...")
    t1 = time.time()
    
    # Gom to_id mới nhất của mỗi công ty (nếu công ty có nhiều tin, lấy 1-2 tin để đảm bảo có email)
    to_id_list = []
    for cname, g in company_groups.items():
        if g["to_ids"]:
            to_id_list.extend(g["to_ids"][:2])  # Lấy tối đa 2 tin gần nhất để tìm email/sđt

    details_cache = {}
    done_details = 0
    total_to_scrape = len(to_id_list)

    with ThreadPoolExecutor(max_workers=25) as executor:
        futures = {executor.submit(scrape_job_detail, tid): tid for tid in to_id_list}
        for f in as_completed(futures):
            tid, info = f.result()
            details_cache[tid] = info
            done_details += 1
            if done_details % 100 == 0 or done_details == total_to_scrape:
                print(f"    - Tiến độ cào chi tiết: {done_details}/{total_to_scrape} ({done_details/total_to_scrape*100:.1f}%)")

    print(f" -> Đã cào xong thông tin liên hệ trong {time.time()-t1:.2f}s.")

    # Gán chi tiết vào từng công ty (kết hợp các to_id của công ty để có email và SĐT đầy đủ nhất)
    seanet_final_records = []
    for cname, g in company_groups.items():
        phone = ""
        fax = ""
        email = ""
        rep = ""
        addr = ""
        salary = ""
        primary_tid = g["to_ids"][0] if g["to_ids"] else ""

        for tid in g["to_ids"][:2]:
            dt = details_cache.get(tid, {})
            if not phone and dt.get("phone"):
                phone = dt.get("phone")
            if not fax and dt.get("fax"):
                fax = dt.get("fax")
            if not email and dt.get("email"):
                email = dt.get("email")
            if not rep and dt.get("contact_person"):
                rep = dt.get("contact_person")
            if not addr and dt.get("addr"):
                addr = dt.get("addr")
            if not salary and dt.get("salary"):
                salary = dt.get("salary")

        # Tổng hợp vị trí tuyển dụng
        pos_list = sorted(list(g["positions"]))
        pos_str = " | ".join(pos_list[:8])

        # Nhận diện loại tàu từ titles
        all_titles_text = " ".join(g["titles"]).lower()
        ship_type_tag = "Tàu to"
        if "예선" in all_titles_text or "tug" in all_titles_text:
            ship_type_tag = "Tàu dắt (예선)"
        elif "tanker" in all_titles_text or "탱커" in all_titles_text:
            ship_type_tag = "Tàu to (Tanker)"
        elif "bulk" in all_titles_text or "벌크" in all_titles_text:
            ship_type_tag = "Tàu to (Bulk Carrier)"
        elif "container" in all_titles_text or "컨테이너" in all_titles_text:
            ship_type_tag = "Tàu to (Container)"
        elif "여객" in all_titles_text or "ferry" in all_titles_text:
            ship_type_tag = "Tàu to (Tàu khách)"

        loc_str = ", ".join(list(g["locations"])[:2])
        if not addr:
            addr = loc_str

        phone = clean_phone(phone)
        fax = clean_phone(fax)
        email = clean_email(email)
        web_link = f"https://seanet.co.kr/job/job_view.html?to_id={primary_tid}" if primary_tid else "https://seanet.co.kr"

        seanet_final_records.append({
            "company": cname,
            "type_vi": f"{ship_type_tag} - Tuyển dụng Seanet",
            "type_kr": "선원채용 (Maritime Crew Recruitment)",
            "position": pos_str,
            "phone": phone,
            "fax": fax,
            "email": email,
            "rep": rep,
            "addr": addr,
            "salary": salary,
            "deadline": g["latest_deadline"],
            "website": web_link,
            "category": f"{ship_type_tag} (Tuyển dụng Seanet)"
        })

    # 4. Đọc dữ liệu hiện tại trong KR_SHIP_DSTU_0RAW.csv
    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    raw_csv_path = os.path.join(workspace_dir, "KR_SHIP_DSTU_0RAW.csv")
    col2_csv_path = os.path.join(workspace_dir, "KR_SHIP_DSTU_2COL.csv")

    existing_records = []
    if os.path.exists(raw_csv_path):
        with open(raw_csv_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            headers = next(reader)
            for row in reader:
                if len(row) >= 9:
                    c_name = row[1]
                    c_vi = row[2]
                    c_kr = row[3]
                    if len(row) >= 11:
                        c_pos = row[4]
                        c_phone = row[5]
                        c_fax = row[6]
                        c_email = row[7]
                        c_rep = row[8]
                        c_addr = row[9]
                        c_web = row[10]
                    else:
                        c_pos = ""
                        c_phone = row[4]
                        c_fax = row[5]
                        c_email = row[6]
                        c_rep = row[7]
                        c_addr = row[8]
                        c_web = row[9] if len(row) > 9 else ""

                    # Chỉ giữ lại các bản ghi không phải Seanet cũ
                    if "Seanet" not in c_vi and "선원채용" not in c_kr:
                        existing_records.append({
                            "company": c_name,
                            "type_vi": c_vi,
                            "type_kr": c_kr,
                            "position": c_pos,
                            "phone": c_phone,
                            "fax": c_fax,
                            "email": c_email,
                            "rep": c_rep,
                            "addr": c_addr,
                            "salary": "",
                            "deadline": "",
                            "website": c_web,
                            "category": "Tàu to" if "Tàu to" in c_vi else ("Tàu dắt" if "Tàu dắt" in c_vi else c_vi)
                        })

    print(f"\n[BƯỚC 4/4] Tích hợp: Giữ {len(existing_records)} công ty gốc (DSTUG + MaritimePress) + Thêm {len(seanet_final_records)} công ty từ Seanet...")

    # Gộp toàn bộ
    combined_all = existing_records + seanet_final_records

    # Xuất KR_SHIP_DSTU_0RAW.csv với cột 'Vị trí tuyển dụng'
    raw_headers = [
        "STT", "Công ty (Hàn)", "Phân loại", "Phân loại (Hàn / Anh)", 
        "Vị trí tuyển dụng", "SĐT", "Số Fax", "Email", "Người đại diện", "Địa chỉ trụ sở", "Website"
    ]
    with open(raw_csv_path, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(raw_headers)
        for idx, rec in enumerate(combined_all, 1):
            writer.writerow([
                idx,
                rec["company"],
                rec["type_vi"],
                rec["type_kr"],
                rec["position"],
                rec["phone"],
                rec["fax"],
                rec["email"],
                rec["rep"],
                rec["addr"],
                rec["website"]
            ])

    print(f" -> Đã ghi thành công {len(combined_all)} dòng vào {raw_csv_path}")

    # Đồng bộ KR_SHIP_DSTU_2COL.csv (đẩy email lên đầu)
    print(" -> Đang đồng bộ cập nhật KR_SHIP_DSTU_2COL.csv (20 cột chuẩn Cold Mail)...")
    with_email = [r for r in combined_all if r["email"]]
    without_email = [r for r in combined_all if not r["email"]]
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
            job_title = rec["position"] if rec["position"] else rec["category"]
            writer.writerow([
                idx,
                rec["company"],
                job_title,
                rec["rep"],
                rec["phone"],
                rec["website"],
                rec["email"],
                "",
                rec["addr"],
                rec.get("salary", ""),
                "",
                rec.get("deadline", ""),
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                rec["category"]
            ])

    print(f" -> Đã lưu thành công {len(sorted_records)} dòng vào {col2_csv_path} (Có Email: {len(with_email)} | Không Email: {len(without_email)})")
    print("\n[V] HOÀN TẤT THÀNH CÔNG!")

if __name__ == "__main__":
    main()
