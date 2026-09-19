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

# ==============================================================================
# DYNAMIC PATH CONFIGURATION (Tự động thích ứng mọi thiết bị / thư mục)
# ==============================================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)

SOURCE_CSV_PREF = os.path.join(PROJECT_ROOT, "(16_9) thịt dan mạch - Trang tính1.csv")
SOURCE_CSV_FALLBACK = os.path.join(PROJECT_ROOT, "thit_dan_mach.csv")
SOURCE_CSV = SOURCE_CSV_PREF if os.path.exists(SOURCE_CSV_PREF) else SOURCE_CSV_FALLBACK
ORIGINAL_DATA_CSV = os.path.join(PROJECT_ROOT, "thit_dan_mach.csv")
OUTPUT_CSV = os.path.join(PROJECT_ROOT, "(16_9) thịt dan mạch - Trang tính1.csv")
OUTPUT_CHECKPOINT_CSV = os.path.join(PROJECT_ROOT, "Thịt đan mạch enrich.csv")
CACHE_FILE = os.path.join(CURRENT_DIR, "cache_thit_dan_mach.json")

USER_DATA_DIR = os.path.join(PROJECT_ROOT, "chrome_user_data", "thit_dan_mach_profile")

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
    'yahoo-net.jp', 'yahoo.co.jp', 'ramp.directory', 'prodenmark.com', 'feve.org',
    'usetorg.com', 'torg.com', 'europages.com', 'europages.dk', 'tradekey.com'
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
    'usetorg.com', 'torg.com', 'europages.com', 'europages.dk', 'tradekey.com',

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

FOREIGN_COUNTRIES = {
    'vietnam', 'việt nam', 'greenland', 'grønland', 'deutschland', 'germany', 'tyskland',
    'sverige', 'sweden', 'norge', 'norway', 'polen', 'poland', 'polska', 'finland',
    'storbritannien', 'united kingdom', 'great britain', 'england', 'scotland', 'wales', 'uk',
    'usa', 'united states', 'nederland', 'netherlands', 'holland',
    'france', 'frankrig', 'italien', 'italy', 'spanien', 'spain',
    'china', 'japan', 'canada', 'australia', 'thailand', 'singapore',
    'argentina', 'mexico', 'brazil', 'india', 'russia'
}

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================
def clean_phone_dk(phone_str):
    if not phone_str:
        return ""
    s = str(phone_str).strip().lstrip("'").strip()
    s = re.sub(r'^(tlf|tlf\.|telefon|phone|tel|t)\s*[:.]?\s*', '', s, flags=re.IGNORECASE)
    digits = re.sub(r'[^0-9]', '', s)
    if not digits:
        return ""
    if digits.startswith("0045"):
        digits = digits[4:]
    elif digits.startswith("45") and len(digits) >= 10:
        digits = digits[2:]
    
    # Số điện thoại Đan Mạch tiêu chuẩn luôn có đúng 8 chữ số
    if len(digits) == 8:
        return f"'+45{digits}"
    elif len(digits) > 8 and len(digits) <= 10:
        return f"'+45{digits[-8:]}"
    return ""


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
    
    s = str(raw_email).strip()
    try:
        s = urllib.parse.unquote(s)
    except Exception:
        pass

    s = re.sub(r'^mailto:', '', s, flags=re.IGNORECASE)
    s = re.sub(r'^u003[ce]', '', s, flags=re.IGNORECASE)
    s = s.replace('%20', '').replace('%0A', '').replace('%0D', '')
    s = s.strip('<>()[]{}\'"\\ \t\r\n;,:')

    if not s or '@' not in s:
        return ""

    match = EMAIL_REGEX.search(s)
    if not match:
        return ""
    
    clean = match.group(0).lower().strip('.')
    for ext in INVALID_EXTENSIONS:
        if clean.endswith(ext):
            return ""

    parts = clean.split('@')
    if len(parts) != 2:
        return ""
    user, domain = parts
    if '.' not in domain or len(user) == 0 or len(domain) < 3:
        return ""

    return clean

