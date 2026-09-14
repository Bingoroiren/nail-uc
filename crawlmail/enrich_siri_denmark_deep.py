import os
import sys
import re
import csv
import json
import time
import shutil
import asyncio
import base64
import urllib.parse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# Ensure UTF-8 on Windows console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Paths
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_CSV = os.path.join(WORKSPACE_DIR, "(11_9) SIRI Certified companies Denmark - Trang tính1.csv")
BACKUP_CSV = os.path.join(WORKSPACE_DIR, "(11_9) SIRI Certified companies Denmark - Trang tính1.backup.csv")
OUTPUT_CSV = os.path.join(WORKSPACE_DIR, "đanmạchFT.csv")
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache_siri_denmark_deep.json")
USER_DATA_DIR = os.path.join(WORKSPACE_DIR, "chrome_user_data", "siri_denmark_profile")

# Standard Cold Mail Output Columns (20 standard + 1 Link FB = 21 columns)
STANDARD_FIELDNAMES = [
    'No.', 'Cong ty', 'Chuc danh', 'Nguoi lien he', 'SDT',
    'Lien He', 'Email', 'Lien He mail', 'Dia chi', 'Luong',
    'Ngay dang', 'Han tuyen', 'Check gui', 'Last Subject',
    'Last Body HTML', 'Trang thai Reply', 'Lan Follow-up',
    'Ngay Follow-up gan nhat', 'Mailbox da dung', 'Category',
    'Link FB'
]

# Regex patterns
EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,10}\b')
OBFUSCATED_PATTERNS = [
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s*\[at\]\s*([A-Za-z0-9.-]{1,255})\s*\[dot\]\s*([A-Za-z]{2,7})', re.IGNORECASE),
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s*\(at\)\s*([A-Za-z0-9.-]{1,255})\s*\(dot\)\s*([A-Za-z]{2,7})', re.IGNORECASE),
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s+AT\s+([A-Za-z0-9.-]{1,255})\s+DOT\s+([A-Za-z]{2,7})', re.IGNORECASE),
]

INVALID_EXTENSIONS = (
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.avif',
    '.pdf', '.css', '.js', '.ico', '.woff', '.woff2', '.mp4', '.mp3', '.ttf', '.eot'
)

# Aggregators / Directories (NOT official company websites)
AGGREGATOR_DOMAINS = {
    'cvr.dk', 'datacvr.virk.dk', 'virk.dk', 'proff.dk', 'biq.dk', 'krak.dk', 'degulesider.dk',
    'eniro.dk', '118.dk', 'find-aabenraa.dk', 'dnb.com', 'kompass.com', 'zoominfo.com',
    'yellowpages.dk', 'yellowpages.com', 'yelp.dk', 'yelp.com', 'trustpilot.com', 'dk.trustpilot.com',
    'facebook.com', 'instagram.com', 'twitter.com', 'x.com', 'linkedin.com', 'youtube.com',
    'tiktok.com', 'pinterest.com', 'wikipedia.org', 'google.com', 'bing.com', 'duckduckgo.com',
    'glassdoor.com', 'indeed.com', 'jobindex.dk', 'ofir.dk', 'stepstone.dk', 'workindenmark.dk',
    'opencorporates.com', 'b2bhint.com', 'cybo.com', 'infobel.com', 'firmania.dk',
    'tripadvisor.dk', 'tripadvisor.com', 'booking.com', 'airbnb.com', 'hotels.com',
    'selskabsinfo.dk', 'datanyze.com', 'leadiq.com', 'lusha.com', 'apollo.io',
    'yahoo-net.jp', 'yahoo.co.jp', 'ramp.directory', 'prodenmark.com', 'feve.org'
}

# Junk email domains & third-party widgets / placeholders
JUNK_EMAIL_DOMAINS = {
    # Cookie / CMP & Privacy widgets (như Cookie Information, Cookiebot, OneTrust...)
    'cookieinformation.com', 'cookieinformation.dk', 'cookiebot.com', 'cybot.com',
    'onetrust.com', 'usercentrics.com', 'usercentrics.eu', 'termly.io',
    'iubenda.com', 'trustarc.com', 'complianz.io', 'civicuk.com', 'quantcast.com',
    'didomi.io', 'didomi.com', 'osano.com', 'securiti.ai', 'kunden.de',
    # B2B Lead / Directory aggregators
    'datanyze.com', 'leadiq.com', 'zoominfo.com', 'lusha.com', 'apollo.io',
    'rocketreach.co', 'signalhire.com', 'selskabsinfo.dk', 'proff.dk', 'krak.dk',
    'biq.dk', 'cvr.dk', 'virk.dk', 'degulesider.dk', 'dnb.com', 'kompass.com',
    'yellowpages.dk', 'yellowpages.com', 'yelp.dk', 'yelp.com', 'trustpilot.com',
    'opencorporates.com', 'b2bhint.com', 'cybo.com', 'infobel.com', 'firmania.dk',
    'uni2study.com', 'prodenmark.com', 'feve.org',
    # Templates, Demo, Dummy & Placeholders
    'acmecorporation.com', 'example.com', 'example.org', 'example.net', 'example.dk',
    'domain.com', 'yourdomain.com', 'yoursite.com', 'mycompany.com', 'company.com',
    'companyname.com', 'placeholder.com', 'test.com', 'sample.com', 'email.com',
    'mail.com', 'themetrust.com', 'templatemonster.com', 'themeforest.net', 'envato.com',
    'wixpress.com', 'wix.com', 'squarespace.com', 'weebly.com', 'shopify.com',
    'sentry.io', 'sentry-next.wixpress.com', 'sentry.wixpress.com', 'webador.com', 'one.com',
    'godaddy.com', 'wordpress.com', 'bluepillow.com', 'booking.com', 'tripadvisor.com',
    'google.com', 'facebook.com', 'instagram.com', 'schema.org', 'w3.org'
}

