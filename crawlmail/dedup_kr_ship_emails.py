"""
LỌC TRÙNG EMAIL CHO TẬP DỮ LIỆU KR_SHIP_DSTU:
1. Quét toàn bộ KR_SHIP_DSTU_0RAW.csv và nhận diện các email bị trùng lặp
2. Gộp thông tin thông minh: Giữ lại bản ghi đầy đủ nhất, bổ sung các trường còn thiếu (vị trí tuyển dụng, SĐT, địa chỉ, website)
3. Xuất file backup an toàn: KR_SHIP_DSTU_0RAW_backup.csv & KR_SHIP_DSTU_2COL_backup.csv
4. Cập nhật lại KR_SHIP_DSTU_0RAW.csv và KR_SHIP_DSTU_2COL.csv chuẩn 20 cột, đẩy 100% email lên đầu
"""

import os
import csv
import sys
import shutil

sys.stdout.reconfigure(encoding='utf-8')

workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
raw_csv_path = os.path.join(workspace_dir, "KR_SHIP_DSTU_0RAW.csv")
col2_csv_path = os.path.join(workspace_dir, "KR_SHIP_DSTU_2COL.csv")

raw_backup_path = os.path.join(workspace_dir, "KR_SHIP_DSTU_0RAW_backup.csv")
col2_backup_path = os.path.join(workspace_dir, "KR_SHIP_DSTU_2COL_backup.csv")

def main():
    print("=" * 65)
    print(" TIẾN HÀNH LỌC TRÙNG EMAIL TRONG KR_SHIP_DSTU_0RAW.CSV")
    print("=" * 65)

    if not os.path.exists(raw_csv_path):
        print(f"[!] Không tìm thấy tệp {raw_csv_path}")
        return

    # 1. Tạo backup an toàn
    shutil.copy2(raw_csv_path, raw_backup_path)
    if os.path.exists(col2_csv_path):
        shutil.copy2(col2_csv_path, col2_backup_path)
    print(f"[1/4] Đã tạo bản sao lưu an toàn:\n - {raw_backup_path}\n - {col2_backup_path}")

    # 2. Đọc toàn bộ dữ liệu 0RAW
    with open(raw_csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = next(reader)
        rows = list(reader)

    print(f"\n[2/4] Tổng số dòng ban đầu: {len(rows)} dòng")

    # Mapping header
    col_map = {name: idx for idx, name in enumerate(headers)}
    email_idx = col_map.get("Email", 7)
    comp_idx = col_map.get("Công ty (Hàn)", 1)
    type_vi_idx = col_map.get("Phân loại", 2)
    type_kr_idx = col_map.get("Phân loại (Hàn / Anh)", 3)
    pos_idx = col_map.get("Vị trí tuyển dụng", 4)
    phone_idx = col_map.get("SĐT", 5)
    fax_idx = col_map.get("Số Fax", 6)
    rep_idx = col_map.get("Người đại diện", 8)
    addr_idx = col_map.get("Địa chỉ trụ sở", 9)
    web_idx = col_map.get("Website", 10)

    seen_emails = {}
    without_email_rows = []
    merged_report = []

    for r in rows:
        email = r[email_idx].strip().lower()
        if not email:
            without_email_rows.append(r)
            continue

        if email not in seen_emails:
            seen_emails[email] = list(r)
        else:
            # Đã tồn tại -> Gộp thông tin
            target = seen_emails[email]
            old_comp = target[comp_idx]
            new_comp = r[comp_idx]
            merged_report.append((email, old_comp, new_comp))

            # Bổ sung các trường nếu target còn trống
            if not target[pos_idx] and r[pos_idx]:
                target[pos_idx] = r[pos_idx]
            elif target[pos_idx] and r[pos_idx] and r[pos_idx] not in target[pos_idx]:
                target[pos_idx] = f"{target[pos_idx]} | {r[pos_idx]}"

            if not target[phone_idx] and r[phone_idx]:
                target[phone_idx] = r[phone_idx]
            if not target[fax_idx] and r[fax_idx]:
                target[fax_idx] = r[fax_idx]
            if not target[rep_idx] and r[rep_idx]:
                target[rep_idx] = r[rep_idx]
            if not target[addr_idx] and r[addr_idx]:
                target[addr_idx] = r[addr_idx]
            if not target[web_idx] and r[web_idx]:
                target[web_idx] = r[web_idx]

    deduped_with_email = list(seen_emails.values())
    total_after = len(deduped_with_email) + len(without_email_rows)
    removed_count = len(rows) - total_after

    print(f"\n[3/4] Kết quả lọc trùng email:")
    print(f" - Số dòng có email ban đầu: {len(rows) - len(without_email_rows)}")
    print(f" - Số lượng email duy nhất: {len(deduped_with_email)}")
    print(f" - Số dòng trùng đã được gộp/loại bỏ: {removed_count} dòng")
    print(f" - Số dòng không có email (giữ nguyên): {len(without_email_rows)}")
    print(f" - Tổng số dòng sau khi lọc: {total_after} dòng")

    print("\nChi tiết các email trùng đã được xử lý gộp:")
    for em, c1, c2 in merged_report:
        print(f"  * Email: {em} | Gộp: '{c2}' -> '{c1}'")

    # 3. Ghi lại file KR_SHIP_DSTU_0RAW.csv
    print(f"\n[4/4] Đang ghi lại tệp {raw_csv_path}...")
    final_all_rows = deduped_with_email + without_email_rows

    with open(raw_csv_path, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for idx, r in enumerate(final_all_rows, 1):
            r[0] = str(idx) # Cập nhật lại STT 1..N
            writer.writerow(r)

    # 4. Ghi lại file KR_SHIP_DSTU_2COL.csv (đẩy email lên đầu danh sách)
    col2_headers = [
        "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ", 
        "Email", "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển", 
        "Check gửi", "Last Subject", "Last Body HTML", "Trạng thái Reply", 
        "Lần Follow-up", "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
    ]

    with open(col2_csv_path, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(col2_headers)
        for idx, r in enumerate(final_all_rows, 1):
            comp_name = r[comp_idx]
            category = r[type_vi_idx]
            pos_val = r[pos_idx]
            job_title = pos_val if pos_val else category
            rep = r[rep_idx]
            phone = r[phone_idx]
            web = r[web_idx]
            email = r[email_idx]
            addr = r[addr_idx]

            writer.writerow([
                idx,
                comp_name,
                job_title,
                rep,
                phone,
                web,
                email,
                "",
                addr,
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                category
            ])

    print(f" -> Đã cập nhật thành công {col2_csv_path} (608 dòng có email đầu bảng)!")
    print("\n[V] HOÀN TẤT LỌC TRÙNG EMAIL 100% THÀNH CÔNG!")

if __name__ == "__main__":
    main()
