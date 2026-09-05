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

INPUT_CSV = os.path.join(ROOT_DIR, "data", "raw", "farm_norway.csv")
OUTPUT_CSV = os.path.join(ROOT_DIR, "data", "formatted", "farm_norway_with_emails_formatted.csv")
CLEAN_DEDUP_CSV = os.path.join(ROOT_DIR, "data", "formatted", "farm_norway_clean_dedup.csv")
PROGRESS_FILE = os.path.join(ROOT_DIR, "data", "progress", "scraping_progress_farm_no_emails.json")

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b')

# Norwegian Category Translation Map to Vietnamese
CATEGORY_TRANSLATIONS = {
    "gård": "Trang trại / Nông trại",
    "gårdsbruk": "Trang trại / Nông trại",
    "bondegård": "Trang trại / Nông trại gia đình",
    "organisk gård": "Nông trại hữu cơ / Sinh thái",
    "øko-gård": "Nông trại hữu cơ / Sinh thái",
    "økologisk gård": "Nông trại hữu cơ / Sinh thái",
    "vingård": "Vườn nho / Nhà làm rượu vang",
    "juletregård": "Trang trại trồng cây thông Noel",
    "fiskeoppdrettsanlegg": "Trang trại / Cơ sở nuôi cá",
    "fiskeoppdrett": "Trang trại / Cơ sở nuôi cá",
    "fiskeoppdretter": "Cơ sở / Doanh nghiệp nuôi cá",
    "oppdrettsanlegg for sjømat": "Trang trại / Cơ sở nuôi hải sản",
    "sjømatoppdrett": "Trang trại / Cơ sở nuôi hải sản",
    "akvakulturanlegg": "Cơ sở / Trang trại nuôi trồng thủy sản",
    "akvakultur": "Nuôi trồng thủy sản",
    "foredling av frukt og grønnsaker": "Cơ sở chế biến rau củ quả",
    "fruktgård": "Vườn cây ăn quả / Trang trại hoa quả",
    "bærgård": "Trang trại trồng quả mọng / Dâu tây",
    "melkebruk": "Trang trại bò sữa / Sản xuất sữa",
    "husdyrbruk": "Trang trại chăn nuôi gia súc",
    "grønnsaksdyrking": "Trang trại trồng rau",
    "landbruksvirksomhet": "Doanh nghiệp / Cơ sở nông nghiệp"
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

IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.js', '.css', '.ico', '.pdf')

def safe_print(msg):
    try:
        print(msg, flush=True)
    except Exception:
        pass

def translate_category(cat_str):
    if not cat_str:
        return "Nông trại / Thủy sản"
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
    generic_biz_usernames = ['post', 'postmottak', 'info', 'firmapost', 'kontakt', 'salg', 'office', 'gard', 'fisk']
    
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

async def crawl_site_for_emails(page, url):
    if not url or "google.com" in url or "facebook.com" in url:
        return []
    emails = set()
    try:
        await page.goto(url, timeout=12000, wait_until="commit")
        await page.wait_for_timeout(1000)
        
        body_text = await page.locator("body").inner_text()
        for email in EMAIL_REGEX.findall(body_text):
            emails.add(email.lower())
            
        html_content = await page.content()
        for email in EMAIL_REGEX.findall(html_content):
            emails.add(email.lower())
            
        mailto_links = await page.locator('a[href^="mailto:"]').all()
        for link in mailto_links:
            href = await link.get_attribute("href")
            if href:
                em = href.replace("mailto:", "").split("?")[0].strip().lower()
                if EMAIL_REGEX.match(em):
                    emails.add(em)
                    
        # Check subpages if no emails found on homepage
        if not emails:
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
                        if any(k in text_lower or k in href_lower for k in ['kontakt', 'contact', 'om-oss', 'about', 'location']):
                            subpage_urls.append(full_url.split('#')[0])
                            
            for sub_url in list(set(subpage_urls))[:2]:
                try:
                    await page.goto(sub_url, timeout=8000, wait_until="commit")
                    await page.wait_for_timeout(1000)
                    sub_text = await page.locator("body").inner_text()
                    for email in EMAIL_REGEX.findall(sub_text):
                        emails.add(email.lower())
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
    if not os.path.exists(INPUT_CSV):
        safe_print(f"[-] Input raw CSV not found: {INPUT_CSV}")
        return
        
    safe_print(f"[*] Processing Norway Farm & Aquaculture listings from: {INPUT_CSV}")
    
    with open(INPUT_CSV, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        input_rows = list(reader)
        
    fieldnames = [
        "No.", "Cong ty", "Chuc danh", "Nguoi lien he", "SDT", "Lien He", "Email", 
        "Lien He mail", "Dia chi", "Luong", "Ngay dang", "Han tuyen", "Check gui", 
        "Last Subject", "Last Body HTML", "Trang thai Reply", "Lan Follow-up", 
        "Ngay Follow-up gan nhat", "Mailbox da dung", "Category"
    ]
    
    processed_companies = set()
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    if os.path.exists(PROGRESS_FILE):
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

    # Crawl website emails
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await stealth_async(page)
        
        total = len(formatted_rows)
        for i, row in enumerate(formatted_rows):
            comp_name = row["Cong ty"]
            web_url = row["Lien He"]
            
            if comp_name in processed_companies:
                continue
                
            is_valid_site = web_url.startswith("http") and "google.com" not in web_url
            
            if is_valid_site:
                safe_print(f"[{i+1}/{total}] Crawling emails for Norway Farm/Aquaculture: '{comp_name}' -> {web_url}...")
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
            await page.wait_for_timeout(random.uniform(500, 1000))
            
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
    safe_print(f"[SUCCESS] Norway Farm Data Processed & Formatted.")
    safe_print(f" Total Unique Farms/Aquaculture: {len(sorted_final)}")
    safe_print(f" Farms WITH Single Email: {len(rows_with_email)}")
    safe_print(f" Farms WITHOUT Email: {len(rows_without_email)}")
    safe_print(f"==================================================")

if __name__ == "__main__":
    asyncio.run(main())
