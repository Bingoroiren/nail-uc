import os
import sys
import re
import csv
import io
import json
import time
import asyncio
import urllib.parse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# Ensure UTF-8 unbuffered output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)

INPUT_CSV = os.path.join(PROJECT_ROOT, "(16_9) thịt dan mạch - Trang tính1.csv")
OUTPUT_DEDUP_CSV = os.path.join(PROJECT_ROOT, "(16_9) thịt dan mạch - SẴN SÀNG GỬI (ĐÃ LỌC TRÙNG).csv")
CACHE_FILE = os.path.join(CURRENT_DIR, "cache_thit_dan_mach_virk.json")
USER_DATA_DIR = os.path.abspath(os.path.join(PROJECT_ROOT, "chrome_user_data", "virk_profile"))

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Lỗi lưu cache: {e}")

def clean_query_name(name):
    if not name:
        return ""
    # Chỉ tách theo dấu phẩy để bỏ các hậu tố chi nhánh phụ (VD: ", Skodborg Mejeri")
    parts = name.split(',')
    q = parts[0].strip()
    return q

def extract_virk_data(html_content):
    data = {'phone': '', 'email': '', 'cvr': '', 'manager': ''}
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 1. CVR-nummer
    cvr_match = re.search(r'CVR-nummer\s*([0-9]{8})', soup.get_text())
    if cvr_match:
        data['cvr'] = cvr_match.group(1)

    # 2. Telefon & Mail trong các hàng thuộc tính
    for row in soup.find_all('div', class_='row'):
        row_text = row.get_text(separator=' | ', strip=True)
        if 'Telefon' in row_text and not data['phone']:
            m = re.search(r'Telefon\s*\|\s*([+0-9 ]+)', row_text)
            if m:
                clean_p = re.sub(r'[^0-9+]', '', m.group(1).strip())
                if clean_p and not clean_p.startswith('+'):
                    clean_p = '+45' + clean_p
                data['phone'] = f"'{clean_p}"
                
        if ('Mail' in row_text or 'Email' in row_text) and not data['email']:
            m = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b', row_text)
            if m:
                em = m.group(0).lower().replace('%20', '').strip()
                if not any(em.endswith(x) for x in ['.png', '.jpg', '.jpeg', '.svg']):
                    data['email'] = em

    # Fallback tìm email trong toàn bộ nội dung mở rộng nếu chưa tìm thấy trong hàng
    if not data['email']:
        all_emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,10}\b', html_content)
        clean_m = [e.lower().replace('%20', '').strip() for e in all_emails if not any(x in e.lower() for x in ['.png', '.jpg', '.jpeg', '.svg', 'virk.dk', 'erhvervsstyrelsen.dk', 'sentry', 'wix'])]
        if clean_m:
            data['email'] = clean_m[0]

    # 3. Người đại diện / Giám đốc
    for h in soup.find_all(['h2', 'h3', 'h4', 'strong', 'span']):
        txt = h.get_text(strip=True)
        if any(k in txt for k in ['Direktion', 'Foreningsrepræsentant', 'Ejer', 'Bestyrelse']):
            parent = h.find_parent('div')
            if parent:
                for line in parent.get_text().split('\n'):
                    line = line.strip()
                    if line and not any(k in line for k in ['Direktion', 'Foreningsrepræsentant', 'Indtrådt', 'Tiltrådt', 'Ejer', 'Bestyrelse', 'Cookies']):
                        if len(line) < 50 and not re.search(r'[0-9]{4}', line):
                            data['manager'] = line
                            break
            if data['manager']:
                break

    return data

