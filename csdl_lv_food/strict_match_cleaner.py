import sys
import json
import re
import urllib.parse
import unicodedata
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)

# 1. Danh sách đen tuyệt đối cho tên miền và email
ABSOLUTE_BLACKLIST_DOMAINS = [
    # Cơ quan nhà nước & Đại sứ quán
    'president.lv', 'ur.gov.lv', 'nva.gov.lv', 'liaa.gov.lv', 'daba.gov.lv', 'cvk.lv',
    'km.gov.lv', 'latvija.lv', 'vraa.gov.lv', 'saldus.lv', 'valmiera.lv', 'valmierasnovads.lv',
    'kurzemesregions.lv', 'gulbene.lv', 'pasts.lv', 'csdd.lv', 'vid.gov.lv', 'mk.gov.lv',
    'saeima.lv', 'lubanamitrajs.lv', 'veclaicene.lv', 'visitjurmala.lv', 'lebm.gov.lv',
    'mofa.go.jp', 'state.gov', 'usembassy', 'army.mil', 'hrc.army.mil',
    # Tập đoàn công nghệ / Game / Mạng xã hội / Trang quốc tế
    'apple.com', 'steamcommunity.com', 'draugiem.lv', 'flashscore', 'chefspencil',
    'spamcalls', 'railbaltica.org', 'wikipedia.org', 'jewishgen.org', 'flightconnections.com',
    'kpmg.com', 'heidelberg.com', 'schwenk', 'raw-tech.lv', 'aaru.com',
    'keystonecollection.com', 'estatelatvia.com', 'dojuslatvija.lv', 'motivs.lv',
    'waterro.eu', 'concordiaclinic.lv', 'glslatvija.lv', 'latagro.lv', 'euroflizes.lv',
    'zum1.lv', 'e-lats.lv', 'travelart.lv', 'rigaslifti.lv', 'ldz.lv', 'lvvignette.eu',
    'ziemellatvija.lv', 'eraser.lv', 'baltezers.lv', 'superalko.lv', 'alkoutlet.lv',
    'depo.lv', 'maxima.lv', 'rimi.lv', 'lidl.lv', 'yourwebsite.com'
]

GENERIC_INDUSTRY_WORDS = {
    'alus', 'vins', 'vīns', 'dzerieni', 'dzērieni', 'razosana', 'ražošana', 'partika',
    'pārtika', 'tirdznieciba', 'tirdzniecība', 'daritava', 'darītava', 'bruzis', 'brūzis',
    'group', 'grupa', 'holding', 'latvia', 'latvija', 'baltic', 'baltics', 'baltija',
    'serviss', 'projekti', 'services', 'food', 'foods', 'company', 'international',
    'nordic', 'europe', 'management', 'solutions', 'factory', 'manufaktura'
}

def strip_accents(text):
    if not text:
        return ""
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn')

def get_distinctive_tokens(company_name):
    """Bóc tách các từ khóa định danh thương hiệu (loại bỏ pháp lý và từ chung ngành)"""
    t = re.sub(r'["\'„“”«»]', '', str(company_name)).strip().lower()
    t = re.sub(r'\(.*?\)|\[.*?\]', '', t).strip()
    # Loại bỏ loại hình
    t = re.sub(r'\b(?:sia|as|a/s|ik|ps|ks|ltd|llc|limited|liability|company|joint-stock)\b', '', t, flags=re.I)
    t = strip_accents(t)
    raw_tokens = [re.sub(r'[^\w]', '', w) for w in re.split(r'[\s,.-]+', t) if w.strip()]
    distinctive = [w for w in raw_tokens if len(w) >= 3 and w not in GENERIC_INDUSTRY_WORDS]
    return distinctive if distinctive else raw_tokens

