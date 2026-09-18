import sys
import io
import json
import time
import os
import re
import csv
import urllib.parse
import ddddocr
from curl_cffi import requests
from bs4 import BeautifulSoup

# Ensure UTF-8 unbuffered output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

CATEGORY_BASE = "https://rekvizitai.vz.lt/en/companies/sewing_materials/{page}/"
URLS_FILE = "crawlmail/rekvizitai_urls.json"
CACHE_FILE = "crawlmail/cache_rekvizitai_siuvimas.json"
OUTPUT_COLD_MAIL_CSV = "(17_9) rekvizitai_siuvimas - Trang tính1.csv"
OUTPUT_FULL_CSV = "rekvizitai_siuvimas_full_details.csv"

def collect_all_urls():
    if os.path.exists(URLS_FILE):
        try:
            with open(URLS_FILE, 'r', encoding='utf-8') as f:
                urls = json.load(f)
                if urls and len(urls) >= 1500:
                    print(f"[*] Đã tải {len(urls)} URLs công ty từ cache: {URLS_FILE}")
                    return urls
        except Exception:
            pass

    print("[*] Đang thu thập toàn bộ danh sách URL công ty từ danh mục (khoảng 1811 công ty / 121 trang)...")
    ocr = ddddocr.DdddOcr(show_ad=False)
    session = requests.Session()
    all_urls = []
    seen = set()
    prev_first = None

    for p in range(1, 130):
        url = CATEGORY_BASE.format(page=p)
        page_companies = []
        for attempt in range(5):
            try:
                r = session.get(url, impersonate="chrome124", timeout=15)
                if r.status_code != 200:
                    time.sleep(1)
                    continue
                
                soup = BeautifulSoup(r.text, 'html.parser')
                img = soup.find("img", id="security_code_image")
                if img:
                    img_url = img["src"]
                    r_img = session.get(img_url, impersonate="chrome124", timeout=10)
                    code = ocr.classification(r_img.content).upper().strip()
                    payload = {"security_code": code, "ok": "Continue"}
                    r_post = session.post(url, data=payload, impersonate="chrome124", timeout=15)
                    soup = BeautifulSoup(r_post.text, 'html.parser')
                    if soup.find("img", id="security_code_image"):
                        time.sleep(0.5)
                        continue

                for a in soup.find_all('a', href=True):
                    h = a['href']
                    if '/en/company/' in h and not any(x in h for x in ['/report/', '/print/', '/order/']):
                        clean_h = h.split('?')[0].rstrip('/') + '/'
                        if clean_h not in page_companies:
                            page_companies.append(clean_h)
                break
            except Exception as e:
                time.sleep(1)

        if not page_companies:
            print(f"Trang {p}: Hết danh sách hoặc không tìm thấy công ty.")
            break

        first_comp = page_companies[0]
        if first_comp == prev_first:
            print(f"Trang {p}: Trùng trang trước (đã đến cuối danh mục).")
            break
        prev_first = first_comp

        new_count = 0
        for u in page_companies:
            if u not in seen:
                seen.add(u)
                all_urls.append(u)
                new_count += 1
        print(f"Trang {p:3d}: +{new_count:2d} công ty | Tổng: {len(all_urls)}")
        time.sleep(0.2)

    os.makedirs("crawlmail", exist_ok=True)
    with open(URLS_FILE, "w", encoding="utf-8") as f:
        json.dump(all_urls, f, indent=2, ensure_ascii=False)
    print(f"[+] Thu thập xong toàn bộ {len(all_urls)} URLs.")
    return all_urls