JUNK_PREFIXES = {
    'noreply', 'no-reply', 'donotreply', 'privacy', 'terms', 'cookies', 'cookie',
    'gdpr', 'abuse', 'security', 'webmaster', 'sentry', 'mailer-daemon',
    'postmaster', 'example', 'muster', 'dpo', 'test', 'dataprotection',
    'dataprotectionoffice', 'datenschutz', 'kundeservice-noreply'
}

PREFERRED_USERNAMES = {
    'info', 'kontakt', 'contact', 'kontor', 'mail', 'post', 'office',
    'salg', 'sales', 'support', 'service', 'job', 'hr', 'karriere', 'career',
    'kundeservice', 'admin', 'ordre', 'order', 'hovedkontor'
}

DANISH_LEGAL_SUFFIXES = [
    r'\ba/s\b', r'\baps\b', r'\bi/s\b', r'\bk/s\b', r'\bp/s\b',
    r'\bs\.m\.b\.a\.\b', r'\bsmba\b', r'\ba\.m\.b\.a\.\b', r'\bamba\b',
    r'\bf\.m\.b\.a\.\b', r'\bfmba\b', r'\bholding\b', r'\bgroup\b',
    r'\bdenmark\b', r'\bdanmark\b', r'\bdk\b', r'\baktielselskab\b',
    r'\banpartsselskab\b', r'\bfilial\b'
]

def clean_phone_dk(phone_str):
    if not phone_str:
        return ""
    s = str(phone_str).strip().lstrip("'").strip()
    s = re.split(r'\b(ext|x|extension|tlf|tlf\.|telefon)\b', s, flags=re.IGNORECASE)[0].strip()
    digits = re.sub(r'[^0-9]', '', s)
    if not digits:
        return ""
    if digits.startswith("0045"):
        clean = f"+{digits[2:]}"
    elif digits.startswith("45") and len(digits) == 10:
        clean = f"+{digits}"
    elif len(digits) == 8:
        clean = f"+45{digits}"
    elif digits.startswith("45") and len(digits) > 10:
        clean = f"+{digits[:10]}"
    else:
        clean = f"+{digits}"
    return f"'{clean}"

def clean_single_email(raw_email):
    """
    Cleans raw email string:
    - Decodes URL percent-encoding (%20, %0A, %0D, etc.)
    - Removes whitespace and leftover %20 tokens
    - Strips prefixes like mailto:, u003e, <, >, quotes
    - Validates proper email format
    """
    if not raw_email:
        return ""
    
    # 1. Decode URL percent-encoding
    s = str(raw_email).strip()
    try:
        s = urllib.parse.unquote(s)
    except Exception:
        pass

    # 2. Strip standard prefixes & leftover URL tokens like %20
    for prefix in ['mailto:', 'u003e', 'u003c', '&lt;', '&gt;', ':', ' ']:
        if s.lower().startswith(prefix):
            s = s[len(prefix):].strip()

    # Specifically clean %20 in case it was not unquoted or present as literal
    s = s.replace('%20', '').replace('%2520', '').replace(' ', '').replace('\t', '').replace('\r', '').replace('\n', '').strip()
    s = s.strip("'\"<>[](),;")

    if '@' not in s:
        return ""

    parts = s.split('@')
    if len(parts) != 2:
        return ""
    local_part, domain = parts[0].strip().lower(), parts[1].strip().lower()

    local_part = re.sub(r'^[^\w]+|[^\w]+$', '', local_part)
    domain = re.sub(r'^[^\w]+|[^\w]+$', '', domain)

    if not local_part or not domain or '.' not in domain:
        return ""

    if any(domain.endswith(ext) for ext in INVALID_EXTENSIONS):
        return ""

    # Loại bỏ chuỗi phiên bản package (như alpinejs@3.14.8, htmx.org@2.0.4)
    if re.search(r'@\d+\.\d+', s) or re.search(r'\.\d+$', domain):
        return ""
    if any(domain.endswith('.' + ext) for ext in ['js', 'ts', 'css', 'json', 'map', 'min', 'esm', 'mjs']):
        return ""

    clean_email = f"{local_part}@{domain}"
    if not EMAIL_REGEX.match(clean_email):
        return ""

    # Check junk usernames and domains
    if any(jp in local_part for jp in JUNK_PREFIXES):
        return ""

    for jd in JUNK_EMAIL_DOMAINS:
        if domain == jd or domain.endswith('.' + jd):
            return ""

    return clean_email

def decode_cloudflare_email(hex_str):
    try:
        hex_data = bytes.fromhex(hex_str)
        key = hex_data[0]
        dec = ''.join(chr(b ^ key) for b in hex_data[1:]).strip().lower()
        return clean_single_email(dec)
    except Exception:
        return ""

def clean_fb_link(href):
    if not href:
        return ""
    h = href.strip()
    hl = h.lower()
    if 'facebook.com' in hl or 'fb.me' in hl:
        # Exclude system, policy, share, help and dialog pages
        if any(x in hl for x in [
            'sharer', 'share.php', 'plugins', 'dialog', 'tr?', 'photo.php', 'video.php',
            '/sharer.php', 'facebook.com/share', 'facebook.com/events', 'facebook.com/privacy',
            'facebook.com/policies', 'facebook.com/legal', 'facebook.com/help', 'facebook.com/terms',
            'facebook.com/login', 'facebook.com/signup', 'facebook.com/pages/create'
        ]):
            return ""
        parsed = urllib.parse.urlparse(h)
        clean_path = parsed.path.rstrip('/')
        if clean_path in ['', '/', '/home.php', '/login.php', '/privacy', '/policies', '/help']:
            return ""
        return f"https://www.facebook.com{clean_path}"
    return ""

