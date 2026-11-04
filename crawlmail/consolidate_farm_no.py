# -*- coding: utf-8 -*-
"""
HỆ THỐNG GỘP VÀ LỌC TRÙNG DỮ LIỆU NÔNG NGHIỆP NA UY (PROFF.NO + GULESIDER.NO)
=============================================================================
Tác dụng:
1. Gộp toàn bộ dữ liệu 2 nguồn lớn nhất Na Uy:
   - Proff.no: 8.545 trang trại, doanh nghiệp nông nghiệp (Sauehold, Storfehold, Jordbruk, Svinehold...)
   - Gulesider.no: 1.140 hồ sơ (1.063 doanh nghiệp, hợp tác xã, cơ giới hóa máy móc nông nghiệp)
2. So khớp & Khử trùng lặp thông minh:
   - ƯU TIÊN DOANH NGHIỆP CÓ EMAIL TRƯỚC: Tuyệt đối không để bản ghi rỗng đè mất bản ghi có Email!
   - Khử trùng theo mã số doanh nghiệp 9 chữ số (Orgnr)
   - Khử trùng theo Tên chuẩn hóa (NFKD, khử legal forms) + Thành phố
   - Khử trùng Email: Đảm bảo 100% email là DUY NHẤT trong toàn bộ tệp, tránh double-send
3. Làm giàu dữ liệu chéo:
   - Tự động lấy Lãnh đạo (Daglig leder/Styreleder), Doanh thu, Nhân viên, NACE từ Proff bổ sung cho Gulesider
4. Chuẩn hóa & Làm sạch toàn diện:
   - Giải mã triệt để mã URL (%26 -> &, %C3%B8 -> ø, %C3%A5 -> å, %C3%A6 -> æ)
   - Sửa lỗi viết hoa dị dạng (Hjørnegård, Lågen, Stensrød, Søfteland...)
   - Chuẩn hóa loại hình pháp lý: AS, ANS, ENK, DA, SA...
   - Cắt bỏ tên thành phố bị nối dính ở đuôi tên công ty
   - Chuẩn hóa SĐT có nháy đơn '+47...
5. Xuất đồng bộ 2 tệp chuẩn quy chuẩn 17 ký tự:
   - NO_FARM_COMB_0RAW.csv: Tệp thô 20 cột đầy đủ dữ liệu tài chính, quản lý, NACE
   - NO_FARM_COMB_2COL.csv: Tệp Cold Mail 20 cột chuẩn hóa, ĐẨY 100% CÔNG TY CÓ EMAIL LÊN ĐẦU (Dòng 1..179)
6. Tự động đồng bộ vào csdl_mlt/ và archive/no_norway/
"""

import sys
import re
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

LEGAL_FORMS = [
    r'\baksjeselskap\b', r'\bas\b', r'\bans\b', r'\benk\b', r'\bda\b',
    r'\bsa\b', r'\bba\b', r'\bnuf\b', r'\bks\b', r'\bhf\b'
]

LOWER_WORDS = ['og', 'i', 'av', 'på', 'for', 'til', 'med']

# Danh sách đen cố định theo Quy tắc 12 (GEMINI.md)
PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre'
]

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

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
        if up in ['AS', 'ANS', 'ENK', 'DA', 'SA', 'BA', 'KS', 'HF', 'NUF']:
            words.append(up)
        elif low in LOWER_WORDS and len(words) > 0:
            words.append(low)
        elif w == '&':
            words.append('&')
        else:
            words.append(fix_title_casing(w))
    name = ' '.join(words)
    city = extract_city_from_addr(addr_or_city) if ',' in str(addr_or_city) or re.search(r'\d{4}', str(addr_or_city)) else str(addr_or_city)
    if city and str(city).strip() not in ['', 'None', 'nan']:
        c_clean = str(city).strip()
        pat = re.compile(r'\s+' + re.escape(c_clean) + r'$', re.I)
        name = pat.sub('', name).strip()
    return name.strip()

def normalize_comp_name(name):
    if not name:
        return ""
    n = re.sub(r'\(.*?\)|\[.*?\]', '', str(name))
    n = unicodedata.normalize('NFKD', n).lower()
    n = ''.join(c for c in n if not unicodedata.combining(c))
    for lf in LEGAL_FORMS:
        n = re.sub(lf, ' ', n)
    n = re.sub(r'[^a-z0-9]', ' ', n)
    return re.sub(r'\s+', ' ', n).strip()

