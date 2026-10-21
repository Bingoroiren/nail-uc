# -*- coding: utf-8 -*-
"""
Rescue Missed D&B Slovakia Companies:
Cào lại toàn bộ các công ty bị sót hoặc chưa cào từ D&B Slovakia:
1. Đọc danh bạ gốc (1,000 công ty).
2. Lọc danh sách 165 công ty bị sót (từ dòng 858 do đứt mạng và 872-1002 chưa chạy).
3. Mở Google Chrome thực tế (headless=False) với profile có sẵn.
4. Bắt lỗi Execution context was destroyed khi Cloudflare chuyển trang.
5. CHỈ lưu vào CSV khi thực sự tải được trang profile hợp lệ.
6. Cơ chế Retry 3 lần nếu gặp lỗi mạng (ERR_NETWORK_CHANGED, ERR_NAME_NOT_RESOLVED).
"""

import sys
import os
import re
import csv
import time
from pathlib import Path
import pandas as pd
from playwright.sync_api import sync_playwright

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

OUTPUT_DIR = Path("D:/glc/nail uc/csdl_sk_agcy")
DATABASE_CSV = OUTPUT_DIR / "dnb_slovakia_agcy_database.csv"
DETAILED_CSV = OUTPUT_DIR / "dnb_slovakia_agcy_detailed.csv"
PROFILE_DIR = Path("D:/glc/nail uc/chrome_user_data/dnb_profile")

FIELDNAMES = [
    'No.', 'Company', 'Address', 'City', 'Region', 'Country', 'Website', 
    'Key_Principal', 'Employees', 'Description', 'Detail_URL', 'Source'
]

def safe_title(page):
    """Lấy tiêu đề trang an toàn, tránh lỗi Execution context was destroyed khi đang chuyển trang"""
    try:
        return page.title() or ""
    except Exception:
        return "navigating"

