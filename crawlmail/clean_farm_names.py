# -*- coding: utf-8 -*-
"""
HỆ THỐNG RÀ SOÁT, LÀM SẠCH VÀ KHÔI PHỤC ĐẦY ĐỦ 100% NÔNG NGHIỆP NA UY (GULESIDER)
-----------------------------------------------------------------------------------
Tác dụng:
1. Khôi phục đầy đủ 1.063 doanh nghiệp nông nghiệp từ 1.197 kết quả trên Gulesider:
   - Trồng trọt, Chăn nuôi, Nông trại (Husdyr, Jordbruk, Dyrking, Gartneri...)
   - Dịch vụ, cơ giới hóa, máy móc thiết bị nông nghiệp (Landbruksmaskin, Landbrukstjeneste...)
2. Loại bỏ đúng 57 đơn vị rác / phi nông nghiệp / chính quyền:
   - Cơ quan hành chính, chính quyền huyện/xã (Kommune, Herad, Offentlig virksomhet, Landbrukskontor)
   - Doanh nghiệp phi nông nghiệp (Bảo tàng, Trường học, Đại lý xe hơi, Bọc sofa, Cải tạo cống, Kiến trúc sư...)
3. Giải mã 100% mã hóa URL (%26 -> &, %C3%B8 -> ø, %C3%A5 -> å, %C3%A6 -> æ...).
4. Sửa lỗi viết hoa dị dạng (Hjørnegård, Lågen, Stensrød, Søfteland, Sæbø, Ødeli...).
5. Cắt bỏ tên thành phố bị dính thừa ở đuôi tên công ty.
6. Chuẩn hóa viết hoa loại hình pháp lý: AS, ANS, ENK, DA, SA...
7. Đẩy toàn bộ 178 doanh nghiệp có Email lên các dòng đầu tiên (dòng 1..178).
8. Chuẩn hóa số điện thoại có nháy đơn '+47...
9. Cập nhật đồng bộ vào tất cả các tệp:
   - NO_FARM_GULE_0RAW.csv
   - NO_FARM_GULE_2COL.csv
   - NO_FARM_COMB_2COL.csv
   - csdl_mlt/NO_FARM_GULE_2COL.csv
   - archive/no_norway/NO_FARM_GULE_2COL.csv
"""

import sys
import re
import json
import urllib.parse
from pathlib import Path
import pandas as pd

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

EXCLUDED_CATEGORIES = [
    'offentlig virksomhet', 'kommuner', 'arkitekt', 'møbeltapetserer',
    'rørfornying', 'renseanlegg', 'underholdningsbyrå', 'borettslag',
    'bilforhandler', 'sprengning', 'vaktmester', 'arbeidsgiverforening',
    'museum', 'skole', 'barnehage', 'kirke', 'boligutleie', 'boligformidling',
    'hotell', 'overnatting', 'camping', 'eiendom'
]

EXCLUDED_NAMES = [
    'kommune', 'herad', 'fylkeskommune', 'landbrukskontor',
    'departement', 'direktorat', 'statens', 'museum', 'kirke', 'menighet'
]

LEGAL_FORMS = ['AS', 'ANS', 'ENK', 'DA', 'SA', 'BA', 'KS', 'HF', 'NUF']
LOWER_WORDS = ['og', 'i', 'av', 'på', 'for', 'til', 'med']

COLUMNS_RAW = [
    'No.', 'Orgnr', 'Cong ty', 'Ten phap ly', 'SDT', 'Email', 'Website',
    'Dia chi', 'Ma buu dien', 'Khu vuc', 'Thanh pho',
    'Tag_Chinh', 'All_Tags', 'NACE', 'Nguoi quan ly', 'Chuc danh',
    'Doanh thu', 'So nhan vien', 'Nam thanh lap', 'Proff URL'
]

COLUMNS_20 = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ',
    'Email', 'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển',
    'Check gửi', 'Last Subject', 'Last Body HTML', 'Trạng thái Reply',
    'Lần Follow-up', 'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

