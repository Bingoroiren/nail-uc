import asyncio
import csv
import os
import re
import urllib.parse
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
import sys

# Set Windows Proactor Event Loop Policy for robust subprocess piping
if sys.platform == 'win32':
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception as e:
        print(f"[WARNING] Could not set WindowsProactorEventLoopPolicy: {e}")

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

# File paths (default or from CLI args)
INPUT_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "nail_salons_australia.csv")
OUTPUT_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "nail_salons_with_emails.csv")

# Parse retry-empty option
RETRY_EMPTY = "--retry-empty" in sys.argv
if RETRY_EMPTY:
    sys.argv.remove("--retry-empty")

if len(sys.argv) > 2:
    INPUT_CSV = sys.argv[1]
    OUTPUT_CSV = sys.argv[2]
elif len(sys.argv) == 2:
    print("Usage: python email_scraper.py [input_csv] [output_csv] [--retry-empty]")
    sys.exit(1)

# Ensure output directory exists
out_dir = os.path.dirname(os.path.abspath(OUTPUT_CSV))
if out_dir:
    os.makedirs(out_dir, exist_ok=True)

# Email Regex & Invalid list
EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Z|a-z]{2,7}\b')
INVALID_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf', '.css', '.js', '.ico', '.woff', '.woff2', '.mp4', '.mp3')

# Obfuscated email patterns (e.g. info [at] domain [dot] com)
# Use bounded quantifiers to prevent catastrophic backtracking on large HTML/JS strings
OBFUSCATED_PATTERNS = [
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s*\[at\]\s*([A-Za-z0-9.-]{1,255})\s*\[dot\]\s*([A-Za-z]{2,7})', re.IGNORECASE),
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s*\(at\)\s*([A-Za-z0-9.-]{1,255})\s*\(dot\)\s*([A-Za-z]{2,7})', re.IGNORECASE),
    re.compile(r'([A-Za-z0-9._%+-]{1,64})\s+AT\s+([A-Za-z0-9.-]{1,255})\s+DOT\s+([A-Za-z]{2,7})'),
]

# Common contact & recruitment page paths to guess if no emails found (Central European & Global)
CONTACT_PAGE_GUESSES = [
    # Slovakia, Czech Republic, Central Europe - Contact & Recruitment
    '/kontakt', '/kontakt.html', '/kontakt.php',
    '/kontakty', '/kontakty.html',
    '/kariera', '/kariera.html', '/kariera.php',
    '/praca', '/praca.html', '/praca.php',
    '/o-nas', '/o-nas.html', '/onas.html',
    '/napiste-nam', '/impressum',
    # Global / English
    '/contact', '/contact-us', '/contact.html',
    '/careers', '/career', '/jobs',
    '/about', '/about-us', '/about.html',
    '/get-in-touch',
]

