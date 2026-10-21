# -*- coding: utf-8 -*-
"""
Playwright Deep Email & Phone Re-Crawler for Austria Agency Dataset (High-Performance Bulletproof DOM Engine):
1. Tự động chuyển đổi sang HTTPS nếu HTTP bị lỗi kết nối (net::ERR_CONNECTION_RESET).
2. Tự động vượt qua Cookie Consent Banners (Borlabs, OneTrust, Usercentrics, Cookiebot) để giải phóng Footer.
3. Cuộn trang mượt mà đa điểm (50% và 100%) để kích hoạt toàn bộ Lazy-Loaded Footer và dynamic content.
4. Quét toàn diện TẤT CẢ các Frames (Frameset / Iframes) trong tài liệu HTML.
5. Bóc tách siêu tốc & toàn diện qua evaluate JavaScript:
   - Quét thẻ a[href*="mailto:"]
   - Quét thẻ a[href*="tel:"] lấy số điện thoại chính thức (thêm dấu nháy đơn ')
   - Bóc tách văn bản Footer chuyên biệt (footer, [class*="footer"], [id*="footer"], .bottom, #bottom)
   - Bóc tách thuộc tính ẩn: [data-email], [data-mail], [title*="@"], [aria-label*="@"]
   - Bóc tách toàn bộ document.body.innerText đã render xong qua JavaScript
   - Giải mã Cloudflare data-cfemail (phép XOR hex)
   - Obfuscated email regex ([at], (at), AT, [dot], (dot), DOT, &#64;, &commat;)
6. Ưu tiên số 1 TUYỆT ĐỐI cho Link Liên hệ thật trên DOM (Priority 25 cho /Impressum, Priority 20 cho /Kontakt...).
7. Fallback đường dẫn chuẩn Áo/Đức (/impressum, /kontakt...) và fallback về Root Domain nếu URL là trang con sâu.
8. Fallback quét Fanpage Facebook qua Googlebot / Desktop page.
9. Chấm điểm B2B Agency Manpower tuyển chọn DUY NHẤT 1 email giá trị nhất.
10. Cơ chế RESET 100%: Tự động xóa bỏ toàn bộ cache rỗng cũ, quét lại toàn bộ các công ty chưa có email.
11. Lưu tăng dần vào AT_AGCY_SHET_1ENR.csv sau mỗi công ty, hỗ trợ Resume an toàn.
"""

import sys
import os
import re
import csv
import json
import time
import html
import asyncio
import urllib.parse
from pathlib import Path
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# Cau hinh UTF-8 cho console Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = str(ROOT_DIR / "AT_AGCY_SHET_1ENR.csv")
if not os.path.exists(INPUT_CSV):
    INPUT_CSV = str(ROOT_DIR / "AT_AGCY_SHET_0RAW.csv")

OUTPUT_CSV = str(ROOT_DIR / "AT_AGCY_SHET_1ENR.csv")
BACKUP_CSV = str(ROOT_DIR / "AT_AGCY_SHET_1ENR_backup.csv")
CACHE_FILE = str(ROOT_DIR / "crawlmail" / "cache_recrawl_emails_at_agcy.json")

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Z|a-z]{2,10}\b')
INVALID_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf', '.css', '.js', '.ico', '.woff', '.woff2', '.mp4', '.mp3', '.ttf')

COOKIE_SELECTORS = [
    '#onetrust-accept-btn-handler',
    '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
    '#CybotCookiebotDialogBodyButtonAccept',
    '.cc-allow',
    '.cc-btn.cc-allow',
    '.cm__btn--accept',
    'button[id*="accept" i]',
    'button[class*="accept" i]',
    'button[id*="cookie" i]',
    'button[class*="cookie" i]',
    'a[class*="cookie" i]',
    'button:has-text("Alle akzeptieren")',
    'button:has-text("Akzeptieren")',
    'button:has-text("Zustimmen")',
    'button:has-text("Einverstanden")',
    'button:has-text("Accept all")',
    'button:has-text("I agree")',
    'button:has-text("Alles akzeptieren")',
    '#cookie-accept',
    '.cookie-accept',
    '.borlabs-cookie-preference',
    '#tarteaucitronPersonalize2'
]

