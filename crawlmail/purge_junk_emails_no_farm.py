# -*- coding: utf-8 -*-
"""
HỆ THỐNG THANH LỌC TOÀN DIỆN MAIL RÁC, MAIL MẪU, BOT & CÔNG TY LỆCH NGÀNH (NO_FARM)
=============================================================================
1. Khắc phục & Cứu mail thật:
   - Thay thế 'noamv22@site123-gal-editor-b.com' -> 'lekvenpaahaukaasen@gmail.com' (mail thật của trang trại Lekven).
2. Xóa bỏ 100% mail rác, mail template, bot crawler, aggregator:
   - support@readymag.com (Readymag web builder support)
   - info@mysite.com (Wix placeholder)
   - claudebot@anthropic.com (Anthropic AI crawler bot)
   - xe.iaso@techaro.lol (Spam bot .lol)
   - info@a1wellnessdrips.co.uk (Parked spam site)
   - contact@kuula.co (Photo viewer 360 platform)
   - hello@campanyon.com & post@campio.no (OTA booking aggregator)
3. Loại bỏ hoàn toàn các doanh nghiệp phi nông nghiệp bị Google Maps map nhầm:
   - Nha sĩ: post@tannlegenedepotgaten.no (Jørgen Torp)
   - Nhà tang lễ: post@opsahlbegravelsesbyra.no (Terje Heggen), post@jolstad.no (Lister Begravelsesbyrå)
   - Luật sư: isv@advokatforeningen.no (Advokat Lars Bjarne Salte), agb@vagaadvokat.no (Anders Gustav Bjørnsen)
   - Vật lý trị liệu: post@clausenfysioterapi.no (Clausen)
   - Giặt ủi: post@buggeland-vaskeri.no (Buggeland Vaskeri)
   - Thợ nề / Xây dựng: support@readymag.com (Oppegaard Mur)
   - Khách sạn nghỉ dưỡng: hotel@solstrand.com (Berge Gard v/ Morten Solstrand)
4. Sắp xếp lại danh sách chuẩn Rule 3: 100% doanh nghiệp có Email lên đầu.
5. Đồng bộ vào toàn bộ các thư mục: root, csdl_mlt/, archive/no_norway/.
"""

import sys
import os
import re
import pandas as pd
from pathlib import Path

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

COL_20_HEADERS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ', 'Email', 
    'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển', 'Check gửi', 
    'Last Subject', 'Last Body HTML', 'Trạng thái Reply', 'Lần Follow-up', 
    'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

# 1. Danh sách email rác/template/bot/aggregator cần xóa bỏ
JUNK_EMAILS = {
    'support@readymag.com',
    'info@mysite.com',
    'claudebot@anthropic.com',
    'xe.iaso@techaro.lol',
    'info@a1wellnessdrips.co.uk',
    'contact@kuula.co',
    'hello@campanyon.com',
    'post@campio.no',
    'noamv22@site123-gal-editor-b.com'
}

# 2. Cứu mail thật thay thế
EMAIL_REPLACEMENTS = {
    'Lekven på Haukåsen Gård'.lower(): 'lekvenpaahaukaasen@gmail.com'
}

# 3. Danh sách công ty lệch ngành hoàn toàn bị Google Maps map nhầm
NON_FARM_COMPANIES = [
    'advokat lars bjarne salte',
    'anders gustav bjørnsen',
    'jørgen torp',
    'terje heggen',
    'lister begravelsesbyrå',
    'clausen',
    'buggeland vaskeri karl hodnefjell',
    'oppegaard mur og tradisjonshåndverk as',
    'berge gard v/ morten solstrand'
]

def sync_to_dirs(df, filename):
    p_root = ROOT_DIR / filename
    p_csdl = ROOT_DIR / "csdl_mlt" / filename
    p_arch = ROOT_DIR / "archive" / "no_norway" / filename

    df.to_csv(p_root, index=False, encoding='utf-8-sig')
    p_csdl.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p_csdl, index=False, encoding='utf-8-sig')
    p_arch.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p_arch, index=False, encoding='utf-8-sig')
    print(f"  [+] Đã cập nhật và đồng bộ: {filename} ({len(df):,} dòng)")

