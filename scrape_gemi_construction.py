import asyncio
import csv
import json
import os
import re
import sys
from playwright.async_api import async_playwright

# Đảm bảo mã hóa UTF-8 cho console Windows
if sys.platform.startswith('win'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

OUTPUT_CSV = "gemi_construction_companies.csv"

def extract_gemi_number(href):
    """Trích xuất số GEMI từ link chi tiết, ví dụ: /company/123456789000"""
    if not href:
        return ""
    match = re.search(r'/company/(\d+)', href)
    if match:
        return match.group(1)
    return ""

def find_values_by_keys(data, target_keys, found_values=None):
    """Tìm đệ quy tất cả các giá trị có key khớp với target_keys trong JSON"""
    if found_values is None:
        found_values = []
    if isinstance(data, dict):
        for k, v in data.items():
            if any(tk in k.lower() for tk in target_keys):
                if isinstance(v, str) and v.strip():
                    found_values.append(v.strip())
                elif isinstance(v, (int, float)):
                    found_values.append(str(v))
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, str) and item.strip():
                            found_values.append(item.strip())
                        elif isinstance(item, (int, float)):
                            found_values.append(str(item))
                        elif isinstance(item, dict):
                            find_values_by_keys(item, target_keys, found_values)
            else:
                find_values_by_keys(v, target_keys, found_values)
    elif isinstance(data, list):
        for item in data:
            find_values_by_keys(item, target_keys, found_values)
    return list(set(found_values))

async def scrape_company_details(context, href):
    """Mở trang chi tiết công ty, bắt phản hồi JSON từ API details và click fallback từ DOM nếu cần"""
    detail_url = f"https://publicity.businessportal.gr{href}"
    detail_page = await context.new_page()
    email = ""
    phone = ""
    name_en = ""
    
    try:
        # Lắng nghe sự kiện phản hồi từ API /api/company/details để trích xuất JSON trực tiếp
        api_data = {}
        
        async def handle_response(response):
            if "api/company/details" in response.url:
                try:
                    if response.status == 200:
                        text = await response.text()
                        api_data["json"] = json.loads(text)
                except Exception:
                    pass
                    
        detail_page.on("response", handle_response)
        
        # Điều hướng trực tiếp đến trang chi tiết
        await detail_page.goto(detail_url, timeout=45000, wait_until="domcontentloaded")
        
        # Đợi tối đa 3 giây để nhận phản hồi từ API JSON
        for _ in range(10):
            if "json" in api_data:
                break
            await asyncio.sleep(0.3)
            
        if "json" in api_data and api_data["json"]:
            # Trích xuất dữ liệu sạch trực tiếp từ JSON API
            js = api_data["json"]
            emails = find_values_by_keys(js, ["email", "mail"])
            phones = find_values_by_keys(js, ["phone", "tel"])
            names_en = find_values_by_keys(js, ["latin", "english", "eng"])
            
            if emails:
                email = ", ".join(emails)
            if phones:
                phone = ", ".join(phones)
            if names_en:
                # Tìm tên có chữ Latin dài nhất hoặc chứa ký tự tiếng Anh làm tên tiếng Anh
                names_en.sort(key=len, reverse=True)
                name_en = names_en[0]
                
            if email or phone or name_en:
                # Đã lấy được dữ liệu sạch, kiểm tra xem có thiếu tên tiếng Anh không
                if not name_en:
                    try:
                        sibling = detail_page.locator('xpath=//*[text()="Επωνυμία με λατινικούς χαρακτήρες" or contains(text(), "λατινικούς")]/following-sibling::*[1]')
                        await sibling.wait_for(state="attached", timeout=3000)
                        name_en = (await sibling.first.inner_text()).strip()
                    except Exception:
                        pass
                await detail_page.close()
                return email, phone, name_en
        
        # Fallback: Click mở rộng accordion từ DOM nếu không nhận được JSON sạch từ API
        # Lấy tên Latin từ DOM trước
        try:
            sibling = detail_page.locator('xpath=//*[text()="Επωνυμία με λατινικούς χαρακτήρες" or contains(text(), "λατινικούς")]/following-sibling::*[1]')
            await sibling.wait_for(state="attached", timeout=3000)
            name_en = (await sibling.first.inner_text()).strip()
        except Exception:
            pass

        # Tìm accordion "Στοιχεία Επικοινωνίας" (Thông tin liên lạc)
        contact_header_xpath = '//h6[text()="Στοιχεία Επικοινωνίας" or text()="Στοιχεία επικοινωνίας" or contains(text(), "Contact")]/ancestor::*[contains(@class, "MuiAccordionSummary-root")]'
        contact_header = detail_page.locator(contact_header_xpath)
        
        if await contact_header.count() > 0:
            # Click để mở dropdown thông tin liên hệ
            await contact_header.first.click()
            await detail_page.wait_for_timeout(1500)
            
            # Trích xuất link email (mailto:)
            email_loc = detail_page.locator('//h6[text()="Στοιχεία Επικοινωνίας" or text()="Στοιχεία επικοινωνίας" or contains(text(), "Contact")]/ancestor::*[contains(@class, "MuiAccordionSummary-root")]/following-sibling::*//a[starts-with(@href, "mailto:")]')
            if await email_loc.count() > 0:
                mail_href = await email_loc.first.get_attribute("href")
                if mail_href:
                    email = mail_href.replace("mailto:", "").strip().lower()
                    
            # Trích xuất link số điện thoại (tel:)
            phone_loc = detail_page.locator('//h6[text()="Στοιχεία Επικοινωνίας" or text()="Στοιχεία επικοινωνίας" or contains(text(), "Contact")]/ancestor::*[contains(@class, "MuiAccordionSummary-root")]/following-sibling::*//a[starts-with(@href, "tel:")]')
            if await phone_loc.count() > 0:
                tel_href = await phone_loc.first.get_attribute("href")
                if tel_href:
                    phone = tel_href.replace("phone:", "").replace("tel:", "").strip()
        else:
            print(f"  [-] Không tìm thấy mục 'Στοιχεία Επικοινωνίας' cho {detail_url}")
            
    except Exception as e:
        print(f"  [-] Lỗi khi cào trang chi tiết {detail_url}: {e}")
    finally:
        await detail_page.close()
        
    return email, phone, name_en