OBFUSCATED_PATTERNS = [
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s*(?:\[at\]|\(at\)|\[@\]|\sat\s)\s*([A-Za-z0-9.-]{1,255})\s*(?:\[dot\]|\(dot\)|\.|\sdot\s)\s*([A-Za-z]{2,10})', re.IGNORECASE),
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s*(?:&#64;|&commat;)\s*([A-Za-z0-9.-]+\.[A-Za-z]{2,10})', re.IGNORECASE),
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s+AT\s+([A-Za-z0-9.-]{1,255})\s+DOT\s+([A-Za-z]{2,10})'),
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s*(?:@|\[at\]|\(at\))\s*([A-Za-z0-9.-]+\.[A-Za-z]{2,10})', re.IGNORECASE),
]

JUNK_EMAIL_DOMAINS = {
    'sentry.io', 'sentry-next.wixpress.com', 'sentry.wixpress.com', 'wixpress.com',
    'wix.com', 'wixsite.com', 'wordpress.com', 'squarespace.com', 'weebly.com',
    'godaddy.com', 'schema.org', 'trustpilot.com', 'google.com', 'facebook.com',
    'instagram.com', 'twitter.com', 'tiktok.com', 'youtube.com', 'linkedin.com',
    'example.com', 'example.org', 'example.net', 'domain.com', 'yourdomain.com',
    'yourcompany.com', 'your-domain.com', 'your-site.com', 'mydomain.com',
    'mycompany.com', 'company.com', 'website.com', 'site.com', 'placeholder.com',
    'sample.com', 'demo.com', 'templatemonster.com', 'themeforest.net', 'envato.com',
    'colorlib.com', 'bootstrapmade.com', 'htmlstream.com', 'nicepage.com', 'mobirise.com',
    'email.com', 'mail.com'
}

SYSTEM_USERNAMES = {
    'noreply', 'no-reply', 'donotreply', 'privacy', 'terms', 'cookies', 'gdpr',
    'abuse', 'security', 'webmaster', 'sentry', 'mailer-daemon', 'test', 'example',
    'hostmaster', 'postmaster', 'root'
}

TEMPLATE_USERNAMES = {
    'youremail', 'your-email', 'your_email', 'your.email',
    'yourname', 'your-name', 'your_name', 'your.name',
    'yourcompany', 'myemail', 'myname',
    'username', 'user', 'name', 'sample', 'demo', 'test', 'testing',
    'placeholder', 'someone', 'nobody',
    'john.doe', 'johndoe', 'jane.doe', 'janedoe',
    'first.last', 'firstname.lastname'
}

TEMPLATE_USERNAME_PATTERNS = [
    re.compile(r'^(your|my)[-_.]?(email|mail|name|domain|company)', re.IGNORECASE),
    re.compile(r'^(sample|demo|test|testing|placeholder|fake|template)', re.IGNORECASE),
    re.compile(r'^(john\.doe|jane\.doe|johndoe|janedoe)$', re.IGNORECASE),
]

def score_email_b2b(email, website_domain=""):
    if not email or not isinstance(email, str):
        return -1
    e = email.replace('%20', '').strip().lower().rstrip('.,;:')
    if not EMAIL_REGEX.match(e):
        return -1
    u, d = e.split('@', 1)

    if d in JUNK_EMAIL_DOMAINS or any(d.endswith('.' + jd) for jd in JUNK_EMAIL_DOMAINS):
        return -1
    if u in SYSTEM_USERNAMES or u in TEMPLATE_USERNAMES:
        return -1
    if any(p.search(u) for p in TEMPLATE_USERNAME_PATTERNS):
        return -1
    if any(k in u for k in ['youremail', 'your-email', 'yourname', 'your-name']):
        return -1
    if u in ['email', 'mail'] and d in ['email.com', 'mail.com', 'domain.com', 'company.com']:
        return -1
    if any(e.endswith(ext) for ext in INVALID_EXTENSIONS):
        return -1

    score = 10

    clean_domain = website_domain.lower().replace('www.', '').split('/')[0] if website_domain else ""
    if clean_domain and (clean_domain in d or d in clean_domain):
        score += 50
    elif d.endswith('.at'):
        score += 20
    elif d.endswith('.de') or d.endswith('.eu'):
        score += 10

    hr_keywords = [
        'karriere', 'jobs', 'bewerbung', 'recruiting', 'recruitment', 'hr', 'personal',
        'personalne', 'praca', 'talent', 'people', 'career', 'careers', 'hiring'
    ]
    if any(u == k or u.startswith(k) for k in hr_keywords):
        score += 50
    elif any(u == k or u.startswith(k) for k in ['geschaeftsfuehrung', 'leitung', 'ceo', 'director', 'manager', 'vertrieb', 'sales', 'management', 'inhaber', 'vorstand']):
        score += 45
    elif any(u == k or u.startswith(k) for k in ['office', 'kontakt', 'contact', 'info', 'zentrale', 'empfang', 'sekretariat', 'kaufmaennisch', 'mail', 'post']):
        score += 40
    elif '.' in u and score >= 60:
        score += 25
    elif d in ['gmail.com', 'gmx.at', 'aon.at', 'chello.at', 'web.de', 'yahoo.com']:
        score += 10
    elif any(u == k or u.startswith(k) for k in ['support', 'admin', 'hilfe', 'service', 'buchhaltung', 'rechnung', 'faktury']):
        score += 5

    return score

def select_best_email(found_emails, website_domain=""):
    if not found_emails:
        return ""
    valid = []
    for em in found_emails:
        s = score_email_b2b(em, website_domain)
        if s > 0:
            valid.append((s, em))
    if not valid:
        return ""
    valid.sort(key=lambda x: x[0], reverse=True)
    return valid[0][1]

def decode_cloudflare_email(hex_str):
    try:
        hex_data = bytes.fromhex(hex_str)
        key = hex_data[0]
        return ''.join(chr(b ^ key) for b in hex_data[1:]).strip().lower()
    except Exception:
        return ""

def extract_cloudflare_emails(html_content):
    if not html_content:
        return []
    emails = []
    for cfemail in re.findall(r'data-cfemail=["\']([0-9a-fA-F]+)["\']', html_content):
        decoded = decode_cloudflare_email(cfemail)
        if decoded and '@' in decoded:
            emails.append(decoded)
    return emails

def extract_emails_from_text(raw_text):
    if not raw_text:
        return []
    text = html.unescape(raw_text)
    emails = set()
    for match in EMAIL_REGEX.findall(text):
        email = match.replace('%20', '').strip().lower().rstrip('.,;:')
        if not any(email.endswith(ext) for ext in INVALID_EXTENSIONS):
            emails.add(email)
    for pattern in OBFUSCATED_PATTERNS:
        for m in pattern.finditer(text):
            if len(m.groups()) == 3:
                email = f"{m.group(1)}@{m.group(2)}.{m.group(3)}".lower()
            elif len(m.groups()) == 2:
                email = f"{m.group(1)}@{m.group(2)}".lower()
            else:
                continue
            if not any(email.endswith(ext) for ext in INVALID_EXTENSIONS):
                emails.add(email)
    return list(emails)

def clean_fb_link(href):
    if not href:
        return None
    h = href.lower()
    if "facebook.com" in h or "fb.com" in h:
        if any(x in h for x in ["share.php", "sharer", "plugins", "dialog", "intent"]):
            return None
        clean = href.split('?')[0].rstrip('/')
        if len(clean.split('/')) > 3:
            return clean
    return None

async def bypass_cookies(page):
    for sel in COOKIE_SELECTORS:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=300):
                await btn.click()
                await page.wait_for_timeout(600)
                break
        except Exception:
            pass