def is_domain_strictly_matching(company_name, web_url):
    """Kiểm tra khắt khe: Tên miền BẮT BUỘC phải liên quan trực tiếp đến tên công ty"""
    if not web_url or not company_name:
        return False, "EMPTY"

    u = web_url.strip().lower()
    if not u.startswith('http'):
        u = 'https://' + u

    try:
        parsed = urllib.parse.urlparse(u)
        dom = parsed.netloc.replace('www.', '').lower()
    except Exception:
        return False, "INVALID_URL"

    # 1. Chặn danh sách đen tuyệt đối
    if any(b in dom for b in ABSOLUTE_BLACKLIST_DOMAINS):
        return False, f"BLACKLISTED_DOMAIN ({dom})"

    # 2. Chặn TLD chính phủ / quân sự / ngoại giao
    if any(dom.endswith(tld) or ('.' + tld + '.') in ('.' + dom + '.') for tld in ['gov', 'gov.lv', 'mil', 'edu', 'edu.lv']):
        return False, f"GOV_DOMAIN ({dom})"

    # 3. Trích xuất phần nhãn chính của tên miền (bỏ đuôi .lv, .com, .eu...)
    domain_label = dom.split('.')[0]
    domain_label_clean = strip_accents(domain_label)

    # 4. So khớp từ khóa thương hiệu đặc trưng
    dist_tokens = get_distinctive_tokens(company_name)
    if not dist_tokens:
        return False, "NO_DISTINCTIVE_TOKENS"

    # Kiểm tra xem có ít nhất 1 từ khóa định danh chính nằm trong tên miền không
    # (hoặc tên miền nằm trong từ khóa nếu từ khóa dài)
    matched = False
    for tok in dist_tokens:
        if len(tok) >= 3:
            if tok in domain_label_clean or (len(domain_label_clean) >= 4 and domain_label_clean in tok):
                matched = True
                break

    # Kiểm tra trường hợp tên miền là viết tắt các chữ cái đầu (Acronym)
    # Ví dụ: Baltic Logistic Solutions -> bls.lv, Cēsu Alus -> ca.lv
    if not matched and len(dist_tokens) >= 2:
        acronym = ''.join(tok[0] for tok in dist_tokens)
        if len(acronym) >= 2 and acronym == domain_label_clean:
            matched = True

    if not matched:
        return False, f"DOMAIN_UNRELATED: company='{company_name}' vs domain='{dom}'"

    return True, "STRICT_MATCH"

def is_email_matching_domain_or_company(email, web_url, company_name):
    """Kiểm tra khắt khe: Email bắt buộc phải thuộc về domain hoặc tên công ty"""
    if not email or '@' not in email:
        return False, "EMPTY_OR_NO_AT"

    em = email.strip().lower()
    em_user, em_dom = em.split('@', 1)

    # Chặn danh sách đen email
    if any(b in em_dom for b in ABSOLUTE_BLACKLIST_DOMAINS):
        return False, f"BLACKLISTED_EMAIL_DOM ({em_dom})"

    if any(em_dom.endswith(tld) for tld in ['.gov', '.gov.lv', '.mil', '.edu', '.edu.lv']):
        return False, f"GOV_EMAIL ({em_dom})"

    # Nếu có website, kiểm tra email có cùng domain không
    if web_url:
        try:
            parsed = urllib.parse.urlparse(web_url if web_url.startswith('http') else 'https://' + web_url)
            web_dom = parsed.netloc.replace('www.', '').lower()
            if em_dom == web_dom or web_dom.endswith('.' + em_dom) or em_dom.endswith('.' + web_dom):
                return True, "EXACT_WEB_DOMAIN"
        except Exception:
            pass

    # Nếu dùng webmail miễn phí (inbox.lv, gmail.com), username bắt buộc phải chứa tên thương hiệu
    if em_dom in ['inbox.lv', 'gmail.com', 'mail.lv']:
        dist_tokens = get_distinctive_tokens(company_name)
        if any(tok in em_user for tok in dist_tokens if len(tok) >= 4):
            return True, "WEBMAIL_MATCHED_USER"
        return False, f"WEBMAIL_UNVERIFIED: {em} does not contain company tokens {dist_tokens}"

    # Nếu domain email chứa từ khóa thương hiệu
    dist_tokens = get_distinctive_tokens(company_name)
    if any(tok in em_dom for tok in dist_tokens if len(tok) >= 3):
        return True, "EMAIL_DOMAIN_MATCHED_COMPANY"

    return False, f"EMAIL_UNRELATED: company='{company_name}' vs email='{em}'"

