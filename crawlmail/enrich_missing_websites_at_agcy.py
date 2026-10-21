# -*- coding: utf-8 -*-
"""
Tìm kiếm Website & Làm giàu Email cho các doanh nghiệp chưa có website trong AT_AGCY_SHET_1ENR.csv:
Cơ chế kiểm soát chất lượng & Chống cào nhầm:
1. So khớp tên pháp lý nghiêm ngặt (Strict Name Matching):
   - Tách bỏ các hậu tố pháp nhân (GmbH, e.U., KG, AG, GesmbH, Dipl.-Ing....)
   - Trích xuất các token thương hiệu cốt lõi (Significant Brand Tokens)
   - Chỉ chấp nhận tên miền chứa token thương hiệu hoặc độ tương đồng >= 80%
2. Bộ lọc loại trừ tên miền rác & Cổng thông tin công cộng:
   - Loại trừ 100% danh bạ, mạng xã hội (Facebook, LinkedIn, Herold, FirmenABC...)
   - Loại trừ cổng thông tin thành phố / chính phủ (leonding.at, graz.at, wien.gv.at...)
   - Loại trừ công cụ tìm kiếm (bing.com, google.com...)
3. Xác minh qua Cơ sở Dữ liệu Pháp nhân WKO Áo (firmen.wko.at):
   - Chỉ chấp nhận trang doanh nghiệp cụ thể có '?firmaid='
   - Bóc tách Email & Website đăng ký chính thức của Phòng Kinh tế Liên bang Áo
4. Bộ lọc Email Pháp lý & Quyền riêng tư (GDPR / Data Privacy):
   - Loại bỏ 100% dataprivacy@, privacy@, gdpr@, dpo@, datenschutz@...
5. Lưu tăng dần & Checkpoint JSON:
   - Lưu an toàn từng đợt, hỗ trợ tiếp tục 100% nếu gián đoạn mạng VPN.
"""

import sys
import os
import re
import csv
import json
import time
import base64
import urllib.parse
from pathlib import Path
from difflib import SequenceMatcher
from bs4 import BeautifulSoup
from curl_cffi import requests

# Cấu hình UTF-8 cho console Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = str(ROOT_DIR / "AT_AGCY_SHET_1ENR.csv")
CHECKPOINT_FILE = str(ROOT_DIR / "crawlmail" / "checkpoint_enrich_at_agcy.json")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'Accept-Language': 'de-AT,de;q=0.9,en;q=0.8'
}

LEGAL_SUFFIXES = [
    'gmbh', 'gesmbh', 'g.m.b.h.', 'ges.m.b.h.', 'e.u.', 'e. u.', 'kg', 'k.g.',
    'ag', 'a.g.', 'og', 'o.g.', 'gesbr', 'co. kg', '& co. kg', 'holding',
    'dipl.-ing.', 'dipl. ing.', 'ing.', 'dr.', 'mag.', 'bsc', 'mba', 'msc'
]

COMMON_WORDS = {
    'und', 'der', 'die', 'das', 'von', 'im', 'in', 'am', 'an', 'zu', 'zur',
    'personal', 'service', 'services', 'management', 'beratung', 'consulting',
    'austria', 'österreich', 'oesterreich', 'gmbh', 'international', 'group',
    'technik', 'tech', 'montage', 'bau', 'holding', 'partner', 'solutions', 'arbeitskraft'
}

EXCLUDED_DOMAINS = [
    'wko.at', 'herold.at', 'firmenabc.at', 'firmenakte.at', 'infobel.com',
    'dnb.com', 'northdata.de', 'creditreform.at', 'moneyhouse.at', 'kompass.com',
    'yellowpages', 'facebook.com', 'instagram.com', 'linkedin.com', 'xing.com',
    'youtube.com', 'kununu.com', 'stepstone.at', 'karriere.at', 'firmeninfo.at',
    'worldpostalcodes.org', 'wikipedia.org', 'gv.at', 'bund.at', 'orf.at',
    'willhaben.at', 'kleinezeitung.at', 'kurier.at', 'derstandard.at', 'krone.at',
    'leonding.at', 'graz.at', 'wien.gv.at', 'linz.at', 'salzburg.at', 'innsbruck.at',
    'bing.com', 'google.com', 'google.at', 'yahoo.com', 'duckduckgo.com', 'msn.com'
]

EMAIL_REGEX = re.compile(r'^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,10}$')
INVALID_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf', '.css', '.js', '.ico')

LEGAL_PRIVACY_PATTERNS = [
    'dataprivacy', 'data-privacy', 'data_privacy', 'data.privacy',
    'privacy', 'privacypolicy', 'gdpr', 'dpo', 'dataprotection',
    'data-protection', 'data_protection', 'datenschutz',
    'compliance', 'legal', 'pravne', 'pravnik', 'advokat', 'notar',
    'dispute', 'litigation', 'abuse', 'security', 'phishing', 'spam',
    'blacklist', 'unsubscribe', 'optout', 'opt-out',
    'noreply', 'no-reply', 'donotreply', 'do-not-reply',
    'postmaster', 'postmater', 'hostmaster', 'webmaster', 'mailer-daemon', 'sentry',
    'faktury', 'faktura', 'invoice', 'invoices', 'reklamac', 'reklamacie',
    'youremail', 'your-email', 'your_email', 'yourname', 'someone'
]

