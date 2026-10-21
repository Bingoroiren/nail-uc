# -*- coding: utf-8 -*-
"""
Script tong hop 8 Agency va Van phong Hanh chinh E-7-3 Han Quoc chuyen dong tau
va chen vao KR_AGCY_NVER_0RAW.csv, KR_AGCY_NVER_1ENR.csv, KR_AGCY_NVER_2COL.csv
"""

import os
import sys
import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

VIP_AGENCIES = [
    {
        "Cong ty": "(주)GK아너스 / GK글로벌행정사사무소 (GK Honors)",
        "Chuc danh": "Cung ứng thợ hàn & thợ điện E-7-3 đóng tàu (HD Hyundai Samho, Samsung Heavy)",
        "Nguoi lien he": "Đại diện di trú (Giấy phép: 23-SU-RG-059)",
        "SDT": "'+82-2-773-7731 / +82-10-8004-7104",
        "Lien He": "http://www.gkhonors.com/",
        "Email": "pe1350063@daum.net",
        "Lien He mail": "http://www.gkhonors.com/",
        "Dia chi": "서울특별시 금천구 가산동 459-7 가산A1타워 1512호",
        "Luong": "",
        "Ngay dang": "2026-10-06",
        "Han tuyen": "",
        "Check gui": "",
        "Last Subject": "",
        "Last Body HTML": "",
        "Trang thai Reply": "",
        "Lan Follow-up": "",
        "Ngay Follow-up gan nhat": "",
        "Mailbox da dung": "",
        "Category": "Agency E-7-3 Đóng tàu & Hành chính di trú"
    },
    {
        "Cong ty": "랑스파트너스(주) (Langs Partners)",
        "Chuc danh": "Cung ứng thợ hàn E-7-3 đóng tàu (Hợp tác trực tiếp cty phái cử VN)",
        "Nguoi lien he": "이현주 (Hyunju Lee) - Hotline phụ trách VN",
        "SDT": "'+82-51-965-1000 / +82-10-3021-1345",
        "Lien He": "https://www.langspartners.com/",
        "Email": "info@langspartners.com",
        "Lien He mail": "https://www.langspartners.com/",
        "Dia chi": "부산광역시 해운대구 좌동로 166",
        "Luong": "",
        "Ngay dang": "2026-10-06",
        "Han tuyen": "",
        "Check gui": "",
        "Last Subject": "",
        "Last Body HTML": "",
        "Trang thai Reply": "",
        "Lan Follow-up": "",
        "Ngay Follow-up gan nhat": "",
        "Mailbox da dung": "",
        "Category": "Agency E-7-3 Đóng tàu & Cung ứng nhân lực quốc tế"
    },
    {
        "Cong ty": "주식회사 탑코리아 (Top Korea)",
        "Chuc danh": "Cung ứng thợ hàn E-7-3 đóng tàu & cơ khí (Xưởng Ulsan/Geoje)",
        "Nguoi lien he": "노성환 대표 (No Seong-hwan - Luật sư hành chính di trú)",
        "SDT": "'+82-51-723-2840 / +82-10-6894-1345",
        "Lien He": "http://top-korea.co.kr/sub0201.php",
        "Email": "topkorea2840@naver.com",
        "Lien He mail": "http://top-korea.co.kr/",
        "Dia chi": "부산광역시 기장군",
        "Luong": "",
        "Ngay dang": "2026-10-06",
        "Han tuyen": "",
        "Check gui": "",
        "Last Subject": "",
        "Last Body HTML": "",
        "Trang thai Reply": "",
        "Lan Follow-up": "",
        "Ngay Follow-up gan nhat": "",
        "Mailbox da dung": "",
        "Category": "Agency E-7-3 Đóng tàu & Luật sư di trú"
    },
    {
        "Cong ty": "티엠글로벌서비스 (TM Global Service)",
        "Chuc danh": "Nhập khẩu thợ hàn E-7-3 đóng tàu (VPĐD Hà Nội, Nha Trang, Vũng Tàu)",
        "Nguoi lien he": "김병일 대표 (Kim Byeong-il)",
        "SDT": "'+82-10-9145-1451",
        "Lien He": "https://www.tmgs.co.kr/?id=inc&action=shipbuilding",
        "Email": "tm1451@tmgs.co.kr",
        "Lien He mail": "https://www.tmgs.co.kr/?id=request",
        "Dia chi": "Hàn Quốc (VPĐD tại Hà Nội, Nha Trang, Vũng Tàu)",
        "Luong": "",
        "Ngay dang": "2026-10-06",
        "Han tuyen": "",
        "Check gui": "",
        "Last Subject": "",
        "Last Body HTML": "",
        "Trang thai Reply": "",
        "Lan Follow-up": "",
        "Ngay Follow-up gan nhat": "",
        "Mailbox da dung": "",
        "Category": "Agency E-7-3 Đóng tàu"
    },
    {
        "Cong ty": "정의LAW행정사사무소 (Jeong-ui Law)",
        "Chuc danh": "Hành chính tuyển dụng & Quota E-7 nhân lực Việt Nam (đóng tàu, cơ khí)",
        "Nguoi lien he": "권근환 대표 행정사 (Kwon Geun-hwan)",
        "SDT": "'+82-53-252-9068 / +82-53-252-9069",
        "Lien He": "https://blog.naver.com/lawfirm_jeongui",
        "Email": "lawjeongui@naver.com",
        "Lien He mail": "https://blog.naver.com/lawfirm_jeongui",
        "Dia chi": "대구광역시 수성구 범어동 173-1 상영빌딩 4층",
        "Luong": "",
        "Ngay dang": "2026-10-06",
        "Han tuyen": "",
        "Check gui": "",
        "Last Subject": "",
        "Last Body HTML": "",
        "Trang thai Reply": "",
        "Lan Follow-up": "",
        "Ngay Follow-up gan nhat": "",
        "Mailbox da dung": "",
        "Category": "Văn phòng Hành chính Di trú (행정사) E-7"
    },
    {
        "Cong ty": "안민 행정사사무소 (Anmin)",
        "Chuc danh": "Xin Thư tiến cử KOSHIPA & Visa E-7-3 thợ hàn đóng tàu",
        "Nguoi lien he": "Bộ phận Visa E-7-3 Đóng tàu",
        "SDT": "'+82-1544-5799 / +82-2-866-6800",
        "Lien He": "http://anmin.kr/34",
        "Email": "anmin5799@naver.com",
        "Lien He mail": "http://anmin.kr/",
        "Dia chi": "서울특별시 구로구 구로동 155-75 도림로16길 10, 3층",
        "Luong": "",
        "Ngay dang": "2026-10-06",
        "Han tuyen": "",
        "Check gui": "",
        "Last Subject": "",
        "Last Body HTML": "",
        "Trang thai Reply": "",
        "Lan Follow-up": "",
        "Ngay Follow-up gan nhat": "",
        "Mailbox da dung": "",
        "Category": "Văn phòng Hành chính Di trú (행정사) KOSHIPA E-7-3"
    },
    {
        "Cong ty": "비전행정사사무소 (Visas Korea / Vision)",
        "Chuc danh": "Thủ tục bảo lãnh doanh nghiệp & Mời lao động E-7 đóng tàu / kỹ thuật",
        "Nguoi lien he": "이원중 대표 (Lee Won-jung)",
        "SDT": "'+82-2-363-2251 / +82-10-2081-3408",
        "Lien He": "https://www.visaskorea.com/",
        "Email": "5000meter@gmail.com",
        "Lien He mail": "https://www.visaskorea.com/",
        "Dia chi": "서울특별시 중구 퇴계로 324 성우빌딩 3층",
        "Luong": "",
        "Ngay dang": "2026-10-06",
        "Han tuyen": "",
        "Check gui": "",
        "Last Subject": "",
        "Last Body HTML": "",
        "Trang thai Reply": "",
        "Lan Follow-up": "",
        "Ngay Follow-up gan nhat": "",
        "Mailbox da dung": "",
        "Category": "Văn phòng Hành chính Di trú (행정사) E-7"
    },
    {
        "Cong ty": "임원일 행정사사무소 (Im Won-il)",
        "Chuc danh": "Thủ tục nhập cảnh thợ hàn/thợ sơn E-7-3 (Gần HD Hyundai Samho Yeongam)",
        "Nguoi lien he": "임원일 대표 행정사 (Im Won-il)",
        "SDT": "'+82-61-721-0048 / +82-10-2261-0257",
        "Lien He": "http://blog.naver.com/wonil5262",
        "Email": "wonil5262@naver.com",
        "Lien He mail": "http://blog.naver.com/wonil5262",
        "Dia chi": "전라남도 순천시 (Khu vực lân cận HD Hyundai Samho)",
        "Luong": "",
        "Ngay dang": "2026-10-06",
        "Han tuyen": "",
        "Check gui": "",
        "Last Subject": "",
        "Last Body HTML": "",
        "Trang thai Reply": "",
        "Lan Follow-up": "",
        "Ngay Follow-up gan nhat": "",
        "Mailbox da dung": "",
        "Category": "Văn phòng Hành chính Di trú (행정사) E-7-3 Đóng tàu"
    }
]