def decode_cloudflare_email(cf_hex):
    try:
        hex_data = bytes.fromhex(cf_hex)
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
        if any(x in hl for x in [
            'sharer', 'share.php', 'plugins', 'dialog', 'tr?', 'photo.php', 'video.php',
            'policy', 'policies', 'legal', 'privacy', 'terms', 'help', 'login', 'signup',
            'create', '.php', '/share', 'pages/create'
        ]):
            return ""
        parsed = urllib.parse.urlparse(h)
        clean_path = parsed.path.rstrip('/')
        if clean_path in ['', '/', '/home', '/profile.php']:
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

def is_denmark_location(address: str) -> bool:
    """
    Kiểm tra địa điểm có thuộc Đan Mạch hay không.
    - Loại bỏ triệt để các địa điểm ngoài Đan Mạch (Việt Nam, Greenland, Đức, Mỹ, Argentina, Mexico,...)
    - Bảo toàn các tên đường Đan Mạch chứa tên nước (như Englandsvej, Norgesvej, Sverigesvej, Norgeskajen).
    - Kiểm tra mã bưu chính 4 số chuẩn của Đan Mạch (1000 - 9999).
    """
    if not address:
        return False
    addr = address.strip()
    addr_clean = re.sub(r'^[\s\ue000-\uf8ff\u2000-\u206f\W_]+', '', addr).strip()
    addr_lower = addr_clean.lower()

    parts = [p.strip() for p in addr_clean.split(',') if p.strip()]
    last_part = parts[-1].lower() if parts else addr_lower

    # 1. Nếu phần cuối rõ ràng là Denmark / Danmark / DK -> Hợp lệ Đan Mạch
    if any(dk == last_part or last_part.endswith(' ' + dk) for dk in ['denmark', 'danmark', 'dk']):
        return True

    # 2. Nếu phần cuối khớp tên quốc gia nước ngoài -> Loại bỏ
    for fc in FOREIGN_COUNTRIES:
        if fc == last_part or re.search(r'\b' + re.escape(fc) + r'\b', last_part):
            return False

    # 3. Kiểm tra từ khóa nước ngoài trong toàn bộ địa chỉ (loại trừ các hậu tố tên đường Đan Mạch: vej, gade, kaj,...)
    addr_without_streets = re.sub(r'\b\w+(vej|gade|kaj|kajen|allé|alle|stræde|plads|torv)\b', '', addr_lower)
    for fc in FOREIGN_COUNTRIES:
        if re.search(r'\b' + re.escape(fc) + r'\b', addr_without_streets):
            return False

    # 4. Kiểm tra mã bưu điện 4 chữ số Đan Mạch (1000 - 9999 kèm tên thị xã/thành phố)
    if re.search(r'\b(dk[- ]?)?[1-9][0-9]{3}\s+[A-Za-zæøåÆØÅ]', addr_clean):
        return True

    # 5. Nếu có từ denmark / danmark ở bất kỳ đâu
    if 'denmark' in addr_lower or 'danmark' in addr_lower:
        return True

    return False

def is_valid_place_in_denmark(address: str, phone: str = "", website: str = "") -> tuple:
    """
    Xác định địa điểm trên Maps có thuộc Đan Mạch hay không:
    - Nếu có địa chỉ hiển thị: bắt buộc phải thuộc Đan Mạch (loại bỏ nếu thuộc nước khác).
    - Nếu không có địa chỉ hiển thị (cơ sở dịch vụ / B2B): kiểm tra SĐT (+45) hoặc Website (.dk).
    """
    if address:
        if is_denmark_location(address):
            return True, f"Địa chỉ hợp lệ Đan Mạch: {address}"
        return False, f"Địa chỉ nằm ngoài Đan Mạch: {address}"

    # Trường hợp không có nút địa chỉ trên Maps (như Grøndals & Co. ApS)
    clean_ph = clean_phone_dk(phone)
    if clean_ph.startswith("'+45") or clean_ph.startswith("+45"):
        return True, f"Hợp lệ Đan Mạch theo SĐT: {clean_ph}"

    if website:
        domain = extract_clean_domain(website)
        if domain.endswith('.dk'):
            return True, f"Hợp lệ Đan Mạch theo website: {domain}"

    return False, "Không có địa chỉ và không có SĐT/Website Đan Mạch để xác thực"

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
    is_same_brand_domain = (site_sld and email_sld == site_sld) or (email_sld in brand_tokens)
    is_brand_username = any(b in username for b in brand_tokens)

    if is_same_brand_domain:
        if is_brand_username:
            return 250
        if username in PREFERRED_USERNAMES:
            return 230
        return 200

    # 3. Khớp một phần tên thương hiệu (Tier 2: 150 - 180 điểm)
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

    # 5. Email thuộc Đan Mạch (.dk) hoặc các tiền tố liên hệ chuẩn (kontakt, info, salg, mail, order, support)
    # Rất nhiều cty con dùng mail cty mẹ (ví dụ kcfrugt.dk dùng kontakt@ingwersen.dk, bccatering.dk dùng info@bcca.dk)
    if domain.endswith('.dk') or domain.endswith('.com') or domain.endswith('.eu') or domain.endswith('.net'):
        if username in PREFERRED_USERNAMES:
            return 100
        if is_brand_username:
            return 90
        # Bất kỳ email .dk nào tìm thấy trên website hợp lệ
        if domain.endswith('.dk'):
            return 70
        return 40

    # 6. Webmail công cộng (Gmail, Outlook...)
    if domain in {'gmail.com', 'hotmail.com', 'yahoo.com', 'outlook.com', 'icloud.com', 'live.com'}:
        if is_brand_username or username in PREFERRED_USERNAMES:
            return 50
        return 35

    # 7. Tên miền khác không thuộc blacklist (Tier 7: 15 điểm để bảo tồn nếu không có mail khác)
    return 15

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

