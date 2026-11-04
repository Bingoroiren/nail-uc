# -*- coding: utf-8 -*-
"""
HỆ THỐNG ĐỐI CHIẾU & LÀM GIÀU DỮ LIỆU THỊT GÀ LITVA (LT_POUL - STRICT CHICKEN ONLY)
-------------------------------------------------------------------------------------
Yêu cầu cốt lõi từ người dùng:
1. TUYỆT ĐỐI KHÔNG THÊM CÔNG TY MỚI từ các ngành khác (bảo toàn đúng 979 công ty gà/gia cầm gốc).
   Lý do: Content gửi mail là về nhân lực "chế biến gà / gia cầm", nếu lọt công ty chế biến thịt khác
   hoặc ngành khác thì nội dung chào hàng sẽ bị lệch, làm giảm tỷ lệ chuyển đổi.
2. CHỈ ĐỐI CHIẾU LÀM GIÀU (ENRICH):
   - Bổ sung Email B2B cho các công ty đang thiếu mail.
   - Nâng cấp email chất lượng cao hơn và sửa lỗi chính tả (fmail.com -> gmail.com).
   - Điền SĐT (luôn có nháy đơn '), Website, Địa chỉ, Người liên hệ còn thiếu.
3. LOẠI BỎ 24 MAIL BOUNCE / LỖI từ chiến dịch trước (bảo vệ uy tín hòm thư gửi).
4. Đẩy 100% doanh nghiệp có Email lên đầu danh sách (dòng 1..N).
5. Đánh lại số thứ tự No. liên tục từ 1 đến 979.
6. TUYỆT ĐỐI KHÔNG DỪNG CÁC TIẾN TRÌNH ĐANG CHẠY NGẦM.
"""

import sys
import os
import re
import shutil
import urllib.parse
import unicodedata
from pathlib import Path
import pandas as pd

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

# File gốc nguyên bản 979 công ty gia cầm
FILE_ORIG_BACKUP = ROOT_DIR / "archive" / "lt_lithuania" / "LT_POUL_WEBD_2COL_pre_enrich_backup.csv"
FILE_FOOD_CLEAN = ROOT_DIR / "LT_FOOD_WEBS - CleanData.csv"
FILE_TRACKER = ROOT_DIR / "Mail Tracker - mail.csv"
FILE_BOUNCE_AUDIT = ROOT_DIR / "archive" / "lt_lithuania" / "LT_FOOD_DA_LOAI_BO_REPLY_BOUNCE.csv"

# File đầu ra đồng bộ
OUT_POUL_2COL = ROOT_DIR / "LT_POUL_WEBD_2COL.csv"
OUT_AUDIT_CSV = ROOT_DIR / "archive" / "lt_lithuania" / "LT_POUL_DA_LOAI_BO_REPLY_BOUNCE.csv"
CSDL_2COL = ROOT_DIR / "csdl_mlt" / "LT_POUL_WEBD_2COL.csv"
ARCHIVE_2COL = ROOT_DIR / "archive" / "lt_lithuania" / "LT_POUL_WEBD_2COL.csv"

COLUMNS_20 = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

# Rule #12: Danh sách đen vĩnh viễn
PERMANENT_BLACKLIST = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre', 'daigre'
]

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST)

def normalize_company_name(name):
    """Smart & Strict Name Matching cho Litva (Rule #11)"""
    if not name:
        return ""
    name_clean = re.sub(r'\([^\)]*\)|\[[^\]]*\]', ' ', str(name))
    n = unicodedata.normalize('NFKD', name_clean).lower()
    n = ''.join(c for c in n if not unicodedata.combining(c))
    
    legal_forms = [
        'uzdaroji akcine bendrove', 'akcine bendrove', 'mazoji bendrija', 'viesoji istaiga',
        'individuali imone', 'zemes ukio kooperatyvas', 'zemes ukio bendrove', 'kooperatine bendrove',
        'uab', 'mb', 'ab', 'vsi', 'ii', 'zub', 'zuk', 'kb', 'tub', 'kub', 'jsc', 'llc', 'firma'
    ]
    for lf in sorted(legal_forms, key=len, reverse=True):
        n = re.sub(rf'\b{lf}\b', ' ', n)
        
    n = ' '.join(re.sub(r'[^a-z0-9]', ' ', n).split())
    return n

def clean_phone_lt(p):
    """Chuẩn hóa SĐT Litva có nháy đơn (') và mã vùng +370 (Rule #2)"""
    if not p or str(p).strip() in ['', 'nan', 'None']:
        return ''
    s = str(p).strip().lstrip("'").strip()
    digits = re.sub(r'[^0-9]', '', s)
    if not digits:
        return ''
    if digits.startswith('370'):
        formatted = f"+{digits}"
    elif digits.startswith('8') and len(digits) == 9:
        formatted = f"+370{digits[1:]}"
    elif len(digits) == 8:
        formatted = f"+370{digits}"
    else:
        formatted = f"+{digits}" if not s.startswith('+') else s
    return f"'{formatted}"

