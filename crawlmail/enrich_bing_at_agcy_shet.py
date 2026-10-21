# -*- coding: utf-8 -*-
"""
Bing Search & Deep Web Enrichment for AT_AGCY_SHET_0RAW.csv:
1. Giai phap VPN Resilient: Timeout 25s, co che Retry 3 lan voi Exponential Backoff chong lag mang.
2. SO KHOP TEN NGHIEM NGAT 3 TANG (Strict 3-Layer Matching) - CHONG 100% LUU NHAM DATA:
   - Tang 1: Loc bo triet de 100% domain danh ba, dang ky kinh doanh, so vang, mang xa hoi.
   - Tang 2: So khop Thuong hieu trong Domain (Brand Token Match) hoac So khop Tieu de (Strict Title Match).
   - Tang 3: Xac thuc On-Page / Impressum: Bat buoc trang chu hoac Impressum phai chua ten phap ly hoac tu khoa nganh nghe cua cong ty.
3. Quet website tim Email B2B va So dien thoai (tel:):
   - Uu tien the <a> thuc te tren DOM menu (Priority 10: /kontakt, /impressum, /ueber-uns, /karriere, /jobs...).
   - Doan mo ban dia Ao/Duc (Priority 2) sau khi het link DOM.
   - Giai ma Cloudflare data-cfemail, mailto:, regex obfuscation.
   - Cham diem B2B tuyen chon 1 email co gia tri nhat (HR/Tuyen dung, Ban giam doc, Cong lien he chinh thuc).
   - Boc tach So dien thoai qua href="tel:" (luon co dau nhay don ' o dau).
4. Luu tang dan (Incremental Auto-Save) sau moi cong ty va Cache Checkpoint JSON (Resume 100%).
5. Tep xuat chuan: AT_AGCY_SHET_1ENR.csv.
"""

import sys
import os
import re
import csv
import json
import time
import base64
import asyncio
import urllib.parse
from pathlib import Path
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

# Cau hinh UTF-8 cho console Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = str(ROOT_DIR / "AT_AGCY_SHET_0RAW.csv")
OUTPUT_CSV = str(ROOT_DIR / "AT_AGCY_SHET_1ENR.csv")
BACKUP_CSV = str(ROOT_DIR / "AT_AGCY_SHET_0RAW_backup.csv")
CACHE_FILE = str(ROOT_DIR / "crawlmail" / "cache_enrich_bing_at_agcy_shet.json")

# Danh sach hau to loai hinh doanh nghiep Ao (Austria Legal Forms)
LEGAL_FORMS_AT = [
    'gesellschaft mit beschränkter haftung', 'gesellschaft mit beschrankter haftung',
    'gmbh & co. kg', 'gmbh & co kg', 'gmbh & co.kg', 'gmbh & co',
    'gesellschaft m.b.h.', 'gesellschaft mbh', 'ges.m.b.h.', 'gesmbh', 'ges. mbh',
    'gmbh', 'g.m.b.h.',
    'aktiengesellschaft', 'ag', 'a.g.',
    'offene gesellschaft', 'og', 'o.g.',
    'kommanditgesellschaft', 'kg', 'k.g.',
    'eingetragenes einzelunternehmen', 'eingetragene unternehmerin', 'e.u.', 'eu',
    'societas europaea', 'se',
    'genossenschaft', 'egen', 'e.gen.',
    'holding', 'group', 'gruppe'
]

# Bo loc tu khoa loai tru domain danh ba / dang ky kinh doanh / review / mang xa hoi
EXCLUDED_KEYWORDS = [
    'firmen', 'branche', 'directory', 'verzeichnis', 'katalog', 'register',
    'yellowpages', 'gelbeseiten', 'wko.at', 'herold', 'docfinder', 'karriere',
    'stepstone', 'monster', 'willhaben', 'tripadvisor', 'evi.gv', 'northdata',
    'creditreform', 'wirtschaft', 'unternehmen24', 'infobel', 'facebook',
    'linkedin', 'instagram', 'twitter', 'x.com', 'youtube', 'tiktok', 'pinterest',
    'wikipedia', 'google', 'bing.com', 'ksv.at', 'austrialisting', 'austriayp',
    'firmania', 'blitzblank', 'advantageaustria', 'kununu', 'xing.com', 'whocallsme',
    'tellows', 'justizonline', 'firmensicht', 'austrian-registers', 'edikte.justiz',
    'opencorporates', 'cybo.com', 'kompass', 'cylex', 'tupalo', 'webwiki', 'unilocal'
]

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Z|a-z]{2,10}\b')
INVALID_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf', '.css', '.js', '.ico', '.woff', '.woff2', '.mp4', '.mp3', '.ttf')

