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

# Import config
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SRC_DIR)
import config_agency_at as config

def safe_print(msg):
    try:
        print(msg, flush=True)
    except Exception:
        pass

KEYWORDS = [
    ("arbeitskr%c3%a4fte%c3%bcberlassung", "Arbeitskräfteüberlassung"),
    ("personalbereitstellung", "Personalbereitstellung"),
    ("personalleasing", "Personalleasing"),
    ("zeitarbeit", "Zeitarbeit"),
    ("leiharbeit", "Leiharbeit")
]

REGIONS = [
    ("", "Toàn quốc"),
    ("wien", "Wien"),
    ("nieder%C3%B6sterreich", "Niederösterreich"),
    ("ober%C3%B6sterreich", "Oberösterreich"),
    ("steiermark", "Steiermark"),
    ("tirol", "Tirol"),
    ("salzburg", "Salzburg"),
    ("k%C3%A4rnten", "Kärnten"),
    ("vorarlberg", "Vorarlberg"),
    ("burgenland", "Burgenland"),
    # Wien districts
    ("wien-1-bezirk-innere-stadt", "Wien 1"),
    ("wien-2-bezirk-leopoldstadt", "Wien 2"),
    ("wien-3-bezirk-landstrasse", "Wien 3"),
    ("wien-4-bezirk-wieden", "Wien 4"),
    ("wien-5-bezirk-margareten", "Wien 5"),
    ("wien-6-bezirk-mariahilf", "Wien 6"),
    ("wien-7-bezirk-neubau", "Wien 7"),
    ("wien-8-bezirk-josefstadt", "Wien 8"),
    ("wien-9-bezirk-alsergrund", "Wien 9"),
    ("wien-10-bezirk-favoriten", "Wien 10"),
    ("wien-11-bezirk-simmering", "Wien 11"),
    ("wien-12-bezirk-meidling", "Wien 12"),
    ("wien-13-bezirk-hietzing", "Wien 13"),
    ("wien-14-bezirk-penzing", "Wien 14"),
    ("wien-15-bezirk-rudolfsheim-f%C3%BCnfhaus", "Wien 15"),
    ("wien-16-bezirk-ottakring", "Wien 16"),
    ("wien-17-bezirk-hernals", "Wien 17"),
    ("wien-18-bezirk-w%C3%A4hring", "Wien 18"),
    ("wien-19-bezirk-d%C3%B6bling", "Wien 19"),
    ("wien-20-bezirk-brigittenau", "Wien 20"),
    ("wien-21-bezirk-floridsdorf", "Wien 21"),
    ("wien-22-bezirk-donaustadt", "Wien 22"),
    ("wien-23-bezirk-liesing", "Wien 23")
]

async def scrape_detail_page(page, detail_url):
    comp_name = ""
    phone = ""
    email = ""
    website = ""
    address = "Áo (Austria)"
    
    full_url = f"https://firmen.wko.at{detail_url}" if detail_url.startswith("/") else detail_url
    
    for attempt in range(2):
        try:
            await page.goto(full_url, wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(300)
            
            # Company name
            h1_tags = await page.locator("h1").all()
            if h1_tags:
                comp_name = (await h1_tags[0].inner_text()).strip()
                
            # Email
            mailto_links = await page.locator("a[href^='mailto:']").all()
            if mailto_links:
                href = await mailto_links[0].get_attribute("href")
                if href:
                    email = href.replace("mailto:", "").split("?")[0].strip().lower()
                    
            # Phone
            tel_links = await page.locator("a[href^='tel:']").all()
            if tel_links:
                href = await tel_links[0].get_attribute("href")
                if href:
                    raw_ph = href.replace("tel:", "").strip()
                    phone = urllib.parse.unquote(raw_ph).replace("%20", " ").strip()
                    phone = re.sub(r'\s+', ' ', phone)
                    if phone and not phone.startswith("'"):
                        phone = f"'{phone}"
                    
            # Website
            ext_links = await page.locator("a[target='_blank']").all()
            for el in ext_links:
                href = await el.get_attribute("href")
                if href and href.startswith("http") and "firmen.wko.at" not in href and "wko.at" not in href and "google.com" not in href:
                    website = href.strip()
                    break
                    
            # Address
            body_text = await page.locator("body").inner_text()
            addr_match = re.search(r'Adresse:\s*([^\n]+)', body_text)
            if addr_match:
                address = addr_match.group(1).strip()
            else:
                loc_match = re.search(r'(\d{4}\s+[A-ZÄÖÜa-zäöüß\s-]+)', body_text)
                if loc_match:
                    address = loc_match.group(1).strip()
            break

        except Exception as e:
            if attempt == 0:
                await page.wait_for_timeout(1000)
            else:
                pass
        
    return comp_name, phone, email, website, address

async def get_browser_and_context(playwright_instance):
    # Try CDP connection first to leverage user's authenticated session
    try:
        browser = await playwright_instance.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        safe_print("[+] Đã kết nối thành công qua CDP (Chrome đang mở) - Tránh hoàn toàn bot detection.")
        return browser, context, True
    except Exception:
        pass
        
    # Fallback to stealth Playwright
    safe_print("[*] Khởi động Chromium với chế độ Stealth...")
    browser = await playwright_instance.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox"
        ]
    )
    context = await browser.new_context(
        viewport={"width": 1400, "height": 900},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        extra_http_headers={"Accept-Language": "de-AT,de;q=0.9,en-US;q=0.8,en;q=0.7"}
    )
    return browser, context, False