def normalize_phrase(p: str) -> str:
    """Normalizes company name, stripping Danish corporate suffixes and punctuation."""
    if not p:
        return ""
    p = p.lower()
    for s in DANISH_LEGAL_SUFFIXES:
        p = re.sub(s, ' ', p, flags=re.IGNORECASE)
    p = re.sub(r'[^a-z0-9æøå\s]', ' ', p)
    return ' '.join(p.split())

def is_valid_name_match(company_name: str, candidate_title: str) -> tuple:
    """
    Quy tắc lọc theo yêu cầu:
    1. So khớp tên gốc và tên hiển thị trên map không phân biệt hoa thường.
    2. Tên trên map phải giống hệt tên gốc. Nếu tên trên map có từ mà tên gốc không có thì loại bỏ,
       TRỪ KHI:
       - Các cụm đó nằm hoàn toàn trong ngoặc (...) hoặc [...]
       - Hoặc nằm sau các dấu gạch ngang / phân tách (-, –, —, |, /, :, •)
       - Hoặc tên gốc nằm hoàn toàn trong ngoặc không chứa từ lạ.
    """
    if not candidate_title or not company_name:
        return False, "Tên rỗng"

    comp_norm = normalize_phrase(company_name)
    title_norm = normalize_phrase(candidate_title)

    # 1. Trùng khớp hoàn toàn 100%
    if comp_norm == title_norm:
        return True, "Khớp y đúc 100% (bỏ qua hoa thường)"

    comp_words = set(comp_norm.split())
    title_words = set(title_norm.split())

    # 2. Trường hợp tên trên map là tập con của tên gốc (không chứa bất kỳ từ lạ nào)
    # Ví dụ: Map: 'A+ Siam Sushi', Gốc: 'A+ Siam Sushi Restaurant ApS'
    diff_words = title_words - comp_words
    if not diff_words and len(title_words) >= 1:
        if title_norm in comp_norm or any(len(w) >= 3 for w in title_words):
            return True, "Hợp lệ: Tên trên map là tập con của tên gốc (không chứa từ lạ nào)"

    # 3. Tên gốc nằm trong tên trên map, kiểm tra các từ thừa
    title_no_brackets = re.sub(r'\([^\)]*\)', '', candidate_title)
    title_no_brackets = re.sub(r'\[[^\]]*\]', '', title_no_brackets)

    parts = re.split(r'[-–—|/:\•·]', title_no_brackets)
    for part in parts:
        part_norm = normalize_phrase(part)
        part_words = set(part_norm.split())
        if part_norm == comp_norm:
            return True, "Hợp lệ: Chứa cụm y đúc, từ thừa nằm sau dấu gạch ngang hoặc trong ngoặc"
        if not (part_words - comp_words) and len(part_words) >= 1:
            if part_norm in comp_norm:
                return True, "Hợp lệ: Phần trước/sau gạch ngang không chứa từ lạ nào"

    if normalize_phrase(title_no_brackets) == comp_norm:
        return True, "Hợp lệ: Chứa cụm y đúc, từ thừa nằm trọn trong ngoặc"

    brackets_content = re.findall(r'\(([^\)]*)\)|\[([^\]]*)\]', candidate_title)
    for b_tuple in brackets_content:
        b_str = b_tuple[0] or b_tuple[1]
        if normalize_phrase(b_str) == comp_norm:
            return True, "Hợp lệ: Tên gốc nằm hoàn toàn trong ngoặc của tên trên Map"

    return False, f"Có từ lạ ({diff_words}) không nằm trong ngoặc hoặc dấu gạch ngang"

def extract_clean_domain(url):
    if not url:
        return ""
    u = url.strip()
    if not u.startswith(('http://', 'https://')):
        u = 'https://' + u
    try:
        parsed = urllib.parse.urlparse(u)
        netloc = parsed.netloc.lower()
        if netloc.startswith('www.'):
            netloc = netloc[4:]
        return netloc.split(':')[0].strip()
    except Exception:
        return ""

def is_platform_or_aggregator(domain):
    if not domain:
        return True
    d = domain.lower()
    for agg in AGGREGATOR_DOMAINS:
        if d == agg or d.endswith('.' + agg):
            return True
    return False

def decode_bing_url(bing_href):
    """Giải mã URL đích từ liên kết chuyển hướng của Bing"""
    if not bing_href:
        return ""
    if 'bing.com/ck/a?' in bing_href:
        try:
            parsed = urllib.parse.urlparse(bing_href)
            params = urllib.parse.parse_qs(parsed.query)
            if 'u' in params:
                u_val = params['u'][0]
                if u_val.startswith('a1'):
                    b64_str = u_val[2:]
                    b64_str += '=' * ((4 - len(b64_str) % 4) % 4)
                    return base64.b64decode(b64_str).decode('utf-8', errors='ignore')
        except Exception:
            pass
    return bing_href