def update_csv_files(reader, fieldnames):
    # Đánh OK cho cột Check gui nếu có email
    for r in reader:
        em = r.get('Email', '').strip().replace('%20', '')
        r['Email'] = em
        if em:
            r['Check gui'] = 'OK'
        else:
            r['Check gui'] = ''

    try:
        with open(INPUT_CSV, "w", encoding="utf-8-sig", newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(reader)
    except Exception as e:
        print(f"Lỗi ghi file gốc: {e}")

    try:
        def score_row(row):
            score = 0
            if row.get('SDT', '').strip(): score += 3
            if row.get('Nguoi lien he', '').strip(): score += 2
            if row.get('Dia chi', '').strip(): score += 2
            if row.get('Lien He', '').strip(): score += 1
            if row.get('Link FB', '').strip(): score += 1
            return score

        email_groups = {}
        for r in reader:
            em = r.get('Email', '').strip().lower()
            if em:
                email_groups.setdefault(em, []).append(r)

        dedup_rows = []
        for em, rows in email_groups.items():
            best_row = max(rows, key=score_row)
            dedup_rows.append(best_row)

        for i, r in enumerate(dedup_rows, 1):
            r['No.'] = i

        with open(OUTPUT_DEDUP_CSV, "w", encoding="utf-8-sig", newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(dedup_rows)
    except Exception as e:
        print(f"Lỗi ghi file dedup: {e}")

async def main():
    print("="*75)
    print("BỘ ENRICH DỮ LIỆU THỊT ĐAN MẠCH QUA DATACVR.VIRK.DK (OFFICIAL CVR REGISTRY)")
    print("Chế độ: Giao diện trực quan (headless=False) để theo dõi & giải xác minh")
    print("="*75)

    if not os.path.exists(INPUT_CSV):
        print(f"[!] Không tìm thấy file: {INPUT_CSV}")
        return

    with open(INPUT_CSV, "r", encoding="utf-8-sig") as f:
        reader = list(csv.DictReader(f))
        fieldnames = list(reader[0].keys())

    total = len(reader)
    cache = load_cache()
    print(f"[*] Tổng số dòng dữ liệu: {total}")
    print(f"[*] Đã cào thành công có sẵn trong cache Virk: {sum(1 for v in cache.values() if v.get('virk_url'))} công ty.")

    async with async_playwright() as p:
        print("[*] Đang mở trình duyệt Google Chrome trực quan...")
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            channel="chrome",
            headless=False,
            viewport={"width": 1280, "height": 850},
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = context.pages[0] if context.pages else await context.new_page()

        processed_since_save = 0

        for idx, row in enumerate(reader, 1):
            cname = row.get("Cong ty", "").strip()
            if not cname:
                continue

            # Chỉ bỏ qua nếu công ty này ĐÃ CÀO THÀNH CÔNG trước đó (có virk_url)
            if cname in cache and cache[cname].get('virk_url'):
                cached_data = cache[cname]
                if cached_data.get('virk_email'):
                    row['Email'] = cached_data['virk_email']
                if cached_data.get('virk_phone') and not row.get('SDT'):
                    row['SDT'] = cached_data['virk_phone']
                if cached_data.get('virk_manager') and not row.get('Nguoi lien he'):
                    row['Nguoi lien he'] = cached_data['virk_manager']
                continue

            query = clean_query_name(cname)
            print(f"\n[{idx}/{total}] 🔍 Đang tra Virk: {cname} (Từ khóa: '{query}')")

            virk_res = {'virk_email': '', 'virk_phone': '', 'virk_cvr': '', 'virk_manager': '', 'virk_url': ''}

            target_company_url = None
            search_url = f"https://datacvr.virk.dk/soegeresultater?fritekst={urllib.parse.quote(query)}&sideIndex=0&size=10"

            try:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=25000)

                # Chờ Vue SPA render kết quả (1-15 giây) hoặc phát hiện màn hình Cloudflare
                for s in range(1, 16):
                    await asyncio.sleep(1)
                    title = await page.title()
                    if "just a moment" in title.lower() or "security verification" in title.lower():
                        print(f"   🛑 PHÁT HIỆN XÁC MINH CLOUDFLARE (giây {s})! Vui lòng bấm xác minh trên màn hình Chrome...")
                        continue

                    content = await page.content()
                    if '/enhed/virksomhed/' in content:
                        soup = BeautifulSoup(content, 'html.parser')
                        for a in soup.find_all('a', href=True):
                            h = a['href']
                            if '/enhed/virksomhed/' in h:
                                target_company_url = urllib.parse.urljoin("https://datacvr.virk.dk", h)
                                break
                        if target_company_url:
                            break
                    elif '0 resultater' in content:
                        print("   ⚪ Virk báo 0 kết quả.")
                        break

                if target_company_url:
                    virk_res['virk_url'] = target_company_url
                    print(f"   -> Đang mở hồ sơ CVR: {target_company_url}")
                    await page.goto(target_company_url, wait_until="domcontentloaded", timeout=25000)

                    # Chờ Vue mount nút "Udvidede virksomhedsoplysninger" và click mở rộng
                    try:
                        btn = await page.wait_for_selector('#accordion-udvidede-virksomhedsoplysninger-button', timeout=12000)
                        if btn:
                            is_exp = await btn.get_attribute('aria-expanded')
                            if is_exp != 'true':
                                await btn.click()
                                await asyncio.sleep(1.2)
                    except Exception:
                        pass

                    # Click mở rộng thêm "P-enheder" nếu có
                    try:
                        p_btn = await page.query_selector('#accordion-produktionsenheder-button')
                        if p_btn:
                            is_exp = await p_btn.get_attribute('aria-expanded')
                            if is_exp != 'true':
                                await p_btn.click()
                                await asyncio.sleep(0.5)
                    except Exception:
                        pass

                    comp_html = await page.content()
                    extracted = extract_virk_data(comp_html)

                    virk_res['virk_email'] = extracted['email']
                    virk_res['virk_phone'] = extracted['phone']
                    virk_res['virk_cvr'] = extracted['cvr']
                    virk_res['virk_manager'] = extracted['manager']

                    if extracted['email']:
                        old_mail = row.get('Email', '')
                        row['Email'] = extracted['email']
                        print(f"   🎯 EMAIL CHÍNH THỨC TỪ VIRK: {extracted['email']} (Cũ: {old_mail})")
                    else:
                        print(f"   ⚪ Virk không niêm yết email -> Giữ email cũ: {row.get('Email', 'Không có')}")

                    if extracted['phone']:
                        row['SDT'] = extracted['phone']
                        print(f"   📞 SĐT TỪ VIRK: {extracted['phone']}")

                    if extracted['manager'] and not row.get('Nguoi lien he'):
                        row['Nguoi lien he'] = extracted['manager']
                else:
                    print(f"   ⚪ Không tìm thấy kết quả trên Virk -> Giữ nguyên email cũ: {row.get('Email', 'Không có')}")

            except Exception as e:
                print(f"   [!] Lỗi tra cứu {cname}: {e}")

            cache[cname] = virk_res
            processed_since_save += 1

            if processed_since_save >= 5:
                save_cache(cache)
                update_csv_files(reader, fieldnames)
                print(f"   [Checkpoint]: Đã lưu cache và cập nhật file CSV...")
                processed_since_save = 0

            await asyncio.sleep(1.5)

        save_cache(cache)
        update_csv_files(reader, fieldnames)
        print("\n" + "="*75)
        print("✅ HOÀN TẤT ENRICH DỮ LIỆU THỊT ĐAN MẠCH QUA VIRK!")
        print(f"📁 File chính: {INPUT_CSV}")
        print(f"📁 File sẵn sàng gửi đã lọc trùng: {OUTPUT_DEDUP_CSV}")
        print("="*75)
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
