# -*- coding: utf-8 -*-
"""
Visual Enrichment Pipeline for KR_SHIP_ALLS via Naver Search & Deep Web:
- Headless = False: Trình duyệt Chromium thực tế hiển thị trực quan (1280x800) để quan sát.
- Multi-Anchor Naver Search với bộ bóc tách Component FDS mới của Naver.
- Cầu nối hồ sơ doanh nghiệp đã kiểm duyệt (Saramin, JobKorea, Bizno, Catch) để bốc link 홈페이지 chuẩn 100%.
- Duyệt trực quan website công ty, quét sâu trang liên hệ (contact, 오시는길, 문의) tìm Email B2B.
- Lọc triệt để rác CDN/Font tiếng Hàn, mạng xã hội, cổng thông tin tuyển dụng, thuế, thư bạ hiệp hội.
- Bộ chấm điểm B2B chuẩn Workspace, lưu tăng dần (mode='a', flush), xuất file 1ENR và 2COL (Emails on top).
"""

import sys
import os
import re
import csv
import json
import time
import asyncio
import argparse
import unicodedata
import urllib.parse
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# Configure UTF-8 console output for Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = str(ROOT_DIR / "(xong 10_9) KR_SHIP_ALLS - CleanData.csv")
OUTPUT_ENR = str(ROOT_DIR / "KR_SHIP_NAVR_1ENR.csv")
OUTPUT_COL = str(ROOT_DIR / "KR_SHIP_NAVR_2COL.csv")
CACHE_FILE = str(ROOT_DIR / "crawlmail" / "cache_enrich_kr_ship_naver.json")

LEGAL_FORMS_KR = [
    '주식회사', '(주)', '㈜', '유한회사', '(유)', '유한책임회사',
    '합자회사', '(합)', '합명회사', '사단법인', '(사)', '재단법인', '(재)',
    'co., ltd.', 'co.,ltd.', 'co., ltd', 'co.,ltd', 'co ltd',
    'inc.', 'inc', 'corp.', 'corp', 'corporation', 'company'
]

EXCLUDED_DOMAINS = {
    # Social & Global platforms
    'facebook.com', 'instagram.com', 'linkedin.com', 'twitter.com', 'x.com',
    'youtube.com', 'tiktok.com', 'pinterest.com', 'wikipedia.org', 'namu.wiki',
    'google.com', 'google.co.kr', 'maps.google.com', 'apple.com',
    'naver.com', 'daum.net', 'kakao.com', 'yellowpages', 'tripadvisor',
    'sedoparking.com', 'dan.com', 'hugedomains.com', 'godaddy.com', 'namecheap.com', 'gabia.com',
    'whois.co.kr', 'cafe24.com',
    # Recruitment & Job Portals
    'saramin.co.kr', 'jobkorea.co.kr', 'incruit.com', 'incruit.co.kr', 'wanted.co.kr', 'catch.co.kr',
    'jasoseol.com', 'worxphere.ai', 'jobplanet.co.kr', 'work.go.kr', 'worknet.go.kr',
    'alba.co.kr', 'albamon.com', 'peoplenjob.com', 'careernet.re.kr', 'scout.co.kr', 'career.co.kr',
    'rndcircle.io',
    # Business Registry, Credit Scoring, Financial & Tax portals
    'nicebizinfo.com', 'bizno.net', 'kreport.co.kr', 'cretop.com', 'kedrating.com', 'thevc.kr',
    'moneypin.biz', 'bolta.io', 'finboard.co.kr', 'rememberapp.co.kr', 'sankun.com', 'dataline.co.kr',
    'bizinfo.go.kr', 'smtech.go.kr', 'nts.go.kr', 'nhis.or.kr', 'nps.or.kr', 'krx.co.kr',
    'stockplus.com', 'investing.com', 'paxnet.co.kr', '38.co.kr', 'fnguide.com', 'koreacharts.com',
    # Associations, Directories, Portals, General Books & Games
    'kosic.or.kr', 'koshipa.or.kr', 'komea.kr', 'komsa.or.kr', 'yeogie.kr', 'cjuc.or.kr', 'grandculture.net',
    'happycampus.com', 'pe.kr', 'yes24.com', 'aladin.co.kr', 'kyobobook.co.kr', 'arknights.kr',
    'visitkorea.or.kr', 'wjsevin.com',
    # News & Media
    'chosun.com', 'donga.com', 'yna.co.kr', 'hankyung.com', 'mk.co.kr', 'etoday.co.kr',
    'sedaily.com', 'nocutnews.co.kr', 'digitaltoday.co.kr', 'thinkpool.com', 'hani.co.kr',
    'soraknews.co.kr', 'korea.kr'
}