async def scroll_page_smoothly(page):
    """Cuộn trang mượt mà đa điểm để kích hoạt 100% Lazy-Loaded Footer và AJAX scripts."""
    try:
        # Cuộn 50% trang
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        await page.wait_for_timeout(500)
        # Cuộn sát đáy trang
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(800)
    except Exception:
        pass

async def fast_evaluate_page_dom(page):
    """
    Trích xuất toàn diện DOM từ TẤT CẢ các Frames (Frameset, Iframes và Main frame):
    - a[href*="mailto:"]
    - a[href*="tel:"]
    - Các vùng Footer chuyên biệt
    - Các thuộc tính ẩn chứa email ([data-email], [data-mail], [title*="@"], [aria-label*="@"])
    - InnerText và HTML đầy đủ
    """
    mailtos = []
    tels = []
    links = []
    body_texts = []
    footer_texts = []
    htmls = []
    attr_emails = []

    for frame in page.frames:
        try:
            res = await frame.evaluate('''() => {
                const mailtos = Array.from(document.querySelectorAll('a[href*="mailto:"]')).map(a => a.href);
                const tels = Array.from(document.querySelectorAll('a[href*="tel:"]')).map(a => a.href);
                const links = Array.from(document.querySelectorAll('a[href]')).map(a => ({
                    href: a.href,
                    text: (a.innerText || a.textContent || '').trim().replace(/\\s+/g, ' ')
                }));
                const bodyText = document.body ? (document.body.innerText || document.body.textContent || '') : '';
                const html = document.documentElement ? document.documentElement.outerHTML : '';

                // Bóc tách footer và các container liên hệ chuyên biệt
                let footerText = '';
                const footerSelectors = [
                    'footer', '[class*="footer" i]', '[id*="footer" i]', 
                    '.bottom', '#bottom', '[class*="impressum" i]', '[id*="impressum" i]',
                    '[class*="contact" i]', '[id*="contact" i]',
                    '[class*="kontakt" i]', '[id*="kontakt" i]'
                ];
                document.querySelectorAll(footerSelectors.join(', ')).forEach(f => {
                    footerText += ' ' + (f.innerText || f.textContent || '');
                });

                // Quét email trong attributes
                const attrMails = [];
                document.querySelectorAll('[data-email], [data-mail], [title*="@"], [aria-label*="@"]').forEach(el => {
                    if (el.getAttribute('data-email')) attrMails.push(el.getAttribute('data-email'));
                    if (el.getAttribute('data-mail')) attrMails.push(el.getAttribute('data-mail'));
                    if (el.getAttribute('title')) attrMails.push(el.getAttribute('title'));
                    if (el.getAttribute('aria-label')) attrMails.push(el.getAttribute('aria-label'));
                });

                return { mailtos, tels, links, bodyText, footerText, html, attrMails };
            }''')
            if res:
                mailtos.extend(res.get('mailtos', []))
                tels.extend(res.get('tels', []))
                links.extend(res.get('links', []))
                attr_emails.extend(res.get('attrMails', []))
                if res.get('bodyText'):
                    body_texts.append(res['bodyText'])
                if res.get('footerText'):
                    footer_texts.append(res['footerText'])
                if res.get('html'):
                    htmls.append(res['html'])
        except Exception:
            pass

    return {
        'mailtos': mailtos,
        'tels': tels,
        'links': links,
        'attr_emails': attr_emails,
        'bodyText': '\n'.join(body_texts),
        'footerText': '\n'.join(footer_texts),
        'html': '\n'.join(htmls)
    }