def normalize_city(city):
    if not city:
        return ""
    c = unicodedata.normalize('NFKD', str(city)).lower()
    c = ''.join(x for x in c if not unicodedata.combining(x))
    return re.sub(r'[^a-z0-9]', '', c)

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
    em = str(email_raw).strip().lower()
    em = em.replace('%20', '').replace('\u00a0', '').replace('\xa0', '').replace('&nbsp;', '')
    em = re.sub(r'[\s\u200b\ufeff]', '', em)
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', em):
        return ""
    bad_prefixes = ['youremail', 'your-email', 'yourname', 'someone', 'john.doe', 'example', 'name@', 'email@', 'user@']
    bad_domains = ['example.com', 'domain.com', 'company.com', 'email.com', 'sentry.io', 'wixpress.com', 'wordpress.com']
    if any(em.startswith(b) for b in bad_prefixes) or any(em.endswith(b) for b in bad_domains):
        return ""
    return em

def format_clean_record(r):
    addr_or_city = f"{r.get('Dia chi', '')}, {r.get('Thanh pho', '')}"
    comp = beautify_company_name(r.get('Cong ty', ''), addr_or_city)
    r['Cong ty'] = comp
    r['Ten phap ly'] = beautify_company_name(r.get('Ten phap ly', comp), addr_or_city)
    r['SDT'] = clean_phone(r.get('SDT', ''))
    r['Email'] = clean_email(r.get('Email', ''))
    return r

def is_excluded(comp, tag_str):
    if is_blacklisted_company(comp):
        return True
    comp_l = comp.lower()
    if any(re.search(r'\b' + re.escape(ex) + r'\b', comp_l) for ex in EXCLUDED_NAMES):
        return True
    tag_l = tag_str.lower()
    if any(ex in tag_l for ex in EXCLUDED_CATEGORIES):
        return True
    return False