def extract_sld(domain_or_url):
    """Trích xuất tên miền gốc (Second-Level Domain) bỏ qua subdomain và TLD"""
    if not domain_or_url:
        return ""
    d = domain_or_url.strip().lower()
    if '://' in d:
        try:
            d = urllib.parse.urlparse(d).netloc
        except Exception:
            pass
    if d.startswith('www.'):
        d = d[4:]
    d = d.split(':')[0]
    parts = d.split('.')
    if len(parts) >= 2:
        if len(parts) >= 3 and parts[-2] in ['co', 'com', 'org', 'net', 'edu', 'gov']:
            return parts[-3]
        return parts[-2]
    return parts[0]

def extract_brand_tokens(company_name):
    """Trích xuất các từ khóa thương hiệu chính từ tên công ty (bỏ qua hậu tố pháp lý)"""
    if not company_name:
        return set()
    p = company_name.lower()
    for s in DANISH_LEGAL_SUFFIXES:
        p = re.sub(s, ' ', p, flags=re.IGNORECASE)
    p = re.sub(r'[^a-z0-9æøå\s]', ' ', p)
    tokens = {w for w in p.split() if len(w) >= 3}
    return tokens

def score_email(email, site_url="", company_name=""):
    """
    Hệ thống chấm điểm email thông minh:
    - Ưu tiên cao nhất cho email trùng thương hiệu/tên công ty (như dinex@dinex.dk)
    - Nhận diện email theo tên miền website (kể cả khác đuôi .net vs .dk)
    - Loại bỏ triệt để (0 điểm) các email từ bên thứ 3 (như cookieinformation, sentry, widgets, acme demo)
    """
    if not email:
        return 0
    clean = clean_single_email(email)
    if not clean:
        return 0
    username, domain = clean.split('@', 1)
    site_sld = extract_sld(site_url)
    email_sld = extract_sld(domain)
    brand_tokens = extract_brand_tokens(company_name)

    # 1. Kiểm tra blacklist tên miền và username
    for jd in JUNK_EMAIL_DOMAINS:
        if domain == jd or domain.endswith('.' + jd) or email_sld == extract_sld(jd):
            return 0
    if any(jp in username for jp in JUNK_PREFIXES):
        return 0

    # 2. Khớp tuyệt đối thương hiệu công ty (Tier 1: 200 - 250 điểm)
    # Ví dụ: Dinex A/S -> dinex@dinex.dk trên trang dinex.net
    is_same_brand_domain = (site_sld and email_sld == site_sld) or (email_sld in brand_tokens)
    is_brand_username = any(b in username for b in brand_tokens)

    if is_same_brand_domain:
        if is_brand_username:  # Ví dụ: dinex@dinex.dk
            return 250
        if username in PREFERRED_USERNAMES:  # Ví dụ: info@dinex.dk, kontakt@dinex.net
            return 230
        return 200

    # 3. Khớp một phần tên thương hiệu (Tier 2: 150 - 180 điểm)
    # Ví dụ: bms-hc.com vs bms, delegate-group.com vs delegate
    is_partial_brand = (site_sld and (site_sld in email_sld or email_sld in site_sld)) or any(b in email_sld for b in brand_tokens)
    if is_partial_brand:
        if username in PREFERRED_USERNAMES or is_brand_username:
            return 180
        return 150

    # 4. Trùng toàn bộ domain của site
    clean_site_domain = extract_clean_domain(site_url)
    if clean_site_domain and (domain == clean_site_domain or domain.endswith('.' + clean_site_domain)):
        if username in PREFERRED_USERNAMES:
            return 140
        return 120

    # 5. Webmail công cộng (Gmail, Outlook...)
    if domain in {'gmail.com', 'hotmail.com', 'yahoo.com', 'outlook.com', 'icloud.com', 'live.com'}:
        if is_brand_username or username in PREFERRED_USERNAMES:
            return 50
        return 35

    # 6. Tên miền bên thứ 3 hoàn toàn không liên quan (Tier 6: 0 điểm - BỎ QUA)
    # Tránh tuyệt đối việc cào nhầm widget cookie, analytics, ad networks, case study
    return 0

async def check_and_wait_if_verify(page, context_name="Trang web"):
    """Phát hiện nếu bị bắt verify/captcha/robot và tạm dừng để người dùng xử lý trực tiếp trên màn hình"""
    try:
        is_verify = await page.evaluate("""() => {
            const bodyText = (document.body ? document.body.innerText : '').toLowerCase();
            const hasCaptcha = !!document.querySelector('iframe[src*="recaptcha"], iframe[src*="captcha"], #captcha, .g-recaptcha, #challenge-running, #cf-challenge-running, div[id*="captcha"], div[class*="captcha"]');
            const keywords = [
                'jeg er ikke en robot', "i'm not a robot", 'unusual traffic', 
                'bekræft, at du er et menneske', 'please verify', 'roboter', 
                'automated queries', 'verify you are human', 'challenge'
            ];
            return hasCaptcha || keywords.some(k => bodyText.includes(k));
        }""")
        if is_verify:
            print(f"\n   🛑 [{context_name}] PHÁT HIỆN YÊU CẦU XÁC MINH (VERIFY/CAPTCHA)!")
            print(f"      👉 Vui lòng giải CAPTCHA trên cửa sổ trình duyệt Chrome...")
            for _ in range(60):  # Chờ tối đa 90 giây
                await page.wait_for_timeout(1500)
                still_verify = await page.evaluate("""() => {
                    const bodyText = (document.body ? document.body.innerText : '').toLowerCase();
                    const hasCaptcha = !!document.querySelector('iframe[src*="recaptcha"], iframe[src*="captcha"], #captcha, .g-recaptcha, #challenge-running, #cf-challenge-running, div[id*="captcha"], div[class*="captcha"]');
                    const keywords = [
                        'jeg er ikke en robot', "i'm not a robot", 'unusual traffic', 
                        'bekræft, at du er et menneske', 'please verify', 'roboter', 
                        'automated queries', 'verify you are human', 'challenge'
                    ];
                    return hasCaptcha || keywords.some(k => bodyText.includes(k));
                }""")
                if not still_verify:
                    print(f"      ✅ Đã xác minh xong! Tự động tiếp tục quét...\n")
                    await page.wait_for_timeout(2000)
                    break
    except Exception:
        pass