async def crawl_facebook_fanpage(page, fb_url):
    desktop_url = fb_url
    if "m.facebook.com" in desktop_url:
        desktop_url = desktop_url.replace("m.facebook.com", "www.facebook.com")
    elif "facebook.com" in desktop_url and "www.facebook.com" not in desktop_url:
        desktop_url = desktop_url.replace("facebook.com", "www.facebook.com")

    if not desktop_url.startswith(('http://', 'https://')):
        desktop_url = 'https://' + desktop_url

    emails = []
    try:
        await page.goto(desktop_url, timeout=20000, wait_until="commit")
        await page.wait_for_timeout(3000)
        dom_data = await fast_evaluate_page_dom(page)
        for m in dom_data['mailtos']:
            e = urllib.parse.unquote(m.replace('mailto:', '')).split('?')[0].replace('%20', '').strip().lower()
            if '@' in e and '.' in e:
                emails.append(e)
        emails.extend(extract_emails_from_text(dom_data['bodyText']))
        emails.extend(extract_emails_from_text(dom_data['html']))
    except Exception:
        pass

    return list(set(emails))

async def deep_crawl_website_playwright(page, website_url):
    """
    Quy trình cào Playwright chuyên sâu chuẩn mực:
    1. Tự động fallback HTTPS nếu HTTP bị lỗi kết nối hoặc reset.
    2. Tự động bypass Cookie Consent Dialog.
    3. Cuộn trang mượt mà kích hoạt Lazy-Loaded Footers.
    4. Trích xuất đồng thời Homepage & Footer & Attributes & All Frames.
    5. Theo dõi link THẬT trên DOM menu liên hệ (Ưu tiên Impressum, Kontakt).
    6. Fallback Guess Paths nếu menu không có link trực tiếp.
    7. Fallback Root Domain nếu URL ban đầu là subpage sâu.
    8. Fallback Facebook Fanpage.
    """
    target_url = website_url.strip()
    if not target_url.startswith(('http://', 'https://')):
        target_url = 'http://' + target_url

    parsed = urllib.parse.urlparse(target_url)
    domain = parsed.netloc.lower().replace('www.', '')

    all_emails = set()
    all_phones = []
    fb_links = set()

    # 1. Truy cập Trang chủ (kèm cơ chế HTTPS Retry)
    print(f"    [*] Loading Homepage: {target_url}...")
    loaded = False
    for attempt_url in [target_url, target_url.replace('http://', 'https://') if 'http://' in target_url else target_url]:
        try:
            await page.goto(attempt_url, timeout=22000, wait_until="domcontentloaded")
            await bypass_cookies(page)
            await scroll_page_smoothly(page)
            loaded = True
            target_url = attempt_url
            break
        except Exception as e:
            if 'http://' in attempt_url:
                print(f"    [*] HTTP bi reset -> Dang thu lai voi HTTPS: {attempt_url.replace('http://', 'https://')}")
            else:
                print(f"    [-] Load Homepage that bai: {e}")

    if not loaded:
        return "", ""

    # Trích xuất dữ liệu trang chủ qua JS Evaluate siêu tốc từ TẤT CẢ FRAMES
    data = await fast_evaluate_page_dom(page)

    # a. Mailto links
    for m in data['mailtos']:
        e = urllib.parse.unquote(m.replace('mailto:', '')).split('?')[0].replace('%20', '').strip().lower()
        if '@' in e and '.' in e:
            all_emails.add(e)

    # b. Tel links
    for t in data['tels']:
        p_raw = urllib.parse.unquote(t.replace('tel:', '')).split('?')[0].strip()
        p_clean = re.sub(r'[^\d+]', '', p_raw)
        if p_clean and len(p_clean) >= 7:
            all_phones.append(f"'{p_clean}")

    # c. Footer Text, Attributes & Body Text
    for e in extract_emails_from_text(data['footerText']):
        all_emails.add(e)
    for e in data['attr_emails']:
        for sub_e in extract_emails_from_text(e):
            all_emails.add(sub_e)
    for e in extract_emails_from_text(data['bodyText']):
        all_emails.add(e)

    # d. Cloudflare hex
    for e in extract_cloudflare_emails(data['html']):
        all_emails.add(e)

    # e. Facebook links
    for l in data['links']:
        fb = clean_fb_link(l['href'])
        if fb:
            fb_links.add(fb)

    # Kiểm tra nếu trang chủ đã có email B2B điểm cao
    best_cand = select_best_email(all_emails, domain)
    has_high_score_email = best_cand and score_email_b2b(best_cand, domain) >= 60

    # 2. Khám phá Subpages từ LINK THẬT TRÊN DOM (Priority 25: Impressum, 20: Kontakt...)
    allowed_domains = {domain}
    for f in page.frames:
        fn = urllib.parse.urlparse(f.url).netloc.lower().replace('www.', '')
        if fn:
            allowed_domains.add(fn)

    real_contact_links = []
    seen_urls = {target_url.rstrip('/')}

    for l in data['links']:
        h = l['href'].split('#')[0].rstrip('/')
        t = l['text'].lower()
        h_lower = h.lower()

        if not h.startswith(('http://', 'https://')):
            continue

        p_cand = urllib.parse.urlparse(h)
        cand_domain = p_cand.netloc.lower().replace('www.', '')
        if cand_domain in allowed_domains:
            if h not in seen_urls:
                seen_urls.add(h)
                priority = 1
                # Ưu tiên cao nhất tại Áo & Đức là IMPRESSUM (luật định bắt buộc có email chính thức)
                if any(k in t or k in h_lower for k in ['impressum', 'kontakt', 'contact', 'standorte', 'anfahrt']):
                    priority = 25
                elif any(k in t or k in h_lower for k in ['karriere', 'jobs', 'bewerbung', 'recruiting', 'personal', 'hr']):
                    priority = 20
                elif any(k in t or k in h_lower for k in ['ueber-uns', 'wir-ueber-uns', 'team', 'about', 'unternehmen']):
                    priority = 15
                elif any(k in t or k in h_lower for k in ['service', 'dienstleistung']):
                    priority = 10

                if priority >= 10:
                    real_contact_links.append((priority, h))

    real_contact_links.sort(key=lambda x: x[0], reverse=True)

    # Nếu chưa có email chất lượng cao, duyệt tối đa 6 trang con liên hệ thật
    if not has_high_score_email:
        for prio, sub_url in real_contact_links[:6]:
            try:
                print(f"    [*] Visiting Real DOM Subpage: {sub_url}...")
                await page.goto(sub_url, timeout=18000, wait_until="domcontentloaded")
                await bypass_cookies(page)
                await scroll_page_smoothly(page)

                sub_data = await fast_evaluate_page_dom(page)

                for m in sub_data['mailtos']:
                    e = urllib.parse.unquote(m.replace('mailto:', '')).split('?')[0].replace('%20', '').strip().lower()
                    if '@' in e and '.' in e:
                        all_emails.add(e)

                for t in sub_data['tels']:
                    p_raw = urllib.parse.unquote(t.replace('tel:', '')).split('?')[0].strip()
                    p_clean = re.sub(r'[^\d+]', '', p_raw)
                    if p_clean and len(p_clean) >= 7:
                        all_phones.append(f"'{p_clean}")

                for e in extract_emails_from_text(sub_data['footerText']):
                    all_emails.add(e)
                for e in sub_data['attr_emails']:
                    for sub_e in extract_emails_from_text(e):
                        all_emails.add(sub_e)
                for e in extract_emails_from_text(sub_data['bodyText']):
                    all_emails.add(e)
                for e in extract_cloudflare_emails(sub_data['html']):
                    all_emails.add(e)

                cand = select_best_email(all_emails, domain)
                if cand and score_email_b2b(cand, domain) >= 60:
                    break
            except Exception:
                continue

    # 3. Fallback: Nếu vẫn chưa có email, thử các đường dẫn chuẩn đoán trước (Guess Paths)
    cand = select_best_email(all_emails, domain)
    if not cand:
        base_origin = f"{parsed.scheme}://{parsed.netloc}".rstrip('/')
        guess_subpaths = [
            "/impressum", "/impressum.html", "/impressum.php", "/impressum/",
            "/kontakt", "/kontakt.html", "/kontakt.php", "/kontakt/",
            "/ueber-uns", "/karriere"
        ]
        for sp in guess_subpaths:
            guess_url = base_origin + sp
            if guess_url in seen_urls:
                continue
            seen_urls.add(guess_url)
            try:
                print(f"    [*] Trying Guess Path: {guess_url}...")
                await page.goto(guess_url, timeout=12000, wait_until="domcontentloaded")
                await bypass_cookies(page)
                await scroll_page_smoothly(page)
                g_data = await fast_evaluate_page_dom(page)
                for m in g_data['mailtos']:
                    e = urllib.parse.unquote(m.replace('mailto:', '')).split('?')[0].replace('%20', '').strip().lower()
                    if '@' in e and '.' in e:
                        all_emails.add(e)
                for e in extract_emails_from_text(g_data['footerText']):
                    all_emails.add(e)
                for e in extract_emails_from_text(g_data['bodyText']):
                    all_emails.add(e)
                for e in extract_cloudflare_emails(g_data['html']):
                    all_emails.add(e)
                cand = select_best_email(all_emails, domain)
                if cand:
                    break
            except Exception:
                continue

    # 4. Fallback: Nếu URL ban đầu là subpage sâu (vd: /Projekte?cat2=8) và chưa có email -> kiểm tra Root Homepage
    cand = select_best_email(all_emails, domain)
    if not cand and parsed.path and parsed.path not in ('', '/'):
        root_homepage = f"{parsed.scheme}://{parsed.netloc}/"
        if root_homepage not in seen_urls:
            seen_urls.add(root_homepage)
            try:
                print(f"    [*] Fallback to Root Domain Homepage: {root_homepage}...")
                await page.goto(root_homepage, timeout=15000, wait_until="domcontentloaded")
                await bypass_cookies(page)
                await scroll_page_smoothly(page)
                r_data = await fast_evaluate_page_dom(page)
                for m in r_data['mailtos']:
                    e = urllib.parse.unquote(m.replace('mailto:', '')).split('?')[0].replace('%20', '').strip().lower()
                    if '@' in e and '.' in e:
                        all_emails.add(e)
                for e in extract_emails_from_text(r_data['footerText']):
                    all_emails.add(e)
                for e in extract_emails_from_text(r_data['bodyText']):
                    all_emails.add(e)
            except Exception:
                pass

    # 5. Fallback: Facebook Fanpage nếu vẫn chưa có email
    final_email = select_best_email(all_emails, domain)
    if not final_email and fb_links:
        for fb_url in list(fb_links)[:2]:
            print(f"    [*] Fallback Scanning Facebook Fanpage: {fb_url}...")
            fb_emails = await crawl_facebook_fanpage(page, fb_url)
            if fb_emails:
                for fe in fb_emails:
                    all_emails.add(fe)
                final_email = select_best_email(all_emails, domain)
                if final_email:
                    print(f"       [+] Tim thay email tren Facebook: {final_email}")
                    break

    final_phone = all_phones[0] if all_phones else ""
    return final_email, final_phone