def consolidate_norway_agriculture():
    print("=" * 80)
    print(" KÍCH HOẠT HỆ THỐNG GỘP VÀ LỌC TRÙNG NÔNG NGHIỆP NA UY (PROFF + GULESIDER)")
    print("=" * 80)

    p_gule_raw = ROOT_DIR / "NO_FARM_GULE_0RAW.csv"
    p_proff_raw = ROOT_DIR / "NO_FARM_WEBD_0RAW.csv"

    if not p_gule_raw.exists() or not p_proff_raw.exists():
        print("Lỗi: Không tìm thấy file dữ liệu đầu vào!")
        return

    df_gule_raw = pd.read_csv(p_gule_raw, encoding='utf-8-sig', dtype=str).fillna('')
    df_proff_raw = pd.read_csv(p_proff_raw, encoding='utf-8-sig', dtype=str).fillna('')

    print(f"Đã nạp Gulesider RAW: {len(df_gule_raw):,} dòng")
    print(f"Đã nạp Proff RAW    : {len(df_proff_raw):,} dòng")

    # 1. Lập chỉ mục Proff RAW để làm giàu dữ liệu tài chính & lãnh đạo
    proff_by_org = {}
    proff_by_name_city = {}
    proff_by_name = {}

    for _, r in df_proff_raw.iterrows():
        p = format_clean_record(r.to_dict())
        o = p.get('Orgnr', '').strip()
        city = p.get('Thanh pho', '').strip()
        n_city = normalize_city(city)
        n_name = normalize_comp_name(p.get('Cong ty', ''))

        if o and len(o) == 9:
            proff_by_org[o] = p
        if n_name:
            if n_city:
                proff_by_name_city[(n_name, n_city)] = p
            proff_by_name[n_name] = p

    print(f"Đã chỉ mục Proff: {len(proff_by_org):,} theo Orgnr, {len(proff_by_name):,} theo Tên")

    # Hàm làm giàu dữ liệu từ Proff
    def enrich_from_proff(rec):
        o = rec.get('Orgnr', '').strip()
        n_name = normalize_comp_name(rec.get('Cong ty', ''))
        n_city = normalize_city(rec.get('Thanh pho', ''))

        p_match = None
        if o and len(o) == 9 and o in proff_by_org:
            p_match = proff_by_org[o]
        elif (n_name, n_city) in proff_by_name_city:
            p_match = proff_by_name_city[(n_name, n_city)]
        elif n_name and n_name in proff_by_name:
            p_match = proff_by_name[n_name]

        if p_match:
            if not rec.get('Nguoi quan ly'): rec['Nguoi quan ly'] = p_match.get('Nguoi quan ly', '')
            if not rec.get('Chuc danh'): rec['Chuc danh'] = p_match.get('Chuc danh', '')
            if not rec.get('Doanh thu'): rec['Doanh thu'] = p_match.get('Doanh thu', '')
            if not rec.get('So nhan vien'): rec['So nhan vien'] = p_match.get('So nhan vien', '')
            if not rec.get('Nam thanh lap'): rec['Nam thanh lap'] = p_match.get('Nam thanh lap', '')
            if not rec.get('NACE') or 'Gulesider' in rec.get('NACE'): rec['NACE'] = p_match.get('NACE', rec.get('NACE', ''))
            if not rec.get('Khu vuc'): rec['Khu vuc'] = p_match.get('Khu vuc', '')
            if not rec.get('Website') and p_match.get('Website'): rec['Website'] = p_match.get('Website', '')
            if not rec.get('Proff URL') or 'gulesider' in rec.get('Proff URL'):
                rec['Proff URL'] = p_match.get('Proff URL', rec.get('Proff URL', ''))
        return rec

    # 2. Tách toàn bộ bản ghi thành 2 nhóm: CÓ EMAIL và KHÔNG CÓ EMAIL
    # Ưu tiên tuyệt đối: Xử lý 100% bản ghi CÓ EMAIL trước để không bao giờ bị bản ghi rỗng nuốt mất!
    g_records = [format_clean_record(r.to_dict()) for _, r in df_gule_raw.iterrows()]
    p_records = [format_clean_record(r.to_dict()) for _, r in df_proff_raw.iterrows()]

    all_with_email = []
    all_without_email = []

    for r in g_records + p_records:
        em = r.get('Email', '')
        tag_str = r.get('Tag_Chinh', '') + ' ' + r.get('All_Tags', '')
        if is_excluded(r.get('Cong ty', ''), tag_str):
            continue
        if em and '@' in em:
            all_with_email.append(r)
        else:
            all_without_email.append(r)

    print(f"Tổng bản ghi hợp lệ: {len(all_with_email):,} có Email, {len(all_without_email):,} không Email")

    # 3. Xử lý nhóm CÓ EMAIL (Khử trùng email tuyệt đối, mỗi hộp thư chỉ xuất hiện 1 lần)
    master_with_email = []
    seen_emails = set()
    seen_orgs = set()
    seen_name_cities = set()
    seen_names = set()

    for r in all_with_email:
        em = r.get('Email', '').lower()
        if em in seen_emails:
            continue
        seen_emails.add(em)

        r = enrich_from_proff(r)

        o = r.get('Orgnr', '').strip()
        n_name = normalize_comp_name(r.get('Cong ty', ''))
        n_city = normalize_city(r.get('Thanh pho', ''))

        if o and len(o) == 9:
            seen_orgs.add(o)
        if n_name and n_city:
            seen_name_cities.add((n_name, n_city))
        if n_name:
            seen_names.add(n_name)

        master_with_email.append(r)

    print(f"Sau khử trùng: Giữ trọn vẹn {len(master_with_email):,} doanh nghiệp CÓ EMAIL B2B DUY NHẤT!")

    # 4. Xử lý nhóm KHÔNG CÓ EMAIL (Khử trùng theo Orgnr, Tên + Thành phố, Tên)
    master_without_email = []

    for r in all_without_email:
        o = r.get('Orgnr', '').strip()
        n_name = normalize_comp_name(r.get('Cong ty', ''))
        n_city = normalize_city(r.get('Thanh pho', ''))

        # Nếu công ty đã có trong nhóm có email hoặc đã xuất hiện trước đó -> Bỏ qua
        if o and len(o) == 9 and o in seen_orgs:
            continue
        if n_name and n_city and (n_name, n_city) in seen_name_cities:
            continue
        if n_name and n_name in seen_names:
            continue

        r = enrich_from_proff(r)

        if o and len(o) == 9:
            seen_orgs.add(o)
        if n_name and n_city:
            seen_name_cities.add((n_name, n_city))
        if n_name:
            seen_names.add(n_name)

        master_without_email.append(r)

    print(f"Sau khử trùng: Bổ sung {len(master_without_email):,} doanh nghiệp không có email.")

    # 5. Gộp và đánh số thứ tự: 100% CÔNG TY CÓ EMAIL NẰM Ở CÁC DÒNG ĐẦU TIÊN (Dòng 1..N)
    final_master_raw = master_with_email + master_without_email
    for i, r in enumerate(final_master_raw, start=1):
        r['No.'] = str(i)

    # 6. Tạo tệp Cold Mail 20 cột (NO_FARM_COMB_2COL.csv) tương ứng
    final_master_2col = []
    for r in final_master_raw:
        c_name = r.get('Cong ty', '')
        c_leader = r.get('Nguoi quan ly', '')
        c_role = r.get('Chuc danh', '')
        c_phone = r.get('SDT', '')
        c_email = r.get('Email', '')

        street = r.get('Dia chi', '')
        zipcode = r.get('Ma buu dien', '')
        city = r.get('Thanh pho', '')
        addr_parts = [p for p in [street, f"{zipcode} {city}".strip()] if p]
        full_addr = ', '.join(addr_parts) if addr_parts else street

        category = r.get('Tag_Chinh', '') or 'Jordbruk'

        row_20 = {
            'No.': r.get('No.', ''),
            'Công ty': c_name,
            'Chức danh': c_role,
            'Người liên hệ': c_leader,
            'SĐT': c_phone,
            'Liên Hệ': '',
            'Email': c_email,
            'Liên Hệ mail': '',
            'Địa chỉ': full_addr,
            'Lương': '',
            'Ngày đăng': '',
            'Hạn tuyển': '',
            'Check gửi': 'Chưa gửi' if c_email else '',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trạng thái Reply': '',
            'Lần Follow-up': '',
            'Ngày Follow-up gần nhất': '',
            'Mailbox đã dùng': '',
            'Category': category
        }
        final_master_2col.append(row_20)

    # 7. Xuất file UTF-8 with BOM và đồng bộ hệ thống
    comb_raw_path = ROOT_DIR / "NO_FARM_COMB_0RAW.csv"
    comb_2col_path = ROOT_DIR / "NO_FARM_COMB_2COL.csv"
    csdl_path = ROOT_DIR / "csdl_mlt" / "NO_FARM_COMB_2COL.csv"
    archive_2col_path = ROOT_DIR / "archive" / "no_norway" / "NO_FARM_COMB_2COL.csv"
    archive_raw_path = ROOT_DIR / "archive" / "no_norway" / "NO_FARM_COMB_0RAW.csv"

    pd.DataFrame(final_master_raw, columns=COLUMNS_RAW).to_csv(comb_raw_path, index=False, encoding='utf-8-sig')
    pd.DataFrame(final_master_2col, columns=COLUMNS_20).to_csv(comb_2col_path, index=False, encoding='utf-8-sig')

    csdl_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(final_master_2col, columns=COLUMNS_20).to_csv(csdl_path, index=False, encoding='utf-8-sig')

    archive_2col_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(final_master_2col, columns=COLUMNS_20).to_csv(archive_2col_path, index=False, encoding='utf-8-sig')
    pd.DataFrame(final_master_raw, columns=COLUMNS_RAW).to_csv(archive_raw_path, index=False, encoding='utf-8-sig')

    print("=" * 80)
    print(" HOÀN TẤT GỘP VÀ LỌC TRÙNG DỮ LIỆU NÔNG NGHIỆP NA UY!")
    print(f" - TỔNG DOANH NGHIỆP NÔNG NGHIỆP DUY NHẤT : {len(final_master_2col):,}")
    print(f" - DOANH NGHIỆP CÓ EMAIL B2B (Dòng 1..{len(master_with_email)}): {len(master_with_email):,}")
    print(f" - DOANH NGHIỆP CHƯA CÓ EMAIL (Dòng {len(master_with_email)+1}..{len(final_master_2col)}): {len(master_without_email):,}")
    print(f" - File Cold Mail 20 cột đã tạo           : {comb_2col_path.name}")
    print(f" - File RAW 20 cột đã tạo                 : {comb_raw_path.name}")
    print(f" - Đã đồng bộ sang csdl_mlt               : {csdl_path}")
    print(f" - Đã lưu trữ sang archive                : {archive_2col_path}")
    print("=" * 80)

if __name__ == '__main__':
    consolidate_norway_agriculture()