REGISTRY_DOMAINS = {
    'saramin.co.kr', 'jobkorea.co.kr', 'bizno.net', 'nicebizinfo.com', 'catch.co.kr'
}

JUNK_EMAIL_DOMAINS = {
    'nicebizinfo.com', 'saramin.co.kr', 'jobkorea.co.kr', 'incruit.com', 'incruit.co.kr',
    'worxphere.ai', 'jasoseol.com', 'moneypin.biz', 'rndcircle.io', 'korea.kr',
    'kosic.or.kr', 'koshipa.or.kr', 'komsa.or.kr', 'sentry.io', 'wixpress.com',
    'hancoma.com', 'yo-star.com', 'knto.or.kr', 'yes24.com', 'yeogie.kr', 'cjuc.or.kr'
}

INVALID_EMAIL_EXTENSIONS = (
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf',
    '.css', '.js', '.ico', '.woff', '.woff2', '.ttf', '.mp4', '.mp3'
)

JUNK_EMAIL_PATTERNS = [
    r'@[vV]?\d+\.\d+',
    r'core-js', r'rspack', r'lodash', r'react', r'tailwindcss', r'aos@',
    r'pretendard', r'sentry', r'wixpress', r'wix\.com', r'wordpress', r'schema\.org',
    r'example\.com', r'domain\.com', r'email\.com', r'yourcompany', r'yourname',
    r'noreply', r'no-reply', r'donotreply', r'privacy@', r'terms@', r'cookie'
]

PERMANENT_BLACKLIST_COMPANIES = [
    'scandi standard', 'scandi-standard', 'scandi standart',
    'biliarta',
    'daigre', 'daigrė'
]

def is_blacklisted_company(name):
    if not name:
        return False
    n = unicodedata.normalize('NFKD', str(name)).lower()
    n_clean = ''.join(c for c in n if not unicodedata.combining(c))
    return any(b in n_clean for b in PERMANENT_BLACKLIST_COMPANIES)

def clean_company_name(name):
    if not name:
        return ""
    c = str(name).strip()
    for lf in LEGAL_FORMS_KR:
        c = c.replace(lf, '')
    c = re.sub(r'[㈜\(\)\[\]\s]', '', c)
    return c.strip()

def is_domain_excluded(domain):
    if not domain:
        return True
    d = domain.lower().strip()
    if d.startswith('www.'):
        d = d[4:]
    for ex in EXCLUDED_DOMAINS:
        if d == ex or d.endswith('.' + ex):
            return True
    if any(d.endswith(tld) for tld in ['.es.kr', '.ms.kr', '.hs.kr', '.ac.kr', '.go.kr', '.re.kr', '.mil.kr']):
        return True
    return False

def extract_region(address):
    if not address or str(address) == 'nan':
        return ""
    addr = str(address).strip()
    for reg in ['부산', '울산', '경남', '창원', '거제', '통영', '김해', '인천', '경기', '전남', '목포', '여수', '영암', '서울', '충남', '당진', '서산']:
        if reg in addr:
            return reg
    return ""

def clean_phone(phone):
    if not phone or str(phone) == 'nan':
        return ""
    p = str(phone).strip()
    p = re.sub(r'^(?:Tel|TEL|전화|T\.)[:\s]*', '', p).strip()
    if p and not p.startswith("'"):
        p = f"'{p}"
    return p