async def main():
    test_mode = "--test" in sys.argv
    reset_mode = "--reset" in sys.argv
    
    if reset_mode:
        if os.path.exists(config.SCRAPER_PROGRESS_FILE):
            os.remove(config.SCRAPER_PROGRESS_FILE)
        if os.path.exists(config.EMAIL_PROGRESS_FILE):
            os.remove(config.EMAIL_PROGRESS_FILE)
        if os.path.exists(config.RAW_CSV_PATH):
            os.remove(config.RAW_CSV_PATH)
        safe_print("[*] Đã đặt lại (RESET) tiến trình và file dữ liệu thô cũ.")
        
    processed_urls = set()
    os.makedirs(os.path.dirname(config.SCRAPER_PROGRESS_FILE), exist_ok=True)
    if os.path.exists(config.SCRAPER_PROGRESS_FILE) and not reset_mode:
        try:
            with open(config.SCRAPER_PROGRESS_FILE, "r", encoding="utf-8") as f:
                p_data = json.load(f)
                processed_urls = set(p_data.get("processed", []))
            safe_print(f"[+] Đã tải {len(processed_urls)} công ty đã thu thập từ trước.")
        except Exception:
            pass

    safe_print(f"==================================================")
    safe_print(f"[*] Khởi chạy WKO Austria Agency Scraper Toàn Quốc")
    safe_print(f"==================================================")

    fieldnames = ["Business_Name", "Phone", "Email", "Website", "Address", "Category", "Detail_URL"]
    os.makedirs(os.path.dirname(config.RAW_CSV_PATH), exist_ok=True)
    
    if reset_mode or not os.path.exists(config.RAW_CSV_PATH):
        with open(config.RAW_CSV_PATH, mode="w", encoding="utf-8-sig", newline="") as f_out:
            writer = csv.DictWriter(f_out, fieldnames=fieldnames)
            writer.writeheader()

    async with async_playwright() as p:
        browser, context, is_cdp = await get_browser_and_context(p)
        
        # Open a dedicated worker page for discovery
        page = await context.new_page()
        if not is_cdp:
            await stealth_async(page)
            
        # 1. Thu thập danh sách hồ sơ công ty trên toàn bộ danh mục và các bang
        scan_list = []
        for kw, kw_label in KEYWORDS:
            for reg, reg_label in REGIONS:
                url = f"https://firmen.wko.at/{kw}/{reg}/" if reg else f"https://firmen.wko.at/{kw}/"
                scan_list.append((url, f"{kw_label} ({reg_label})"))
                
        safe_print(f"[*] Tổng số danh mục & khu vực sẽ quét: {len(scan_list)}")
        
        # Dictionary of unique discovered items: detail_url -> initial card data
        unique_targets = {}
        
        for idx, (url, label) in enumerate(scan_list, 1):
            safe_print(f"[{idx}/{len(scan_list)}] Đang quét: {label}...")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(600)
                
                # Extract all cards from page
                card_data = await page.evaluate("""() => {
                    const list = [];
                    const containers = document.querySelectorAll('.result-container');
                    for (const c of containers) {
                        const link = c.querySelector('a[href*="firmaid="]');
                        if (!link) continue;
                        const name = link.innerText.trim();
                        const href = link.getAttribute('href');
                        if (!name || !href) continue;
                        
                        let phone = '';
                        let email = '';
                        let website = '';
                        let address = '';
                        
                        const tel = c.querySelector('a[href^="tel:"]');
                        if (tel) phone = tel.getAttribute('href').replace('tel:', '').trim();
                        
                        const mail = c.querySelector('a[href^="mailto:"]');
                        if (mail) email = mail.getAttribute('href').replace('mailto:', '').split('?')[0].trim();
                        
                        const ext = c.querySelectorAll('a[target="_blank"]');
                        for (const l of ext) {
                            const h = l.getAttribute('href') || '';
                            if (h.startsWith('http') && !h.includes('wko.at') && !h.includes('google.com')) {
                                website = h;
                                break;
                            }
                        }
                        
                        const text = c.innerText;
                        const m = text.match(/(\\d{4}\\s+[A-ZÄÖÜa-zäöüß\\s-]+)/);
                        if (m) address = m[1].trim();
                        
                        list.push({name, detailUrl: href, phone, email, website, address});
                    }
                    return list;
                }""")
                
                added_this_page = 0
                for c in card_data:
                    full_u = f"https://firmen.wko.at{c['detailUrl']}" if c['detailUrl'].startswith('/') else c['detailUrl']
                    if full_u not in unique_targets and full_u not in processed_urls:
                        unique_targets[full_u] = c
                        added_this_page += 1
                        
                safe_print(f"  -> Thấy {len(card_data)} thẻ (+{added_this_page} mới). Tổng công ty độc nhất hiện tại: {len(unique_targets) + len(processed_urls)}")
                
            except Exception as e:
                safe_print(f"  [-] Bỏ qua lỗi {label}: {e}")
                
            if test_mode and len(unique_targets) >= 15:
                safe_print("[!] Đã đạt số lượng mẫu cho chế độ Test.")
                break

        safe_print(f"\n==================================================")
        safe_print(f"[+] Hoàn thành bước tìm kiếm danh bạ.")
        safe_print(f"[+] Tổng số công ty mới cần trích xuất chi tiết: {len(unique_targets)}")
        safe_print(f"==================================================")
        
        # 2. Chi tiết từng công ty và ghi thẳng vào CSV thô
        count = 0
        total_to_scrape = len(unique_targets)
        
        for c_url, c_info in unique_targets.items():
            count += 1
            name = c_info["name"]
            phone = c_info["phone"]
            email = c_info["email"]
            website = c_info["website"]
            address = c_info["address"]
            
            # Nếu thẻ tìm kiếm thiếu số điện thoại hoặc email do ẩn cho thành viên, mở trang chi tiết
            if not phone or not email or not website:
                try:
                    d_name, d_phone, d_email, d_web, d_addr = await scrape_detail_page(page, c_url)
                    if d_name:
                        name = d_name
                    if d_phone:
                        phone = d_phone
                    if d_email:
                        email = d_email
                    if d_web:
                        website = d_web
                    if d_addr and d_addr != "Áo (Austria)":
                        address = d_addr
                except Exception:
                    pass

            if phone:
                phone = urllib.parse.unquote(phone).replace("%20", " ").strip()
                phone = re.sub(r'\s+', ' ', phone)
                if not phone.startswith("'"):
                    phone = f"'{phone}"

            row_data = {
                "Business_Name": name,
                "Phone": phone,
                "Email": email.lower().strip(),
                "Website": website.strip(),
                "Address": address if address else "Áo (Austria)",
                "Category": config.CATEGORY_VN,
                "Detail_URL": c_url
            }

            with open(config.RAW_CSV_PATH, mode="a", encoding="utf-8-sig", newline="") as f_out:
                writer = csv.DictWriter(f_out, fieldnames=fieldnames)
                writer.writerow(row_data)

            processed_urls.add(c_url)
            
            # Định kỳ in tiến trình
            if count % 10 == 0 or count == 1 or count == total_to_scrape:
                safe_print(f"  [{count}/{total_to_scrape}] Đã trích xuất: {name} (Email: {email if email else 'chưa có'}, SĐT: {phone if phone else 'chưa có'})")

            # Lưu checkpoint mỗi 10 công ty
            if count % 10 == 0:
                with open(config.SCRAPER_PROGRESS_FILE, "w", encoding="utf-8") as pf:
                    json.dump({"processed": list(processed_urls)}, pf)

        # Lưu checkpoint cuối
        with open(config.SCRAPER_PROGRESS_FILE, "w", encoding="utf-8") as pf:
            json.dump({"processed": list(processed_urls)}, pf)

        await page.close()
        if not is_cdp:
            await browser.close()

    safe_print(f"\n==================================================")
    safe_print(f"[SUCCESS] Đã cào toàn bộ danh sách WKO Austria thành công!")
    safe_print(f" Tổng cộng: {len(processed_urls)} công ty.")
    safe_print(f" File dữ liệu thô: {config.RAW_CSV_PATH}")
    safe_print(f"==================================================")

if __name__ == "__main__":
    asyncio.run(main())
