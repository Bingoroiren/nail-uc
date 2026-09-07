import asyncio
import csv
import json
import os
import re
import sys
import random
import urllib.parse
from playwright.async_api import async_playwright

try:
    from playwright_stealth import stealth_async
except ImportError:
    async def stealth_async(page):
        pass

# Set console output encoding to UTF-8
if sys.platform.startswith('win') and hasattr(sys.stdout, 'buffer'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)

INPUT_CSV = os.path.join(ROOT_DIR, "data", "raw", "agency_norway.csv")
OUTPUT_CSV = os.path.join(ROOT_DIR, "data", "formatted", "agency_norway_with_emails_formatted.csv")
CLEAN_DEDUP_CSV = os.path.join(ROOT_DIR, "data", "formatted", "agency_norway_clean_dedup.csv")
PROGRESS_FILE = os.path.join(ROOT_DIR, "data", "progress", "scraping_progress_agency_no_emails.json")

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b')

# Norwegian Category Translation Map to Vietnamese
CATEGORY_TRANSLATIONS = {
    "landbrukstjenester": "Dịch vụ nông nghiệp",
    "landbruksrådgiving": "Tư vấn & Dịch vụ nông nghiệp",
    "landbruksservice": "Dịch vụ nông nghiệp",
    "landbruksorganisasjon": "Tổ chức / Hiệp hội nông nghiệp",
    "vikarbyrå": "Công ty môi giới / cho thuê lao động",
    "vikarbyråer": "Công ty môi giới / cho thuê lao động",
    "rekrutteringsbyrå": "Công ty tuyển dụng / Môi giới nhân sự",
    "rekrutteringsbyråer": "Công ty tuyển dụng / Môi giới nhân sự",
    "bemanningsbyrå": "Công ty cung ứng & Cho thuê nhân sự",
    "bemanningsbyråer": "Công ty cung ứng & Cho thuê nhân sự",
    "bemanningsselskap": "Doanh nghiệp cung ứng nhân sự",
    "arbeidsformidling": "Agency / Trung tâm giới thiệu việc làm",
    "rekruttering": "Dịch vụ tuyển dụng nhân sự",
    "rekrutteringsselskap": "Công ty tuyển dụng nhân sự",
    "personalutleie": "Dịch vụ cho thuê nhân lực",
    "personaltjenester": "Dịch vụ nhân sự",
    "bemanningsbyra": "Công ty cung ứng nhân sự",
    "rekrutteringsbyra": "Công ty tuyển dụng",
    "vikarbyra": "Công ty môi giới lao động"
}

JUNK_DOMAINS = [
    "facebook.com", "twitter.com", "instagram.com", "linkedin.com", "youtube.com",
    "wix.com", "wixsite.com", "wordpress.com", "squarespace.com", "weebly.com",
    "godaddy.com", "example.com", "domain.com", "placeholder.com", "wixpress.com", "sentry.io"
]

SYSTEM_USERNAMES = [
    "noreply", "no-reply", "donotreply", "privacy", "terms", "cookies", "gdpr",
    "abuse", "security", "webmaster", "sentry", "admin", "mailer-daemon"
]

IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.avif', '.js', '.css', '.ico', '.pdf')

def safe_print(msg):
    try:
        print(msg, flush=True)
    except Exception:
        pass

def translate_category(cat_str):
    if not cat_str:
        return "Agency / Dịch vụ nông nghiệp"
    cat_lower = cat_str.lower().strip()
    for key, trans in CATEGORY_TRANSLATIONS.items():
        if key in cat_lower or cat_lower in key:
            return trans
    return cat_str

