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

SOURCE_CSV = os.path.join(PROJECT_ROOT, "thit_dan_mach.csv")
OUTPUT_CSV = os.path.join(PROJECT_ROOT, "Thịt đan mạch enrich.csv")
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

FOREIGN_COUNTRIES = [
    'sverige', 'sweden', 'norge', 'norway', 'tyskland', 'germany', 'deutschland',
    'polen', 'poland', 'finland', 'storbritannien', 'united kingdom', 'england',
    'usa', 'united states', 'nederland', 'netherlands', 'holland', 'france', 'frankrig',
    'italien', 'italy', 'spanien', 'spain'
]

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
    """Kiểm tra địa điểm có thuộc Đan Mạch hay không. Loại bỏ nếu thuộc quốc gia khác."""
    if not address:
        # Nếu không trích xuất được địa chỉ rõ ràng, chấp nhận nếu query Maps đã giới hạn ở Đan Mạch
        return True
    
    addr_lower = address.lower()

    # Kiểm tra nếu xuất hiện tên quốc gia khác mà không chứa Đan Mạch
    has_foreign = any(fc in addr_lower for fc in FOREIGN_COUNTRIES)
    has_dk = any(dk in addr_lower for dk in ['danmark', 'denmark', ' dk', ', dk']) or re.search(r'\b\d{4}\b', addr_lower)

    if has_foreign and not has_dk:
        return False
    
    return True

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

    # 5. Webmail công cộng (Gmail, Outlook...)
    if domain in {'gmail.com', 'hotmail.com', 'yahoo.com', 'outlook.com', 'icloud.com', 'live.com'}:
        if is_brand_username or username in PREFERRED_USERNAMES:
            return 50
        return 35

    # 6. Tên miền bên thứ 3 hoàn toàn không liên quan (Tier 6: 0 điểm - BỎ QUA)
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

