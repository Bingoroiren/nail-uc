import sys
import io
import time
from playwright.sync_api import sync_playwright

# Ensure UTF-8 output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

TEST_URL = "https://www.proff.dk/branches%C3%B8g?q=Arbejdskrafts%20tjenester"

def run_visual_test(timeout_sec=60):
    print("=" * 70)
    print("   KIỂM TRA MỨC ĐỘ CHẶN PROFF.DK (CHẾ ĐỘ TRỰC QUAN: HEADLESS = FALSE)")
    print(f"   URL: {TEST_URL}")
    print(f"   Timeout: {timeout_sec}s")
    print("=" * 70)

    with sync_playwright() as p:
        print("[*] Đang khởi chạy trình duyệt Chromium (hiển thị trên màn hình)...")
        browser = p.chromium.launch(
            headless=False,
            slow_mo=300,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized"
            ]
        )
        
        context = browser.new_context(
            no_viewport=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="da-DK"
        )
        
        page = context.new_page()

        print(f"[*] Đang tải trang: {TEST_URL}...")
        start_time = time.time()
        
        try:
            response = page.goto(TEST_URL, timeout=timeout_sec * 1000, wait_until="domcontentloaded")
            load_time = time.time() - start_time
            status_code = response.status if response else 0
            title = page.title()
            
            print(f"[*] Mã phản hồi HTTP : {status_code}")
            print(f"[*] Tiêu đề trang     : {title}")
            print(f"[*] Thời gian phản hồi: {load_time:.2f}s")
            
            # Kiểm tra các dấu hiệu bị chặn
            content = page.content().lower()
            is_blocked = False
            block_reason = ""
            
            if status_code == 403:
                is_blocked = True
                block_reason = "HTTP 403 Forbidden (CloudFront / WAF từ chối truy cập)"
            elif "request could not be satisfied" in content:
                is_blocked = True
                block_reason = "CloudFront WAF Block ('The request could not be satisfied')"
            elif "cloudflare" in content and ("cf-challenge" in content or "turnstile" in content or "verify you are human" in content):
                is_blocked = True
                block_reason = "Cloudflare Captcha / Bot Challenge"
            elif "access denied" in content:
                is_blocked = True
                block_reason = "Access Denied / IP Blocked"

            # Xử lý Cookie Consent nếu có
            try:
                cookie_btn = page.locator('button:has-text("Tillad alle"), button:has-text("Accept all"), button#onetrust-accept-btn-handler, button[aria-label*="Tillad alle"]')
                if cookie_btn.count() > 0 and cookie_btn.first.is_visible():
                    print("[*] Đang tự động chấp nhận Cookie banner...")
                    cookie_btn.first.click()
                    page.wait_for_timeout(1000)
            except Exception:
                pass

            # Kiểm tra danh sách kết quả doanh nghiệp
            companies = page.locator('a[href*="/firma/"]')
            comp_count = companies.count()
            
            print("\n" + "-" * 70)
            print("                 KẾT QUẢ ĐÁNH GIÁ MỨC ĐỘ CHẶN")
            print("-" * 70)
            
            if is_blocked:
                print(f"[X] TRẠNG THÁI: BỊ CHẶN!")
                print(f"[!] Nguyên nhân: {block_reason}")
                print(f"[!] Khuyến nghị : Đổi location/server trên VPN hoặc chuyển sang IP khác.")
            else:
                print(f"[✓] TRẠNG THÁI: HOÀN TOÀN KHÔNG BỊ CHẶN (VƯỢT WAF THÀNH CÔNG)!")
                print(f"[+] Tìm thấy {comp_count} liên kết doanh nghiệp trên trang.")
                
                # Thử nghiệm click vào 1 công ty đầu tiên để kiểm tra trang chi tiết
                if comp_count > 0:
                    first_link = companies.first
                    company_name = first_link.inner_text().strip()
                    first_href = first_link.get_attribute("href")
                    print(f"[*] Đang test mở trang chi tiết công ty: {company_name or first_href}")
                    detail_resp = page.goto(f"https://www.proff.dk{first_href}" if first_href.startswith('/') else first_href, timeout=30000)
                    detail_status = detail_resp.status if detail_resp else 0
                    print(f"[✓] Trang chi tiết phản hồi HTTP {detail_status} - Không bị chặn.")
                    page.wait_for_timeout(2000)

            print("-" * 70)
            print("[*] Giữ trình duyệt 5 giây để bạn quan sát trực tiếp trên màn hình...")
            page.wait_for_timeout(5000)

        except Exception as e:
            print(f"[!] Gặp lỗi khi tải trang: {e}")
            page.wait_for_timeout(5000)
        finally:
            browser.close()
            print("[*] Đã đóng trình duyệt kiểm tra.")

if __name__ == "__main__":
    timeout = 60
    if len(sys.argv) > 1:
        try:
            timeout = int(sys.argv[1])
        except ValueError:
            pass
    run_visual_test(timeout)