def clean_email(email_str):
    if not email_str:
        return None
    e = email_str.lower().strip().replace('%20', '').strip('.,;:()[]"\'')
    if '@' not in e or len(e) < 6:
        return None
    if any(e.endswith(ext) for ext in INVALID_EMAIL_EXTENSIONS):
        return None
    for pat in JUNK_EMAIL_PATTERNS:
        if re.search(pat, e):
            return None
    user, _, dom = e.partition('@')
    if not user or not dom or '.' not in dom:
        return None
    if dom in JUNK_EMAIL_DOMAINS or any(dom.endswith('.' + jd) for jd in JUNK_EMAIL_DOMAINS):
        return None
    if is_domain_excluded(dom):
        return None
    return e

def score_email_b2b(email, website_domain=""):
    e = email.lower().strip()
    user, _, domain = e.partition('@')
    score = 0
    if website_domain and website_domain in domain:
        score += 50
    if any(k in user for k in ['recruit', 'job', 'career', 'hr', 'insa', 'personal', 'crew', 'crewing']):
        score += 50
    elif any(k in user for k in ['ceo', 'director', 'manager', 'president', 'master', 'daepyo', 'sales', 'overseas', 'trade', 'obchod']):
        score += 45
    elif any(k in user for k in ['info', 'contact', 'office', 'help', 'service', 'inquiry', 'admin', 'biz']):
        score += 40
    elif '.' in user and website_domain in domain:
        score += 25
    elif any(w in domain for w in ['naver.com', 'daum.net', 'hanmail.net', 'gmail.com']):
        score += 10
    else:
        score += 5
    return score

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[!] Error saving cache: {e}", flush=True)

def extract_homepage_from_registry_soup(soup):
    """
    Extract ONLY explicit homepage/website links from a registry page.
    Never fallback to random external links or banners.
    """
    for tr in soup.select('tr, div[class*="info"], dl, div[class*="detail"], div[class*="company_info"]'):
        text_block = tr.get_text(" ", strip=True)
        if any(k in text_block for k in ['홈페이지', '웹사이트', 'Homepage', 'Website']):
            for a in tr.find_all('a', href=True):
                h = a['href'].strip()
                if h.startswith(('http://', 'https://')):
                    p = urllib.parse.urlparse(h)
                    dom = p.netloc.lower()
                    if not is_domain_excluded(dom) and '.' in dom and len(dom) >= 4:
                        return f"{p.scheme}://{p.netloc}"

    for a in soup.find_all('a', href=True):
        h = a['href'].strip()
        t = a.get_text(strip=True).lower()
        title = a.get('title', '').lower()
        if any(k in t or k in title for k in ['홈페이지', '회사홈페이지', '공식홈페이지', 'homepage']):
            if h.startswith(('http://', 'https://')):
                p = urllib.parse.urlparse(h)
                dom = p.netloc.lower()
                if not is_domain_excluded(dom) and '.' in dom and len(dom) >= 4:
                    return f"{p.scheme}://{p.netloc}"
    return None

