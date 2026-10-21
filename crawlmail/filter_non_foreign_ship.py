"""
LOẠI BỎ CÁC CÔNG TY KHÔNG TUYỂN NGƯỜI NƯỚC NGOÀI KHỎI KR_SHIP_DSTU:
1. Nhận diện các nhóm doanh nghiệp theo Luật Hàng hải và Quy định tuyển dụng Hàn Quốc:
   - Tàu khách nội địa / Phà chở khách ven biển (내항여객선 / 페리 / 훼리 / 크루즈)
   - Hiệp hội / Dịch vụ hoa tiêu dẫn tàu vào cảng (도선사 / 도선사회 / 도선선)
   - Doanh nghiệp nhà nước / Cơ quan công quyền quản lý cảng (항만공사 / 해양교통안전공단 / 어촌어항공단)
   - Trường học / Đại học / Cơ sở đào tạo công lập (수산고등학교 / 해양대학교)
   - Văn phòng Hiệp hội / Nghiệp đoàn phi lợi nhuận thuần túy hành chính (선주상호보험조합 / 선박관리협회 / 예선업협동조합)
2. Lưu các công ty bị loại bỏ vào: KR_SHIP_EXCL_0RAW.csv (kèm lý do chi tiết)
3. Cập nhật lại KR_SHIP_DSTU_0RAW.csv (đánh lại STT 1..N)
4. Đồng bộ lại KR_SHIP_DSTU_2COL.csv (chuẩn 20 cột, đẩy 100% email lên đầu)
"""

import os
import csv
import sys
import shutil

sys.stdout.reconfigure(encoding='utf-8')

workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
raw_csv_path = os.path.join(workspace_dir, "KR_SHIP_DSTU_0RAW.csv")
col2_csv_path = os.path.join(workspace_dir, "KR_SHIP_DSTU_2COL.csv")
excl_csv_path = os.path.join(workspace_dir, "KR_SHIP_EXCL_0RAW.csv")

def identify_non_foreign(row):
    comp = row[1]
    cat_vi = row[2]
    cat_kr = row[3]
    pos = row[4]

    # 1. Domestic passenger ferries
    if '내항여객선' in cat_vi or 'Tàu khách' in cat_vi or any(k in comp for k in ['여객', '페리', '훼리', '크루즈', '유람선']):
        if not any(k in comp for k in ['화물', '카고', 'cargo', 'bulk', 'tanker', '상선']):
            return 'Tàu khách nội địa / Phà ven bờ (Luật Hàn Quốc chỉ sử dụng thuyền viên nội địa)'

    # 2. Pilot associations & pilot boats
    if any(k in comp for k in ['도선사', '도선사회', '도선선']):
        return 'Hoa tiêu dẫn tàu / Dịch vụ luồng cảng (Độc quyền công dân Hàn Quốc)'

    # 3. Government / Port authorities / Public agencies
    if any(k in comp for k in ['항만공사', '교통안전공단', '어촌어항공단', '기금재단', '한국선급']):
        return 'Cơ quan nhà nước / Doanh nghiệp công quyền (Chỉ tuyển viên chức công dân Hàn)'

    # 4. Public schools & Maritime universities
    if any(k in comp for k in ['고등학교', '대학교', '대학원', '선원학교']):
        return 'Cơ sở giáo dục / Đại học hàng hải công lập (Không tuyển thuyền viên nước ngoài)'

    # 5. Non-crew administrative associations
    if any(k in comp for k in ['협회', '협동조합', '보험조합']) and not any(k in comp for k in ['해운', '선박', '쉬핑']):
        return 'Văn phòng Hiệp hội / Nghiệp đoàn hành chính (Không phải đơn vị khai thác tàu)'

    # 6. Pure shore-based office administrative
    if pos and all(k in pos for k in ['사무직']) and not any(k in pos for k in ['해기사', '선장', '기관장', '항사', '기사', '선원', '부원', '조기', '갑판', '감독', '정비']):
        if any(k in pos for k in ['회계', '일반행정', '사무국']):
            return 'Chỉ tuyển nhân viên văn phòng nội bộ / kế toán bờ (사무직/회계)'

    return None