OBFUSCATED_PATTERNS = [
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s*\[at\]\s*([A-Za-z0-9.-]{1,255})\s*\[dot\]\s*([A-Za-z]{2,7})', re.IGNORECASE),
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s*\(at\)\s*([A-Za-z0-9.-]{1,255})\s*\(dot\)\s*([A-Za-z]{2,7})', re.IGNORECASE),
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s+AT\s+([A-Za-z0-9.-]{1,255})\s+DOT\s+([A-Za-z]{2,7})'),
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s*(?:@|\[at\]|\(at\))\s*([A-Za-z0-9.-]+\.[A-Za-z]{2,7})', re.IGNORECASE),
]

JUNK_EMAIL_DOMAINS = {
    'facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com', 'youtube.com',
    'wix.com', 'wixsite.com', 'wordpress.com', 'squarespace.com', 'weebly.com',
    'godaddy.com', 'example.com', 'domain.com', 'placeholder.com', 'wixpress.com',
    'sentry.io', 'sentry.wixpress.com', 'schema.org', 'trustpilot.com', 'google.com',
    'yourcompany.com', 'yourdomain.com', 'email.com', 'mail.com'
}

SYSTEM_USERNAMES = {
    'noreply', 'no-reply', 'donotreply', 'privacy', 'terms', 'cookies', 'gdpr',
    'abuse', 'security', 'webmaster', 'sentry', 'mailer-daemon', 'test', 'example',
    'youremail', 'your-email', 'yourname', 'your-name', 'someone', 'john.doe', 'user'
}

DOMAIN_CACHE = {}

def clean_company_name_at(name):
    if not name:
        return ""
    n = re.sub(r'["\'„“”«»]', '', str(name)).strip().lower()
    for lf in sorted(LEGAL_FORMS_AT, key=len, reverse=True):
        n = re.sub(rf'\b{re.escape(lf)}\b', '', n)
    n = re.sub(r'[^\w\s]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n

def decode_bing_url(href):
    """Giai ma link redirect b_algo cua Bing ve URL that voi base64 padding chuan."""
    if not href:
        return ""
    if '/ck/a?' in href:
        try:
            p = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            u = p.get('u', [''])[0]
            if u.startswith('a1'):
                b64 = u[2:]
                padding = (4 - len(b64) % 4) % 4
                padded_b64 = b64 + '=' * padding
                return base64.urlsafe_b64decode(padded_b64.encode('ascii')).decode('utf-8', errors='ignore')
        except Exception:
            return ""
    return href

def decode_cloudflare_email(cf_hex):
    try:
        r = int(cf_hex[:2], 16)
        email = ''.join([chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2)])
        return email.strip().lower()
    except Exception:
        return ""

def score_email_b2b(email, website_domain=""):
    if not email or not isinstance(email, str):
        return -1
    e = email.strip().lower()
    if not EMAIL_REGEX.match(e):
        return -1
    if any(e.endswith(ext) for ext in INVALID_EXTENSIONS):
        return -1

    parts = e.split('@')
    if len(parts) != 2:
        return -1
    u, d = parts[0], parts[1]

    if d in JUNK_EMAIL_DOMAINS or any(d.endswith('.' + jd) for jd in JUNK_EMAIL_DOMAINS):
        return -1
    if u in SYSTEM_USERNAMES:
        return -1
    if any(k in u for k in ['youremail', 'your-email', 'yourname', 'your-name', 'someone', 'john.doe']):
        return -1
    if u in ['email', 'mail'] and d in ['email.com', 'mail.com', 'domain.com', 'company.com']:
        return -1

    score = 10

    # Trung domain website (+50d)
    clean_domain = website_domain.lower().replace('www.', '').split('/')[0] if website_domain else ""
    if clean_domain and (clean_domain in d or d in clean_domain):
        score += 50
    elif d.endswith('.at'):
        score += 20
    elif d.endswith('.de') or d.endswith('.eu'):
        score += 10

    # UU TIEN SO 1: Bo phan Nhan su / Tuyen dung (+50d)
    hr_keywords = [
        'karriere', 'jobs', 'bewerbung', 'recruiting', 'recruitment', 'hr', 'personal',
        'personalne', 'praca', 'talent', 'people', 'career', 'careers', 'hiring'
    ]
    if any(u == k or u.startswith(k) for k in hr_keywords):
        score += 50
    # UU TIEN SO 2: Ban Giam Doc / Lanh dao (+45d)
    elif any(u == k or u.startswith(k) for k in ['geschaeftsfuehrung', 'leitung', 'ceo', 'director', 'manager', 'vertrieb', 'sales', 'management', 'inhaber', 'vorstand']):
        score += 45
    # UU TIEN SO 3: Cong lien he chinh thuc (+40d)
    elif any(u == k or u.startswith(k) for k in ['office', 'kontakt', 'contact', 'info', 'zentrale', 'empfang', 'sekretariat', 'kaufmaennisch', 'mail', 'post']):
        score += 40
    # Email ca nhan theo domain rieng (+25d)
    elif '.' in u and score >= 60:
        score += 25
    # Webmail mien phi (+10d)
    elif d in ['gmail.com', 'gmx.at', 'aon.at', 'chello.at', 'web.de', 'yahoo.com']:
        score += 10
    # Email ky thuat / ke toan (+5d)
    elif any(u == k or u.startswith(k) for k in ['support', 'admin', 'hilfe', 'service', 'buchhaltung', 'rechnung', 'faktury']):
        score += 5

    return score