async def main():
    print("="*70)
    print("       GEMI GREECE - BỘ CÀO THÔNG TIN CÔNG TY XÂY DỰNG")
    print("="*70)
    print(f"[*] Kết quả sẽ được lưu vào: {OUTPUT_CSV}\n")
    
    # Khởi tạo file CSV nếu chưa có
    file_exists = os.path.isfile(OUTPUT_CSV)
    fieldnames = ["Tên công ty", "Tên tiếng Anh", "Số GEMI", "Điện thoại", "Email", "Link chi tiết"]
    
    # Mở browser chế độ headful để người dùng thao tác và giải CAPTCHA
    async with async_playwright() as p:
        print("[*] Đang khởi động trình duyệt Chrome...")
        browser = await p.chromium.launch(
            headless=False, # Hiện trình duyệt để bypass reCAPTCHA và chọn bộ lọc
            channel="chrome", # Dùng Chrome thực của máy để tránh bị chặn
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900}
        )
        page = await context.new_page()
        
        print("[*] Đang điều hướng đến publicity.businessportal.gr...")
        await page.goto("https://publicity.businessportal.gr/", timeout=60000)
        
        print("\n" + "!"*70)
        print(" HƯỚNG DẪN THAO TÁC TRÊN TRÌNH DUYỆT:")
        print(" 1. Click vào nút 'Φιλτρα' (Filters) trên giao diện web.")
        print(" 2. Tại ô 'Δραστηριότητα' (Activity), click chọn 'ΣΤ ΚΑΤΑΣΚΕΥΕΣ'.")
        print(" 3. Bạn cũng có thể thêm các bộ lọc khác nếu muốn (Ví dụ: trạng thái, tỉnh thành).")
        print(" 4. Nhấp nút 'Αναζήτηση' (Search) ở dưới cùng để thực hiện tìm kiếm.")
        print(" 5. Giải CAPTCHA / Xác minh robot nếu trang web yêu cầu.")
        print("!"*70 + "\n")
        
        input("==> Sau khi kết quả tìm kiếm hiển thị trên màn hình, hãy nhấn [ENTER] ở đây để bắt đầu cào tự động... ")
        
        print("\n[*] Đang bắt đầu quá trình cào dữ liệu...")
        
        page_num = 1
        total_scraped = 0
        
        while True:
            print(f"\n[+] Đang xử lý Trang {page_num}...")
            
            # Lấy danh sách link các công ty trên trang hiện tại
            company_links = page.locator('a[href^="/company/"], a[href*="/company/"]')
            links_count = await company_links.count()
            print(f"[+] Tìm thấy {links_count} công ty trên trang này.")
            
            if links_count == 0:
                print("[-] Không tìm thấy công ty nào. Dừng quá trình cào.")
                break
                
            # Lấy toàn bộ href và name trước để tránh mất DOM state khi chuyển trang
            companies_data = []
            for i in range(links_count):
                try:
                    name = await company_links.nth(i).inner_text()
                    href = await company_links.nth(i).get_attribute("href")
                    if href:
                        companies_data.append((name.strip(), href.strip()))
                except Exception:
                    pass
            
            # Loại bỏ các liên kết trùng lặp trên trang
            companies_data = list(dict.fromkeys(companies_data))
            
            for idx, (name, href) in enumerate(companies_data, 1):
                gemi = extract_gemi_number(href)
                print(f"  [{idx}/{len(companies_data)}] Đang xử lý: {name} (GEMI: {gemi})")
                
                # Cào email, sđt và tên tiếng Anh
                email, phone, name_en = await scrape_company_details(context, href)
                
                print(f"    -> Tên tiếng Anh: {name_en if name_en else 'Không có'}")
                print(f"    -> Điện thoại: {phone if phone else 'Không có'} | Email: {email if email else 'Không có'}")
                
                # Ghi ngay vào CSV để tránh mất dữ liệu nếu bị ngắt giữa chừng
                with open(OUTPUT_CSV, mode="a", encoding="utf-8-sig", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    if not file_exists:
                        writer.writeheader()
                        file_exists = True
                    writer.writerow({
                        "Tên công ty": name,
                        "Tên tiếng Anh": name_en,
                        "Số GEMI": gemi,
                        "Điện thoại": phone,
                        "Email": email,
                        "Link chi tiết": f"https://publicity.businessportal.gr{href}"
                    })
                total_scraped += 1
                await asyncio.sleep(0.5) # Delay nhẹ để tránh quá tải server
            
            # Tìm nút chuyển trang tiếp theo
            next_button_selector = 'button[aria-label*="next" i], button[aria-label*="επόμεν" i], .MuiPaginationItem-root:has(svg[data-testid="NavigateNextIcon"])'
            next_button = page.locator(next_button_selector).last
            
            if await next_button.count() > 0:
                is_disabled = await next_button.get_attribute("disabled") is not None
                is_disabled_class = "Mui-disabled" in (await next_button.get_attribute("class") or "")
                
                if is_disabled or is_disabled_class:
                    print("\n[+] Đã đến trang cuối cùng.")
                    break
                else:
                    print("\n[*] Đang chuyển sang trang tiếp theo...")
                    await next_button.click()
                    # Đợi trang mới load xong danh sách mới
                    await page.wait_for_timeout(3000)
                    page_num += 1
            else:
                print("\n[-] Không tìm thấy nút chuyển trang tiếp theo. Dừng cào.")
                break
                
        print("\n" + "="*70)
        print(f" Hoàn tất! Đã cào thành công {total_scraped} công ty.")
        print(f" Dữ liệu đã lưu tại: {OUTPUT_CSV}")
        print("="*70)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