def score_email(email):
    email = email.lower().strip()
    if "@" not in email or not EMAIL_REGEX.match(email):
        return 0
    if any(email.endswith(ext) for ext in IMAGE_EXTS):
        return 0
        
    username, domain = email.split("@", 1)
    if username in SYSTEM_USERNAMES or any(x in username for x in ['no-reply', 'noreply', 'privacy']):
        return 0
    if any(jd in domain for jd in JUNK_DOMAINS):
        return 0
        
    public_domains = ['gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'online.no', 'broadpark.no', 'c2i.net']
    generic_biz_usernames = ['post', 'postmottak', 'info', 'firmapost', 'kontakt', 'salg', 'office', 'jobb', 'rekruttering']
    
    if domain not in public_domains and username in generic_biz_usernames:
        return 10
    elif domain not in public_domains:
        return 9
    elif domain in public_domains and username in generic_biz_usernames:
        return 8
    else:
        return 7

def pick_best_single_email(email_str):
    if not email_str or not email_str.strip():
        return ""
    raw_emails = re.split(r'[\s,;]+', email_str.strip())
    valid_emails = []
    for em in raw_emails:
        clean_em = em.strip().lower()
        score = score_email(clean_em)
        if score > 0:
            valid_emails.append((score, clean_em))
            
    if not valid_emails:
        return ""
        
    valid_emails.sort(key=lambda x: (x[0], -len(x[1])), reverse=True)
    return valid_emails[0][1]

async def setup_vpn_speed_route(page):
    """Blocks heavy static assets (images, fonts, media, css) to accelerate website loading over Netherlands VPN."""
    async def route_handler(route):
        req = route.request
        resource_type = req.resource_type
        if resource_type in ["image", "media", "font", "stylesheet"]:
            await route.abort()
        else:
            await route.continue_()
    try:
        await page.route("**/*", route_handler)
    except Exception:
        pass

async def crawl_site_for_emails(page, url):
    if not url or "google.com" in url or "facebook.com" in url:
        return []
    emails = set()
    try:
        # Load page with 20s timeout and domcontentloaded strategy (VPN speed optimization)
        await page.goto(url, timeout=20000, wait_until="domcontentloaded")
        await page.wait_for_timeout(1000)
        
        try:
            body_text = await page.locator("body").inner_text()
            for email in EMAIL_REGEX.findall(body_text):
                emails.add(email.lower())
        except Exception:
            pass
            
        try:
            html_content = await page.content()
            for email in EMAIL_REGEX.findall(html_content):
                emails.add(email.lower())
        except Exception:
            pass
            
        try:
            mailto_links = await page.locator('a[href^="mailto:"]').all()
            for link in mailto_links:
                href = await link.get_attribute("href")
                if href:
                    em = href.replace("mailto:", "").split("?")[0].strip().lower()
                    if EMAIL_REGEX.match(em):
                        emails.add(em)
        except Exception:
            pass
                    
        # Check contact / about subpages if no emails found on main page
        if not emails:
            try:
                links = await page.locator('a[href]').all()
                subpage_urls = []
                for link in links:
                    href = await link.get_attribute("href")
                    text = await link.inner_text()
                    text_lower = text.lower() if text else ""
                    href_lower = href.lower() if href else ""
                    
                    if href and not href_lower.startswith(('mailto:', 'tel:', 'javascript:', '#')):
                        full_url = urllib.parse.urljoin(url, href)
                        if urllib.parse.urlparse(full_url).netloc == urllib.parse.urlparse(url).netloc:
                            if any(k in text_lower or k in href_lower for k in ['kontakt', 'contact', 'om-oss', 'about', 'karriere', 'jobb']):
                                subpage_urls.append(full_url.split('#')[0])
                                
                for sub_url in list(set(subpage_urls))[:2]:
                    try:
                        await page.goto(sub_url, timeout=12000, wait_until="domcontentloaded")
                        await page.wait_for_timeout(1000)
                        sub_text = await page.locator("body").inner_text()
                        for email in EMAIL_REGEX.findall(sub_text):
                            emails.add(email.lower())
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass
        
    scored = []
    for em in emails:
        sc = score_email(em)
        if sc > 0:
            scored.append((sc, em))
            
    scored.sort(key=lambda x: (x[0], -len(x[1])), reverse=True)
    return [em for sc, em in scored]

async def main():
    test_mode = "--test" in sys.argv
    reset_mode = "--reset" in sys.argv

    if reset_mode and os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)

    if not os.path.exists(INPUT_CSV):
        safe_print(f"[-] Input raw CSV not found: {INPUT_CSV}")
        return
        
    safe_print(f"[*] Processing Norway Agency listings from: {INPUT_CSV}")
    
    with open(INPUT_CSV, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        input_rows = list(reader)

    if test_mode:
        input_rows = input_rows[:5]
        safe_print(f"[!] TEST MODE ACTIVE: Crawling emails for top {len(input_rows)} records only.")
        
    fieldnames = [
        "No.", "Cong ty", "Chuc danh", "Nguoi lien he", "SDT", "Lien He", "Email", 
        "Lien He mail", "Dia chi", "Luong", "Ngay dang", "Han tuyen", "Check gui", 
        "Last Subject", "Last Body HTML", "Trang thai Reply", "Lan Follow-up", 
        "Ngay Follow-up gan nhat", "Mailbox da dung", "Category"
    ]
    
    processed_companies = set()
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    if os.path.exists(PROGRESS_FILE) and not reset_mode:
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f_p:
                p_data = json.load(f_p)
                processed_companies = set(p_data.get("processed", []))
            safe_print(f"[+] Loaded {len(processed_companies)} already processed records from progress file.")
        except Exception:
            pass

    formatted_rows = []
    
    for idx, row in enumerate(input_rows):
        comp_name = row.get("Business_Name", "").strip()
        category = row.get("Category", "").strip()
        phone = row.get("Phone", "").strip()
        address = row.get("Address", "").strip()
        website = row.get("Website", "").strip()
        
        if phone and not phone.startswith("'"):
            phone = f"'{phone}"
            
        trans_cat = translate_category(category)
        
        formatted_rows.append({
            "No.": str(idx + 1),
            "Cong ty": comp_name,
            "Chuc danh": "",
            "Nguoi lien he": "",
            "SDT": phone,
            "Lien He": website,
            "Email": "",
            "Lien He mail": "",
            "Dia chi": address,
            "Luong": "",
            "Ngay dang": "",
            "Han tuyen": "",
            "Check gui": "",
            "Last Subject": "",
            "Last Body HTML": "",
            "Trang thai Reply": "",
            "Lan Follow-up": "0",
            "Ngay Follow-up gan nhat": "",
            "Mailbox da dung": "",
            "Category": trans_cat
        })

    def save_progress(proc_set):
        os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
        try:
            with open(PROGRESS_FILE, "w", encoding="utf-8") as f_p:
                json.dump({"processed": list(proc_set)}, f_p, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # Crawl website emails with VPN asset-blocking optimization
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            extra_http_headers={"Accept-Language": "no-NO,no;q=0.9,en-US;q=0.8,en;q=0.7,nl;q=0.6"}
        )
        page = await context.new_page()
        await stealth_async(page)
        await setup_vpn_speed_route(page)
        
        total = len(formatted_rows)
        for i, row in enumerate(formatted_rows):
            comp_name = row["Cong ty"]
            web_url = row["Lien He"]
            
            if comp_name in processed_companies and not test_mode:
                continue
                
            is_valid_site = web_url.startswith("http") and "google.com" not in web_url
            
            if is_valid_site:
                safe_print(f"[{i+1}/{total}] Crawling emails for Norway Agency: '{comp_name}' -> {web_url}...")
                found_emails = await crawl_site_for_emails(page, web_url)
                if found_emails:
                    row["Email"] = found_emails[0] # Pick single best email
                    safe_print(f"  [+] Found best email: {row['Email']}")
                else:
                    safe_print("  [-] No emails found.")
            else:
                safe_print(f"[{i+1}/{total}] Skipping email crawl for: '{comp_name}' (No valid website)")
                
            processed_companies.add(comp_name)
            save_progress(processed_companies)
            await page.wait_for_timeout(random.uniform(300, 600))
            
        await browser.close()

    # Deduplicate & Sort: Push records with email to the top
    deduped_records = {}
    for r in formatted_rows:
        key = r["Cong ty"].lower().strip()
        if not key:
            continue
        if key not in deduped_records:
            deduped_records[key] = r
        else:
            existing = deduped_records[key]
            if not existing["Email"] and r["Email"]:
                existing["Email"] = r["Email"]
            if not existing["SDT"] and r["SDT"]:
                existing["SDT"] = r["SDT"]
            if not existing["Lien He"] and r["Lien He"]:
                existing["Lien He"] = r["Lien He"]

    final_list = list(deduped_records.values())
    
    # Pick best single email per row
    for r in final_list:
        r["Email"] = pick_best_single_email(r["Email"])

    rows_with_email = [r for r in final_list if r["Email"].strip()]
    rows_without_email = [r for r in final_list if not r["Email"].strip()]
    
    sorted_final = rows_with_email + rows_without_email
    for idx, r in enumerate(sorted_final, 1):
        r["No."] = str(idx)

    # Save to output CSV files
    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    for out_path in [OUTPUT_CSV, CLEAN_DEDUP_CSV]:
        try:
            with open(out_path, mode="w", encoding="utf-8-sig", newline="") as f_out:
                writer = csv.DictWriter(f_out, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(sorted_final)
            safe_print(f"[+] Output CSV written to: {out_path}")
        except Exception as e:
            safe_print(f"[-] Error writing CSV {out_path}: {e}")

    safe_print(f"\n==================================================")
    safe_print(f"[SUCCESS] Norway Agency Data Processed & Formatted.")
    safe_print(f" Total Unique Agencies: {len(sorted_final)}")
    safe_print(f" Agencies WITH Single Email: {len(rows_with_email)}")
    safe_print(f" Agencies WITHOUT Email: {len(rows_without_email)}")
    safe_print(f"==================================================")

if __name__ == "__main__":
    asyncio.run(main())