def select_best_email(found_emails, website_domain=""):
    valid_emails = [e for e in set(found_emails) if score_email_b2b(e, website_domain) > 0]
    if not valid_emails:
        return ""
    return max(valid_emails, key=lambda e: score_email_b2b(e, website_domain))

async def fetch_html_with_retry(url, session, retries=2, timeout=25):
    """
    Tai HTML voi Timeout 25s va Retry 2-3 lan chong rot mang khi dung VPN.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'de-AT,de;q=0.9,en;q=0.8'
    }
    for attempt in range(retries + 1):
        try:
            resp = await session.get(url, headers=headers, impersonate="chrome120", timeout=timeout, verify=False)
            if resp.status_code == 200:
                return resp.text
        except Exception:
            if attempt < retries:
                await asyncio.sleep(2.0 * (attempt + 1))
    return ""

def extract_emails_and_phones_from_html(html_text, website_domain=None):
    if not html_text:
        return set(), ""
    found_emails = set()
    found_phone = ""

    # 1. Cloudflare decode
    for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', html_text):
        dec = decode_cloudflare_email(cf)
        if score_email_b2b(dec, website_domain) > 0:
            found_emails.add(dec)

    # 2. mailto: links (loai bo %20 va query)
    for m in re.findall(r'href=["\']mailto:\s*([^"\'?#\s]+)', html_text, re.IGNORECASE):
        clean_m = urllib.parse.unquote(m).replace('%20', '').strip().lower().rstrip('.,;:')
        if score_email_b2b(clean_m, website_domain) > 0:
            found_emails.add(clean_m)

    # 3. Regex standard
    for m in EMAIL_REGEX.findall(html_text):
        clean_m = m.strip().lower().rstrip('.,;:')
        if score_email_b2b(clean_m, website_domain) > 0:
            found_emails.add(clean_m)

    # 4. Obfuscated
    for pat in OBFUSCATED_PATTERNS:
        for match in pat.findall(html_text):
            if len(match) == 3:
                rec = f"{match[0]}@{match[1]}.{match[2]}".lower()
            elif len(match) == 2:
                rec = f"{match[0]}@{match[1]}".lower()
            else:
                continue
            if score_email_b2b(rec, website_domain) > 0:
                found_emails.add(rec)

    # 5. Tel: link for Phone
    tel_matches = re.findall(r'href=["\']tel:\s*([^"\'?#\s]+)', html_text, re.IGNORECASE)
    if tel_matches:
        raw_p = urllib.parse.unquote(tel_matches[0]).strip()
        p_clean = re.sub(r'[^\d+]', '', raw_p)
        if p_clean and len(p_clean) >= 7:
            found_phone = f"'{p_clean}"

    return found_emails, found_phone

async def verify_onpage_authenticity(base_url, company_name, session):
    """
    XAC THUC ON-PAGE (TANG 3):
    Truy cap trang chu hoac /impressum de kiem tra xem website co thuc su
    nhac den ten cong ty hoac tu khoa thuong hieu hay khong.
    Chong 100% truong hop luu nham web cua cong ty khac co trung tu khoa pho bien.
    """
    q_clean = clean_company_name_at(company_name)
    tokens = [t for t in q_clean.split() if len(t) >= 3 and t not in ['und', 'der', 'die', 'das', 'fur', 'für', 'service', 'austria']]

    # Kiem tra Trang chu
    home_html = await fetch_html_with_retry(base_url, session, retries=1, timeout=20)
    if home_html:
        home_lower = home_html.lower()
        if q_clean in home_lower or company_name.lower() in home_lower:
            return True, "HOME_FULL_NAME_MATCH", home_html

        # Kiem tra neu tat ca cac tu khoa dac trung xuat hien tren trang
        if tokens and all(t in home_lower for t in tokens):
            return True, "HOME_TOKENS_MATCH", home_html

    # Kiem tra trang Impressum (luat Ao bat buoc moi web doanh nghiep deu phai ghi ten phap ly tai Impressum)
    impressum_url = urllib.parse.urljoin(base_url, "/impressum")
    imp_html = await fetch_html_with_retry(impressum_url, session, retries=1, timeout=20)
    if imp_html:
        imp_lower = imp_html.lower()
        if q_clean in imp_lower or company_name.lower() in imp_lower:
            return True, "IMPRESSUM_FULL_NAME_MATCH", home_html or imp_html
        if tokens and all(t in imp_lower for t in tokens):
            return True, "IMPRESSUM_TOKENS_MATCH", home_html or imp_html

    return False, "ONPAGE_VERIFICATION_FAILED", home_html

async def search_bing_for_website(company_name, session):
    """
    Tim website chinh chu qua Bing Search voi SO KHOP TEN 3 TANG:
    Tang 1: Loai bo domain danh ba.
    Tang 2: So khop tieu de / domain brand.
    Tang 3: Xac thuc on-page Impressum / Title.
    """
    clean_name = re.sub(r'["\'„“”«»]', '', company_name).strip()
    query = f'{clean_name} Austria'
    search_url = f'https://www.bing.com/search?q={urllib.parse.quote_plus(query)}'

    html_content = await fetch_html_with_retry(search_url, session, retries=2, timeout=25)
    if not html_content:
        return "", "BING_NETWORK_TIMEOUT", ""

    q_clean = clean_company_name_at(company_name)
    tokens = [t for t in q_clean.split() if len(t) >= 3 and t not in ['und', 'der', 'die', 'das', 'fur', 'für', 'service', 'austria']]
    brand_compact = q_clean.replace(' ', '')

    soup = BeautifulSoup(html_content, 'html.parser')
    for li in soup.select('li.b_algo'):
        h2_a = li.select_one('h2 a')
        if not h2_a:
            continue

        candidate_title = h2_a.get_text().strip()
        raw_href = h2_a.get('href')
        real_url = decode_bing_url(raw_href)

        if not real_url or not real_url.startswith(('http://', 'https://')):
            continue

        parsed = urllib.parse.urlparse(real_url)
        domain = parsed.netloc.lower().replace('www.', '')

        # TANG 1: Loai bo triet de 100% domain danh ba / dang ky kinh doanh
        if not domain or any(k in domain for k in EXCLUDED_KEYWORDS):
            continue

        # TANG 2: So khop Tieu de & Domain Token
        t_clean = clean_company_name_at(candidate_title)
        d_clean = domain.replace('-', '').replace('.', '')

        pre_matched = False
        pre_match_type = ""

        # 2a. Tieu de chua ten cong ty
        if q_clean in t_clean:
            pre_matched = True
            pre_match_type = "TITLE_EXACT"
        elif any(clean_company_name_at(p) == q_clean for p in re.split(r'[-–—|/:,]', candidate_title) if p.strip()):
            pre_matched = True
            pre_match_type = "TITLE_DELIMITER"
        # 2b. Domain chua thuong hieu
        elif len(brand_compact) >= 4 and brand_compact in d_clean:
            pre_matched = True
            pre_match_type = "DOMAIN_BRAND"
        elif len(tokens) >= 2 and all(t in d_clean for t in tokens[:2]):
            pre_matched = True
            pre_match_type = "DOMAIN_TOKENS"
        elif len(tokens) == 1 and len(tokens[0]) >= 4 and tokens[0] in d_clean:
            pre_matched = True
            pre_match_type = "DOMAIN_SINGLE_TOKEN"

        if not pre_matched:
            continue

        # TANG 3: XAC THUC ON-PAGE / IMPRESSUM TRUOC KHI CHAP NHAN
        base_site = f"{parsed.scheme}://{parsed.netloc}/"
        verified, ver_reason, site_html = await verify_onpage_authenticity(base_site, company_name, session)

        if verified:
            return base_site, f"{pre_match_type}+{ver_reason}", site_html
        else:
            # Thu muc tiep theo trong ket qua Bing
            continue

    return "", "NO_AUTHENTIC_MATCH", ""

async def crawl_website_for_contacts(website_url, company_name, session, preloaded_html=""):
    if not website_url or not website_url.startswith(('http://', 'https://')):
        return "", "", ""

    parsed = urllib.parse.urlparse(website_url)
    domain = parsed.netloc.lower().replace('www.', '')

    if domain in DOMAIN_CACHE:
        c = DOMAIN_CACHE[domain]
        return c.get("email", ""), c.get("phone", ""), c.get("facebook", "")

    all_emails = set()
    best_phone = ""
    fb_link = ""

    # Trang chu (tai su dung preloaded_html neu co)
    home_html = preloaded_html or await fetch_html_with_retry(website_url, session, retries=2, timeout=25)
    if home_html:
        emails, phone = extract_emails_and_phones_from_html(home_html, domain)
        all_emails.update(emails)
        if phone:
            best_phone = phone

    # Priority 10: Tim link that tren Menu / DOM Trang Chu
    candidate_links = []
    if home_html:
        try:
            soup = BeautifulSoup(home_html, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = a['href'].strip()
                text = (a.get_text() or "").strip().lower()
                href_lower = href.lower()

                # Facebook
                if not fb_link and any(fb in href_lower for fb in ['facebook.com/', 'fb.com/']):
                    if not any(x in href_lower for x in ['sharer', 'share.php', 'plugins', 'intent', 'dialog']):
                        clean_fb = href.split('?')[0].rstrip('/')
                        if len(clean_fb.split('/')) > 3:
                            fb_link = clean_fb

                full_url = urllib.parse.urljoin(website_url, href)
                parsed_cand = urllib.parse.urlparse(full_url)
                if parsed_cand.netloc.replace('www.', '') == domain:
                    clean_cand = full_url.split('#')[0]
                    priority = 1
                    if any(k in text or k in href_lower for k in [
                        'kontakt', 'impressum', 'karriere', 'jobs', 'bewerbung',
                        'ueber-uns', 'wir-ueber-uns', 'anfahrt', 'team', 'standort', 'contact'
                    ]):
                        priority = 10
                    elif any(k in text or k in href_lower for k in ['about', 'uber-uns', 'service']):
                        priority = 5
                    candidate_links.append((priority, clean_cand))
        except Exception:
            pass

    # Priority 2: Guess paths
    parsed_base = urllib.parse.urlparse(website_url)
    base_origin = f"{parsed_base.scheme}://{parsed_base.netloc}"
    guess_paths = [
        '/kontakt', '/kontakt.html', '/kontakt.php',
        '/impressum', '/impressum.html', '/impressum.php',
        '/karriere', '/karriere.html', '/jobs',
        '/ueber-uns', '/ueber-uns.html', '/contact'
    ]
    for gp in guess_paths:
        candidate_links.append((2, base_origin + gp))

    candidate_links.sort(key=lambda x: x[0], reverse=True)
    unique_sub_urls = []
    for prio, sub_url in candidate_links:
        clean_sub = sub_url.rstrip('/')
        if clean_sub not in [u.rstrip('/') for u in unique_sub_urls] and clean_sub != website_url.rstrip('/'):
            unique_sub_urls.append(sub_url)

    # Quet toi da 8 subpages
    for sub_url in unique_sub_urls[:8]:
        sub_html = await fetch_html_with_retry(sub_url, session, retries=1, timeout=20)
        if not sub_html:
            continue
        sub_emails, sub_phone = extract_emails_and_phones_from_html(sub_html, domain)
        all_emails.update(sub_emails)
        if not best_phone and sub_phone:
            best_phone = sub_phone

        best_cand = select_best_email(all_emails, domain)
        if best_cand and score_email_b2b(best_cand, domain) >= 60:
            break

    # Fallback Facebook
    best_email = select_best_email(all_emails, domain)
    if not best_email and fb_link:
        fb_about = fb_link + "/about"
        fb_html = await fetch_html_with_retry(fb_about, session, retries=1, timeout=20)
        if fb_html:
            fb_emails, _ = extract_emails_and_phones_from_html(fb_html, domain)
            all_emails.update(fb_emails)
            best_email = select_best_email(all_emails, domain)

    DOMAIN_CACHE[domain] = {"email": best_email, "phone": best_phone, "facebook": fb_link}
    return best_email, best_phone, fb_link

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
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

async def main():
    if not os.path.exists(INPUT_CSV):
        print(f"[-] Khong tim thay {INPUT_CSV}")
        return

    import shutil
    if not os.path.exists(BACKUP_CSV):
        shutil.copy2(INPUT_CSV, BACKUP_CSV)
        print(f"[*] Da sao luu {INPUT_CSV} sang {BACKUP_CSV}")

    cache = load_cache()

    read_file = OUTPUT_CSV if os.path.exists(OUTPUT_CSV) else INPUT_CSV
    print(f"[*] Dang doc du lieu tu: {read_file}")

    with open(read_file, 'r', encoding='utf-8-sig', errors='ignore') as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    for r in rows:
        p = r.get("SĐT", "").strip()
        if p and not p.startswith("'"):
            r["SĐT"] = f"'{p}"

    total_rows = len(rows)
    print("=" * 80)
    print("LAM GIAU DU LIEU BING SEARCH & DEEP WEB (3-LAYER STRICT MATCHING & VPN RESILIENT)")
    print(f"Tong so doanh nghiep: {total_rows}")
    print(f"Tep xuat: {OUTPUT_CSV}")
    print("=" * 80)

    session = AsyncSession(verify=False)

    enriched_count = 0
    for idx, row in enumerate(rows):
        company = row.get("Công ty", "").strip()
        curr_phone = row.get("SĐT", "").strip()
        curr_web = row.get("Liên Hệ", "").strip()
        curr_email = row.get("Email", "").strip()

        needs_phone = not curr_phone
        needs_web = not curr_web
        needs_email = not curr_email

        if not needs_phone and not needs_web and not needs_email:
            continue

        print(f"\n[{idx+1}/{total_rows}] [*] Doanh nghiep: '{company}'")

        updated = False
        preloaded_html = ""

        # Buoc 1: Neu thieu Website -> Tra cuu Bing Search voi So khop nghiem ngat 3 tang
        if needs_web:
            cache_key = company.upper()
            cached_item = cache.get(cache_key)

            if cached_item is None:
                print(f"    [*] Dang tra cuu Bing Search & Kiem tra so khop 3 tang...")
                found_site, match_type, preloaded_html = await search_bing_for_website(company, session)
                cache[cache_key] = {"url": found_site, "match_type": match_type}
                save_cache(cache)
                await asyncio.sleep(0.5)
            else:
                found_site = cached_item.get("url", "")
                match_type = cached_item.get("match_type", "")

            if found_site:
                row["Liên Hệ"] = found_site
                print(f"       [+] Website xac thuc thanh cong ({match_type}): {found_site}")
                updated = True
                curr_web = found_site
                needs_web = False
            else:
                print(f"       [-] Khong tim thay website nao so khop chinh xac ({match_type}).")

        # Buoc 2: Neu co Website va con thieu Email hoac Phone -> Quet Website
        effective_web = row.get("Liên Hệ", "").strip()
        if effective_web and (needs_email or needs_phone):
            print(f"    [*] Dang quet Website tim Email/Phone: {effective_web}...")
            found_email, found_phone, fb = await crawl_website_for_contacts(effective_web, company, session, preloaded_html)

            if needs_email and found_email:
                row["Email"] = found_email
                print(f"       [+] B2B Email tim thay: {found_email}")
                updated = True

            if needs_phone and found_phone:
                row["SĐT"] = found_phone
                print(f"       [+] SĐT tim thay: {found_phone}")
                updated = True

        if updated:
            enriched_count += 1
            save_csv(rows, fieldnames, OUTPUT_CSV)
            print(f"    [+] CAP NHAT THANH CONG!")
        else:
            print(f"    [-] Khong co du lieu moi.")

        if (idx + 1) % 5 == 0:
            save_csv(rows, fieldnames, OUTPUT_CSV)

    await session.close()

    save_csv(rows, fieldnames, OUTPUT_CSV)
    print("\n" + "=" * 80)
    print("HOAN TAT LAM GIAU DU LIEU QUA BING SEARCH & DEEP WEB!")
    print(f"Tong so doanh nghiep duoc bo sung thong tin: {enriched_count}")
    print(f"Tep xuat: {OUTPUT_CSV}")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