async def lookup_on_google_maps(page, company_name: str, address: str = "") -> dict:
    """Tra cứu trên Google Maps với quy tắc lọc tên nghiêm ngặt"""
    clean_name = re.sub(r'\([^\)]*\)', '', company_name).strip()
    query = f"{clean_name} Denmark"
    encoded = urllib.parse.quote(query)
    maps_url = f"https://www.google.com/maps/search/{encoded}"

    result = {"phone": "", "website": "", "maps_title": "", "address": "", "is_match": False, "match_reason": ""}

    try:
        await page.goto(maps_url, wait_until="domcontentloaded", timeout=25000)
        await check_and_wait_if_verify(page, "Google Maps")
        try:
            await page.wait_for_selector("h1, a.hfpxzc", timeout=6000)
        except Exception:
            pass
        await page.wait_for_timeout(2000)

        # Chấp nhận cookie Google nếu có
        await page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('button, a'));
            for (const b of btns) {
                const txt = (b.innerText || b.getAttribute('aria-label') || '').toLowerCase();
                if (txt.includes('accept all') || txt.includes('godkend alle') || txt.includes('alle akzeptieren') || txt.includes('i agree')) {
                    b.click();
                    break;
                }
            }
        }""")
        await page.wait_for_timeout(1000)

        # 1. Kiểm tra nếu Google Maps mở trực tiếp 1 địa điểm duy nhất (H1 hiển thị tên)
        h1_texts = await page.locator("h1.DUwDvf, h1").all_text_contents()
        direct_title = ""
        for t in h1_texts:
            t_clean = t.strip()
            if t_clean and t_clean.lower() not in ['results', 'kết quả', 'resultater', 'google maps', 'search']:
                direct_title = t_clean
                break

        target_matched = False
        if direct_title:
            ok, reason = is_valid_name_match(company_name, direct_title)
            if ok:
                target_matched = True
                result["is_match"] = True
                result["maps_title"] = direct_title
                result["match_reason"] = reason

        # 2. Nếu không phải địa điểm duy nhất, kiểm tra danh sách kết quả (Feed Cards)
        if not target_matched:
            cards = await page.locator("a.hfpxzc, a[href*='/maps/place/']").all()
            if cards:
                for idx, c in enumerate(cards[:6]):
                    aria = (await c.get_attribute("aria-label") or "").strip()
                    if not aria:
                        continue
                    ok, reason = is_valid_name_match(company_name, aria)
                    if ok:
                        target_matched = True
                        result["is_match"] = True
                        result["maps_title"] = aria
                        result["match_reason"] = reason
                        # Click mở thẻ địa điểm
                        try:
                            await c.click()
                            try:
                                await page.wait_for_selector('a[data-item-id*="authority"], button[data-item-id*="phone"]', timeout=5000)
                            except Exception:
                                pass
                            await page.wait_for_timeout(1500)
                        except Exception:
                            pass
                        break

        # Trích xuất thông tin khi đã tìm thấy địa điểm khớp
        if target_matched:
            details = await page.evaluate("""() => {
                let website = "";
                let phone = "";
                let address = "";

                const webEl = document.querySelector('a[data-item-id*="authority"]');
                if (webEl) {
                    website = webEl.href || webEl.getAttribute('href') || "";
                }

                const phoneEl = document.querySelector('button[data-item-id*="phone"]');
                if (phoneEl) {
                    phone = (phoneEl.innerText || phoneEl.getAttribute('aria-label') || '').replace(/^Telefon:\s*|^Phone:\s*/i, '').trim();
                }

                const addrEl = document.querySelector('button[data-item-id*="address"]');
                if (addrEl) {
                    address = (addrEl.innerText || addrEl.getAttribute('aria-label') || '').replace(/^Adresse:\s*|^Address:\s*/i, '').trim();
                }

                return { website: website, phone: phone, address: address };
            }""")

            result["website"] = details.get("website", "")
            result["phone"] = clean_phone_dk(details.get("phone", ""))
            result["address"] = details.get("address", "")

    except Exception as e:
        result["match_reason"] = f"Lỗi Maps: {e}"

    return result

async def lookup_on_web_search(page, company_name: str) -> str:
    """Tìm kiếm website chính thức qua Bing Search khi Google Maps không có kết quả"""
    clean_name = re.sub(r'\([^\)]*\)', '', company_name).strip()
    query = f"{clean_name} Denmark website"
    
    try:
        bing_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
        await page.goto(bing_url, wait_until="domcontentloaded", timeout=20000)
        await check_and_wait_if_verify(page, "Bing Search")
        await page.wait_for_timeout(2000)

        # Lấy danh sách kết quả tìm kiếm
        results = await page.evaluate("""() => {
            const items = [];
            const cards = Array.from(document.querySelectorAll('li.b_algo'));
            for (const c of cards) {
                const a = c.querySelector('h2 a, a');
                if (a && a.href) {
                    items.push({
                        title: a.innerText.trim(),
                        href: a.href
                    });
                }
            }
            return items;
        }""")

        for r in results:
            raw_href = r.get('href', '')
            decoded_url = decode_bing_url(raw_href)
            title = r.get('title', '')
            domain = extract_clean_domain(decoded_url)

            if not domain or is_platform_or_aggregator(domain):
                continue

            # Kiểm tra tiêu đề kết quả hoặc tên miền với quy tắc so khớp
            ok, _ = is_valid_name_match(company_name, title)
            norm_c = normalize_phrase(company_name).replace(' ', '')
            domain_flat = domain.replace('.', '').replace('-', '')
            if ok or (norm_c and len(norm_c) >= 4 and norm_c in domain_flat):
                parsed = urllib.parse.urlparse(decoded_url)
                netloc = parsed.netloc
                # Nếu là subdomain phụ như chat., app., login. thì chuyển về main domain
                parts = netloc.split('.')
                if len(parts) >= 3 and parts[0] in ['chat', 'app', 'login', 'webmail', 'portal']:
                    netloc = '.'.join(parts[1:])
                return f"{parsed.scheme}://{netloc}"

    except Exception as e:
        print(f"      [Bing Search Error]: {e}")

    return ""

async def deep_crawl_website(page, website_url: str, company_name: str = "") -> tuple:
    """
    Quét sâu website bao gồm trang chủ và các subpage contact/about:
    - Trích xuất email từ HTML, JS, mailto, Cloudflare (lọc bỏ triệt để %20, rác và bên thứ 3)
    - Trích xuất SĐT
    - Trích xuất Link Fanpage Facebook
    """
    if not website_url or not website_url.startswith('http'):
        if website_url.startswith('www.'):
            website_url = 'https://' + website_url
        else:
            return "", "", ""

    found_emails = set()
    found_phones = set()
    fb_link = ""
    scanned_urls = set()
    site_domain = extract_clean_domain(website_url)

    def extract_from_html_content(html_text):
        nonlocal fb_link
        emails = set()
        phones = set()

        if not html_text:
            return emails, phones

        # 1. Cloudflare emails
        for cf in re.findall(r'data-cfemail="([0-9a-fA-F]+)"', html_text):
            dec = decode_cloudflare_email(cf)
            if dec:
                emails.add(dec)

        # 2. Mailto links
        for m in re.findall(r'href=[\'"]mailto:([^\'"\s>]+)', html_text, re.I):
            clean_m = clean_single_email(m)
            if clean_m:
                emails.add(clean_m)

        # 3. Regex Email trong HTML & JavaScript
        for em in EMAIL_REGEX.findall(html_text):
            clean_em = clean_single_email(em)
            if clean_em:
                emails.add(clean_em)

        # 4. Obfuscated emails [at] [dot]
        for pat in OBFUSCATED_PATTERNS:
            for m in pat.finditer(html_text):
                em_dec = f"{m.group(1)}@{m.group(2)}.{m.group(3)}"
                clean_em = clean_single_email(em_dec)
                if clean_em:
                    emails.add(clean_em)

        # 5. SĐT tel:
        for tel in re.findall(r'href=[\'"]tel:([^\'"\s>]+)', html_text, re.I):
            cp = clean_phone_dk(tel)
            if cp:
                phones.add(cp)

        # 6. Link Facebook Fanpage
        if not fb_link:
            try:
                soup = BeautifulSoup(html_text, 'html.parser')
                for a in soup.find_all('a', href=True):
                    candidate_fb = clean_fb_link(a['href'])
                    if candidate_fb:
                        fb_link = candidate_fb
                        break
            except Exception:
                pass

        return emails, phones

    # Quét trang chủ
    try:
        await page.goto(website_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000)
        scanned_urls.add(website_url)

        home_html = await page.content()
        em, ph = extract_from_html_content(home_html)
        found_emails.update(em)
        found_phones.update(ph)

        # Trích xuất SĐT từ text hiển thị thực tế trên body (tránh regex nhầm số timestamp trong file CSS/JS)
        body_phones = await page.evaluate("""() => {
            const text = document.body ? document.body.innerText : '';
            const matches = text.match(/(?:\\+45\\s*|0045\\s*)?[2-9][0-9\\s]{7,11}[0-9]/g) || [];
            return matches.map(m => m.trim());
        }""")
        for bp in body_phones:
            cp = clean_phone_dk(bp)
            if cp:
                found_phones.add(cp)

        # Trích xuất các liên kết trang liên hệ (từ thẻ <a> và thẻ <select option value>)
        subpage_candidates = await page.evaluate("""() => {
            const links = [];
            document.querySelectorAll('a[href]').forEach(a => links.push({ text: a.innerText || '', href: a.getAttribute('href') || '' }));
            document.querySelectorAll('select option[value]').forEach(opt => links.push({ text: opt.innerText || '', href: opt.getAttribute('value') || '' }));

            const res = [];
            const keywords = ['kontakt', 'contact', 'om-os', 'about', 'kundeservice', 'find-os', 'kontakt-os', 'restaurant', 'info', 'om', 'afdeling'];
            const hostParts = window.location.hostname.split('.');
            const baseRoot = hostParts.length >= 2 ? hostParts.slice(-2).join('.') : window.location.hostname;

            for (const l of links) {
                const href = l.href;
                const text = (l.text || '').toLowerCase();
                const hLower = href.toLowerCase();
                if (!href || hLower.startsWith('mailto:') || hLower.startsWith('tel:') || hLower.startsWith('javascript:')) continue;
                try {
                    const full = new URL(href, window.location.origin).href;
                    const fullHost = new URL(full).hostname;
                    if (fullHost === window.location.hostname || fullHost.endsWith('.' + baseRoot)) {
                        if (keywords.some(k => text.includes(k) || hLower.includes(k))) {
                            if (!res.includes(full)) res.push(full);
                        } else if (fullHost !== window.location.hostname && !res.includes(full)) {
                            // Subdomain nội bộ (như restaurant.aplussiamsushi.dk)
                            res.push(full);
                        }
                    }
                } catch(e) {}
            }
            return res.slice(0, 4);
        }""")

        # Nếu trang chủ chưa tìm thấy email và chưa có subpage, thêm các subpage đoán chuẩn
        if not found_emails and not subpage_candidates:
            parsed_root = urllib.parse.urlparse(website_url)
            base_origin = f"{parsed_root.scheme}://{parsed_root.netloc}"
            for p_guess in ['/kontakt', '/contact', '/om-os']:
                subpage_candidates.append(base_origin + p_guess)

        # Quét các trang con liên hệ
        for sub_url in subpage_candidates[:3]:
            if sub_url in scanned_urls:
                continue
            scanned_urls.add(sub_url)
            try:
                await page.goto(sub_url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(1500)
                sub_html = await page.content()
                sub_em, sub_ph = extract_from_html_content(sub_html)
                found_emails.update(sub_em)
                found_phones.update(sub_ph)
                if any(score_email(e, website_url, company_name) >= 150 for e in found_emails):
                    break
            except Exception:
                pass

    except Exception as e:
        pass

    # Chọn email tốt nhất theo điểm số
    best_email = ""
    if found_emails:
        scored = [(score_email(e, website_url, company_name), e) for e in found_emails if score_email(e, website_url, company_name) > 0]
        scored.sort(key=lambda x: (x[0], -len(x[1])), reverse=True)
        if scored:
            best_email = scored[0][1]

    best_phone = list(found_phones)[0] if found_phones else ""
    return best_email, best_phone, fb_link

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache_data):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def export_coldmail_csv(all_rows):
    """Ghi dữ liệu ra tệp đanmạchFT.csv theo chuẩn 21 cột cold mail"""
    try:
        with open(OUTPUT_CSV, mode="w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=STANDARD_FIELDNAMES)
            writer.writeheader()
            for r in all_rows:
                writer.writerow({k: r.get(k, '') for k in STANDARD_FIELDNAMES})
        print(f"\n[💾] Đã cập nhật tệp kết quả: {OUTPUT_CSV}")
    except Exception as e:
        print(f"\n[❌ Lỗi ghi file {OUTPUT_CSV}]: {e}")

async def run_enrichment(limit: int = 0, start_idx: int = 0):
    print("=" * 75)
    print("  🚀 CHƯƠNG TRÌNH LÀM GIÀU DỮ LIỆU CÔNG TY SIRI ĐAN MẠCH (đanmạchFT)")
    print("  👉 Chế độ: Hiển thị trực tiếp trình duyệt Chrome (headless=False)")
    print("  👉 Quy tắc lọc tên: Nghiêm ngặt từ Bộ cào Canada / Áo")
    print("  👉 Lọc ký tự mail: Triệt để giải mã và loại bỏ %20, dấu thừa")
    print("=" * 75)

    if not os.path.exists(SOURCE_CSV):
        print(f"[❌ ERROR] Không tìm thấy tệp nguồn: {SOURCE_CSV}")
        return

    with open(SOURCE_CSV, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        source_rows = list(reader)

    print(f"[*] Tổng số dòng dữ liệu đọc được: {len(source_rows)}")

    standardized_rows = []
    missing_indices = []

    for i, r in enumerate(source_rows):
        row_dict = {
            'No.': str(i + 1),
            'Cong ty': r.get('Cong ty', '').strip(),
            'Chuc danh': r.get('Chuc danh', '').strip(),
            'Nguoi lien he': r.get('Nguoi lien he', '').strip(),
            'SDT': clean_phone_dk(r.get('SDT', '')),
            'Lien He': r.get('Lien He', '').strip(),
            'Email': clean_single_email(r.get('Email', '')),
            'Lien He mail': clean_single_email(r.get('Lien He mail', '')),
            'Dia chi': r.get('Dia chi', '').strip(),
            'Luong': r.get('Luong', '').strip(),
            'Ngay dang': r.get('Ngay dang', '').strip(),
            'Han tuyen': r.get('Han tuyen', '').strip(),
            'Check gui': 'OK' if clean_single_email(r.get('Email', '')) else '',
            'Last Subject': r.get('Last Subject', '').strip(),
            'Last Body HTML': r.get('Last Body HTML', '').strip(),
            'Trang thai Reply': r.get('Trang thai Reply', '').strip(),
            'Lan Follow-up': r.get('Lan Follow-up', '0').strip(),
            'Ngay Follow-up gan nhat': r.get('Ngay Follow-up gan nhat', '').strip(),
            'Mailbox da dung': r.get('Mailbox da dung', '').strip(),
            'Category': 'SIRI Certified Company Denmark',
            'Link FB': ''
        }
        standardized_rows.append(row_dict)
        if not row_dict['Email']:
            missing_indices.append(i)

    print(f"[*] Dòng đã có sẵn Email: {len(standardized_rows) - len(missing_indices)}")
    print(f"[*] Dòng chưa có Email cần cào: {len(missing_indices)}")

    cache = load_cache()
    print(f"[*] Đã tải {len(cache)} kết quả từ bộ nhớ đệm (cache).")

    # Áp dụng dữ liệu từ cache nếu có sẵn
    for idx in missing_indices:
        c_name = standardized_rows[idx]['Cong ty']
        if c_name in cache:
            c_data = cache[c_name]
            if c_data.get('email'):
                standardized_rows[idx]['Email'] = c_data['email']
                standardized_rows[idx]['Check gui'] = 'OK'
            if c_data.get('phone') and not standardized_rows[idx]['SDT']:
                standardized_rows[idx]['SDT'] = c_data['phone']
            if c_data.get('website') and not standardized_rows[idx]['Lien He']:
                standardized_rows[idx]['Lien He'] = c_data['website']
            if c_data.get('fb_link'):
                standardized_rows[idx]['Link FB'] = c_data['fb_link']
            if c_data.get('address') and not standardized_rows[idx]['Dia chi']:
                standardized_rows[idx]['Dia chi'] = c_data['address']

    pending_indices = [idx for idx in missing_indices if not standardized_rows[idx]['Email']]
    print(f"[*] Số dòng còn thiếu email thực tế cần xử lý: {len(pending_indices)}")

    if start_idx > 0:
        pending_indices = [i for i in pending_indices if i >= start_idx]
    if limit > 0:
        pending_indices = pending_indices[:limit]

    print(f"[*] Sẽ xử lý: {len(pending_indices)} công ty trong đợt này.\n")

    export_coldmail_csv(standardized_rows)

    if not pending_indices:
        print("[🎉] Tất cả các công ty đã có email hoặc đã hoàn thành!")
        return

    os.makedirs(USER_DATA_DIR, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--start-maximized',
                '--no-sandbox'
            ],
            viewport=None
        )

        page = browser.pages[0] if browser.pages else await browser.new_page()

        total_pending = len(pending_indices)
        for cur_i, row_idx in enumerate(pending_indices, start=1):
            row = standardized_rows[row_idx]
            comp_name = row['Cong ty']
            comp_addr = row['Dia chi']

            print(f"\n[{cur_i}/{total_pending}] [Dòng {row_idx + 1}] Đang tra cứu: \"{comp_name}\"")

            website = ""
            phone = row['SDT']
            email = ""
            fb_link = ""
            matched_source = ""

            # BƯỚC 1: Tra cứu trên Google Maps
            print(f"   🗺️ [Tầng 1] Tra cứu Google Maps...")
            map_res = await lookup_on_google_maps(page, comp_name, comp_addr)
            if map_res.get('is_match'):
                print(f"      ✅ Khớp Google Maps: \"{map_res.get('maps_title')}\" ({map_res.get('match_reason')})")
                website = map_res.get('website', '')
                if map_res.get('phone') and not phone:
                    phone = map_res['phone']
                matched_source = "Google Maps"
            else:
                print(f"      ⚠️ Không khớp Google Maps: {map_res.get('match_reason')}")

            # BƯỚC 2: Fallback Web Search (Bing) nếu chưa có website
            if not website:
                print(f"   🔎 [Tầng 2] Fallback Web Search (Bing)...")
                website = await lookup_on_web_search(page, comp_name)
                if website:
                    print(f"      ✅ Tìm thấy website qua Web Search: {website}")
                    matched_source = "Bing Search"
                else:
                    print(f"      ❌ Không tìm thấy website chính chủ.")

            # BƯỚC 3: Quét sâu Website để lấy Email, Phone, Facebook
            if website:
                print(f"   🌐 [Tầng 3] Deep Crawl Website: {website} ...")
                site_email, site_phone, site_fb = await deep_crawl_website(page, website, comp_name)
                if site_email:
                    email = site_email
                    print(f"      📧 Tìm thấy Email: {email}")
                else:
                    print(f"      ⚪ Không tìm thấy email trên website.")

                if site_phone and not phone:
                    phone = site_phone
                    print(f"      📞 Tìm thấy SĐT: {phone}")

                if site_fb:
                    fb_link = site_fb
                    print(f"      🔵 Tìm thấy Link Facebook: {fb_link}")

            # Cập nhật kết quả vào dòng dữ liệu
            if email:
                row['Email'] = email
                row['Check gui'] = 'OK'
            if phone and not row['SDT']:
                row['SDT'] = phone
            if website and not row['Lien He']:
                row['Lien He'] = website
            if fb_link:
                row['Link FB'] = fb_link

            # Lưu vào Cache
            cache[comp_name] = {
                'email': email,
                'phone': phone,
                'website': website,
                'fb_link': fb_link,
                'source': matched_source,
                'timestamp': time.strftime("%Y-%m-%d %H:%M:%S")
            }
            save_cache(cache)

            # Ghi checkpoint ra CSV mỗi công ty
            export_coldmail_csv(standardized_rows)
            await asyncio.sleep(1.0)

        await browser.close()

    print("\n" + "=" * 75)
    print("  🎉 HOÀN TẤT ĐỢT LÀM GIÀU DỮ LIỆU!")
    print(f"  👉 Tệp đầu ra: {OUTPUT_CSV}")
    print("=" * 75)

if __name__ == "__main__":
    limit_arg = 0
    start_arg = 0
    for arg in sys.argv[1:]:
        if arg.startswith("--limit="):
            limit_arg = int(arg.split("=")[1])
        elif arg == "--limit" and len(sys.argv) > sys.argv.index(arg) + 1:
            limit_arg = int(sys.argv[sys.argv.index(arg) + 1])
        elif arg.startswith("--start="):
            start_arg = int(arg.split("=")[1])
        elif arg == "--start" and len(sys.argv) > sys.argv.index(arg) + 1:
            start_arg = int(sys.argv[sys.argv.index(arg) + 1])

    asyncio.run(run_enrichment(limit=limit_arg, start_idx=start_arg))