JUNK_EMAIL_DOMAINS = {
    # System & Tracking
    'sentry.io', 'sentry-next.wixpress.com', 'sentry.wixpress.com', 'wixpress.com',
    'wix.com', 'wixsite.com', 'wordpress.com', 'squarespace.com', 'weebly.com',
    'godaddy.com', 'schema.org', 'trustpilot.com', 'google.com', 'facebook.com',
    'instagram.com', 'twitter.com', 'tiktok.com', 'youtube.com', 'linkedin.com',
    # Templates, Themes & Placeholders
    'example.com', 'example.org', 'example.net', 'domain.com', 'yourdomain.com',
    'yourcompany.com', 'your-domain.com', 'your-site.com', 'mydomain.com',
    'mycompany.com', 'company.com', 'website.com', 'site.com', 'placeholder.com',
    'sample.com', 'demo.com', 'templatemonster.com', 'themeforest.net', 'envato.com',
    'colorlib.com', 'bootstrapmade.com', 'htmlstream.com', 'nicepage.com', 'mobirise.com'
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
    """
    Chấm điểm email tối ưu cho B2B Manpower Agency (Môi giới lao động B2B):
    - Tuyệt đối ưu tiên: Bộ phận Nhân sự / Tuyển dụng / Việc làm (HR, Recruitment).
    - Ưu tiên cao: Ban Giám đốc / Điều hành (CEO, Vedenie, Director) & Bộ phận thông tin (Info, Kontakt, Office).
    - Trả về -1 nếu là mail rác, mail template hoặc file giả mạo.
    """
    if not email or not isinstance(email, str):
        return -1
    e = email.replace('%20', '').strip().lower().rstrip('.,;:')
    if not EMAIL_REGEX.match(e):
        return -1
    u, d = e.split('@', 1)

    # 1. Loại trừ blacklist & mail template / demo
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

    # 2. Thưởng điểm trùng domain website (+50đ)
    clean_domain = website_domain.lower().replace('www.', '').split('/')[0] if website_domain else ""
    if clean_domain and (clean_domain in d or d in clean_domain):
        score += 50

    # 3. ƯU TIÊN SỐ 1: Bộ phận Nhân sự / Tuyển dụng / Việc làm (+50đ) -> Trúng đích 100% Agency lao động!
    if u in ['praca', 'kariera', 'hr', 'personalne', 'jobs', 'recruitment', 'nabor', 'zamestnanie', 'career', 'careers', 'talent', 'people', 'rekrutacja']:
        score += 50
    # 4. ƯU TIÊN SỐ 2: Ban Giám đốc / Lãnh đạo điều hành (+45đ) -> Người quyết định hợp đồng cung ứng!
    elif u in ['vedenie', 'riaditel', 'konatel', 'ceo', 'director', 'manager', 'obchod', 'sales', 'management', 'owner']:
        score += 45
    # 5. ƯU TIÊN SỐ 3: Cổng liên hệ chính thức / Bộ phận thông tin (+40đ) -> Cổng kết nối B2B chính thức!
    elif u in ['info', 'kontakt', 'contact', 'office', 'biuro', 'sekretariat', 'recepcia', 'kancelaria', 'mail']:
        score += 40
    # 6. Email đích danh cá nhân theo domain riêng (+25đ)
    elif '.' in u and score >= 60:
        score += 25
    # 7. Webmail miễn phí (+10đ - chỉ nhận nếu không có mail domain riêng)
    elif d in ['gmail.com', 'seznam.cz', 'zoznam.sk', 'post.sk', 'azet.sk']:
        score += 10
    # 8. Email kỹ thuật / hỗ trợ chung (+5đ)
    elif u in ['support', 'admin', 'help', 'webmaster']:
        score += 5

    return score



def extract_emails_from_text(text):
    if not text:
        return []
    emails = set()
    for match in EMAIL_REGEX.findall(text):
        email = match.strip().lower()
        if not any(email.endswith(ext) for ext in INVALID_EXTENSIONS):
            emails.add(email)
    # Also check for obfuscated emails
    for pattern in OBFUSCATED_PATTERNS:
        for m in pattern.finditer(text):
            email = f"{m.group(1)}@{m.group(2)}.{m.group(3)}".lower()
            if not any(email.endswith(ext) for ext in INVALID_EXTENSIONS):
                emails.add(email)
    return list(emails)

def decode_cloudflare_email(hex_str):
    try:
        hex_data = bytes.fromhex(hex_str)
        key = hex_data[0]
        return ''.join(chr(b ^ key) for b in hex_data[1:])
    except Exception:
        return ""

def extract_cloudflare_emails(html):
    if not html:
        return []
    emails = []
    for cfemail in re.findall(r'data-cfemail="([0-9a-fA-F]+)"', html):
        decoded = decode_cloudflare_email(cfemail)
        if decoded and '@' in decoded:
            emails.append(decoded.strip().lower())
    return emails


def clean_fb_link(href):
    if not href:
        return None
    href_lower = href.lower()
    if "facebook.com" in href_lower:
        if any(x in href_lower for x in ["share.php", "sharer.php", "facebook.com/sharer", "facebook.com/dialog", "facebook.com/plugins"]):
            return None
        return href
    return None

def clean_ig_link(href):
    if not href:
        return None
    href_lower = href.lower()
    if "instagram.com" in href_lower:
        if any(x in href_lower for x in ["developer", "about", "press", "directory"]):
            return None
        return href
    return None

async def crawl_facebook(page, url):
    # Convert standard or mobile facebook links to www.facebook.com for desktop rendering with Googlebot
    desktop_url = url
    if "m.facebook.com" in desktop_url:
        desktop_url = desktop_url.replace("m.facebook.com", "www.facebook.com")
    elif "facebook.com" in desktop_url and "www.facebook.com" not in desktop_url:
        desktop_url = desktop_url.replace("facebook.com", "www.facebook.com")
    
    if not desktop_url.startswith(('http://', 'https://')):
        desktop_url = 'https://' + desktop_url

    emails = []
    try:
        print(f"[*] Navigating to Facebook (Googlebot): {desktop_url}")
        await page.goto(desktop_url, timeout=25000, wait_until="commit")
        await page.wait_for_timeout(5000)
    except Exception as e:
        print(f"[-] Facebook load failed ({url}): {e}")
        return []

    # 1. Search mailto links
    try:
        mailto_links = await page.locator('a[href^="mailto:"]').all()
        for link in mailto_links:
            href = await link.get_attribute("href")
            if href:
                email = href.replace("mailto:", "").split("?")[0].strip().lower()
                if not any(email.endswith(ext) for ext in INVALID_EXTENSIONS):
                    emails.append(email)
    except Exception:
        pass

    # 2. Search body text (DOM contains background content under login dialog)
    try:
        body_text = await page.locator("body").inner_text()
        emails.extend(extract_emails_from_text(body_text))
    except Exception:
        pass

    # Search Cloudflare emails
    try:
        html = await page.content()
        emails.extend(extract_cloudflare_emails(html))
    except Exception:
        pass

    return list(set(emails))

async def crawl_instagram(page, url):
    target_url = url
    if not target_url.startswith(('http://', 'https://')):
        target_url = 'https://' + target_url

    try:
        print(f"[*] Navigating to Instagram: {target_url}")
        await page.goto(target_url, timeout=25000, wait_until="commit")
        
        # Wait up to 10s for splash screen to disappear and bio/login elements to render
        for _ in range(10):
            await page.wait_for_timeout(1000)
            body_text = await page.locator("body").inner_text()
            if "Log In" in body_text or "followers" in body_text or "Profile isn't available" in body_text:
                break
    except Exception as e:
        print(f"[-] Instagram load failed ({url}): {e}")
        return []

    emails = []
    try:
        body_text = await page.locator("body").inner_text()
        emails.extend(extract_emails_from_text(body_text))
    except Exception:
        pass

    try:
        html = await page.content()
        emails.extend(extract_cloudflare_emails(html))
    except Exception:
        pass

    return list(set(emails))

async def safe_scroll_to_bottom(page):
    """Safely scroll to the bottom of the page to trigger lazy-loaded content."""
    try:
        await page.evaluate("if (document.body) window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1000)
    except Exception:
        pass

async def crawl_regular_site(page, url):
    try:
        print(f"[*] Navigating to Website: {url}")
        await page.goto(url, timeout=25000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await safe_scroll_to_bottom(page)
        try:
            title = await page.title()
            print(f"[*] Page loaded. Title: {title}")
        except Exception:
            pass
    except Exception as e:
        print(f"[-] Website load failed ({url}): {e}")
        return [], [], []

    emails = []
    fb_links = set()
    ig_links = set()
    
    # Extract links helper
    async def extract_links_and_emails(current_page):
        # 1. Search mailto
        try:
            mailto_links = await current_page.locator('a[href^="mailto:"]').all()
            for link in mailto_links:
                href = await link.get_attribute("href")
                if href:
                    email = href.replace("mailto:", "").split("?")[0].strip().lower()
                    if not any(email.endswith(ext) for ext in INVALID_EXTENSIONS):
                        emails.append(email)
        except Exception:
            pass

        # 2. Search body text (visible content)
        try:
            body_text = await current_page.locator("body").inner_text()
            found = extract_emails_from_text(body_text)
            if found:
                emails.extend(found)
                print(f"[+] Found in body_text on {current_page.url}: {found}")
            else:
                print(f"[-] No emails in body_text on {current_page.url}. Body text length: {len(body_text)}")
        except Exception as e:
            print(f"[-] Body text extraction error on {current_page.url}: {e}")

        # Search Cloudflare obfuscated emails and raw HTML source using a single content fetch
        try:
            html = await current_page.content()
            emails.extend(extract_cloudflare_emails(html))
            html_emails = extract_emails_from_text(html)
            emails.extend(html_emails)
        except Exception:
            pass

        # 4. Harvest social media links (FB/IG)
        try:
            links = await current_page.locator('a[href]').all()
            for link in links:
                href = await link.get_attribute("href")
                if href:
                    fb = clean_fb_link(href)
                    ig = clean_ig_link(href)
                    if fb: fb_links.add(fb)
                    if ig: ig_links.add(ig)
        except Exception:
            pass

    # Process homepage
    await extract_links_and_emails(page)

    # Search subpages if no emails found yet
    emails = list(set(emails))
    if not emails:
        # Fallback wait for slow SPA/React rendering under concurrent CPU load
        await page.wait_for_timeout(2000)
        await extract_links_and_emails(page)
        emails = list(set(emails))
        
    if not emails:
        candidate_links = []
        try:
            links = await page.locator('a[href]').all()
            for link in links:
                href = await link.get_attribute("href")
                text = await link.inner_text()
                text_lower = text.lower() if text else ""
                href_lower = href.lower() if href else ""
                
                if href and not href_lower.startswith(('mailto:', 'tel:', 'javascript:', '#')):
                    full_url = urllib.parse.urljoin(url, href)
                    if urllib.parse.urlparse(full_url).netloc == urllib.parse.urlparse(url).netloc:
                        full_url_clean = full_url.split('#')[0]
                        priority = 1
                        if any(k in text_lower or k in href_lower for k in [
                            # HR & Recruitment (Highest B2B Agency value)
                            'kariera', 'praca', 'nabor', 'personalne', 'zamestnanie',
                            'career', 'careers', 'jobs', 'recruitment', 'hr', 'hiring',
                            # Official Contact & Info
                            'kontakt', 'contact', 'kontakty', 'napiste', 'impressum',
                            'about', 'o-nas', 'onas', 'support', 'reach', 'info',
                            'location', 'salon', 'find', 'store', 'mums', 'sobre',
                            'επικοινων', 'epikoinon', '聯絡', '關於', '关于', '联系',
                            'contat', 'team', 'enquir', 'inquiry'
                        ]):
                            priority = 10  # Highest priority: Real contact & recruitment links in website navigation
                        elif any(k in text_lower or k in href_lower for k in [
                            'services', 'sluzby', 'book', 'us', 'pakalpojumi',
                            'servicos', 'υπηρεσιες', '服務', '服务', 'help', 'footer', 'sitemap'
                        ]):
                            priority = 5
                        
                        candidate_links.append((priority, full_url_clean))
        except Exception:
            pass

        # Fallback guesses for common contact pages (priority 2: only after real links)
        parsed_base = urllib.parse.urlparse(url)
        base_origin = f"{parsed_base.scheme}://{parsed_base.netloc}"
        for guess_path in CONTACT_PAGE_GUESSES:
            guess_url = base_origin + guess_path
            candidate_links.append((2, guess_url))

        candidate_links.sort(key=lambda x: x[0], reverse=True)
        unique_sub_urls = []
        for priority, sub_url in candidate_links:
            clean_sub = sub_url.rstrip('/')
            if clean_sub not in [u.rstrip('/') for u in unique_sub_urls] and clean_sub != url.rstrip('/'):
                unique_sub_urls.append(sub_url)

        # Scrape up to 8 subpages (prioritizing real contact links)
        for sub_url in unique_sub_urls[:8]:
            try:
                print(f"[*] Navigating to Subpage: {sub_url}")
                await page.goto(sub_url, timeout=15000, wait_until="domcontentloaded")
                await page.wait_for_timeout(1000)
                await safe_scroll_to_bottom(page)
                await extract_links_and_emails(page)
                # Stop early if emails found
                if list(set(emails)):
                    break
            except Exception:
                pass

    return list(set(emails)), list(fb_links), list(ig_links)

def save_progress(rows, path, fieldnames):
    temp_path = path + ".tmp"
    try:
        with open(temp_path, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
        os.rename(temp_path, path)
    except Exception as e:
        print(f"[-] Error saving progress to {path}: {e}")

async def process_row(row, semaphore, writer, output_file, processed_urls):
    url = row.get('URL') or row.get('Liên Hệ') or ''
    website = (row.get('Website') or row.get('Liên Hệ') or '').strip()
    
    if url in processed_urls:
        return

    if not website:
        row['Email'] = ''
        if writer:
            try:
                writer.writerow(row)
                output_file.flush()
            except Exception:
                pass
        if url:
            processed_urls.add(url)
        return

    async with semaphore:
        is_fb = "facebook.com" in website.lower()
        is_ig = "instagram.com" in website.lower()
        
        emails = []
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                
                # 1. Setup Context based on website type
                if is_fb:
                    context = await browser.new_context(
                        user_agent="Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                        viewport={"width": 1280, "height": 800}
                    )
                elif is_ig:
                    context = await browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        viewport={"width": 1280, "height": 800}
                    )
                else:
                    context = await browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        viewport={"width": 1280, "height": 800}
                    )
                
                page = await context.new_page()
                page.set_default_timeout(30000)
                page.set_default_navigation_timeout(30000)
                
                # 2. Define nested scrape logic to run with a global timeout
                async def do_scrape():
                    nonlocal page, context
                    fb_fallback_links = []
                    ig_fallback_links = []
                    found_emails = []
                    
                    if is_fb:
                        found_emails = await crawl_facebook(page, website)
                    elif is_ig:
                        found_emails = await crawl_instagram(page, website)
                    else:
                        target_url = website
                        if not target_url.startswith(('http://', 'https://')):
                            target_url = 'https://' + target_url
                        found_emails, fb_fallback_links, ig_fallback_links = await crawl_regular_site(page, target_url)
                    
                    # 3. Fallback social crawling if regular website had no emails but had social page links
                    if not is_fb and not is_ig and not found_emails and (fb_fallback_links or ig_fallback_links):
                        print(f"[*] Fallback: No emails found on {website}. Scanning social pages...")
                        
                        # Close regular website page/context
                        if page: await page.close()
                        if context: await context.close()
                        page = None
                        context = None
                        
                        # Check Facebook fallback pages
                        for fb_url in fb_fallback_links:
                            try:
                                context = await browser.new_context(
                                    user_agent="Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                                    viewport={"width": 1280, "height": 800}
                                )
                                page = await context.new_page()
                                page.set_default_timeout(30000)
                                page.set_default_navigation_timeout(30000)
                                fb_emails = await crawl_facebook(page, fb_url)
                                if fb_emails:
                                    found_emails.extend(fb_emails)
                                    print(f"[+] Fallback Facebook success: {fb_url} -> {fb_emails}")
                                    break
                            except Exception as e:
                                print(f"[-] Fallback Facebook failed ({fb_url}): {e}")
                            finally:
                                if page: await page.close()
                                if context: await context.close()
                                page = None
                                context = None
                        
                        # Check Instagram fallback pages
                        if not found_emails:
                            for ig_url in ig_fallback_links:
                                try:
                                    context = await browser.new_context(
                                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                                        viewport={"width": 1280, "height": 800}
                                    )
                                    page = await context.new_page()
                                    page.set_default_timeout(30000)
                                    page.set_default_navigation_timeout(30000)
                                    ig_emails = await crawl_instagram(page, ig_url)
                                    if ig_emails:
                                        found_emails.extend(ig_emails)
                                        print(f"[+] Fallback Instagram success: {ig_url} -> {ig_emails}")
                                        break
                                except Exception as e:
                                    print(f"[-] Fallback Instagram failed ({ig_url}): {e}")
                                finally:
                                    if page: await page.close()
                                    if context: await context.close()
                                    page = None
                                    context = None
                    return found_emails

                try:
                    emails = await asyncio.wait_for(do_scrape(), timeout=90.0)
                except asyncio.TimeoutError:
                    print(f"[!] Timeout Error: Scanning {website} took longer than 90 seconds. Aborting task to prevent hang.")
                    emails = []

                # Clean, filter junk, score, and select ONLY 1 BEST EMAIL
                parsed_domain = urllib.parse.urlparse(website).netloc.lower().replace('www.', '')
                valid_emails = [e for e in set(emails) if score_email_b2b(e, parsed_domain) > 0]
                best_email = max(valid_emails, key=lambda e: score_email_b2b(e, parsed_domain)) if valid_emails else ""
                row['Email'] = best_email
                print(f"[+] URL: {website} -> Best Email: {best_email if best_email else 'None found'} (selected from {len(emails)} raw)")

                
                if writer:
                    try:
                        writer.writerow(row)
                        output_file.flush()
                    except Exception as write_err:
                        print(f"[-] Critical: Failed to write row to CSV: {write_err}")
                processed_urls.add(url)
            
        except Exception as e:
            print(f"[-] Error processing {website}: {e}")
            row['Email'] = ''
            if writer:
                try:
                    writer.writerow(row)
                    output_file.flush()
                except Exception as write_err:
                    print(f"[-] Critical: Failed to write error row to CSV: {write_err}")
            processed_urls.add(url)

async def main():
    if not os.path.exists(INPUT_CSV):
        print(f"Error: Input file {INPUT_CSV} does not exist.")
        return

    # 1. Read existing rows to process
    with open(INPUT_CSV, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        all_rows = list(reader)
        fieldnames = reader.fieldnames
        if 'Email' not in fieldnames:
            fieldnames.append('Email')

    # 2. Check already processed URLs in output CSV
    processed_urls = set()
    emails_by_url = {}
    file_exists = os.path.exists(OUTPUT_CSV)
    if file_exists:
        try:
            with open(OUTPUT_CSV, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                is_formatted = reader.fieldnames and 'Công ty' in reader.fieldnames
                if is_formatted and not (INPUT_CSV == OUTPUT_CSV and RETRY_EMPTY):
                    print("[WARNING] Output CSV appears to be already formatted. Starting fresh by overwriting it.")
                    file_exists = False
                else:
                    for row in reader:
                        url = row.get('URL') or row.get('Liên Hệ')
                        if url:
                            email = row.get('Email', '').strip()
                            emails_by_url[url] = email
                            
                            website = (row.get('Website') or row.get('Liên Hệ') or "").strip()
                            if RETRY_EMPTY and website and not email:
                                # Do not mark as processed if we are retrying empty emails and website exists
                                pass
                            else:
                                processed_urls.add(url)
            if file_exists:
                print(f"[*] Resuming: Loaded {len(processed_urls)} already processed records.")
        except Exception as e:
            print(f"[-] Could not read existing output file, starting fresh: {e}")
            file_exists = False

    # Sync already found emails to all_rows
    for row in all_rows:
        url = row.get('URL') or row.get('Liên Hệ')
        if url in processed_urls:
            row['Email'] = emails_by_url.get(url, '')

    # 3. Filter rows that actually need processing (i.e. not already processed)
    rows_to_process = [row for row in all_rows if (row.get('URL') or row.get('Liên Hệ')) not in processed_urls]
    print(f"[*] Total rows to process: {len(rows_to_process)}")

    if not rows_to_process:
        print("[+] All rows already processed.")
        return

    batch_size = 50

    if RETRY_EMPTY:
        # Retry empty mode: we update the all_rows dataset in memory and save the whole list to file
        website_rows = []
        for row in rows_to_process:
            url = row.get('URL') or row.get('Liên Hệ')
            website = (row.get('Website') or row.get('Liên Hệ') or "").strip()
            if not website:
                row['Email'] = ''
                if url:
                    processed_urls.add(url)
            else:
                website_rows.append(row)

        print(f"[*] Websites to crawl: {len(website_rows)}")

        for i in range(0, len(website_rows), batch_size):
            chunk = website_rows[i:i+batch_size]
            print(f"\n[***] Starting website crawl batch {i//batch_size + 1} ({len(chunk)} websites)...")

            semaphore = asyncio.Semaphore(3) # Max 3 concurrent crawlers

            tasks = []
            for row in chunk:
                task = process_row(row, semaphore, None, None, processed_urls)
                tasks.append(task)

            await asyncio.gather(*tasks)

            print(f"[***] Completed batch {i//batch_size + 1}. Resources released.")
            save_progress(all_rows, OUTPUT_CSV, fieldnames)
            print(f"[*] Progress saved to {OUTPUT_CSV}")
    else:
        # Normal run (appending to output file)
        mode = 'a' if file_exists else 'w'
        with open(OUTPUT_CSV, mode=mode, encoding='utf-8-sig', newline='') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()

            # Separate rows with no website (process instantly to save resources)
            website_rows = []
            for row in rows_to_process:
                url = row.get('URL') or row.get('Liên Hệ')
                website = (row.get('Website') or row.get('Liên Hệ') or "").strip()
                if not website:
                    row['Email'] = ''
                    writer.writerow(row)
                    outfile.flush()
                    if url:
                        processed_urls.add(url)
                else:
                    website_rows.append(row)

            print(f"[*] Websites to crawl: {len(website_rows)}")

            # Process website rows in batches
            for i in range(0, len(website_rows), batch_size):
                chunk = website_rows[i:i+batch_size]
                print(f"\n[***] Starting website crawl batch {i//batch_size + 1} ({len(chunk)} websites)...")

                semaphore = asyncio.Semaphore(3) # Max 3 concurrent crawlers

                tasks = []
                for row in chunk:
                    task = process_row(row, semaphore, writer, outfile, processed_urls)
                    tasks.append(task)

                await asyncio.gather(*tasks)

                print(f"[***] Completed batch {i//batch_size + 1}. Resources released.")

    print(f"\n[+] Email scraping complete! Output saved to {OUTPUT_CSV}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n[*] Tác vụ đã được dừng thủ công bởi người dùng.")
    except Exception as e:
        if "closed" not in str(e).lower() and "pipe" not in str(e).lower():
            print(f"[!] Lỗi phát sinh: {e}")