def purge():
    print("=" * 80)
    print(" BẮT ĐẦU THANH LỌC MAIL RÁC / MAIL MẪU / CÔNG TY LỆCH NGÀNH (NO_FARM)")
    print("=" * 80)

    src_2col = ROOT_DIR / "NO_FARM_COMB_2COL.csv"
    src_1enr = ROOT_DIR / "NO_FARM_GMAP_1ENR.csv"

    df = pd.read_csv(src_2col, encoding='utf-8-sig', dtype=str).fillna('')
    total_before = len(df)
    print(f"[*] Tổng số bản ghi trước khi lọc: {total_before:,}")

    # Bước 1: Thay thế mail thật đã tìm thấy
    for idx, r in df.iterrows():
        comp_l = r['Công ty'].strip().lower()
        if comp_l in EMAIL_REPLACEMENTS:
            new_em = EMAIL_REPLACEMENTS[comp_l]
            df.at[idx, 'Email'] = new_em
            df.at[idx, 'Liên Hệ mail'] = f"mailto:{new_em}"
            df.at[idx, 'Check gửi'] = 'OK'
            print(f"  [*] Đã khôi phục mail thật cho '{r['Công ty']}': {new_em}")

    # Bước 2: Loại bỏ công ty phi nông nghiệp map nhầm
    mask_farm = ~df['Công ty'].str.strip().str.lower().isin(NON_FARM_COMPANIES)
    removed_non_farm = (~mask_farm).sum()
    df = df[mask_farm].copy()
    print(f"  [-] Đã loại bỏ {removed_non_farm} công ty lệch ngành (Luật sư, Nha sĩ, Nhà tang lễ, Giặt ủi...)")

    # Bước 3: Làm sạch các mail rác / mail mẫu còn lại
    cleared_junk_emails = 0
    for idx, r in df.iterrows():
        em = r['Email'].strip().lower()
        if em in JUNK_EMAILS:
            df.at[idx, 'Email'] = ''
            df.at[idx, 'Liên Hệ mail'] = ''
            df.at[idx, 'Check gửi'] = ''
            cleared_junk_emails += 1
            print(f"  [-] Đã xóa mail rác/mẫu tại '{r['Công ty']}': {em}")

    # Bước 4: Kiểm tra lại điều kiện có liên hệ (SĐT hoặc Email)
    has_phone = df['SĐT'].str.strip() != ''
    has_email = df['Email'].str.strip() != ''
    has_contact = has_phone | has_email
    
    df_clean = df[has_contact].copy()

    # Bước 5: Đẩy 100% công ty có Email lên đầu
    with_email = df_clean[df_clean['Email'].str.strip() != ''].copy()
    without_email = df_clean[df_clean['Email'].str.strip() == ''].copy()

    df_final = pd.concat([with_email, without_email], ignore_index=True)
    df_final['No.'] = range(1, len(df_final) + 1)
    df_final = df_final[COL_20_HEADERS]

    # Cập nhật NO_FARM_COMB_2COL.csv
    sync_to_dirs(df_final, "NO_FARM_COMB_2COL.csv")

    # Cập nhật NO_FARM_ONLY_EMAILS_READY.csv
    df_emails_only = with_email.copy().reset_index(drop=True)
    df_emails_only['No.'] = range(1, len(df_emails_only) + 1)
    df_emails_only = df_emails_only[COL_20_HEADERS]
    sync_to_dirs(df_emails_only, "NO_FARM_ONLY_EMAILS_READY.csv")

    # Cập nhật NO_FARM_BOTH_PHONE_EMAIL.csv
    df_both = df_clean[(df_clean['SĐT'].str.strip() != '') & (df_clean['Email'].str.strip() != '')].copy().reset_index(drop=True)
    df_both['No.'] = range(1, len(df_both) + 1)
    df_both = df_both[COL_20_HEADERS]
    sync_to_dirs(df_both, "NO_FARM_BOTH_PHONE_EMAIL.csv")

    # Cập nhật NO_FARM_GMAP_1ENR.csv
    if src_1enr.exists():
        df1 = pd.read_csv(src_1enr, encoding='utf-8-sig', dtype=str).fillna('')
        for idx, r in df1.iterrows():
            comp_l = r['Công ty'].strip().lower()
            if comp_l in EMAIL_REPLACEMENTS:
                df1.at[idx, 'Email'] = EMAIL_REPLACEMENTS[comp_l]
            elif r['Email'].strip().lower() in JUNK_EMAILS:
                df1.at[idx, 'Email'] = ''
        
        mask_farm_1 = ~df1['Công ty'].str.strip().str.lower().isin(NON_FARM_COMPANIES)
        df1 = df1[mask_farm_1].copy()
        
        has_p1 = df1['SĐT'].str.strip() != ''
        has_e1 = df1['Email'].str.strip() != ''
        df1_clean = df1[has_p1 | has_e1].copy()
        
        w_em1 = df1_clean[df1_clean['Email'].str.strip() != ''].copy()
        wo_em1 = df1_clean[df1_clean['Email'].str.strip() == ''].copy()
        df1_final = pd.concat([w_em1, wo_em1], ignore_index=True)
        df1_final['No.'] = range(1, len(df1_final) + 1)
        df1_final.to_csv(src_1enr, index=False, encoding='utf-8-sig')
        print(f"  [+] Đã cập nhật NO_FARM_GMAP_1ENR.csv ({len(df1_final):,} dòng)")

    print("\n" + "=" * 80)
    print(" KẾT QUẢ SAU KHI THANH LỌC TOÀN DIỆN:")
    print(f" - Tổng công ty sạch còn lại               : {len(df_final):,} công ty")
    print(f" - Tổng công ty có Email B2B CHUẨN 100%    : {len(with_email):,} công ty (Dòng 1..{len(with_email)})")
    print(f" - Tổng công ty có SĐT (phục vụ gọi điện)   : {len(without_email):,} công ty (Dòng {len(with_email)+1}..{len(df_final)})")
    print(f" - Có cả SĐT và Email                      : {len(df_both):,} công ty")
    print("=" * 80)

if __name__ == '__main__':
    purge()