# ==============================================================================
# CRAWLING TIERS
# ==============================================================================
async def lookup_on_google_maps(page, company_name: str, address: str = "") -> dict:
    """Tra cứu trên Google Maps với quy tắc lọc tên nghiêm ngặt và lọc địa điểm ngoài Đan Mạch"""
    clean_name = re.sub(r'\([^\)]*\)', '', company_name).strip()
    
    # Trích xuất mã bưu chính / thành phố từ địa chỉ nếu có
    town_token = ""
    if address:
        m_zip = re.search(r'\b(\d{4}\s+[A-Za-zæøåÆØÅ\s]+)', address)
        if m_zip:
            town_token = m_zip.group(1).strip()
            
    query = f"{clean_name} {town_token} Denmark".strip() if town_token else f"{clean_name} Denmark"
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

            found_address = details.get("address", "")
            found_address = re.sub(r'^[\s\ue000-\uf8ff\u2000-\u206f\W_]+', '', found_address)
            found_address = re.sub(r'\s+', ' ', found_address).strip()
            
            # Kiểm tra xem địa điểm có nằm ngoài Đan Mạch hay không
            if not is_denmark_location(found_address):
                result["is_match"] = False
                result["match_reason"] = f"Loại bỏ vì địa điểm nằm ngoài Đan Mạch ({found_address})"
                return result


            result["website"] = details.get("website", "")
            result["phone"] = clean_phone_dk(details.get("phone", ""))
            result["address"] = found_address

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
        await page.goto(website_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000)
        scanned_urls.add(website_url)

        # Lấy nội dung DOM sau khi render JS
        dom_content = await page.content()
        em1, ph1 = extract_from_html_content(dom_content)
        found_emails.update(em1)
        found_phones.update(ph1)

        # Tìm các link liên hệ (contact / about / om os)
        sublinks = await page.evaluate("""(domain) => {
            const links = [];
            const keywords = ['contact', 'kontakt', 'om-os', 'om_os', 'about', 'om', 'kundeservice', 'find-os', 'support'];
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
            return links.slice(0, 4);
        }""", site_domain)

        # Quét các subpages
        for sub_url in sublinks:
            if sub_url in scanned_urls:
                continue
            try:
                await page.goto(sub_url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(1500)
                scanned_urls.add(sub_url)
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
                await page.goto(alt_url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(1500)
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

def export_cold_mail_csv(cache_dict):
    """Xuất file chuẩn Cold Mail (20 cột chuẩn + 1 cột Link FB = 21 cột)"""
    if not os.path.exists(SOURCE_CSV):
        print(f"[-] Không tìm thấy file nguồn: {SOURCE_CSV}")
        return

    with open(SOURCE_CSV, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        source_rows = list(reader)

    export_rows = []
    for idx, row in enumerate(source_rows, start=1):
        cname = row.get('name', '').strip()
        address = row.get('town', '').strip()
        category = row.get('category', '').strip()

        enriched = cache_dict.get(cname, {})
        final_email = enriched.get('email', '')
        final_phone = enriched.get('phone', '')
        final_website = enriched.get('website', '')
        final_fb = enriched.get('fb_link', '')
        
        # Cập nhật địa chỉ nếu Google Maps tìm thấy địa chỉ cụ thể hơn
        final_address = enriched.get('address', '') or address

        export_rows.append({
            'No.': idx,
            'Cong ty': cname,
            'Chuc danh': '',
            'Nguoi lien he': '',
            'SDT': final_phone,
            'Lien He': final_website,
            'Email': final_email,
            'Lien He mail': '',
            'Dia chi': final_address,
            'Luong': '',
            'Ngay dang': '',
            'Han tuyen': '',
            'Check gui': '',
            'Last Subject': '',
            'Last Body HTML': '',
            'Trang thai Reply': '',
            'Lan Follow-up': '',
            'Ngay Follow-up gan nhat': '',
            'Mailbox da dung': '',
            'Category': category,
            'Link FB': final_fb
        })

    with open(OUTPUT_CSV, mode='w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=STANDARD_FIELDNAMES)
        writer.writeheader()
        writer.writerows(export_rows)

    found_emails = sum(1 for r in export_rows if r['Email'])
    found_phones = sum(1 for r in export_rows if r['SDT'])
    found_webs = sum(1 for r in export_rows if r['Lien He'])
    found_fbs = sum(1 for r in export_rows if r['Link FB'])
    print(f"[*] Checkpoint saved to '{OUTPUT_CSV}': {len(export_rows)} rows | {found_emails} Emails | {found_phones} Phones | {found_webs} Websites | {found_fbs} Facebooks")

async def run_enrichment(limit=None):
    if not os.path.exists(SOURCE_CSV):
        print(f"[-] File nguồn không tồn tại: {SOURCE_CSV}")
        return

    with open(SOURCE_CSV, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        all_companies = list(reader)

    print(f"[*] Đã tải {len(all_companies)} công ty từ {SOURCE_CSV}")
    cache = load_cache()
    print(f"[*] Đã tải cache: {len(cache)} công ty đã xử lý")

    # Lọc các dòng chưa có dữ liệu trong cache
    pending_companies = []
    for c in all_companies:
        cname = c.get('name', '').strip()
        if not cname:
            continue
        if cname not in cache or (not cache[cname].get('email') and not cache[cname].get('checked_all')):
            pending_companies.append(c)

    print(f"[*] Cần xử lý: {len(pending_companies)} công ty")
    if limit:
        pending_companies = pending_companies[:limit]
        print(f"[*] Chạy giới hạn {limit} công ty cho phiên test này.")

    if not pending_companies:
        print("[+] Toàn bộ danh sách đã được xử lý xong!")
        export_cold_mail_csv(cache)
        return

    os.makedirs(USER_DATA_DIR, exist_ok=True)

    # CRITICAL: BẮT BUỘC HEADLESS=FALSE để người dùng quan sát trực quan
    async with async_playwright() as p:
        print("[*] Khởi động trình duyệt Google Chrome trực quan (headless=False)...")
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            viewport={"width": 1280, "height": 850},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
                "--no-sandbox"
            ]
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()

        processed_count = 0
        for comp in pending_companies:
            cname = comp.get('name', '').strip()
            town = comp.get('town', '').strip()
            category = comp.get('category', '').strip()
            processed_count += 1

            print(f"\n[{processed_count}/{len(pending_companies)}] Đang xử lý: {cname} ({town})")
            comp_data = cache.get(cname, {
                "website": "", "phone": "", "email": "", "fb_link": "", "address": town, "checked_all": False
            })

            # BƯỚC 1: Tra cứu trên Google Maps
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
                if em:
                    comp_data["email"] = em
                    print(f"      -> 🎯 Email: {em}")
                if ph and not comp_data["phone"]:
                    comp_data["phone"] = ph
                    print(f"      -> 📞 Phone: {ph}")
                if fb:
                    comp_data["fb_link"] = fb
                    print(f"      -> 🌐 Facebook: {fb}")

            comp_data["checked_all"] = True
            cache[cname] = comp_data

            # Lưu checkpoint mỗi 3 công ty
            if processed_count % 3 == 0:
                save_cache(cache)
                export_cold_mail_csv(cache)

            await asyncio.sleep(1)

        # Lưu checkpoint cuối
        save_cache(cache)
        export_cold_mail_csv(cache)
        await browser.close()

    print("\n[+] HOÀN TẤT TIẾN TRÌNH LÀM GIÀU DỮ LIỆU THỊT ĐAN MẠCH!")

if __name__ == '__main__':
    limit_arg = None
    if len(sys.argv) > 1:
        try:
            limit_arg = int(sys.argv[1])
        except ValueError:
            pass
    asyncio.run(run_enrichment(limit=limit_arg))