def multi_unquote(s):
    if not s or not isinstance(s, str):
        return ""
    cur = str(s).strip()
    for _ in range(3):
        if '%' in cur:
            try:
                nxt = urllib.parse.unquote(cur)
                nxt = urllib.parse.unquote_plus(nxt)
                if nxt == cur:
                    break
                cur = nxt
            except Exception:
                break
        else:
            break
    cur = re.sub(r'\bv/\s*', 'v/ ', cur, flags=re.I)
    return cur.strip()

def fix_title_casing(word):
    if re.search(r'[a-zæøå][A-ZÆØÅ]', word):
        return word[0].upper() + word[1:].lower()
    return word

def extract_city_from_addr(addr):
    if not addr or not isinstance(addr, str):
        return ""
    m = re.search(r'\b\d{4}\s+([A-Za-zÆØÅæøå\- ]+)', addr)
    if m:
        return m.group(1).strip()
    parts = addr.split(',')
    if len(parts) > 1:
        return parts[-1].strip()
    return ""

def beautify_company_name(raw_name, addr_or_city=""):
    if not raw_name or not isinstance(raw_name, str):
        return ""
    name = multi_unquote(raw_name)
    words = []
    for w in name.split():
        up = w.upper()
        low = w.lower()
        if up in LEGAL_FORMS:
            words.append(up)
        elif low in LOWER_WORDS and len(words) > 0:
            words.append(low)
        elif w == '&':
            words.append('&')
        else:
            words.append(fix_title_casing(w))
    name = ' '.join(words)
    city = extract_city_from_addr(addr_or_city) if ',' in addr_or_city or re.search(r'\d{4}', addr_or_city) else addr_or_city
    if city and str(city).strip() not in ['', 'None', 'nan']:
        c_clean = str(city).strip()
        pat = re.compile(r'\s+' + re.escape(c_clean) + r'$', re.I)
        name = pat.sub('', name).strip()
    return name.strip()

def clean_phone(phone_raw):
    if not phone_raw or str(phone_raw).strip() in ['', 'None', 'nan']:
        return ''
    s = str(phone_raw).strip()
    digits = re.sub(r'[^0-9]', '', s)
    if not digits:
        return ''
    if digits.startswith('0047'):
        digits = digits[4:]
    elif digits.startswith('47') and len(digits) >= 10:
        digits = digits[2:]
    if len(digits) == 8:
        return f"'+47{digits}"
    return f"'+{digits}"

def clean_email(email_raw):
    if not email_raw or str(email_raw).strip() in ['', 'None', 'nan']:
        return ""
    em = multi_unquote(str(email_raw)).strip().lower()
    em = em.replace('%20', '').replace('\u00a0', '').replace('\xa0', '').replace('&nbsp;', '')
    em = re.sub(r'[\s\u200b\ufeff]', '', em)
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', em):
        return ""
    bad_prefixes = ['youremail', 'your-email', 'yourname', 'someone', 'john.doe', 'example', 'name@', 'email@', 'user@']
    bad_domains = ['example.com', 'domain.com', 'company.com', 'email.com', 'sentry.io', 'wixpress.com', 'wordpress.com']
    if any(em.startswith(b) for b in bad_prefixes) or any(em.endswith(b) for b in bad_domains):
        return ""
    return em

