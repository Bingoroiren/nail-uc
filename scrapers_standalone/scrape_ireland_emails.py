import os
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
# scrape_ireland_emails.py
# Scrapes additional emails for Irish recruiters in '(chờ)Mô giới ireland - CleanData.csv'

import asyncio
import csv
import glob
import os
import re
import sys
import random
import urllib.parse
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

# Set console output encoding to UTF-8 to prevent print errors
if sys.platform.startswith('win'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Regular expression to extract email addresses
EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b')

# Domains to skip (these are directories, not actual corporate homepages)
JUNK_DOMAINS = [
    "lunarcarpentry.vip", "galwaymusiccircle.vip", "irishdbmap.com", 
    "irishdbmap.work", "irelanddbmap", "vi.vip", "musiccircle", "carpentry.vip",
    "facebook.com/sharer", "twitter.com", "instagram.com", "linkedin.com", "youtube.com"
]

def score_email(email):
    email = email.lower().strip()
    if "@" not in email:
        return 0
        
    username, domain = email.split("@", 1)
    
    # Exclude common image extensions or junk matches inside scripts
    if any(email.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.js', '.css']):
        return 0
        
    # Technical, system or legal usernames
    system_usernames = ['noreply', 'no-reply', 'donotreply', 'privacy', 'terms', 'cookies', 'gdpr', 'abuse', 'security', 'webmaster', 'sentry', 'admin', 'info-systems']
    if username in system_usernames or any(x in username for x in ['no-reply', 'noreply', 'privacy', 'terms-of-use', 'cookie-policy']):
        return 0
        
    # Development, hosting or junk domains
    junk_domains = JUNK_DOMAINS + ['sentry.io', 'wix.com', 'wordpress', 'squarespace', 'weebly', 'godaddy', 'example.com', 'domain.com', 'placeholder', 'wixpress', 'wixsite']
    if any(jd in domain for jd in junk_domains) or 'sentry' in domain or 'wix' in domain:
        return 0
        
    # Public email domains (valid but generic)
    public_domains = ['gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'aol.com', 'mail.com', 'live.com', 'msn.com', 'icloud.com']
    if domain in public_domains:
        return 4
        
    # Generic business contact (e.g. info@, hello@, office@)
    generic_business_usernames = ['info', 'hello', 'office', 'contact', 'enquiries', 'sales', 'jobs', 'careers', 'recruitment', 'hr', 'work', 'apply', 'team', 'welcome']
    if username in generic_business_usernames:
        return 8
        
    # Likely a personal/direct corporate contact (e.g. j.smith@, john.doe@)
    return 10


def safe_print(msg):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            print(msg.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8'), flush=True)
        except Exception:
            print(msg.encode('ascii', errors='replace').decode('ascii'), flush=True)

def find_ireland_csv():
    # Locates the target file in the workspace
    patterns = ["*(ch*M*gi*ireland*CleanData.csv", "*ireland - CleanData.csv"]
    for pattern in patterns:
        files = glob.glob(pattern)
        if files:
            return files[0]
    return ""

def save_csv_atomically(file_path, fieldnames, rows):
    temp_path = file_path + ".tmp"
    try:
        with open(temp_path, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        # Swap files
        if os.path.exists(file_path):
            os.remove(file_path)
        os.rename(temp_path, file_path)
    except Exception as e:
        safe_print(f"  [-] Atomic write failed: {e}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass

async def crawl_site_for_emails(page, url):
    if not url:
        return []
    
    emails = set()
    try:
        safe_print(f"  [*] Navigating to: {url}...")
        await page.goto(url, timeout=15000, wait_until="commit")
        await page.wait_for_timeout(1500)
        
        # 1. Scan body text
        body_text = await page.locator("body").inner_text()
        for email in EMAIL_REGEX.findall(body_text):
            emails.add(email.lower())
            
        # 2. Scan raw HTML content
        html_content = await page.content()
        for email in EMAIL_REGEX.findall(html_content):
            emails.add(email.lower())
            
        # 3. Check mailto links
        mailto_links = await page.locator('a[href^="mailto:"]').all()
        for link in mailto_links:
            href = await link.get_attribute("href")
            if href:
                email = href.replace("mailto:", "").split("?")[0].strip().lower()
                if EMAIL_REGEX.match(email):
                    emails.add(email)
                
        # 4. If no emails found yet, look for contact/about subpages
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
                    # Ensure it belongs to the same domain name
                    if urllib.parse.urlparse(full_url).netloc == urllib.parse.urlparse(url).netloc:
                        if any(k in text_lower or k in href_lower for k in ['contact', 'about', 'intro', 'location', 'company', 'office', 'reach', 'mail']):
                            subpage_urls.append(full_url.split('#')[0])
                            
            # Crawl up to 2 subpages
            for sub_url in list(set(subpage_urls))[:2]:
                try:
                    safe_print(f"  [*] Checking Subpage: {sub_url}...")
                    await page.goto(sub_url, timeout=10000, wait_until="commit")
                    await page.wait_for_timeout(1000)
                    sub_text = await page.locator("body").inner_text()
                    for email in EMAIL_REGEX.findall(sub_text):
                        emails.add(email.lower())
                except Exception:
                    pass
    except Exception as e:
        safe_print(f"  [-] Connection failed for {url}: {e}")
        
    # Filter out junk email addresses and score the remaining ones
    scored_emails = []
    for email in emails:
        score = score_email(email)
        if score >= 4:
            scored_emails.append((score, email))
            
    # Sort by score descending and return only the email strings
    scored_emails.sort(key=lambda x: x[0], reverse=True)
    return [email for score, email in scored_emails]

async def main_async():
    files = glob.glob(os.path.join(ROOT_DIR, "data", "formatted", "*(ch*)*ireland*CleanData.csv"))
    if not files:
        safe_print("[-] Could not find any Ireland CSV files in the workspace!")
        return
        
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()
        await stealth_async(page)
        
        for file_path in files:
            safe_print(f"\n======================================================")
            safe_print(f"[*] Processing File: {os.path.basename(file_path)}")
            safe_print(f"======================================================")
            
            # Load all rows
            with open(file_path, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                rows = list(reader)
                
            # Primary columns
            company_col = 'Công ty'
            website_col = 'Liên Hệ'
            email_col = 'Email'
            
            # Check if headers exist
            if company_col not in fieldnames or website_col not in fieldnames or email_col not in fieldnames:
                safe_print(f"[-] CSV file is missing required headers: '{company_col}', '{website_col}', or '{email_col}'!")
                continue
                
            # Filter rows that need crawling
            crawlable_rows = []
            for idx, row in enumerate(rows):
                comp = row.get(company_col, "")
                web = row.get(website_col, "")
                email = row.get(email_col, "")
                
                is_empty_email = not email.strip()
                is_valid_web = web.startswith("http") and not any(jd in web.lower() for jd in JUNK_DOMAINS)
                
                if is_empty_email and is_valid_web:
                    crawlable_rows.append((idx, comp, web))
                    
            total_to_crawl = len(crawlable_rows)
            safe_print(f"[*] Found {total_to_crawl} companies with valid websites but missing emails.")
            
            if total_to_crawl == 0:
                safe_print("[+] All companies in this file already have emails or do not have valid website links.")
                continue
                
            crawled_count = 0
            success_count = 0
            
            for index_in_list, comp_name, url in crawlable_rows:
                crawled_count += 1
                safe_print(f"\n  [{crawled_count}/{total_to_crawl}] Processing: '{comp_name}'...")
                
                emails = await crawl_site_for_emails(page, url)
                if emails:
                    email_str = ", ".join(emails)
                    rows[index_in_list][email_col] = email_str
                    success_count += 1
                    safe_print(f"    [+] Found Emails: {email_str}")
                else:
                    safe_print("    [-] No emails found.")
                    
                # Save progress incrementally to the CSV file atomically
                save_csv_atomically(file_path, fieldnames, rows)
                
                # Politeness delay
                await page.wait_for_timeout(random.uniform(1000, 2000))
                
            safe_print(f"\n[+] Finished file: {os.path.basename(file_path)}")
            safe_print(f"  - Total processed: {crawled_count}")
            safe_print(f"  - New emails found: {success_count}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main_async())