# ==============================================================================
# CRAWLING TIERS
# ==============================================================================
async def lookup_on_google_maps(page, company_name: str, address: str = "") -> dict:
    """Tra cứu trên Google Maps: CHỈ TRA TÊN CÔNG TY và lọc nghiêm ngặt theo quốc gia Đan Mạch"""
    clean_name = re.sub(r'\([^\)]*\)', '', company_name).strip()
    
    # CRITICAL: CHỈ TRA TÊN CÔNG TY, HOÀN TOÀN KHÔNG KÈM THEO ĐỊA CHỈ
    query = clean_name
    encoded = urllib.parse.quote(query)
    maps_url = f"https://www.google.com/maps/search/{encoded}"

    result = {"phone": "", "website": "", "maps_title": "", "address": "", "is_match": False, "match_reason": ""}

    try:
        await page.goto(maps_url, wait_until="domcontentloaded", timeout=45000)
        await check_and_wait_if_verify(page, "Google Maps")
        try:
            await page.wait_for_selector("h1, a.hfpxzc", timeout=12000)
        except Exception:
            pass
        await page.wait_for_timeout(3500)

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
        await page.wait_for_timeout(1500)

        # Trợ hàm bóc tách thông tin từ view hiện tại của Google Maps
        async def extract_current_place_details():
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
            addr = details.get("address", "")
            addr = re.sub(r'^[\s\ue000-\uf8ff\u2000-\u206f\W_]+', '', addr)
            addr = re.sub(r'\s+', ' ', addr).strip()
            details["address"] = addr
            return details

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
                details = await extract_current_place_details()
                found_addr = details.get("address", "")
                is_dk, dk_reason = is_valid_place_in_denmark(found_addr, details.get("phone", ""), details.get("website", ""))
                if is_dk:
                    target_matched = True
                    result["is_match"] = True
                    result["maps_title"] = direct_title
                    result["match_reason"] = f"{reason} | {dk_reason}"
                    result["website"] = details.get("website", "")
                    result["phone"] = clean_phone_dk(details.get("phone", ""))
                    result["address"] = found_addr
                else:
                    print(f"      [Maps Direct Reject]: '{direct_title}' không thuộc Đan Mạch ({dk_reason})")
                    result["match_reason"] = dk_reason

        # 2. Nếu chưa tìm được cơ sở tại Đan Mạch, duyệt danh sách kết quả (Feed Cards)
        if not target_matched:
            cards = await page.locator("a.hfpxzc, a[href*='/maps/place/']").all()
            if cards:
                for idx, c in enumerate(cards[:6]):
                    aria = (await c.get_attribute("aria-label") or "").strip()
                    if not aria:
                        continue
                    ok, reason = is_valid_name_match(company_name, aria)
                    if not ok:
                        continue

                    # Bấm vào card để xem chi tiết
                    try:
                        await c.click()
                        try:
                            await page.wait_for_selector('button[data-item-id*="address"], a[data-item-id*="authority"]', timeout=10000)
                        except Exception:
                            pass
                        await page.wait_for_timeout(2500)
                    except Exception:
                        continue

                    details = await extract_current_place_details()
                    found_addr = details.get("address", "")
                    is_dk, dk_reason = is_valid_place_in_denmark(found_addr, details.get("phone", ""), details.get("website", ""))
                    if is_dk:
                        target_matched = True
                        result["is_match"] = True
                        result["maps_title"] = aria
                        result["match_reason"] = f"{reason} | {dk_reason}"
                        result["website"] = details.get("website", "")
                        result["phone"] = clean_phone_dk(details.get("phone", ""))
                        result["address"] = found_addr
                        break
                    else:
                        print(f"      [Maps Card {idx+1} Reject]: '{aria}' không thuộc Đan Mạch ({dk_reason})")
                        result["match_reason"] = dk_reason

    except Exception as e:
        result["match_reason"] = f"Lỗi Maps: {e}"

    return result

