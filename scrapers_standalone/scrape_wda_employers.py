import asyncio
import csv
import json
import os
import random
import re
import sys
import openpyxl
from playwright.async_api import async_playwright

# Set console output encoding to UTF-8
if sys.platform.startswith('win'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Files paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "wda_employers.csv")
OUTPUT_XLSX = os.path.join(SCRIPT_DIR, "wda_employers.xlsx")
PROGRESS_FILE = os.path.join(ROOT_DIR, "data", "progress", "scraping_progress_wda.json")

# CSV Columns in Vietnamese
FIELDNAMES = [
    "No.",
    "Tên chủ sử dụng",
    "SĐT chủ",
    "SĐT môi giới",
    "Địa điểm làm việc",
    "Ngành nghề",
    "Thứ tự ưu tiên",
    "Số lượng tuyển (Quota)",
    "Quốc tịch mong muốn",
    "Thời hạn mong muốn",
    "Ngày hết hạn",
    "Email liên hệ",
    "Ngoại ngữ khác",
    "Mô tả công việc (JD)",
    "Điều kiện lao động (Lương/Ăn ở)",
    "Link chi tiết"
]

def load_progress():
    """Loads scraping progress to support resume functionality."""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[-] Error loading progress file: {e}")
    return {"completed_links": []}