def update_file(filepath, is_2col=False):
    if not os.path.exists(filepath):
        print(f"File {filepath} khong ton tai, bo qua.")
        return

    df = pd.read_csv(filepath, dtype=str).fillna("")
    print(f"\nDang xu ly: {filepath} (So dong hien tai: {len(df)})")
    
    # Kiem tra xem cac VIP da co trong file chua (theo ten thuong hieu doc nhat)
    brand_keywords = {
        "GK Honors": ["GK아너스", "GK글로벌"],
        "Langs Partners": ["랑스파트너스", "langspartners"],
        "Top Korea": ["탑코리아", "top-korea"],
        "TM Global": ["티엠글로벌", "tmgs"],
        "Jeong-ui Law": ["정의LAW", "정의행정사", "권근환"],
        "Anmin": ["안민 행정사", "anmin"],
        "Vision": ["비전행정사", "visaskorea", "이원중"],
        "Im Won-il": ["임원일"]
    }
    
    existing_text = " ".join(df["Cong ty"].astype(str).tolist() + df["Lien He"].astype(str).tolist() + df["Email"].astype(str).tolist())
    
    new_rows = []
    for vip in VIP_AGENCIES:
        cname = vip["Cong ty"]
        # Find which brand
        kw_list = []
        for b_name, kws in brand_keywords.items():
            if any(k in cname for k in kws):
                kw_list = kws
                break
        
        found = False
        if kw_list:
            for kw in kw_list:
                if kw in existing_text:
                    found = True
                    break
        else:
            if cname in existing_text:
                found = True

        if not found:
            new_rows.append(vip)
        else:
            print(f" -> Da ton tai trong file: {cname}")

    if not new_rows:
        print("Tat ca 8 VIP agency da co trong danh sach.")
        df_combined = df
    else:
        print(f" -> Them moi {len(new_rows)} agency VIP vao dau danh sach.")
        df_vip = pd.DataFrame(new_rows)
        # Bao dam dung thu tu cot
        for col in df.columns:
            if col not in df_vip.columns:
                df_vip[col] = ""
        df_vip = df_vip[df.columns]
        
        # Dat VIP len dau
        df_combined = pd.concat([df_vip, df], ignore_index=True)

    # Chuan hoa SDT co nhay don
    def fix_phone(p):
        p = str(p).strip()
        if not p or p.lower() == 'nan':
            return ''
        if not p.startswith("'"):
            return f"'{p}"
        return p

    df_combined["SDT"] = df_combined["SDT"].apply(fix_phone)

    # Voi 2COL hoac 1ENR: Luon day cac dong co Email len dau danh sach
    # 8 VIP deu co Email nen chac chan nam o tren cung
    with_email = df_combined[df_combined["Email"].astype(str).str.strip().ne("")].copy()
    without_email = df_combined[df_combined["Email"].astype(str).str.strip().eq("")].copy()
    
    # De cac VIP agency o TOP dau tien cua with_email
    vip_names = [v["Cong ty"] for v in VIP_AGENCIES]
    vip_in_with_email = with_email[with_email["Cong ty"].isin(vip_names)]
    other_with_email = with_email[~with_email["Cong ty"].isin(vip_names)]
    
    with_email_sorted = pd.concat([vip_in_with_email, other_with_email], ignore_index=True)
    df_final = pd.concat([with_email_sorted, without_email], ignore_index=True)

    # Danh so No. 1..N
    df_final["No."] = range(1, len(df_final) + 1)

    df_final.to_csv(filepath, index=False, encoding="utf-8-sig")
    print(f" -> Hoan tat ghi {filepath}. Tong so dong: {len(df_final)} (Co email: {len(with_email_sorted)})")

if __name__ == "__main__":
    for target in ["KR_AGCY_NVER_0RAW.csv", "KR_AGCY_NVER_1ENR.csv", "KR_AGCY_NVER_2COL.csv"]:
        update_file(target, is_2col=True)