def extract_company_details(url):
    data = {
        "name": "",
        "legal_name": "",
        "company_code": "",
        "vat_code": "",
        "address": "",
        "city": "",
        "postal_code": "",
        "phone": "",
        "website": "",
        "email": "",
        "manager": "",
        "manager_title": "Director",
        "employees": "",
        "bank": "",
        "activity": "Sewing, materials",
        "rekvizitai_url": url
    }
    
    try:
        r = requests.get(url, impersonate="chrome124", timeout=12)
        if r.status_code != 200:
            return data
            
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # 1. Textarea parsing
        ta = soup.find('textarea')
        if ta:
            for line in ta.get_text().strip().split('\n'):
                line = line.strip()
                if not line:
                    continue
                if line.startswith('Company:'):
                    data['name'] = line.replace('Company:', '').strip()
                elif line.startswith('Address:'):
                    data['address'] = line.replace('Address:', '').strip()
                elif line.startswith('Phone:'):
                    data['phone'] = line.replace('Phone:', '').strip()
                elif line.startswith('Registration code:'):
                    data['company_code'] = line.replace('Registration code:', '').strip()
                elif line.startswith('VAT:'):
                    data['vat_code'] = line.replace('VAT:', '').strip()
                elif line.startswith('Manager:'):
                    m_val = line.replace('Manager:', '').strip()
                    parts = [x.strip() for x in m_val.split(',') if x.strip()]
                    data['manager'] = parts[0]
                    if len(parts) > 1:
                        data['manager_title'] = parts[1]
                elif line.startswith('Bank:'):
                    data['bank'] = line.replace('Bank:', '').strip()
                    
        # 2. Schema JSON-LD parsing
        for s in soup.find_all('script', type='application/ld+json'):
            if s.string and 'Organization' in s.string:
                try:
                    jd = json.loads(s.string)
                    if not data['name']:
                        data['name'] = jd.get('name', '')
                    data['legal_name'] = jd.get('legalName', '')
                    if not data['vat_code']:
                        data['vat_code'] = jd.get('vatID', '')
                    if not data['website']:
                        data['website'] = jd.get('url', '')
                    emp = jd.get('numberOfEmployees', '')
                    if isinstance(emp, dict):
                        data['employees'] = str(emp.get('value', ''))
                    elif emp:
                        data['employees'] = str(emp)
                    addr = jd.get('address', {})
                    if isinstance(addr, dict):
                        data['city'] = addr.get('addressLocality', '')
                        data['postal_code'] = addr.get('postalCode', '')
                        if not data['address']:
                            data['address'] = f"{addr.get('streetAddress', '')}, {data['postal_code']} {data['city']}".strip(', ')
                    acts = jd.get('knowsAbout', [])
                    if isinstance(acts, list) and acts:
                        data['activity'] = '; '.join(acts)
                except Exception:
                    pass
                break
                
        # 3. Fallback phone
        if not data['phone']:
            tel_link = soup.select_one('a[href^="tel:"]')
            if tel_link:
                data['phone'] = tel_link.get_text(strip=True)

        # 4. Check email on Rekvizitai profile
        mail_link = soup.select_one('a[href^="mailto:"]')
        if mail_link:
            raw_mail = mail_link.get('href', '').replace('mailto:', '').split('?')[0].strip()
            data['email'] = urllib.parse.unquote(raw_mail).replace('%20', '').replace(' ', '').strip()
            
        # 5. Deep crawl website if available
        if data['website'] and not data['email']:
            w_url = data['website']
            if not w_url.startswith(('http://', 'https://')):
                w_url = 'http://' + w_url
            try:
                wr = requests.get(w_url, impersonate="chrome124", timeout=7)
                emails = set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', wr.text))
                clean_emails = [e for e in emails if not any(x in e.lower() for x in ['sentry', 'wix', 'shopify', 'example', 'creditinfo', '.png', '.jpg', '.jpeg', '.webp'])]
                if clean_emails:
                    pref = [e for e in clean_emails if any(p in e.lower() for p in ['info@', 'sales@', 'vadyba@', 'uzsak', 'kontakt', 'mail@'])]
                    data['email'] = pref[0] if pref else clean_emails[0]
                else:
                    for sub in ['/kontaktai', '/contacts', '/kontakt', '/apie-mus', '/apie', '/contact-us']:
                        sub_url = w_url.rstrip('/') + sub
                        try:
                            sub_r = requests.get(sub_url, impersonate="chrome124", timeout=5)
                            sub_emails = set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', sub_r.text))
                            sub_clean = [e for e in sub_emails if not any(x in e.lower() for x in ['sentry', 'wix', 'shopify', 'example', 'creditinfo', '.png', '.jpg'])]
                            if sub_clean:
                                pref = [e for e in sub_clean if any(p in e.lower() for p in ['info@', 'sales@', 'vadyba@', 'uzsak', 'kontakt', 'mail@'])]
                                data['email'] = pref[0] if pref else sub_clean[0]
                                break
                        except Exception:
                            pass
            except Exception:
                pass

        if data['email']:
            data['email'] = urllib.parse.unquote(data['email']).replace('%20', '').replace(' ', '').strip()

    except Exception as e:
        print(f"      [Lỗi cào {url}]: {e}")

    return data