async def search_naver_visual(page, comp_name, region=""):
    clean_n = clean_company_name(comp_name)
    if not clean_n:
        return None, None
        
    queries = []
    if region:
        queries.append(f'"{clean_n}" "{region}" 홈페이지')
    queries.append(f'"{clean_n}" 홈페이지')
    if len(clean_n) <= 2:
        queries.append(f'"{clean_n}" 조선')
    else:
        queries.append(f'{clean_n} 조선')

    for q in queries[:2]:
        url = f"https://search.naver.com/search.naver?where=nexearch&query={urllib.parse.quote(q)}"
        try:
            await page.goto(url, timeout=12000, wait_until="domcontentloaded")
            await asyncio.sleep(1.2)
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            docs = soup.select('div[class*="fds-web-doc-root"]')
            for doc in docs:
                links = doc.find_all('a', href=True)
                title_link = None
                for a in links:
                    txt = a.get_text(" ", strip=True)
                    href = a['href'].strip()
                    if not href.startswith('http'):
                        continue
                    if any(k in href for k in ['help.naver.com', 'keep.naver.com']):
                        continue
                    if len(txt) > 3 and not txt.startswith(('Keep', '자세히 보기')):
                        title_link = a
                        break

                if not title_link:
                    continue

                href = title_link['href'].strip()
                title_text = title_link.get_text(" ", strip=True)
                parsed = urllib.parse.urlparse(href)
                dom = parsed.netloc.lower()
                if dom.startswith('www.'):
                    dom = dom[4:]

                # 1. Registry bridge (Saramin, JobKorea, Bizno, Catch)
                if any(reg in dom for reg in REGISTRY_DOMAINS):
                    if any(sub in href for sub in ['/company-info/view', '/Co_Read/', '/article/', '/CS0100', '/company/', '/recruit/']):
                        try:
                            await page.goto(href, timeout=9000, wait_until="domcontentloaded")
                            await asyncio.sleep(1.0)
                            reg_content = await page.content()
                            s_reg = BeautifulSoup(reg_content, 'html.parser')
                            hp = extract_homepage_from_registry_soup(s_reg)
                            if hp:
                                return hp, f"REGISTRY({dom})"
                        except Exception:
                            pass
                    continue

                # 2. Excluded domains check
                if is_domain_excluded(dom):
                    continue

                # 3. Name relevance check in title
                title_clean = re.sub(r'[\s\(\)\[\]㈜\.\-]', '', title_text).lower()
                clean_n_lower = clean_n.lower()
                if clean_n_lower not in title_clean and clean_n_lower not in title_text.lower():
                    core_ascii = re.sub(r'[^a-zA-Z0-9]', '', clean_n).lower()
                    if len(core_ascii) < 4 or core_ascii not in dom:
                        continue

                # 4. Short names (<= 2 Korean chars) require industry keywords
                if len(clean_n) <= 2:
                    ind_keywords = ['조선', '중공업', '엔지니어링', '선박', '해양', '기계', '배관', '철강', '정밀', '테크', 'eng', '공업', '산업', '스틸', '하이텍', '주식회사']
                    doc_text = doc.get_text(" ", strip=True).lower()
                    if not any(k in title_clean for k in ind_keywords) and not any(k in doc_text for k in ['조선', '선박', '해양', '중공업']):
                        continue

                return f"{parsed.scheme}://{parsed.netloc}", "NAVER_WEB_DOC"
        except Exception:
            continue
            
    return None, None

