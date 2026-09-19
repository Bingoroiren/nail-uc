import asyncio
import csv
import sys
import io
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

URL = "https://tsia.org.tw/MemberList?nodeID=26"
OUTPUT_CSV = "tsia_taiwan_semiconductor_members.csv"

# Từ điển dịch ngành nghề bán dẫn Đài Loan sang tiếng Việt
INDUSTRY_MAP = {
    "製造": "Sản xuất / Gia công bán dẫn (Manufacturing / Foundry)",
    "設計": "Thiết kế vi mạch / Chip bán dẫn (IC Design)",
    "設備": "Thiết bị & Máy móc bán dẫn (Semiconductor Equipment)",
    "封裝/測試": "Đóng gói & Kiểm thử (Packaging & Testing / OSAT)",
    "封裝": "Đóng gói bán dẫn (Packaging / Assembly)",
    "測試": "Kiểm thử bán dẫn (Testing)",
    "材料": "Vật liệu bán dẫn (Semiconductor Materials)",
    "光罩": "Mặt nạ quang học bán dẫn (Photomask)",
    "系統": "Hệ thống / Ứng dụng bán dẫn (Systems)",
    "軟體服務": "Phần mềm & Dịch vụ bán dẫn (Software & Services)",
    "軟體": "Phần mềm / EDA Tools (Software)",
    "服務": "Dịch vụ bán dẫn (Services)",
    "其他": "Khác (Others)",
}

def translate_industry(ind_str):
    if not ind_str:
        return ""
    ind_clean = ind_str.strip()
    if ind_clean in INDUSTRY_MAP:
        return INDUSTRY_MAP[ind_clean]
    
    # Ghép nếu có nhiều từ phân cách
    parts = re.split(r'[/,;、\s]+', ind_clean)
    translated_parts = [INDUSTRY_MAP.get(p, p) for p in parts if p]
    return " / ".join(translated_parts) if translated_parts else ind_clean

async def scrape_tsia():
    print("="*70)
    print("BẮT ĐẦU CÀO DANH SÁCH HIỆP HỘI BÁN DẪN ĐÀI LOAN (TSIA)")
    print(f"URL: {URL}")
    print("="*70)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

        all_members = []
        page_num = 1

        while True:
            print(f"[*] Đang cào trang {page_num}...")
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            table = soup.find('table', class_='tableList')
            if not table or not table.find('tbody'):
                print("   [!] Không tìm thấy bảng dữ liệu!")
                break

            rows = table.find('tbody').find_all('tr')
            page_count = 0

            for tr in rows:
                tds = tr.find_all('td')
                if len(tds) >= 3:
                    m_id = tds[0].get_text(strip=True)
                    
                    name_a = tds[1].find('a')
                    if name_a:
                        name = name_a.get_text(strip=True)
                        website = name_a.get('href', '').strip().replace('%20', '')
                        if website.startswith('javascript:'):
                            website = ''
                    else:
                        name = tds[1].get_text(strip=True)
                        website = ''
                    
                    ind_zh = tds[2].get_text(strip=True)
                    ind_vi = translate_industry(ind_zh)

                    if name:
                        all_members.append({
                            "No.": len(all_members) + 1,
                            "Mã hội viên": m_id,
                            "Tên công ty": name,
                            "Website": website,
                            "Ngành nghề (Tiếng Trung)": ind_zh,
                            "Ngành nghề (Tiếng Việt)": ind_vi
                        })
                        page_count += 1

            print(f"   -> Đã lấy {page_count} công ty ở trang {page_num}. Tổng tích luỹ: {len(all_members)}")

            # Tìm nút Next
            # Nút next: <li class="page-next" id="ContentPlaceHolder1_nextpage"><a id="ContentPlaceHolder1_lnkbtnNext">
            next_li = soup.find('li', class_='page-next')
            if not next_li or 'disabled' in next_li.get('class', []):
                print("[*] Đã đến trang cuối cùng!")
                break
            
            # Click vào nút Next trong trang
            next_btn = await page.query_selector('#ContentPlaceHolder1_lnkbtnNext')
            if not next_btn:
                # Thử tìm theo selector class .page-next a
                next_btn = await page.query_selector('li.page-next a')
            
            if not next_btn:
                print("[*] Không tìm thấy selector nút Next, kết thúc.")
                break

            try:
                # Chờ load trang mới sau click
                async with page.expect_response(lambda r: r.status == 200, timeout=10000):
                    await next_btn.click()
                await asyncio.sleep(1.5)
                page_num += 1
            except Exception as e:
                # Thử click đơn giản và sleep
                try:
                    await next_btn.click()
                    await asyncio.sleep(2.5)
                    page_num += 1
                except Exception as e2:
                    print(f"   [!] Lỗi khi click sang trang tiếp: {e2}")
                    break

        await browser.close()

    print("\n" + "="*70)
    print(f"CÀO THÀNH CÔNG TỔNG CỘNG: {len(all_members)} CÔNG TY!")
    print("="*70)

    # Ghi ra CSV
    fieldnames = ["No.", "Mã hội viên", "Tên công ty", "Website", "Ngành nghề (Tiếng Trung)", "Ngành nghề (Tiếng Việt)"]
    with open(OUTPUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_members)

    print(f"📁 Đã lưu file: {OUTPUT_CSV}")

if __name__ == "__main__":
    asyncio.run(scrape_tsia())