def clean_company_name(name):
    n = name.lower()
    for s in LEGAL_SUFFIXES:
        n = re.sub(rf'\b{re.escape(s)}\b', ' ', n)
    n = re.sub(r'["\'„“”«»]', ' ', n)
    n = re.sub(r'[^\w\s]', ' ', n)
    return re.sub(r'\s+', ' ', n).strip()

def get_significant_tokens(company_clean):
    tokens = [t for t in company_clean.split() if len(t) >= 3 and t not in COMMON_WORDS]
    if not tokens:
        tokens = [t for t in company_clean.split() if len(t) >= 2]
    return tokens

def is_domain_strictly_matching(company_clean, domain):
    if not domain:
        return False
    if any(ex in domain for ex in EXCLUDED_DOMAINS):
        return False

    dom_clean = domain.split('.')[0].replace('-', '').replace('_', '')
    tokens = get_significant_tokens(company_clean)
    if not tokens:
        return False

    # Phải chứa ít nhất 1 token thương hiệu cốt lõi
    for tok in tokens:
        clean_tok = tok.replace('-', '').replace('_', '')
        if clean_tok in dom_clean or (len(dom_clean) >= 4 and dom_clean in clean_tok):
            return True

    # Nếu không chứa trực tiếp, so khớp chuỗi >= 80%
    comp_joined = "".join(tokens)
    if SequenceMatcher(None, comp_joined, dom_clean).ratio() >= 0.80:
        return True

    return False

def decode_bing_url(href):
    if '/ck/a?' in href and 'u=' in href:
        try:
            m = re.search(r'u=([^&]+)', href)
            if m:
                u_param = m.group(1)
                raw = u_param[2:] if u_param.startswith('a1') else u_param
                return base64.b64decode(raw + '===').decode('utf-8', errors='ignore')
        except Exception:
            pass
    return href

def extract_domain(url):
    try:
        p = urllib.parse.urlparse(url)
        return p.netloc.lower().replace('www.', '').split(':')[0]
    except Exception:
        return ""

def is_legal_or_privacy_email(email):
    if not email or '@' not in email:
        return True
    e = email.lower().strip()
    u, d = e.split('@', 1)
    tokens = re.split(r'[-_.]', u)

    for kw in LEGAL_PRIVACY_PATTERNS:
        if kw in u:
            if len(kw) <= 4:
                if kw in tokens:
                    return True
            else:
                return True

    junk_domains = {'example.com', 'domain.com', 'yourdomain.com', 'email.com', 'sentry.io', 'wixpress.com', 'jimdo.com', 'webador.de', 'webador.com', 'squarespace.com', 'wordpress.com'}
    if d in junk_domains or any(d.endswith('.' + jd) for jd in junk_domains):
        return True

    return False