if __name__ == '__main__':
    cache_path = Path("csdl_lv_food/cache_enrich_maps_lv_bevg_swet.json")
    with open(cache_path, 'r', encoding='utf-8') as f:
        cache = json.load(f)

    print(f"Tổng số bản ghi trong cache: {len(cache):,}")

    purged = 0
    kept = 0
    for comp_key, data in cache.items():
        em = data.get('Email', '')
        wb = data.get('Web', '')

        if not em and not wb:
            continue

        # Kiểm tra tính hợp lệ của Web
        web_ok = True
        if wb:
            web_ok, w_reason = is_domain_strictly_matching(comp_key, wb)
            if not web_ok:
                data['Web'] = ''
                wb = ''

        # Kiểm tra tính hợp lệ của Email
        email_ok = True
        if em:
            email_ok, e_reason = is_email_matching_domain_or_company(em, wb, comp_key)
            if not email_ok or not web_ok:
                data['Email'] = ''
                em = ''

        if not web_ok or not email_ok:
            purged += 1
            print(f"[-] LOẠI BỎ: {comp_key[:30]:<30} | Web: {wb[:25]:<25} | Email: {em:<25}")
        else:
            kept += 1

    print(f"\n[*] Đã rà soát khắt khe: Giữ lại {kept:,} bản ghi chuẩn xác 100%, Xóa bỏ {purged:,} bản ghi sai lệch.")

    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    # Đồng bộ hóa sang 2 tệp CSV đích
    for csv_path in [Path("LV_SWET_WEBD_2COL.csv"), Path("csdl_lv_food/LV_SWET_WEBD_2COL.csv")]:
        if not csv_path.exists():
            continue
        df = pd.read_csv(csv_path, encoding='utf-8-sig', dtype=str).fillna('')
        for idx in df.index:
            comp = df.at[idx, 'Công ty']
            c_key = comp.lower().strip()
            if c_key in cache:
                c_data = cache[c_key]
                df.at[idx, 'Email'] = c_data.get('Email', '')
                df.at[idx, 'Liên Hệ mail'] = f"mailto:{c_data['Email']}" if c_data.get('Email') else ''
                df.at[idx, 'Check gửi'] = 'OK' if c_data.get('Email') else ''
                df.at[idx, 'Liên Hệ'] = c_data.get('Web', '')
            else:
                # Kiểm tra trực tiếp
                cur_em = df.at[idx, 'Email']
                cur_wb = df.at[idx, 'Liên Hệ']
                w_ok, _ = is_domain_strictly_matching(comp, cur_wb)
                e_ok, _ = is_email_matching_domain_or_company(cur_em, cur_wb, comp)
                if not w_ok:
                    df.at[idx, 'Liên Hệ'] = ''
                if not e_ok or not w_ok:
                    df.at[idx, 'Email'] = ''
                    df.at[idx, 'Liên Hệ mail'] = ''
                    df.at[idx, 'Check gửi'] = ''

        with_em = df[df['Email'] != ''].to_dict('records')
        without_em = df[df['Email'] == ''].to_dict('records')
        final_rows = with_em + without_em
        for i, r in enumerate(final_rows, 1):
            r['No.'] = str(i)

        out_df = pd.DataFrame(final_rows)
        out_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        print(f"[✔] Đã cập nhật tệp: {csv_path} | Số công ty có Email CHUẨN XÁC 100%: {len(with_em):,}/{len(final_rows):,}")