async def lookup_on_web_search(page, company_name: str) -> str:
    """Tìm kiếm website chính thức qua Bing Search khi Google Maps không có kết quả"""
    clean_name = re.sub(r'\([^\)]*\)', '', company_name).strip()
    query = f"{clean_name} Denmark website"
    
    try:
        bing_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
        await page.goto(bing_url, wait_until="domcontentloaded", timeout=35000)
        await check_and_wait_if_verify(page, "Bing Search")
        await page.wait_for_timeout(3000)

        results = await page.evaluate("""() => {
            const items = [];
            const cards = Array.from(document.querySelectorAll('li.b_algo'));
            for (const c of cards) {
                const h2 = c.querySelector('h2');
                const a = c.querySelector('h2 a') || c.querySelector('a');
                if (a && a.href) {
                    items.push({
                        title: h2 ? h2.innerText.trim() : a.innerText.trim(),
                        href: a.href
                    });
                }
            }
            return items;
        }""")

        brand_tokens = extract_brand_tokens(company_name)
        norm_c = normalize_phrase(company_name).replace(' ', '')

        for r in results:
            raw_href = r.get('href', '')
            decoded_url = decode_bing_url(raw_href)
            title = r.get('title', '')
            domain = extract_clean_domain(decoded_url)

            if not domain or is_platform_or_aggregator(domain):
                continue

            sld = extract_sld(domain)
            domain_flat = domain.replace('.', '').replace('-', '')

            # Kiểm tra:
            # 1. Tên miền chứa toàn bộ tên công ty (ví dụ: gormsengourmet.dk vs Gormsen Gourmet)
            is_company_in_domain = bool(norm_c and len(norm_c) >= 4 and (norm_c in domain_flat or domain_flat in norm_c))
            
            # 2. Hoặc tiêu đề kết quả khớp quy tắc lọc VÀ tên miền chứa brand token của công ty
            has_brand_in_domain = any(b in sld or b in domain_flat for b in brand_tokens if len(b) >= 3)
            ok_title, _ = is_valid_name_match(company_name, title)

            if is_company_in_domain or (ok_title and has_brand_in_domain):
                parsed = urllib.parse.urlparse(decoded_url)
                netloc = parsed.netloc
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
        resp = await page.goto(website_url, wait_until="domcontentloaded", timeout=40000)
        await check_and_wait_if_verify(page, f"Website {website_url}")
        title = (await page.title()).lower()
        if (resp and resp.status in [403, 503]) or 'attention required' in title or 'cloudflare' in title:
            print(f"      ⚠️ Website kích hoạt bảo vệ chống bot Cloudflare / WAF (HTTP {resp.status if resp else '403'})")
        await page.wait_for_timeout(3000)
        scanned_urls.add(website_url)

        # Tự động bấm chấp nhận Cookie banner (Cookiebot, OneTrust, v.v.)
        try:
            await page.evaluate("""() => {
                const selectors = [
                    '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
                    '#CybotCookiebotDialogBodyButtonAccept',
                    '#onetrust-accept-btn-handler',
                    '.cmplz-accept', '.cc-allow', '#accept-cookies',
                    'button[id*="accept"]', 'button[class*="accept"]',
                    'button[id*="cookie"]', 'button[class*="cookie"]'
                ];
                for (const s of selectors) {
                    const el = document.querySelector(s);
                    if (el) { el.click(); return; }
                }
                const btns = Array.from(document.querySelectorAll('button, a'));
                for (const b of btns) {
                    const t = (b.innerText || '').toLowerCase().trim();
                    if (['accept all', 'tillad alle', 'godkend alle', 'acceptér alle', 'alle akzeptieren', 'i agree', 'accepter', 'accept'].includes(t)) {
                        b.click();
                        return;
                    }
                }
            }""")
            await page.wait_for_timeout(1500)
        except Exception:
            pass

        # Cuộn trang xuống để kích hoạt nạp footer và lazy-loading
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            await page.wait_for_timeout(1000)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1500)
        except Exception:
            pass

        # Lấy trực tiếp tất cả các link mailto từ DOM
        try:
            dom_mailtos = await page.evaluate("""() => {
                const list = [];
                for (const a of document.querySelectorAll('a[href*="mailto:"]')) {
                    const h = a.getAttribute('href') || a.href || '';
                    const m = h.replace(/^mailto:/i, '').split('?')[0].trim();
                    if (m) list.push(m);
                }
                return list;
            }""")
            for jm in dom_mailtos:
                cm = clean_single_email(jm)
                if cm:
                    found_emails.add(cm)
        except Exception:
            pass

        # Lấy nội dung DOM sau khi render JS
        dom_content = await page.content()
        em1, ph1 = extract_from_html_content(dom_content)
        found_emails.update(em1)
        found_phones.update(ph1)

        # Lấy tên miền thực tế (sau chuyển hướng redirect)
        effective_domain = extract_clean_domain(page.url) or site_domain

        # Tìm các link liên hệ (contact / about / om os / medarbejdere / afdelinger)
        sublinks = await page.evaluate("""(domain) => {
            const links = [];
            const keywords = [
                'contact', 'kontakt', 'om-os', 'om_os', 'about', 'om', 'kundeservice', 'find-os', 
                'support', 'kontakt-os', 'kontakt_os', 'medarbejdere', 'afdelinger', 'afdeling', 
                'kontor', 'personale', 'team', 'ledelse', 'hovedkontor', 'hvem-er-vi', 'locations', 
                'facilities', 'butikker', 'butik', 'find'
            ];
            for (const a of document.querySelectorAll('a[href]')) {
                const href = a.href;
                const text = (a.innerText || '').toLowerCase();
                try {
                    const u = new URL(href);
                    if (u.hostname.includes(domain)) {
                        const path = u.pathname.toLowerCase();
                        if (keywords.some(k => path.includes(k) || text.includes(k))) {
                            if (!links.includes(href)) links.push(href);
                        }
                    }
                } catch(e) {}
            }
            return links.slice(0, 8);
        }""", effective_domain)

        # Quét các subpages liên hệ
        for sub_url in sublinks:
            if sub_url in scanned_urls:
                continue
            try:
                await page.goto(sub_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)
                scanned_urls.add(sub_url)

                # Cuộn trang subpage
                try:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1000)
                except Exception:
                    pass

                # Trích xuất mailto từ DOM subpage
                try:
                    sub_mailtos = await page.evaluate("""() => {
                        const list = [];
                        for (const a of document.querySelectorAll('a[href*="mailto:"]')) {
                            const h = a.getAttribute('href') || a.href || '';
                            const m = h.replace(/^mailto:/i, '').split('?')[0].trim();
                            if (m) list.push(m);
                        }
                        return list;
                    }""")
                    for jm in sub_mailtos:
                        cm = clean_single_email(jm)
                        if cm:
                            found_emails.add(cm)
                except Exception:
                    pass

                sub_dom = await page.content()
                em_sub, ph_sub = extract_from_html_content(sub_dom)
                found_emails.update(em_sub)
                found_phones.update(ph_sub)
            except Exception:
                pass

    except Exception as e:
        # Nếu https lỗi, thử http
        if website_url.startswith('https://'):
            try:
                alt_url = 'http://' + website_url[8:]
                await page.goto(alt_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2500)
                dom_content = await page.content()
                em1, ph1 = extract_from_html_content(dom_content)
                found_emails.update(em1)
                found_phones.update(ph1)
            except Exception:
                pass

    # Chấm điểm và chọn email tốt nhất
    best_email = ""
    best_score = -1
    for em in found_emails:
        sc = score_email(em, website_url, company_name)
        if sc > best_score:
            best_score = sc
            best_email = em

    if best_score <= 0:
        best_email = ""

    best_phone = list(found_phones)[0] if found_phones else ""
    return best_email, best_phone, fb_link