def load_cache():
    """Khi o che do RESET, chi giu lai nhung domain DA CO EMAIL thanh cong, xoa bo 100% cache rong."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                old_cache = json.load(f)
                clean_cache = {k: v for k, v in old_cache.items() if v.get("email")}
                print(f"[*] Reset Cache: Giu lai {len(clean_cache)} domain da co email hop le, xoa sach cache rong cu.")
                return clean_cache
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
        print(f"[-] Khong tim thay file du lieu: {INPUT_CSV}")
        return

    import shutil
    if not os.path.exists(BACKUP_CSV):
        shutil.copy2(INPUT_CSV, BACKUP_CSV)
        print(f"[*] Da sao luu {INPUT_CSV} sang {BACKUP_CSV}")

    # Load cache (tu dong thanh loc toan bo key rong)
    cache = load_cache()
    # Ghi lai ngay file cache da duoc lam sach
    save_cache(cache)

    with open(INPUT_CSV, 'r', encoding='utf-8-sig', errors='ignore') as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    for r in rows:
        p = r.get("SĐT", "").strip()
        if p and not p.startswith("'"):
            r["SĐT"] = f"'{p}"

    # Loc cac dong thieu email
    targets = []
    for idx, r in enumerate(rows):
        web = (r.get("Liên Hệ") or r.get("Website") or "").strip()
        mail = r.get("Email", "").strip()
        if web and web.startswith(('http://', 'https://')) and not mail:
            targets.append((idx, r))

    print("=" * 80)
    print("QUY TRINH PLAYWRIGHT DEEP EMAIL & PHONE CRAWLER (BULLETPROOF DOM ENGINE)")
    print(f"Tong so doanh nghiep trong file: {len(rows)}")
    print(f"So doanh nghiep da co Website nhung THIEU EMAIL: {len(targets)}")
    print(f"[!] CHE DO RESET / RETRY-EMPTY: Tu dong quet lai 100% cac website chua co email!")
    print(f"File xuat: {OUTPUT_CSV}")
    print("=" * 80)

    if not targets:
        print("[+] Tat ca cac doanh nghiep co website da co email day du! Khong can quet lai.")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            locale="de-AT"
        )
        page = await context.new_page()
        await stealth_async(page)

        enriched_count = 0
        for current_idx, (row_idx, row) in enumerate(targets):
            company = row.get("Công ty", "").strip()
            web = (row.get("Liên Hệ") or row.get("Website") or "").strip()
            phone = row.get("SĐT", "").strip()

            print(f"\n[{current_idx+1}/{len(targets)}] [*] Doanh nghiep: '{company}'")
            print(f"    Website: {web}")

            domain = urllib.parse.urlparse(web).netloc.lower().replace('www.', '')
            if domain in cache and cache[domain].get("email"):
                cached_email = cache[domain].get("email")
                row["Email"] = cached_email
                print(f"    [+] Nhan tu Cache Email hop le: {cached_email}")
                enriched_count += 1
                save_csv(rows, fieldnames, OUTPUT_CSV)
                continue

            found_email, found_phone = await deep_crawl_website_playwright(page, web)

            updated = False
            if found_email:
                row["Email"] = found_email
                print(f"    [+] B2B Email tim thay ({company}): {found_email}")
                updated = True
                enriched_count += 1
                # Chi luu vao cache neu co email hop le
                cache[domain] = {"email": found_email, "phone": found_phone}
                save_cache(cache)

            if not phone and found_phone:
                row["SĐT"] = found_phone
                print(f"    [+] SĐT tim thay: {found_phone}")
                updated = True

            if updated:
                save_csv(rows, fieldnames, OUTPUT_CSV)
                print(f"    [+] CAP NHAT THANH CONG!")
            else:
                print(f"    [-] Website khong co email cong khai.")

            if (current_idx + 1) % 5 == 0:
                save_csv(rows, fieldnames, OUTPUT_CSV)

        await browser.close()

    save_csv(rows, fieldnames, OUTPUT_CSV)
    print("\n" + "=" * 80)
    print("HOAN TAT QUET LAI EMAIL QUA PLAYWRIGHT!")
    print(f"Tong so email moi tim thay: {enriched_count}/{len(targets)}")
    print(f"File cap nhat: {OUTPUT_CSV}")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