def clean_email(email):
    """Làm sạch email triệt để theo Rule #3 & data-standards"""
    if not email or not isinstance(email, str):
        return ""
    em = urllib.parse.unquote(str(email).strip())
    for bad in ['\u00a0', '\xa0', '&nbsp;', '%20', '\u200b', '\u200e', '\u200f', '\ufeff', '\u202f', '\u3000']:
        em = em.replace(bad, '')
    em = re.sub(r'^mailto:\s*', '', em, flags=re.I)
    em = re.sub(r'\s+', '', em).strip(" .,;:\"'<>[](){}\\/")
    
    em = re.sub(r'@fmail\.com$', '@gmail.com', em, flags=re.I)
    em = re.sub(r'@gmai\.com$', '@gmail.com', em, flags=re.I)
    em = re.sub(r'@gmial\.com$', '@gmail.com', em, flags=re.I)
    
    if re.match(r'^20[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', em) and not em.startswith('202'):
        if re.match(r'^20[a-zA-Z]', em):
            em = em[2:]
            
    em = em.lower()
    if not re.match(r'^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,10}$', em):
        return ""
        
    u, d = em.split('@', 1)
    junk_domains = [
        'sentry', 'wixpress', 'wix.com', 'example.com', 'pavyzdys.lt', 'domain.com',
        'yoursite.com', 'email.com', 'test.com', 'cookiebot.com', 'squarespace.com'
    ]
    if any(b in d for b in junk_domains):
        return ""
        
    junk_users = [
        'sentry', 'youremail', 'your-email', 'yourname', 'sample', 'no-reply',
        'donotreply', 'someone', 'john.doe', 'privacy', 'gdpr', 'abuse',
        'postmaster', 'user', 'name', 'pavyzdys', 'jus'
    ]
    if any(b in u for b in junk_users):
        return ""
        
    return em

def score_email_b2b_lt(email, domain=""):
    """Chấm điểm email B2B cho doanh nghiệp Litva"""
    e = clean_email(email)
    if not e or '@' not in e:
        return -1
    u, d = e.split('@', 1)
    
    score = 10
    clean_d = domain.lower().replace('www.', '').split('/')[0] if domain else ""
    if clean_d and (clean_d in d or d in clean_d):
        score += 50
    elif d.endswith('.lt'):
        score += 25

    if u in ['personalas', 'darbas', 'karjera', 'hr', 'jobs', 'recruitment', 'career']:
        score += 50
    elif u in ['direktorius', 'vadovas', 'ceo', 'director', 'manager', 'komercija', 'sales', 'pardavimai']:
        score += 45
    elif u in ['info', 'kontaktai', 'office', 'administracija', 'bendras', 'sekretoriatas', 'reception']:
        score += 40
    elif '.' in u and score >= 60:
        score += 25
    elif u in ['buhalterija', 'saskaitos', 'invoice', 'tiekimas']:
        score += 5
    return score