async def crawl_website_visual(page, base_url, comp_name=""):
    if not base_url or is_domain_excluded(urllib.parse.urlparse(base_url).netloc):
        return None, None
        
    parsed = urllib.parse.urlparse(base_url)
    base_netloc = parsed.netloc.lower()
    clean_domain = base_netloc[4:] if base_netloc.startswith('www.') else base_netloc
    
    found_emails = set()
    source_url = base_url

    # 1. Fast Direct Check with curl_cffi (instant raw HTML inspection)
    try:
        from curl_cffi import requests as curl_requests
        s_fast = curl_requests.Session(impersonate="chrome124")
        r_fast = s_fast.get(base_url, timeout=5, verify=False)
        if r_fast.status_code == 200:
            s_soup = BeautifulSoup(r_fast.text, 'html.parser')
            for a in s_soup.find_all('a', href=re.compile(r'^mailto:', re.I)):
                ce = clean_email(a['href'][7:].split('?')[0].strip())
                if ce: found_emails.add(ce)
            for b in s_soup.select('header, footer, [class*="header"], [class*="footer"], [class*="copyright"], [class*="address"], [class*="info"]'):
                for m in re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', b.get_text(" ", strip=True)):
                    ce = clean_email(m)
                    if ce: found_emails.add(ce)
            for m in re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', r_fast.text):
                ce = clean_email(m)
                if ce: found_emails.add(ce)
    except Exception:
        pass

    # 2. Visual Browser Inspection with Playwright (Render JS, scroll to footer)
    dom_contact_links = []
    try:
        try:
            await page.goto(base_url, timeout=9000, wait_until="domcontentloaded")
        except Exception:
            pass

        await asyncio.sleep(1.0)
        try:
            await page.evaluate("() => { if(document.body) window.scrollTo(0, document.body.scrollHeight); }")
        except Exception:
            pass
        await asyncio.sleep(0.8)

        html = await page.content()
        soup = BeautifulSoup(html, 'html.parser')

        for a in soup.find_all('a', href=re.compile(r'^mailto:', re.I)):
            ce = clean_email(a['href'][7:].split('?')[0].strip())
            if ce: found_emails.add(ce)

        for b in soup.select('header, footer, [class*="header"], [class*="footer"], [class*="bottom"], [class*="copyright"], [class*="address"], [class*="contact"], [class*="info"]'):
            b_txt = b.get_text(" ", strip=True)
            for m in re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', b_txt):
                ce = clean_email(m)
                if ce: found_emails.add(ce)

        for m in re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', html):
            ce = clean_email(m)
            if ce: found_emails.add(ce)

        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            txt = a.get_text(strip=True).lower()
            if any(k in txt or k in href.lower() for k in [
                'contact', 'about', 'location', 'inquiry', 'cs', 'support', 'recruit', 'privacy',
                '오시는', '오시는길', '찾아오시는길', '고객', '고객센터', '고객지원', '문의', '온라인문의',
                '회사소개', '회사', '위치', '채용', '개인정보'
            ]):
                full = urllib.parse.urljoin(base_url, href)
                p_sub = urllib.parse.urlparse(full)
                if p_sub.netloc.lower() == base_netloc and full != base_url:
                    dom_contact_links.append(full)
    except Exception:
        pass

    # 3. Add well-known Korean fallback subpaths if few found on DOM
    if len(dom_contact_links) < 2:
        for fb in [
            '/contact', '/contact-us', '/kr/contact', '/kor/about/contact.php',
            '/sub5/sub5-1.php', '/page/sub05/sub05_01.php', '/customer', '/inquiry', '/privacy'
        ]:
            dom_contact_links.append(urllib.parse.urljoin(base_url, fb))

    uniq_links = list(dict.fromkeys(dom_contact_links))[:4]
    for cl in uniq_links:
        try:
            try:
                await page.goto(cl, timeout=8000, wait_until="domcontentloaded")
            except Exception:
                pass
            await asyncio.sleep(0.8)
            try:
                await page.evaluate("() => { if(document.body) window.scrollTo(0, document.body.scrollHeight); }")
            except Exception:
                pass
            s_html = await page.content()
            s_soup = BeautifulSoup(s_html, 'html.parser')
            for a in s_soup.find_all('a', href=re.compile(r'^mailto:', re.I)):
                ce = clean_email(a['href'][7:].split('?')[0].strip())
                if ce:
                    found_emails.add(ce)
                    source_url = cl
            for b in s_soup.select('header, footer, [class*="header"], [class*="footer"], [class*="copyright"], [class*="contact"], [class*="info"]'):
                for m in re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', b.get_text(" ", strip=True)):
                    ce = clean_email(m)
                    if ce:
                        found_emails.add(ce)
                        source_url = cl
            for m in re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', s_html):
                ce = clean_email(m)
                if ce:
                    found_emails.add(ce)
                    source_url = cl
        except Exception:
            pass

    # 4. Fallback: If still no email, check Naver search snippet for company email
    if not found_emails and comp_name:
        clean_n = clean_company_name(comp_name)
        try:
            q = f'"{clean_n}" 이메일'
            url_nav = f"https://search.naver.com/search.naver?where=nexearch&query={urllib.parse.quote(q)}"
            await page.goto(url_nav, timeout=8000, wait_until="domcontentloaded")
            await asyncio.sleep(0.8)
            nav_html = await page.content()
            for m in re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', nav_html):
                ce = clean_email(m)
                if ce and not any(ign in ce for ign in ['naver.com', 'daum.net', 'google.com']):
                    found_emails.add(ce)
                    source_url = "NAVER_SNIPPET"
        except Exception:
            pass

    if not found_emails:
        return None, None
        
    scored = sorted(list(found_emails), key=lambda x: score_email_b2b(x, clean_domain), reverse=True)
    return scored[0], source_url