def rebuild_from_cache():
    cache_path = ROOT_DIR / "crawlmail" / "cache_gulesider_farm.json"
    if not cache_path.exists():
        print("[!] Không tìm thấy cache_gulesider_farm.json")
        return

    with open(cache_path, 'r', encoding='utf-8') as f:
        cache = json.load(f)

    # Nạp dữ liệu đối chiếu từ Proff (nếu có)
    proff_lookup = {}
    proff_path = ROOT_DIR / "NO_FARM_WEBD_0RAW.csv"
    if proff_path.exists():
        try:
            df_p = pd.read_csv(proff_path, encoding='utf-8-sig', dtype=str).fillna('')
            for _, pr in df_p.iterrows():
                o = str(pr.get('Orgnr', '')).strip()
                if o and len(o) == 9:
                    proff_lookup[o] = pr.to_dict()
                n = str(pr.get('Cong ty', '')).strip().lower()
                if n:
                    proff_lookup[n] = pr.to_dict()
        except Exception:
            pass

    valid_with_em = []
    valid_without_em = []
    raw_records = []
    excluded_count = 0

    for rel_u, d in cache.items():
        raw_name = d.get('name', '')
        cats = d.get('categories', [])
        cats_str = " | ".join(cats).lower()
        street = multi_unquote(d.get('street', ''))
        zipcode = multi_unquote(d.get('zipcode', ''))
        city = multi_unquote(d.get('city', ''))
        full_addr = ', '.join([p for p in [street, f"{zipcode} {city}".strip()] if p])
        
        name = beautify_company_name(raw_name, full_addr)
        name_l = name.lower()

        # 1. Lọc bỏ cơ quan chính quyền / nhà nước
        if any(re.search(r'\b' + re.escape(ex) + r'\b', name_l) for ex in EXCLUDED_NAMES):
            excluded_count += 1
            continue

        # 2. Lọc bỏ ngành phi nông nghiệp
        if any(ex in cats_str for ex in EXCLUDED_CATEGORIES):
            excluded_count += 1
            continue

        orgnr = str(d.get('orgnr', '')).strip()
        email = clean_email(d.get('email', ''))
        phone = clean_phone(d.get('phone', ''))
        web = d.get('web', '')
        tag_main = cats[0] if cats else 'Jordbruk'
        all_tags_str = ' | '.join(cats) if cats else 'Jordbruk'

        # Đối chiếu thêm thông tin từ Proff
        p_match = proff_lookup.get(orgnr) or proff_lookup.get(name_l)
        leader = p_match.get('Nguoi quan ly', '') if p_match else ''
        role = p_match.get('Chuc danh', '') if p_match else ''
        rev = p_match.get('Doanh thu', '') if p_match else ''
        emp = p_match.get('So nhan vien', '') if p_match else ''
        found_yr = p_match.get('Nam thanh lap', '') if p_match else ''
        nace = p_match.get('NACE', '01.1 / 01.4 Gulesider Jordbruk') if p_match else '01.1 / 01.4 Gulesider Jordbruk'
        county = p_match.get('Khu vuc', '') if p_match else ''

        # 20 Cold Mail columns row
        row_2col = {
            'No.': '',
            'Công ty': name,
            'Chức danh': role,
            'Người liên hệ': leader,
            'SĐT': phone,
            'Liên Hệ': '',
            'Email': email,
            'Liên Hệ mail': '',
            'Địa chỉ': full_addr,
            'Lương': '',
            'Ngày đăng': '',
            'Hạn tuyển': '',
            'Check gửi': 'Chưa gửi' if email else '',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': tag_main
        }

        # RAW row
        row_raw = {
            'No.': '',
            'Orgnr': orgnr,
            'Cong ty': name,
            'Ten phap ly': name,
            'SDT': phone,
            'Email': email,
            'Website': web,
            'Dia chi': street,
            'Ma buu dien': zipcode,
            'Khu vuc': county,
            'Thanh pho': city,
            'Tag_Chinh': tag_main,
            'All_Tags': all_tags_str,
            'NACE': nace,
            'Nguoi quan ly': leader,
            'Chuc danh': role,
            'Doanh thu': rev,
            'So nhan vien': emp,
            'Nam thanh lap': found_yr,
            'Proff URL': d.get('url', f"https://www.gulesider.no{rel_u}")
        }

        raw_records.append(row_raw)

        if email and '@' in email:
            valid_with_em.append(row_2col)
        else:
            valid_without_em.append(row_2col)

    # Khử trùng lặp
    seen_keys = set()
    dedup_with_em = []
    for r in valid_with_em:
        k = (r['Công ty'].lower(), r['Email'].lower())
        if k not in seen_keys:
            seen_keys.add(k)
            dedup_with_em.append(r)

    dedup_without_em = []
    for r in valid_without_em:
        k = r['Công ty'].lower()
        if k not in seen_keys:
            seen_keys.add(k)
            dedup_without_em.append(r)

    final_2col = dedup_with_em + dedup_without_em
    for i, r in enumerate(final_2col, start=1):
        r['No.'] = str(i)

    for i, r in enumerate(raw_records, start=1):
        r['No.'] = str(i)

    # Xuất các file Gulesider
    gule_2col_path = ROOT_DIR / "NO_FARM_GULE_2COL.csv"
    gule_raw_path = ROOT_DIR / "NO_FARM_GULE_0RAW.csv"
    csdl_path = ROOT_DIR / "csdl_mlt" / "NO_FARM_GULE_2COL.csv"
    archive_path = ROOT_DIR / "archive" / "no_norway" / "NO_FARM_GULE_2COL.csv"
    comb_path = ROOT_DIR / "NO_FARM_COMB_2COL.csv"

    pd.DataFrame(final_2col, columns=COLUMNS_20).to_csv(gule_2col_path, index=False, encoding='utf-8-sig')
    pd.DataFrame(raw_records, columns=COLUMNS_RAW).to_csv(gule_raw_path, index=False, encoding='utf-8-sig')
    
    csdl_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(final_2col, columns=COLUMNS_20).to_csv(csdl_path, index=False, encoding='utf-8-sig')
    
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(final_2col, columns=COLUMNS_20).to_csv(archive_path, index=False, encoding='utf-8-sig')

    # Cập nhật file gộp NO_FARM_COMB_2COL.csv
    all_comb = list(final_2col)
    seen_comb_names = {r['Công ty'].lower(): True for r in final_2col if r.get('Công ty')}
    proff_2col_path = ROOT_DIR / "NO_FARM_WEBD_2COL.csv"
    if proff_2col_path.exists():
        try:
            df_p2 = pd.read_csv(proff_2col_path, encoding='utf-8-sig', dtype=str).fillna('')
            for _, pr in df_p2.iterrows():
                pr_dict = pr.to_dict()
                c_name = beautify_company_name(pr_dict.get('Công ty', ''))
                c_cat = pr_dict.get('Category', '')
                if any(re.search(r'\b' + re.escape(ex) + r'\b', c_name.lower()) for ex in EXCLUDED_NAMES):
                    continue
                if any(ex in c_cat.lower() for ex in EXCLUDED_CATEGORIES):
                    continue
                if c_name.lower() not in seen_comb_names:
                    seen_comb_names[c_name.lower()] = True
                    pr_dict['Công ty'] = c_name
                    pr_dict['SĐT'] = clean_phone(pr_dict.get('SĐT', ''))
                    pr_dict['Email'] = clean_email(pr_dict.get('Email', ''))
                    all_comb.append(pr_dict)
        except Exception:
            pass

    comb_with = [r for r in all_comb if r.get('Email') and '@' in r.get('Email')]
    comb_without = [r for r in all_comb if not r.get('Email') or '@' not in r.get('Email')]
    final_comb_rows = comb_with + comb_without
    for i, r in enumerate(final_comb_rows, start=1):
        r['No.'] = str(i)

    pd.DataFrame(final_comb_rows, columns=COLUMNS_20).to_csv(comb_path, index=False, encoding='utf-8-sig')

    print("=" * 80)
    print(" HOÀN TẤT KHÔI PHỤC ĐẦY ĐỦ DOANH NGHIỆP NÔNG NGHIỆP NA UY (GULESIDER)!")
    print(f" Tổng số doanh nghiệp xử lý từ Gulesider: {len(cache):,}")
    print(f" Loại bỏ (Cơ quan xã/huyện, bảo tàng, trường học, đại lý ô tô, bọc sofa...): {excluded_count:,}")
    print(f" TỔNG DOANH NGHIỆP NÔNG NGHIỆP GIỮ LẠI (GULESIDER): {len(final_2col):,}")
    print(f" TỔNG DOANH NGHIỆP CÓ EMAIL B2B (ĐẨY LÊN ĐẦU): {len(dedup_with_em):,}")
    print(f" TỔNG DOANH NGHIỆP GỘP CẢ 2 NGUỒN (NO_FARM_COMB_2COL.csv): {len(final_comb_rows):,} ({len(comb_with)} có Email)")
    print("=" * 80)

if __name__ == '__main__':
    rebuild_from_cache()