# ==============================================================================
# MAIN WORKFLOW & CHECKPOINTING
# ==============================================================================
def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Lỗi lưu cache: {e}")

def load_source_companies():
    """Tải danh sách công ty từ file nguồn và từ điển địa chỉ gốc chuẩn của Đan Mạch"""
    orig_addresses = {}
    if os.path.exists(ORIGINAL_DATA_CSV):
        try:
            with open(ORIGINAL_DATA_CSV, mode='r', encoding='utf-8-sig') as f:
                for r in csv.DictReader(f):
                    name = r.get('name', '').strip()
                    town = r.get('town', '').strip()
                    if name and town:
                        orig_addresses[name] = town
        except Exception as e:
            print(f"[-] Không thể đọc file địa chỉ gốc thit_dan_mach.csv: {e}")

    if not os.path.exists(SOURCE_CSV):
        print(f"[-] Không tìm thấy file nguồn: {SOURCE_CSV}")
        return [], orig_addresses

    with open(SOURCE_CSV, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        source_rows = list(reader)

    companies = []
    for idx, row in enumerate(source_rows, start=1):
        cname = (row.get('Cong ty') or row.get('name') or '').strip()
        if not cname:
            continue
        address = (row.get('Dia chi') or row.get('town') or '').strip()
        category = (row.get('Category') or row.get('category') or '').strip()
        website = (row.get('Lien He') or '').strip()
        email = (row.get('Email') or '').strip()
        phone = (row.get('SDT') or '').strip()
        fb = (row.get('Link FB') or '').strip()

        # Nếu địa chỉ cũ bị dính nước ngoài, ưu tiên phục hồi về địa chỉ gốc chuẩn Đan Mạch
        # đồng thời làm sạch các website/email ngoại quốc bị nhiễm từ lần chạy trước
        if not is_denmark_location(address) and cname in orig_addresses:
            address = orig_addresses[cname]
            if any(k in website.lower() for k in ['/viet-nam', '/vietnam', '/asia/', '.vn/', 'greenland']) or website.lower().endswith('.vn'):
                website = ""
            if any(k in email.lower() for k in ['.vn', '@vn.']):
                email = ""

        companies.append({
            'No.': idx,
            'name': cname,
            'town': address,
            'category': category,
            'existing_website': website,
            'existing_email': email,
            'existing_phone': phone,
            'existing_fb': fb,
            'raw_row': row
        })

    return companies, orig_addresses

def export_cold_mail_csv(cache_dict, all_companies, orig_addresses):
    """Xuất file chuẩn Cold Mail (20 cột chuẩn + 1 cột Link FB = 21 cột) đồng bộ cả 2 file đích"""
    export_rows = []
    for comp in all_companies:
        idx = comp['No.']
        cname = comp['name']
        orig_addr = orig_addresses.get(cname, '') or comp['town']
        category = comp['category']

        enriched = cache_dict.get(cname, {})
        final_email = enriched.get('email', '') or comp.get('existing_email', '')
        final_phone = clean_phone_dk(enriched.get('phone', '') or comp.get('existing_phone', ''))
        final_website = enriched.get('website', '') or comp.get('existing_website', '')
        final_fb = enriched.get('fb_link', '') or comp.get('existing_fb', '')

        # Loại bỏ triệt để website / email ngoại quốc (như .vn, /asia/, /viet-nam) bị dính nhầm từ Maps trước đây
        if any(k in final_website.lower() for k in ['/viet-nam', '/vietnam', '/asia/', '.vn/']) or final_website.lower().endswith('.vn'):
            final_website = "https://www.dsv.com/da-dk" if "dsv" in cname.lower() else ""
        if any(k in final_email.lower() for k in ['.vn', '@vn.']):
            final_email = ""

        # Quyết định địa chỉ:
        # 1. Địa chỉ tìm thấy từ Maps nếu nằm trong Đan Mạch
        # 2. Địa chỉ gốc từ Fødevarestyrelsen (thit_dan_mach.csv)
        # 3. Địa chỉ hiện có nếu nằm trong Đan Mạch
        maps_addr = enriched.get('address', '').strip()
        if maps_addr and is_denmark_location(maps_addr):
            final_address = maps_addr
        elif orig_addr and is_denmark_location(orig_addr):
            final_address = orig_addr
        elif comp['town'] and is_denmark_location(comp['town']):
            final_address = comp['town']
        else:
            final_address = orig_addr or comp['town']

        raw = comp.get('raw_row', {})
        export_rows.append({
            'No.': idx,
            'Cong ty': cname,
            'Chuc danh': raw.get('Chuc danh', ''),
            'Nguoi lien he': raw.get('Nguoi lien he', ''),
            'SDT': final_phone,
            'Lien He': final_website,
            'Email': final_email,
            'Lien He mail': raw.get('Lien He mail', ''),
            'Dia chi': final_address,
            'Luong': raw.get('Luong', ''),
            'Ngay dang': raw.get('Ngay dang', ''),
            'Han tuyen': raw.get('Han tuyen', ''),
            'Check gui': raw.get('Check gui', ''),
            'Last Subject': raw.get('Last Subject', ''),
            'Last Body HTML': raw.get('Last Body HTML', ''),
            'Trang thai Reply': raw.get('Trang thai Reply', ''),
            'Lan Follow-up': raw.get('Lan Follow-up', ''),
            'Ngay Follow-up gan nhat': raw.get('Ngay Follow-up gan nhat', ''),
            'Mailbox da dung': raw.get('Mailbox da dung', ''),
            'Category': category,
            'Link FB': final_fb
        })

    # Đồng bộ lưu ra cả file chính và file checkpoint
    for out_path in [OUTPUT_CSV, OUTPUT_CHECKPOINT_CSV]:
        try:
            with open(out_path, mode='w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=STANDARD_FIELDNAMES)
                writer.writeheader()
                writer.writerows(export_rows)
        except Exception as e:
            print(f"[-] Lỗi lưu file '{out_path}': {e}")

    found_emails = sum(1 for r in export_rows if r['Email'])
    found_phones = sum(1 for r in export_rows if r['SDT'])
    found_webs = sum(1 for r in export_rows if r['Lien He'])
    found_fbs = sum(1 for r in export_rows if r['Link FB'])
    print(f"[*] Checkpoint saved: {len(export_rows)} rows | {found_emails} Emails | {found_phones} Phones | {found_webs} Websites | {found_fbs} Facebooks")

async def run_enrichment(limit=None, force_recheck=False):
    all_companies, orig_addresses = load_source_companies()
    if not all_companies:
        print(f"[-] Không có dữ liệu công ty để xử lý!")
        return

    print(f"[*] Đã tải {len(all_companies)} công ty từ {SOURCE_CSV}")
    cache = load_cache()
    print(f"[*] Đã tải cache: {len(cache)} công ty đã xử lý")

    if limit:
        # Khi có limit (test mode), xử lý đúng N công ty đầu tiên
        pending_companies = all_companies[:limit]
        print(f"[*] Chế độ TEST: Xử lý {len(pending_companies)} công ty đầu tiên.")
    else:
        # Lọc các dòng CHƯA CÓ EMAIL (cả trong file CSV nguồn lẫn trong Cache)
        pending_companies = []
        for c in all_companies:
            cname = c['name']
            has_email = bool(c.get('existing_email') or (cname in cache and cache[cname].get('email')))
            is_checked = cname in cache and cache[cname].get('checked_all', False)

            if force_recheck:
                pending_companies.append(c)
            elif not has_email and not is_checked:
                pending_companies.append(c)

        print(f"[*] Lọc danh sách: Có {sum(1 for c in all_companies if c.get('existing_email'))} công ty đã có email sẵn trong CSV.")
        print(f"[*] Cần xử lý: {len(pending_companies)} công ty CHƯA CÓ EMAIL.")

    if not pending_companies:
        print("[+] Toàn bộ danh sách đã được xử lý xong!")
        export_cold_mail_csv(cache, all_companies, orig_addresses)
        return

    os.makedirs(USER_DATA_DIR, exist_ok=True)

    # BẮT BUỘC HEADLESS=FALSE để người dùng quan sát trực quan
    async with async_playwright() as p:
        print("[*] Khởi động trình duyệt Google Chrome trực quan (headless=False)...")
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            locale="da-DK",
            viewport={"width": 1280, "height": 850},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
                "--no-sandbox"
            ]
        )
        await browser.add_init_script("""
            Object.defineProperty(Object.getPrototypeOf(navigator), 'webdriver', {
                get: () => undefined
            });
            window.chrome = { runtime: {} };
        """)
        page = browser.pages[0] if browser.pages else await browser.new_page()
        page.set_default_timeout(45000)
        page.set_default_navigation_timeout(60000)

        processed_count = 0
        for comp in pending_companies:
            cname = comp['name']
            town = comp['town']
            category = comp['category']
            processed_count += 1

            print(f"\n[{processed_count}/{len(pending_companies)}] Đang xử lý: {cname} (Địa chỉ gốc: {town})")
            comp_data = cache.get(cname, {
                "website": comp.get('existing_website', ''),
                "phone": comp.get('existing_phone', ''),
                "email": comp.get('existing_email', ''),
                "fb_link": comp.get('existing_fb', ''),
                "address": town,
                "checked_all": False
            })

            # BƯỚC 1: Tra cứu trên Google Maps (CHỈ TRA TÊN CÔNG TY, KHÔNG KÈM ĐỊA CHỈ)
            maps_res = await lookup_on_google_maps(page, cname, town)
            if maps_res["is_match"]:
                print(f"   [Google Maps Match]: {maps_res['maps_title']} ({maps_res['match_reason']})")
                if maps_res["website"] and not comp_data["website"]:
                    comp_data["website"] = maps_res["website"]
                if maps_res["phone"] and not comp_data["phone"]:
                    comp_data["phone"] = maps_res["phone"]
                if maps_res["address"]:
                    comp_data["address"] = maps_res["address"]
            else:
                print(f"   [Google Maps Miss]: {maps_res['match_reason']}")
                # Nếu địa chỉ cũ bị ngoại quốc, phục hồi về địa chỉ gốc Đan Mạch
                if not is_denmark_location(comp_data.get("address", "")):
                    comp_data["address"] = orig_addresses.get(cname, town)

            # BƯỚC 2: Fallback qua Web Search (Bing) nếu Maps không có website
            if not comp_data["website"]:
                print(f"   [Bing Search Fallback]: Tìm kiếm website...")
                bing_web = await lookup_on_web_search(page, cname)
                if bing_web:
                    print(f"   [Bing Search Match]: {bing_web}")
                    comp_data["website"] = bing_web
                else:
                    print(f"   [Bing Search Miss]: Không tìm thấy website phù hợp")

            # BƯỚC 3: Quét sâu Website nếu có URL
            if comp_data["website"]:
                print(f"   [Deep Crawl]: Đang quét {comp_data['website']}...")
                em, ph, fb = await deep_crawl_website(page, comp_data["website"], cname)
                found_new = False
                if em:
                    comp_data["email"] = em
                    print(f"      -> 🎯 Email: {em}")
                    found_new = True
                if ph and not comp_data["phone"]:
                    comp_data["phone"] = ph
                    print(f"      -> 📞 Phone: {ph}")
                    found_new = True
                if fb:
                    comp_data["fb_link"] = fb
                    print(f"      -> 🌐 Facebook: {fb}")
                    found_new = True

                if not found_new:
                    print(f"      -> ⚪ Đã quét xong: Không tìm thấy email/SĐT mới trên website này")

            comp_data["checked_all"] = True
            cache[cname] = comp_data

            # Lưu checkpoint mỗi 3 công ty
            if processed_count % 3 == 0:
                save_cache(cache)
                export_cold_mail_csv(cache, all_companies, orig_addresses)

            await asyncio.sleep(2)

        # Lưu checkpoint cuối
        save_cache(cache)
        export_cold_mail_csv(cache, all_companies, orig_addresses)
        await browser.close()

    print("\n[+] HOÀN TẤT TIẾN TRÌNH LÀM GIÀU DỮ LIỆU THỊT ĐAN MẠCH!")

if __name__ == '__main__':
    limit_arg = None
    force_arg = False
    for arg in sys.argv[1:]:
        if arg in ['--force', '-f', '--recheck']:
            force_arg = True
        else:
            try:
                limit_arg = int(arg)
            except ValueError:
                pass
    asyncio.run(run_enrichment(limit=limit_arg, force_recheck=force_arg))