def consolidate_coldmail_file():
    if not os.path.exists(OUTPUT_ENR):
        return
        
    print("\n[*] Consolidating final Cold Mail dataset: KR_SHIP_NAVR_2COL.csv...", flush=True)
    rows = []
    with open(OUTPUT_ENR, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for r in reader:
            if is_blacklisted_company(r.get('Công ty')):
                continue
            rows.append(r)
            
    with_email = []
    without_email = []
    for r in rows:
        email = r.get('Email', '').strip()
        if email:
            with_email.append(r)
        else:
            without_email.append(r)
            
    final_rows = with_email + without_email
    for idx, r in enumerate(final_rows, start=1):
        r['No.'] = str(idx)
        p = r.get('SĐT', '')
        if p and not p.startswith("'"):
            r['SĐT'] = f"'{p}"

    with open(OUTPUT_COL, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(final_rows)
        
    print(f"[+] DONE 2COL: Total {len(final_rows)} rows | {len(with_email)} WITH EMAIL (Top) | {len(without_email)} without email.", flush=True)

async def run_pipeline():
    parser = argparse.ArgumentParser(description="Visual Enrich KR_SHIP_ALLS via Naver")
    parser.add_argument("--test", type=int, default=0, help="Test mode: only run on N companies")
    args = parser.parse_args()

    print("=================================================================", flush=True)
    print("   VISUAL NAVER SEARCH & DEEP WEB ENRICHMENT (HEADLESS = FALSE)", flush=True)
    print(f"   Input : {INPUT_CSV}", flush=True)
    print(f"   Output: {OUTPUT_ENR} (1ENR) -> {OUTPUT_COL} (2COL)", flush=True)
    if args.test > 0:
        print(f"   *** TEST MODE ACTIVE: Running on first {args.test} missing companies ***", flush=True)
    print("=================================================================\n", flush=True)

    if not os.path.exists(INPUT_CSV):
        print(f"[-] Input file not found: {INPUT_CSV}", flush=True)
        return

    with open(INPUT_CSV, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        all_rows = list(reader)

    cache = load_cache()

    processed_companies = set()
    if os.path.exists(OUTPUT_ENR):
        try:
            with open(OUTPUT_ENR, 'r', encoding='utf-8-sig') as f:
                for r in csv.DictReader(f):
                    c = r.get('Công ty', '').strip()
                    if c:
                        processed_companies.add(c)
        except Exception:
            pass

    file_exists = os.path.exists(OUTPUT_ENR) and os.path.getsize(OUTPUT_ENR) > 0
    enr_file = open(OUTPUT_ENR, 'a', encoding='utf-8-sig', newline='')
    writer = csv.DictWriter(enr_file, fieldnames=fieldnames)
    if not file_exists:
        writer.writeheader()
        enr_file.flush()

    missing_count = 0
    enriched_count = 0
    tested_count = 0

    print("[*] Launching Chromium Browser (headless=False, 1280x800)...", flush=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="ko-KR",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            for idx, row in enumerate(all_rows, start=1):
                comp_name = row.get('Công ty', '').strip()
                if is_blacklisted_company(comp_name):
                    continue
                if comp_name in processed_companies:
                    continue

                current_email = row.get('Email', '').strip()
                current_web = row.get('Liên Hệ', '').strip()
                address = row.get('Địa chỉ', '').strip()
                region = extract_region(address)
                phone = clean_phone(row.get('SĐT', ''))
                row['SĐT'] = phone

                # If company already has email in original CSV, save directly
                if current_email:
                    # Clean bad web placeholders
                    if current_web in ['http://', 'http://-', '-'] or is_domain_excluded(urllib.parse.urlparse(current_web).netloc):
                        row['Liên Hệ'] = ''
                    writer.writerow(row)
                    enr_file.flush()
                    processed_companies.add(comp_name)
                    continue

                missing_count += 1
                tested_count += 1
                print(f"\n[{idx}/{len(all_rows)}] Target: {comp_name} (Region: {region or 'None'})", flush=True)

                cached_data = cache.get(comp_name)
                if cached_data:
                    c_web = cached_data.get('web', '')
                    c_mail = cached_data.get('email', '')
                    # Validate against bad domains
                    if is_domain_excluded(urllib.parse.urlparse(c_web).netloc) or c_web in ['http://', 'http://-', '-']:
                        c_web = ''
                    if c_mail and clean_email(c_mail) is None:
                        c_mail = ''
                    print(f"  -> Cache Hit: Web={c_web} | Email={c_mail}", flush=True)
                    if c_web:
                        row['Liên Hệ'] = c_web
                    if c_mail:
                        row['Email'] = c_mail
                        row['Liên Hệ mail'] = cached_data.get('source_url', '')
                        enriched_count += 1
                    writer.writerow(row)
                    enr_file.flush()
                    processed_companies.add(comp_name)
                    if args.test > 0 and tested_count >= args.test:
                        break
                    continue

                # Step 1: Visual Naver Search
                best_web, source_type = await search_naver_visual(page, comp_name, region)
                if not best_web and current_web and current_web.startswith('http'):
                    parsed_cw = urllib.parse.urlparse(current_web)
                    if not is_domain_excluded(parsed_cw.netloc) and current_web not in ['http://', 'http://-', '-']:
                        best_web = current_web
                        source_type = "CSV_FALLBACK"

                # Step 2: Visual Deep Crawl
                found_email = None
                mail_source_url = None
                if best_web:
                    print(f"  -> Found Website ({source_type}): {best_web}", flush=True)
                    found_email, mail_source_url = await crawl_website_visual(page, best_web, comp_name)
                    if found_email:
                        print(f"  ==> [SUCCESS] Found B2B Email: {found_email} (from {mail_source_url})", flush=True)
                        row['Email'] = found_email
                        row['Liên Hệ'] = best_web
                        row['Liên Hệ mail'] = mail_source_url or best_web
                        enriched_count += 1
                    else:
                        print(f"  [-] No email found on website: {best_web}", flush=True)
                        row['Liên Hệ'] = best_web
                else:
                    print(f"  [-] No official website found on Naver.", flush=True)

                cache[comp_name] = {
                    "web": best_web or "",
                    "email": found_email or "",
                    "source_url": mail_source_url or "",
                    "timestamp": time.time()
                }
                save_cache(cache)

                writer.writerow(row)
                enr_file.flush()
                processed_companies.add(comp_name)

                if tested_count % 10 == 0:
                    consolidate_coldmail_file()

                if args.test > 0 and tested_count >= args.test:
                    print(f"\n[*] Reached test limit of {args.test} companies.", flush=True)
                    break

        except KeyboardInterrupt:
            print("\n[!] Execution paused by user.", flush=True)
        finally:
            await browser.close()
            enr_file.close()
            consolidate_coldmail_file()

    print(f"\n=================================================================", flush=True)
    print(f"   ENRICHMENT BATCH FINISHED", flush=True)
    print(f"   Missing targets evaluated: {tested_count}", flush=True)
    print(f"   Successfully enriched emails: {enriched_count}", flush=True)
    print(f"   Output files ready:", flush=True)
    print(f"    - {OUTPUT_ENR}", flush=True)
    print(f"    - {OUTPUT_COL} (Cold Mail ready)", flush=True)
    print(f"=================================================================\n", flush=True)

if __name__ == '__main__':
    asyncio.run(run_pipeline())