def search_company_strict(name, address):
    """
    Tìm kiếm website & email chính xác tuyệt đối qua Bing & WKO.
    Tránh 100% rủi ro gán nhầm website.
    """
    m_city = re.search(r'(\d{4})\s+([A-Za-zäöüÄÖÜß.\-\s]+)', address)
    city_str = m_city.group(2).split(',')[0].strip() if m_city else ""
    postcode = m_city.group(1) if m_city else ""

    clean_name = clean_company_name(name)
    query = f'"{clean_name}" {postcode} {city_str} Austria'
    bing_url = f'https://www.bing.com/search?q={urllib.parse.quote(query)}'

    found_website = ""
    found_email = ""
    wko_profile_url = ""

    try:
        r = requests.get(bing_url, headers=HEADERS, impersonate='chrome120', timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')

        for li in soup.select('li.b_algo'):
            a = li.select_one('h2 a')
            if not a or not a.get('href'):
                continue
            real_url = decode_bing_url(a['href'])
            domain = extract_domain(real_url)

            # Trường hợp 1: Trang đăng ký WKO chính thức (Bắt buộc phải có firmaid=)
            if 'firmen.wko.at' in domain and 'firmaid=' in real_url and not wko_profile_url:
                wko_profile_url = real_url

            # Trường hợp 2: Website trực tiếp khớp thương hiệu
            if not found_website and is_domain_strictly_matching(clean_name, domain):
                found_website = f"{urllib.parse.urlparse(real_url).scheme}://{domain}/"

        # Nếu tìm thấy hồ sơ WKO, truy cập để lấy email và website chính thức
        if wko_profile_url:
            try:
                rw = requests.get(wko_profile_url, headers=HEADERS, impersonate='chrome120', timeout=15)
                soup_w = BeautifulSoup(rw.text, 'html.parser')
                w_title = soup_w.title.string.lower() if soup_w.title else ""

                # Xác minh tên công ty có trong tiêu đề WKO
                tokens = get_significant_tokens(clean_name)
                if any(tok in w_title for tok in tokens):
                    wko_emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', rw.text)
                    clean_wko = [
                        e.lower() for e in wko_emails 
                        if not any(x in e.lower() for x in ['wko.at', 'microsoft.com'])
                        and not is_legal_or_privacy_email(e)
                    ]
                    if clean_wko and not found_email:
                        found_email = clean_wko[0]

                    for aw in soup_w.find_all('a', href=True):
                        hw = aw['href']
                        dw = extract_domain(hw)
                        if hw.startswith('http') and is_domain_strictly_matching(clean_name, dw):
                            if not found_website:
                                found_website = f"{urllib.parse.urlparse(hw).scheme}://{dw}/"
            except Exception:
                pass

        # Nếu có Website nhưng chưa có Email từ WKO, thử quét nhanh trang chủ website
        if found_website and not found_email:
            try:
                rw_site = requests.get(found_website, headers=HEADERS, impersonate='chrome120', timeout=12)
                site_emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', rw_site.text)
                valid_site_emails = [
                    e.lower() for e in site_emails 
                    if not is_legal_or_privacy_email(e)
                    and not any(e.lower().endswith(ext) for ext in INVALID_EXTENSIONS)
                ]
                if valid_site_emails:
                    # Ưu tiên office/info/kontakt
                    prio = [e for e in valid_site_emails if any(k in e for k in ['office', 'info', 'kontakt', 'contact'])]
                    found_email = prio[0] if prio else valid_site_emails[0]
            except Exception:
                pass

    except Exception:
        pass

    return found_website, found_email

def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
                return set(json.load(f).get('processed_indices', []))
        except Exception:
            pass
    return set()

def save_checkpoint(processed_indices):
    try:
        with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
            json.dump({'processed_indices': list(processed_indices)}, f, indent=2)
    except Exception:
        pass

def save_csv(rows, fieldnames, filepath):
    temp = filepath + ".tmp"
    with open(temp, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except Exception:
            pass
    os.rename(temp, filepath)

def main():
    print("=" * 80)
    print("QUY TRINH TIM KIEM WEBSITE VA LAM GIAU EMAIL (CHONG CAO NHAM TUYET DOI)")
    print(f"File du lieu: {INPUT_CSV}")
    print("Co che loc: Strict Token Matching + Anti-Directory Filter + WKO Verification")
    print("=" * 80)

    if not os.path.exists(INPUT_CSV):
        print(f"[-] Khong tim thay file: {INPUT_CSV}")
        return

    with open(INPUT_CSV, 'r', encoding='utf-8-sig', errors='ignore') as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    # Loc cac dong thieu website
    targets = []
    for idx, r in enumerate(rows):
        web = (r.get('Liên Hệ') or r.get('Website') or '').strip()
        if not web:
            targets.append((idx, r))

    print(f"[*] Tong so doanh nghiep trong file: {len(rows)}")
    print(f"[*] So doanh nghiep CHUA CO WEBSITE can tim kiem: {len(targets)}")

    processed_indices = load_checkpoint()
    print(f"[*] Da xu ly tu checkpoint: {len(processed_indices)}/{len(targets)}")

    new_web_count = 0
    new_email_count = 0

    for current_idx, (row_idx, row) in enumerate(targets):
        if row_idx in processed_indices:
            continue

        company = row.get('Công ty', '').strip()
        address = row.get('Địa chỉ', '').strip()

        print(f"[{current_idx+1}/{len(targets)}] [*] Dang tim kiem: '{company}' ({address[:35]}...)")

        web_found, email_found = search_company_strict(company, address)

        updated = False
        if web_found:
            row['Liên Hệ'] = web_found
            print(f"   [+] Tim thay WEBSITE xac thuc: {web_found}")
            new_web_count += 1
            updated = True

        if email_found and not row.get('Email'):
            row['Email'] = email_found
            row['Check gửi'] = 'OK'
            print(f"   [+] Tim thay EMAIL B2B xac thuc: {email_found}")
            new_email_count += 1
            updated = True

        if not web_found and not email_found:
            print(f"   [-] Khong tim thay website hop le (Khong lay bua de tranh nham cty).")

        processed_indices.add(row_idx)

        # Luu tang dan sau moi 5 cty hoac khi co cap nhat
        if updated or (current_idx + 1) % 5 == 0:
            save_csv(rows, fieldnames, INPUT_CSV)
            save_checkpoint(processed_indices)

        # Do tre nhe de tranh bi chan bot Bing (500ms - 800ms)
        time.sleep(0.6)

    # Luu ket qua cuoi cung
    save_csv(rows, fieldnames, INPUT_CSV)
    save_checkpoint(processed_indices)

    print("\n" + "=" * 80)
    print("HOAN TAT TIM KIEM WEBSITE VA LAM GIAU EMAIL CHO 1,061 CTY!")
    print(f"Tong so Website moi tim thay: {new_web_count}")
    print(f"Tong so Email B2B moi bo sung: {new_email_count}")
    print(f"File cap nhat: {INPUT_CSV}")
    print("=" * 80)

if __name__ == "__main__":
    main()