def save_cache(cache):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Lỗi lưu cache: {e}")

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def export_csv_files(cache, urls):
    def clean_val(v):
        if not v:
            return ""
        s = urllib.parse.unquote(str(v)).replace('%20', ' ').strip()
        return s

    def clean_mail(v):
        if not v:
            return ""
        return urllib.parse.unquote(str(v)).replace('%20', '').replace(' ', '').strip()

    # 1. Cold Mail CSV (Chuẩn 21 cột)
    cold_mail_headers = [
        "No.", "Cong ty", "Chuc danh", "Nguoi lien he", "SDT", "Lien He", "Email",
        "Lien He mail", "Dia chi", "Luong", "Ngay dang", "Han tuyen", "Check gui",
        "Last Subject", "Last Body HTML", "Trang thai Reply", "Lan Follow-up",
        "Ngay Follow-up gan nhat", "Mailbox da dung", "Category", "Link FB"
    ]
    
    rows_cold = []
    idx = 1
    for u in urls:
        if u in cache:
            d = cache[u]
            ph = clean_val(d.get('phone', ''))
            if ph and not ph.startswith("'"):
                ph = f"'{ph}"
            rows_cold.append({
                "No.": idx,
                "Cong ty": clean_val(d.get('name', '')),
                "Chuc danh": clean_val(d.get('manager_title', 'Director')),
                "Nguoi lien he": clean_val(d.get('manager', '')),
                "SDT": ph,
                "Lien He": clean_val(d.get('website', '')),
                "Email": clean_mail(d.get('email', '')),
                "Lien He mail": "",
                "Dia chi": clean_val(d.get('address', '')),
                "Luong": "",
                "Ngay dang": "",
                "Han tuyen": "",
                "Check gui": "OK" if clean_mail(d.get('email', '')) else "",
                "Last Subject": "",
                "Last Body HTML": "",
                "Trang thai Reply": "",
                "Lan Follow-up": "",
                "Ngay Follow-up gan nhat": "",
                "Mailbox da dung": "",
                "Category": clean_val(d.get('activity', 'Sewing, materials')),
                "Link FB": ""
            })
            idx += 1
            
    try:
        with open(OUTPUT_COLD_MAIL_CSV, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=cold_mail_headers)
            writer.writeheader()
            writer.writerows(rows_cold)
    except Exception as e:
        print(f"Lỗi xuất file cold mail: {e}")

    # 2. Full Details CSV
    full_headers = [
        "name", "legal_name", "company_code", "vat_code", "address", "city",
        "postal_code", "phone", "website", "email", "manager", "manager_title",
        "employees", "bank", "activity", "rekvizitai_url"
    ]
    rows_full = []
    for u in urls:
        if u in cache:
            cd = {}
            for k, v in cache[u].items():
                if k == 'email':
                    cd[k] = clean_mail(v)
                else:
                    cd[k] = clean_val(v)
            rows_full.append(cd)
            
    try:
        with open(OUTPUT_FULL_CSV, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=full_headers)
            writer.writeheader()
            writer.writerows(rows_full)
    except Exception as e:
        print(f"Lỗi xuất file full details: {e}")

def main():
    print("="*70)
    print("      BỘ CÀO DANH SÁCH DOANH NGHIỆP REKVIZITAI.VZ.LT")
    print("      Danh mục: Siuvimas, medžiagos (Sewing, materials)")
    print("="*70)

    urls = collect_all_urls()
    cache = load_cache()
    print(f"[*] Cache hiện tại có: {len(cache)} / {len(urls)} công ty đã cào.")

    pending_urls = [u for u in urls if u not in cache]
    print(f"[*] Cần xử lý: {len(pending_urls)} công ty.\n")

    count = 0
    total = len(urls)
    for idx, u in enumerate(urls, 1):
        if u in cache:
            continue
            
        print(f"[{idx}/{total}] Đang cào: {u}")
        data = extract_company_details(u)
        cache[u] = data
        count += 1
        
        cname = data.get('name', 'N/A')
        phone = data.get('phone', '')
        web = data.get('website', '')
        email = data.get('email', '')
        print(f"   -> {cname} | Phone: {phone} | Web: {web} | Email: {email}")

        if count % 5 == 0:
            save_cache(cache)
            export_csv_files(cache, urls)
            print(f"   [Checkpoint]: Đã lưu {len(cache)} công ty vào CSV.")
            
        time.sleep(0.4)

    save_cache(cache)
    export_csv_files(cache, urls)
    print("\n" + "="*70)
    print(f"✅ HOÀN TẤT CÀO DỮ LIỆU! Tổng cộng: {len(cache)} công ty.")
    print(f"📁 File chuẩn Cold Mail (21 cột): {OUTPUT_COLD_MAIL_CSV}")
    print(f"📁 File chi tiết đầy đủ mã thuế: {OUTPUT_FULL_CSV}")
    print("="*70)

if __name__ == "__main__":
    main()