def rescue_missed():
    print("=" * 70)
    print(" BẮT ĐẦU CÀO BỔ SUNG CÁC CÔNG TY BỊ SÓT (D&B SLOVAKIA)")
    print("=" * 70)

    if not DATABASE_CSV.exists() or not DETAILED_CSV.exists():
        print("[-] Không tìm thấy các file dữ liệu cần thiết.")
        return

    df_base = pd.read_csv(DATABASE_CSV, dtype=str).fillna('')
    valid_base = df_base[df_base['Detail_URL'].str.contains('/company-profiles/', na=False)].copy()
    valid_base['No.'] = range(1, len(valid_base) + 1)
    print(f"[*] Tổng số công ty thực tế trong danh bạ D&B: {len(valid_base):,}")

    df_det = pd.read_csv(DETAILED_CSV, dtype=str).fillna('')
    
    # Gom các bản ghi đã cào thành công (có Key_Principal HOẶC Website)
    successful_dict = {}
    for _, r in df_det.iterrows():
        u = r.get('Detail_URL', '').strip()
        kp = r.get('Key_Principal', '').strip()
        wb = r.get('Website', '').strip()
        if u and (kp or wb):
            successful_dict[u] = r.to_dict()

    print(f"[*] Số công ty đã cào đầy đủ dữ liệu trước đó: {len(successful_dict):,}")

    # Lọc danh sách cần cào bổ sung
    tasks = []
    for _, r in valid_base.iterrows():
        u = r.get('Detail_URL', '').strip()
        if u not in successful_dict:
            tasks.append(r)

    print(f"[*] Số công ty cần cào lại/cào mới: {len(tasks):,}")
    if not tasks:
        print("[✓] Toàn bộ công ty đã được cào đầy đủ! Không còn công ty nào bị sót.")
        return

    with sync_playwright() as p:
        print("[*] Đang khởi chạy Google Chrome thực tế (headless=False)...")
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            headless=False,
            viewport={'width': 1280, 'height': 800},
            args=['--disable-blink-features=AutomationControlled']
        )
        page = context.new_page()

        # Kiểm tra xác thực ban đầu
        first_url = tasks[0]['Detail_URL']
        print(f"[*] Mở trang đầu tiên để kiểm tra Cloudflare: {tasks[0]['Company']}...")
        try:
            page.goto(first_url, timeout=30000, wait_until='domcontentloaded')
        except Exception:
            pass
        time.sleep(3)

        t_init = safe_title(page)
        if 'Just a moment' in t_init or t_init == 'navigating':
            print("\a\n" + "!" * 70)
            print("[!] PHÁT HIỆN CLOUDFLARE: Vui lòng click 'Verify you are human' trên màn hình Chrome!")
            print("!" * 70)
            for w in range(90):
                time.sleep(1)
                t_check = safe_title(page)
                if t_check not in ['navigating', ''] and 'Just a moment' not in t_check:
                    print("[+] Vượt qua Cloudflare thành công!")
                    time.sleep(2)
                    break

        rescued_count = 0
        for i, item in enumerate(tasks, 1):
            cname = item.get('Company', '').strip()
            durl = item.get('Detail_URL', '').strip()
            city = item.get('City', '').strip()
            region = item.get('Region', '').strip()
            country = item.get('Country', 'Slovakia').strip()

            address = ""
            website = ""
            key_principal = ""
            employees = ""
            description = ""

            for attempt in range(3):
                try:
                    page.goto(durl, timeout=30000, wait_until='domcontentloaded')
                    time.sleep(2.5)

                    # Bắt nhịp nếu gặp Cloudflare giữa chừng
                    t_curr = safe_title(page)
                    if 'Just a moment' in t_curr:
                        print(f"\a  [!] Cloudflare yêu cầu tick xác thực tại: {cname}. Đang chờ bạn click...")
                        for _ in range(60):
                            time.sleep(1)
                            t_verify = safe_title(page)
                            if t_verify not in ['navigating', ''] and 'Just a moment' not in t_verify:
                                time.sleep(2)
                                break

                    # Chờ trang ổn định
                    time.sleep(1.5)
                    t_final = safe_title(page)
                    if 'Just a moment' in t_final or '404' in t_final:
                        continue

                    # Đọc nội dung trang an toàn
                    body_text = ""
                    try:
                        body_text = page.locator('body').inner_text(timeout=7000)
                    except Exception:
                        time.sleep(2)
                        body_text = page.locator('body').inner_text(timeout=7000)

                    addr_m = re.search(r'Address:\s*([^\n\r]+)', body_text)
                    if addr_m:
                        address = addr_m.group(1).strip()

                    web_m = re.search(r'Website:\s*([^\n\r]+)', body_text)
                    if web_m:
                        website = web_m.group(1).strip()

                    princ_m = re.search(r'Key Principal:\s*([^\n\r]+)', body_text)
                    if princ_m:
                        key_principal = princ_m.group(1).strip()

                    emp_m = re.search(r'Employees\s*\([^)]*\):\s*([^\n\r]+)', body_text)
                    if emp_m:
                        employees = emp_m.group(1).strip()

                    desc_m = re.search(r'Description:\s*([^\n\r]+)', body_text)
                    if desc_m:
                        description = desc_m.group(1).strip()

                    # Nếu bóc tách thành công
                    if key_principal or website or address:
                        break
                except Exception as e:
                    print(f"  [~] Thử lần {attempt+1}/3 bị lỗi mạng ({e}). Đang thử lại sau 3s...")
                    time.sleep(3)

            # Cập nhật kết quả
            rec = {
                'No.': '',
                'Company': cname,
                'Address': address if address else item.get('Location', ''),
                'City': city,
                'Region': region,
                'Country': country,
                'Website': website,
                'Key_Principal': key_principal,
                'Employees': employees,
                'Description': description,
                'Detail_URL': durl,
                'Source': 'dnb.com'
            }
            successful_dict[durl] = rec
            rescued_count += 1

            status_str = f"Web: {website:<22}" if website else "Web: (chưa có)             "
            leader_str = f"Đại diện: {key_principal}" if key_principal else "Đại diện: (chưa có)"
            print(f"[{rescued_count:>3}/{len(tasks)}] {cname:<35} | {status_str} | {leader_str}")

            # Lưu tăng dần định kỳ sau mỗi 5 công ty
            if rescued_count % 5 == 0 or rescued_count == len(tasks):
                final_rows = []
                idx_num = 1
                for _, r_orig in valid_base.iterrows():
                    u_orig = r_orig.get('Detail_URL', '').strip()
                    if u_orig in successful_dict:
                        row_data = successful_dict[u_orig]
                        row_data['No.'] = idx_num
                        final_rows.append(row_data)
                        idx_num += 1

                with open(DETAILED_CSV, 'w', encoding='utf-8-sig', newline='') as f_out:
                    w = csv.DictWriter(f_out, fieldnames=FIELDNAMES)
                    w.writeheader()
                    w.writerows(final_rows)

            time.sleep(1.2)

        context.close()

    print("\n" + "=" * 70)
    print(f"[✔] HOÀN TẤT CÀO BỔ SUNG TOÀN BỘ CÁC CÔNG TY BỊ SÓT!")
    print(f"[*] Tổng số công ty đã được hoàn thiện trong CSDL: {len(successful_dict):,}")
    print(f"[*] File lưu tại: {DETAILED_CSV}")
    print("=" * 70)

if __name__ == '__main__':
    rescue_missed()
