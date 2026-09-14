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

FORMATTER_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(FORMATTER_DIR)
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, SRC_DIR)
import config_agency_at as config

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b')

# Austrian Phone Regex (+43 or 0...)
AT_PHONE_REGEX = re.compile(r'(?:\+43|0)\s?(?:[1-9]\d{0,3})\s?\d{3,4}\s?\d{3,4}')

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
        
    public_domains = ['gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'gmx.at', 'aon.at']
    generic_biz_usernames = ['office', 'info', 'bewerbung', 'karriere', 'kontakt', 'jobs', 'contact', 'toimisto']
    
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
    async def route_handler(route):
        req = route.request
        if req.resource_type in ["image", "media", "font", "stylesheet"]:
            await route.abort()
        else:
            await route.continue_()
    try:
        await page.route("**/*", route_handler)
    except Exception:
        pass

async def extract_contacts_from_page(page, page_url, timeout=10000):
    emails = set()
    phones = set()
    try:
        await page.goto(page_url, timeout=timeout, wait_until="domcontentloaded")
        await page.wait_for_timeout(400)
        
        try:
            body_text = await page.locator("body").inner_text()
            for email in EMAIL_REGEX.findall(body_text):
                emails.add(email.lower())
            for phone in AT_PHONE_REGEX.findall(body_text):
                clean_p = phone.strip()
                if len(clean_p) >= 8:
                    phones.add(clean_p)
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

        try:
            tel_links = await page.locator('a[href^="tel:"]').all()
            for link in tel_links:
                href = await link.get_attribute("href")
                if href:
                    ph = href.replace("tel:", "").strip()
                    if len(ph) >= 8:
                        phones.add(ph)
        except Exception:
            pass
    except Exception:
        pass
    return emails, phones

async def crawl_site_for_contacts(page, url):
    if not url or "google.com" in url or "facebook.com" in url or "wko.at" in url:
        return [], ""
    emails = set()
    phones = set()
    
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme if parsed.scheme in ['http', 'https'] else 'https'
    netloc = parsed.netloc
    root_url = f"{scheme}://{netloc}"
    
    # 1. Try initial URL
    p_emails, p_phones = await extract_contacts_from_page(page, url, timeout=12000)
    emails.update(p_emails)
    phones.update(p_phones)
    
    # 2. Try root domain homepage if initial URL had path
    if not emails and parsed.path and parsed.path not in ['', '/']:
        r_emails, r_phones = await extract_contacts_from_page(page, root_url, timeout=10000)
        emails.update(r_emails)
        phones.update(r_phones)
        
    # 3. Try German candidate contact pages (/kontakt/, /impressum/, /uber-uns/, /contact/)
    if not emails:
        contact_candidates = [
            f"{root_url}/kontakt/",
            f"{root_url}/kontakt",
            f"{root_url}/impressum/",
            f"{root_url}/impressum",
            f"{root_url}/uber-uns/",
            f"{root_url}/about/",
            f"{root_url}/contact/"
        ]
        for c_url in contact_candidates:
            if c_url.rstrip('/') != url.rstrip('/'):
                c_emails, c_phones = await extract_contacts_from_page(page, c_url, timeout=9000)
                if c_emails:
                    emails.update(c_emails)
                    phones.update(c_phones)
                    break

    scored = []
    for em in emails:
        sc = score_email(em)
        if sc > 0:
            scored.append((sc, em))
            
    scored.sort(key=lambda x: (x[0], -len(x[1])), reverse=True)
    best_emails = [em for sc, em in scored]
    
    phone_str = list(phones)[0] if phones else ""
    return best_emails, phone_str

async def main():
    test_mode = "--test" in sys.argv
    reset_mode = "--reset" in sys.argv

    if reset_mode and os.path.exists(config.EMAIL_PROGRESS_FILE):
        os.remove(config.EMAIL_PROGRESS_FILE)

    if not os.path.exists(config.RAW_CSV_PATH):
        safe_print(f"[-] Input raw CSV not found: {config.RAW_CSV_PATH}")
        return
        
    safe_print(f"[*] Processing Austria Agency listings from: {config.RAW_CSV_PATH}")
    
    with open(config.RAW_CSV_PATH, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        input_rows = list(reader)

    if test_mode:
        input_rows = input_rows[:10]
        safe_print(f"[!] TEST MODE ACTIVE: Crawling emails for top {len(input_rows)} records only.")
        
    fieldnames = [
        "No.", "Cong ty", "Chuc danh", "Nguoi lien he", "SDT", "Lien He", "Email", 
        "Lien He mail", "Dia chi", "Luong", "Ngay dang", "Han tuyen", "Check gui", 
        "Last Subject", "Last Body HTML", "Trang thai Reply", "Lan Follow-up", 
        "Ngay Follow-up gan nhat", "Mailbox da dung", "Category"
    ]
    
    processed_companies = set()
    os.makedirs(os.path.dirname(config.EMAIL_PROGRESS_FILE), exist_ok=True)
    if os.path.exists(config.EMAIL_PROGRESS_FILE) and not reset_mode:
        try:
            with open(config.EMAIL_PROGRESS_FILE, "r", encoding="utf-8") as f_p:
                p_data = json.load(f_p)
                processed_companies = set(p_data.get("processed", []))
            safe_print(f"[+] Loaded {len(processed_companies)} already processed records from progress file.")
        except Exception:
            pass

    formatted_rows = []
    
    for idx, row in enumerate(input_rows):
        comp_name = row.get("Business_Name", "").strip()
        phone = row.get("Phone", "").strip()
        email = row.get("Email", "").strip()
        address = row.get("Address", "Áo (Austria)").strip()
        website = row.get("Website", "").strip()
        
        # Clean %20 and URL encoding from phone numbers
        if phone:
            phone = urllib.parse.unquote(phone).replace("%20", " ").strip()
            # Collapse multiple spaces
            phone = re.sub(r'\s+', ' ', phone)
            if not phone.startswith("'"):
                phone = f"'{phone}"
            
        formatted_rows.append({
            "No.": str(idx + 1),
            "Cong ty": comp_name,
            "Chuc danh": "",
            "Nguoi lien he": "",
            "SDT": phone,
            "Lien He": website,
            "Email": email,
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
            "Category": config.CATEGORY_VN
        })

    def save_progress(proc_set):
        try:
            with open(config.EMAIL_PROGRESS_FILE, "w", encoding="utf-8") as f_p:
                json.dump({"processed": list(proc_set)}, f_p, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # Crawl website emails & phone numbers with VPN asset blocking optimization
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            extra_http_headers={"Accept-Language": "de-AT,de;q=0.9,en-US;q=0.8,en;q=0.7"}
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
                
            is_valid_site = web_url.startswith("http") and "google.com" not in web_url and "wko.at" not in web_url
            
            if is_valid_site and not row["Email"]:
                safe_print(f"[{i+1}/{total}] Crawling contacts for Austria Agency: '{comp_name}' -> {web_url}...")
                found_emails, found_phone = await crawl_site_for_contacts(page, web_url)
                if found_emails:
                    row["Email"] = found_emails[0]
                    safe_print(f"  [+] Found best email: {row['Email']}")
                else:
                    safe_print("  [-] No emails found on site.")
                    
                if not row["SDT"] and found_phone:
                    row["SDT"] = f"'{found_phone}"
                    safe_print(f"  [+] Found phone: {row['SDT']}")
            elif row["Email"]:
                safe_print(f"[{i+1}/{total}] Agency: '{comp_name}' already has email from WKO: {row['Email']}")
            else:
                safe_print(f"[{i+1}/{total}] Skipping contact crawl for: '{comp_name}' (No valid website)")
                
            processed_companies.add(comp_name)
            save_progress(processed_companies)
            await page.wait_for_timeout(random.uniform(200, 400))
            
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
    os.makedirs(os.path.dirname(config.FORMATTED_CSV_PATH), exist_ok=True)
    for out_path in [config.FORMATTED_CSV_PATH, config.CLEAN_DEDUP_CSV_PATH]:
        try:
            with open(out_path, mode="w", encoding="utf-8-sig", newline="") as f_out:
                writer = csv.DictWriter(f_out, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(sorted_final)
            safe_print(f"[+] Output CSV written to: {out_path}")
        except Exception as e:
            safe_print(f"[-] Error writing CSV {out_path}: {e}")

    safe_print(f"\n==================================================")
    safe_print(f"[SUCCESS] Austria Agency Data Processed & Formatted.")
    safe_print(f" Total Unique Agencies: {len(sorted_final)}")
    safe_print(f" Agencies WITH Single Email: {len(rows_with_email)}")
    safe_print(f" Agencies WITHOUT Email: {len(rows_without_email)}")
    safe_print(f"==================================================")

if __name__ == "__main__":
    asyncio.run(main())