def main():
    print("=" * 70)
    print(" LỌC BỎ DOANH NGHIỆP KHÔNG TUYỂN NGƯỜI NƯỚC NGOÀI")
    print("=" * 70)

    if not os.path.exists(raw_csv_path):
        print(f"[!] Không tìm thấy {raw_csv_path}")
        return

    # Đọc dữ liệu
    with open(raw_csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = next(reader)
        rows = list(reader)

    print(f"\n[1/4] Đang phân tích {len(rows)} doanh nghiệp trong danh sách...")

    retained_rows = []
    excluded_rows = []

    for r in rows:
        reason = identify_non_foreign(r)
        if reason:
            excluded_rows.append(r + [reason])
        else:
            retained_rows.append(r)

    print(f" -> Số doanh nghiệp giữ lại (Có tuyển người nước ngoài): {len(retained_rows)} công ty")
    print(f" -> Số doanh nghiệp loại bỏ (Không tuyển người nước ngoài): {len(excluded_rows)} công ty")

    # Phân tích các nhóm loại bỏ
    breakdown = {}
    for r in excluded_rows:
        reason = r[-1]
        breakdown[reason] = breakdown.get(reason, 0) + 1

    print("\nChi tiết các nhóm doanh nghiệp đã loại bỏ:")
    for reas, cnt in sorted(breakdown.items(), key=lambda x: x[1], reverse=True):
        print(f"  * {reas}: {cnt} công ty")

    # 2. Xuất file loại bỏ KR_SHIP_EXCL_0RAW.csv
    print(f"\n[2/4] Đang lưu danh sách loại bỏ vào {excl_csv_path}...")
    excl_headers = headers + ["Lý do loại bỏ"]
    with open(excl_csv_path, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(excl_headers)
        for idx, r in enumerate(excluded_rows, 1):
            r_copy = list(r)
            r_copy[0] = str(idx)
            writer.writerow(r_copy)
    print(f" -> Đã lưu an toàn {len(excluded_rows)} công ty vào {excl_csv_path}")

    # 3. Ghi lại tệp KR_SHIP_DSTU_0RAW.csv sạch
    print(f"\n[3/4] Đang ghi lại tệp {raw_csv_path} ({len(retained_rows)} công ty)...")
    with open(raw_csv_path, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for idx, r in enumerate(retained_rows, 1):
            r[0] = str(idx)
            writer.writerow(r)
    print(f" -> Đã cập nhật thành công {raw_csv_path}")

    # 4. Cập nhật KR_SHIP_DSTU_2COL.csv (đẩy email lên đầu)
    print(f"\n[4/4] Đang cập nhật KR_SHIP_DSTU_2COL.csv...")
    with_email = [r for r in retained_rows if r[7].strip()]
    without_email = [r for r in retained_rows if not r[7].strip()]
    sorted_retained = with_email + without_email

    col2_headers = [
        "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ", 
        "Email", "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển", 
        "Check gửi", "Last Subject", "Last Body HTML", "Trạng thái Reply", 
        "Lần Follow-up", "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
    ]

    with open(col2_csv_path, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(col2_headers)
        for idx, r in enumerate(sorted_retained, 1):
            comp_name = r[1]
            category = r[2]
            pos_val = r[4]
            job_title = pos_val if pos_val else category
            phone = r[5]
            email = r[7]
            rep = r[8]
            addr = r[9]
            web = r[10]

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

    print(f" -> Đã cập nhật thành công {col2_csv_path} (Có Email: {len(with_email)} | Không Email: {len(without_email)})")
    print("\n[V] HOÀN TẤT LỌC BỎ CÁC CÔNG TY KHÔNG TUYỂN NGƯỜI NƯỚC NGOÀI!")

if __name__ == "__main__":
    main()