def main():
    print("=" * 80)
    print(" LÀM GIÀU DỮ LIỆU THỊT GÀ LITVA (LT_POUL - BẢO TOÀN DANH SÁCH 979 CÔNG TY)")
    print(" (Tuyệt đối KHÔNG thêm công ty khác ngành để đúng content chế biến gà)")
    print("=" * 80)

    # Đọc lại từ file backup nguyên bản 979 công ty gia cầm
    if not FILE_ORIG_BACKUP.exists():
        print(f"[ERROR] Không tìm thấy file backup gốc: {FILE_ORIG_BACKUP}")
        return

    df_poul = pd.read_csv(FILE_ORIG_BACKUP, encoding='utf-8-sig', dtype=str).fillna('')
    df_food = pd.read_csv(FILE_FOOD_CLEAN, encoding='utf-8-sig', dtype=str).fillna('')

    total_companies = len(df_poul)
    print(f"[*] Số doanh nghiệp gia cầm gốc  : {total_companies} công ty (100% đúng lĩnh vực)")
    print(f"[*] File đối chiếu CleanData     : {len(df_food)} dòng")

    # 1. Nạp danh sách email Bounce và Reply để loại trừ
    excluded_emails = set()
    excluded_reasons = {}

    if FILE_BOUNCE_AUDIT.exists():
        df_bounce = pd.read_csv(FILE_BOUNCE_AUDIT, encoding='utf-8-sig', dtype=str).fillna('')
        for _, r in df_bounce.iterrows():
            em = clean_email(r.get('Email', ''))
            reason = str(r.get('Lý do loại bỏ', 'Mail lỗi / Bounce chiến dịch cũ')).strip()
            if em:
                excluded_emails.add(em)
                excluded_reasons[em] = reason
        print(f"[*] Đã nạp {len(excluded_emails)} email bounce/lỗi từ chiến dịch trước")

    if FILE_TRACKER.exists():
        df_track = pd.read_csv(FILE_TRACKER, encoding='utf-8-sig', dtype=str).fillna('')
        for _, r in df_track.iterrows():
            for c in ['Người gửi', 'Người phản hồi']:
                em = clean_email(r.get(c, ''))
                if em and '@' in em:
                    excluded_emails.add(em)
                    if em not in excluded_reasons:
                        excluded_reasons[em] = f"Đã phản hồi trong Mail Tracker: {r.get('Tình trạng phản hồi', '')}"

    # 2. Xóa bỏ email bounce trong LT_POUL
    removed_bounce_records = []
    bounced_cleared_count = 0
    for idx, r in df_poul.iterrows():
        comp = r['Công ty']
        em = clean_email(r['Email'])
        if em and em in excluded_emails:
            reason = excluded_reasons.get(em, 'Mail lỗi / Bounce trong CleanData')
            removed_bounce_records.append({
                'Công ty': comp,
                'Email': em,
                'SĐT': r['SĐT'],
                'Địa chỉ': r['Địa chỉ'],
                'Lý do loại bỏ': reason
            })
            df_poul.at[idx, 'Email'] = ''
            df_poul.at[idx, 'Liên Hệ mail'] = ''
            df_poul.at[idx, 'Check gửi'] = ''
            bounced_cleared_count += 1

    print(f"[*] Đã lọc bỏ {bounced_cleared_count} email bounce/lỗi trong danh sách gốc!")

    # 3. Chuẩn bị bảng tra cứu từ LT_FOOD
    df_food['norm'] = df_food['Công ty'].apply(normalize_company_name)
    df_poul['norm'] = df_poul['Công ty'].apply(normalize_company_name)

    food_by_norm = {}
    for _, r in df_food.iterrows():
        nm = r['norm']
        if nm and nm not in food_by_norm:
            food_by_norm[nm] = r

    # 4. Đối chiếu và làm giàu CHỈ TRÊN 979 CÔNG TY HIỆN CÓ
    enriched_emails_count = 0
    upgraded_emails_count = 0
    enriched_phones_count = 0
    enriched_webs_count = 0
    enriched_addrs_count = 0
    enriched_contacts_count = 0

    for idx, r in df_poul.iterrows():
        nm = r['norm']
        if not nm or nm not in food_by_norm:
            continue
            
        f_row = food_by_norm[nm]
        p_em = clean_email(r['Email'])
        f_em = clean_email(f_row['Email'])
        
        # Làm giàu hoặc nâng cấp Email
        if f_em and f_em not in excluded_emails:
            if not p_em:
                df_poul.at[idx, 'Email'] = f_em
                df_poul.at[idx, 'Liên Hệ mail'] = f"mailto:{f_em}"
                df_poul.at[idx, 'Check gửi'] = 'Chưa gửi'
                enriched_emails_count += 1
            else:
                score_p = score_email_b2b_lt(p_em)
                score_f = score_email_b2b_lt(f_em)
                if score_f > score_p:
                    df_poul.at[idx, 'Email'] = f_em
                    df_poul.at[idx, 'Liên Hệ mail'] = f"mailto:{f_em}"
                    upgraded_emails_count += 1

        # Làm giàu SĐT nếu POUL còn thiếu
        p_ph = str(r['SĐT']).strip()
        f_ph = str(f_row['SĐT']).strip()
        if not p_ph and f_ph:
            df_poul.at[idx, 'SĐT'] = clean_phone_lt(f_ph)
            enriched_phones_count += 1

        # Làm giàu Website nếu POUL còn thiếu
        p_wb = str(r['Liên Hệ']).strip()
        f_wb = str(f_row['Liên Hệ']).strip()
        if not p_wb and f_wb:
            df_poul.at[idx, 'Liên Hệ'] = f_wb
            enriched_webs_count += 1

        # Làm giàu Địa chỉ nếu POUL còn thiếu
        p_ad = str(r['Địa chỉ']).strip()
        f_ad = str(f_row['Địa chỉ']).strip()
        if not p_ad and f_ad:
            df_poul.at[idx, 'Địa chỉ'] = f_ad
            enriched_addrs_count += 1

        # Làm giàu Người liên hệ nếu POUL còn thiếu
        p_ct = str(r['Người liên hệ']).strip()
        f_ct = str(f_row['Người liên hệ']).strip()
        if not p_ct and f_ct:
            df_poul.at[idx, 'Người liên hệ'] = f_ct
            enriched_contacts_count += 1

    print(f"[*] Kết quả làm giàu cho {len(df_poul)} công ty thịt gà Litva:")
    print(f"    - Email mới bổ sung         : +{enriched_emails_count}")
    print(f"    - Email nâng cấp chất lượng : +{upgraded_emails_count}")
    print(f"    - SĐT mới bổ sung           : +{enriched_phones_count}")
    print(f"    - Website mới bổ sung       : +{enriched_webs_count}")
    print(f"    - Địa chỉ mới bổ sung       : +{enriched_addrs_count}")
    print(f"    - Người liên hệ bổ sung     : +{enriched_contacts_count}")

    # 5. Chuẩn hóa SĐT và Email
    df_poul['SĐT'] = df_poul['SĐT'].apply(clean_phone_lt)
    df_poul['Email'] = df_poul['Email'].apply(clean_email)
    df_poul['Liên Hệ mail'] = df_poul['Email'].apply(lambda e: f"mailto:{e}" if e else "")

    # 6. Khử trùng lặp Email mà KHÔNG XÓA CÔNG TY (Bảo toàn đúng 979 công ty)
    # Nếu một email bị trùng giữa các công ty con/chi nhánh, công ty đầu tiên giữ mail, công ty sau để trống mail
    seen_emails = set()
    dup_emails_cleared = 0
    for idx, r in df_poul.iterrows():
        em = r['Email'].strip().lower()
        if em:
            if em in seen_emails:
                df_poul.at[idx, 'Email'] = ''
                df_poul.at[idx, 'Liên Hệ mail'] = ''
                df_poul.at[idx, 'Check gửi'] = ''
                dup_emails_cleared += 1
            else:
                seen_emails.add(em)
                
    if dup_emails_cleared > 0:
        print(f"[*] Đã xử lý {dup_emails_cleared} email trùng lặp giữa các chi nhánh (đảm bảo 100% email là duy nhất)!")

    # 7. Sắp xếp: 100% công ty có Email lên đầu (Rule #3)
    has_email = df_poul[df_poul['Email'] != ''].copy()
    no_email = df_poul[df_poul['Email'] == ''].copy()

    df_final = pd.concat([has_email, no_email], ignore_index=True)
    df_final['No.'] = range(1, len(df_final) + 1)
    df_final = df_final[COLUMNS_20]

    # Kiểm tra số lượng công ty phải đúng 979 công ty gốc
    assert len(df_final) == total_companies, f"Số lượng công ty bị lệch: {len(df_final)} vs {total_companies}"

    # 8. Lưu file đồng bộ
    df_final.to_csv(OUT_POUL_2COL, index=False, encoding='utf-8-sig')
    print(f"\n[+] ĐÃ CẬP NHẬT TRỰC TIẾP: {OUT_POUL_2COL}")

    CSDL_2COL.parent.mkdir(parents=True, exist_ok=True)
    df_final.to_csv(CSDL_2COL, index=False, encoding='utf-8-sig')
    print(f"[+] ĐÃ ĐỒNG BỘ CSDL     : {CSDL_2COL}")

    ARCHIVE_2COL.parent.mkdir(parents=True, exist_ok=True)
    df_final.to_csv(ARCHIVE_2COL, index=False, encoding='utf-8-sig')
    print(f"[+] ĐÃ LƯU TRỮ ARCHIVE  : {ARCHIVE_2COL}")

    if removed_bounce_records:
        OUT_AUDIT_CSV.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(removed_bounce_records).to_csv(OUT_AUDIT_CSV, index=False, encoding='utf-8-sig')
        print(f"[+] ĐÃ XUẤT AUDIT LOG BOUNCE ĐÃ LOẠI BỎ: {OUT_AUDIT_CSV}")

    total_with_email = len(df_final[df_final['Email'] != ''])
    total_without_email = len(df_final) - total_with_email

    print("\n" + "=" * 80)
    print(" HOÀN TẤT LÀM GIÀU DỮ LIỆU THỊT GÀ LITVA!")
    print("=" * 80)
    print(f"[*] Tổng số doanh nghiệp BẢO TOÀN : {len(df_final):,} (ĐÚNG 100% 979 CÔNG TY GÀ GỐC)")
    print(f"[*] Doanh nghiệp CÓ EMAIL HỢP LỆ   : {total_with_email:,} ({total_with_email/len(df_final):.1%}) - Hàng 1 đến {total_with_email}")
    print(f"[*] Doanh nghiệp chưa có email     : {total_without_email:,} - Hàng {total_with_email+1} đến {len(df_final)}")
    print("=" * 80)

if __name__ == '__main__':
    main()