def save_progress(completed_links):
    """Saves progress back to progress JSON file."""
    try:
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump({"completed_links": list(completed_links)}, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[-] Error saving progress file: {e}")

def append_to_csv(row_dict):
    """Appends a single scraped record to the output CSV file."""
    file_exists = os.path.isfile(OUTPUT_CSV)
    try:
        with open(OUTPUT_CSV, mode='a', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row_dict)
    except Exception as e:
        print(f"[-] Failed to write row to CSV: {e}")

async def scrape_detail(context, detail_url):
    """Opens detail page in a new tab, extracts details, and closes it."""
    detail_page = await context.new_page()
    email = ""
    other_lang = ""
    job_content = ""
    labor_conditions = ""
    
    try:
        await detail_page.goto(detail_url, timeout=45000, wait_until="domcontentloaded")
        try:
            await detail_page.wait_for_selector('.text-top-info span', timeout=5000)
        except Exception:
            pass
        await detail_page.wait_for_timeout(1500)
        
        # Extract span text contents
        spans = await detail_page.locator('.text-top-info span').all_inner_texts()
        for span in spans:
            clean_span = span.strip()
            if "業務聯繫信箱：" in clean_span:
                email = clean_span.replace("業務聯繫信箱：", "").strip()
            elif "希望外國人其它語言：" in clean_span:
                other_lang = clean_span.replace("希望外國人其它語言：", "").strip()
                
        # Extract job content and labor conditions
        text_con_elements = await detail_page.locator('.text-con').all()
        for elem in text_con_elements:
            elem_text = await elem.inner_text()
            if "工作內容：" in elem_text:
                job_content = elem_text.replace("工作內容：", "").strip()
            elif "勞動條件：" in elem_text:
                labor_conditions = elem_text.replace("勞動條件：", "").strip()
                
    except Exception as e:
        print(f"    [!] Error scraping detail page {detail_url}: {e}")
    finally:
        await detail_page.close()
        
    return email, other_lang, job_content, labor_conditions

async def export_to_xlsx():
    """Converts the final CSV file into a nicely formatted Excel sheet."""
    if not os.path.exists(OUTPUT_CSV):
        return
        
    print("[*] Generating Excel spreadsheet...")
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.title = "Employers"
    sheet.append(FIELDNAMES)
    
    try:
        with open(OUTPUT_CSV, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                sheet.append([row.get(col, "") for col in FIELDNAMES])
        wb.save(OUTPUT_XLSX)
        print(f"[SUCCESS] Excel spreadsheet generated at: {OUTPUT_XLSX}")
    except Exception as e:
        print(f"[-] Failed to write Excel spreadsheet: {e}")

async def get_rows_safe(page, selector="tbody.tbody tr", retries=5):
    """Safely retrieves locator elements with retries if context is destroyed during navigation."""
    for i in range(retries):
        try:
            return await page.locator(selector).all()
        except Exception as e:
            if "destroyed" in str(e).lower() or "navigation" in str(e).lower():
                await page.wait_for_timeout(1000)
                continue
            raise e
    return []

async def main():
    print("="*70)
    print("        TAIWAN WDA EMPLOYER TRANSITION DATABASE SCRAPER")
    print("="*70)
    
    progress = load_progress()
    completed_links = set(progress.get("completed_links", []))
    print(f"[+] Loaded progress: {len(completed_links)} records already scraped.")
    
    list_url = "https://fw.wda.gov.tw/wda-employer/home/fortrans/employer"
    
    async with async_playwright() as p:
        browser = None
        # Try default Chromium first as it is the most stable and isolated context
        for channel in [None, "chrome", "msedge"]:
            try:
                chan_str = f"channel '{channel}'" if channel else "default Chromium"
                print(f"[*] Attempting to launch browser with {chan_str}...")
                launch_args = {
                    "headless": True,  # Set to True to avoid profile locks and GUI hanging
                    "slow_mo": 10,
                    "args": ["--disable-blink-features=AutomationControlled"]
                }
                if channel:
                    launch_args["channel"] = channel
                browser = await p.chromium.launch(**launch_args)
                print(f"[+] Successfully launched browser using {chan_str}!")
                break
            except Exception as e:
                print(f"[-] Failed to launch with channel '{channel}': {e}")
                
        if not browser:
            print("[! ERROR] Could not launch any browser context. Exiting.")
            return
            
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        
        page = await context.new_page()
        
        print(f"[*] Navigating to WDA database list URL: {list_url}")
        try:
            await page.goto(list_url, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
        except Exception as nav_err:
            print(f"[-] Navigation failed: {nav_err}")
            await browser.close()
            return
            
        # Clean up non-POST forms in DOM to prevent jQuery $("form").submit() collision
        print("[*] Cleaning up forms in DOM...")
        try:
            await page.evaluate("""() => {
                document.querySelectorAll('form').forEach(f => {
                    if (!f.method || f.method.toLowerCase() !== 'post') {
                        f.remove();
                    }
                });
            }""")
        except Exception as clean_err:
            print(f"[*] Warning: Could not clean DOM forms: {clean_err}")

        # Get total pages
        total_pages = 37  # Default fallback if parsing fails
        try:
            total_pages_text = await page.locator('label#totalPage').inner_text()
            total_pages = int(total_pages_text.strip())
            print(f"[+] Total pages found: {total_pages}")
        except Exception as pg_err:
            print(f"[*] Warning: Could not parse total page count (using fallback: {total_pages}): {pg_err}")
            
        global_index = len(completed_links) + 1
        
        for page_idx in range(total_pages):
            print(f"\n[Page Progress: {page_idx + 1} / {total_pages}] Loading page index {page_idx}...")
            
            # Select the page number from dropdown
            try:
                # Capture the name of the first business on the current page to detect loading
                first_name_before = ""
                rows_before = await get_rows_safe(page)
                if rows_before:
                    first_name_before = await rows_before[0].locator('td').first.inner_text()
                
                # Only change page if page_idx > 0 (since page 0 is already active)
                if page_idx > 0:
                    # Clean up forms again to prevent any re-created non-POST forms from causing a submit collision
                    try:
                        await page.evaluate("""() => {
                            document.querySelectorAll('form').forEach(f => {
                                if (!f.method || f.method.toLowerCase() !== 'post') {
                                    f.remove();
                                }
                            });
                        }""")
                    except Exception:
                        pass
                        
                    await page.evaluate(f"changePage('{page_idx}')")
                    await page.wait_for_timeout(3000)
                    
                    # Wait for rows content to change/reload
                    for _ in range(15):
                        rows_after = await get_rows_safe(page)
                        if rows_after:
                            first_name_after = await rows_after[0].locator('td').first.inner_text()
                            if first_name_after != first_name_before:
                                break
                        await page.wait_for_timeout(200)
                    await page.wait_for_load_state("domcontentloaded")
                else:
                    await page.wait_for_timeout(2000)
            except Exception as select_err:
                print(f"[-] Error navigating to page index {page_idx}: {select_err}")
                continue
                
            # Extract row items
            rows = await get_rows_safe(page)
            print(f"[+] Found {len(rows)} rows on current page.")
            
            for row_el in rows:
                cols = await row_el.locator('td').all()
                if len(cols) < 11:
                    continue
                    
                # Extract link first to check if we already scraped it
                detail_href = ""
                try:
                    link_el = cols[10].locator('a')
                    if await link_el.count() > 0:
                        detail_href = await link_el.first.get_attribute("href")
                except Exception:
                    pass
                    
                if not detail_href:
                    continue
                    
                detail_url = f"https://fw.wda.gov.tw{detail_href}"
                if detail_url in completed_links:
                    continue
                    
                # Extract basic data columns
                employer_name = await cols[0].inner_text()
                employer_name = employer_name.strip()
                
                employer_phone = await cols[1].inner_text()
                employer_phone = employer_phone.strip()
                
                agency_phone = await cols[2].inner_text()
                agency_phone = agency_phone.strip()
                
                work_location = await cols[3].inner_text()
                work_location = work_location.strip()
                
                job_category = await cols[4].inner_text()
                job_category = job_category.strip()
                
                succession_order = await cols[5].inner_text()
                succession_order = succession_order.strip()
                
                undertake_quota = await cols[6].inner_text()
                undertake_quota = undertake_quota.strip()
                
                nationality = await cols[7].inner_text()
                nationality = nationality.replace("\n", " ").replace("  ", " ").strip()
                
                work_period = await cols[8].inner_text()
                work_period = work_period.strip()
                
                expiry_date = await cols[9].inner_text()
                expiry_date = expiry_date.strip()
                
                print(f"[{global_index}] Scraping details for: {employer_name}...")
                
                # Fetch detailed page fields
                email, other_lang, job_description, labor_conditions = await scrape_detail(context, detail_url)
                
                # Compile final record dict
                record = {
                    "No.": global_index,
                    "Tên chủ sử dụng": employer_name,
                    "SĐT chủ": employer_phone,
                    "SĐT môi giới": agency_phone,
                    "Địa điểm làm việc": work_location,
                    "Ngành nghề": job_category,
                    "Thứ tự ưu tiên": succession_order,
                    "Số lượng tuyển (Quota)": undertake_quota,
                    "Quốc tịch mong muốn": nationality,
                    "Thời hạn mong muốn": work_period,
                    "Ngày hết hạn": expiry_date,
                    "Email liên hệ": email,
                    "Ngoại ngữ khác": other_lang,
                    "Mô tả công việc (JD)": job_description.replace("\n", "  ").strip(),
                    "Điều kiện lao động (Lương/Ăn ở)": labor_conditions.replace("\n", "  ").strip(),
                    "Link chi tiết": detail_url
                }
                
                # Save to CSV
                append_to_csv(record)
                
                # Save progress
                completed_links.add(detail_url)
                save_progress(completed_links)
                
                global_index += 1
                await asyncio.sleep(random.uniform(0.5, 1.5))
                
        print("\n[*] Closing browser context...")
        await context.close()
        await browser.close()
        
    # Export the CSV to Excel Spreadsheet
    await export_to_xlsx()
    print("\n[+] Scraping session complete!")

if __name__ == "__main__":
    asyncio.run(main())
