# -*- coding: utf-8 -*-
"""
PURGE INVALID, JUNK, EXPIRED DOMAIN & SERVER EMAILS - BELGIUM METAL
==================================================================
Bộ lọc chuyên sâu cho BE_METL_KBO0_2COL.csv:
1. Lọc mail lỗi syntax, khoảng trắng ẩn (\xa0, %20), đuôi file, định dạng sai RFC.
2. Lọc mail rác, template, placeholder (test@, sample@, someone@, john.doe@...).
3. Lọc mail server, automated, tracking (no-reply@, mailer-daemon@, privacy@, sentry@...).
4. Lọc mail sàn danh bạ, proxy công chứng (belnot.be, bizbook.be, localservices.be...).
5. Kiểm tra DNS thực tế (MX & A record): Loại bỏ 100% domain hết hạn (NXDOMAIN / No MX No A).
6. Sắp xếp 100% email chất lượng lên đầu, đánh lại số No., đồng bộ csdl_mlt.
"""

import os
import sys
import re
import csv
import dns.resolver
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

COL_20_HEADERS = [
    'No.', 'Công ty', 'Chức danh', 'Người liên hệ', 'SĐT', 'Liên Hệ', 'Email', 
    'Liên Hệ mail', 'Địa chỉ', 'Lương', 'Ngày đăng', 'Hạn tuyển', 'Check gửi', 
    'Last Subject', 'Last Body HTML', 'Trạng thái Reply', 'Lần Follow-up', 
    'Ngày Follow-up gần nhất', 'Mailbox đã dùng', 'Category'
]

MAJOR_DOMAINS = {
    'gmail.com', 'googlemail.com', 'hotmail.com', 'hotmail.be', 'hotmail.fr',
    'outlook.com', 'outlook.be', 'outlook.fr', 'yahoo.com', 'yahoo.fr',
    'yahoo.be', 'icloud.com', 'me.com', 'msn.com', 'live.com', 'live.be',
    'skynet.be', 'telenet.be', 'proximus.be', 'scarlet.be', 'voo.be', 'belgacom.net'
}

JUNK_PREFIXES = {
    'youremail', 'your-email', 'your_email', 'yourname', 'your-name',
    'yourcompany', 'someone', 'john.doe', 'johndoe', 'jane.doe',
    'user', 'username', 'test', 'testing', 'sample', 'demo',
    'placeholder', 'nobody', 'name', 'email', 'mail'
}

SYSTEM_PREFIXES = {
    'noreply', 'no-reply', 'donotreply', 'do-not-reply', 'no_reply',
    'mailer-daemon', 'postmaster', 'hostmaster', 'root', 'daemon',
    'bounce', 'bounces', 'auto-confirm', 'automated',
    'privacy', 'dataprivacy', 'datenschutz', 'gdpr', 'dpo',
    'abuse', 'security', 'noc', 'sentry', 'wix', 'wixpress', 'wordpress'
}

JUNK_DOMAINS = {
    'example.com', 'domain.com', 'yourdomain.com', 'yourcompany.com',
    'company.com', 'website.com', 'site.com', 'email.com', 'mail.com',
    'test.com', 'sample.com',
    'localservices.be', 'bizbook.be', 'pagesdor.be', 'goudengids.be',
    'goldenpages.be', 'infobel.com', 'kompass.com', 'trendstop.knack.be',
    'staatsbladmonitor.be', 'belnot.be', 'notaire.be', 'notaris.be',
    'facebook.com', 'instagram.com', 'linkedin.com', 'google.com'
}

def clean_email_str(em):
    if not em:
        return ""
    e = str(em).strip().lower()
    e = e.replace('\xa0', '').replace('\u00a0', '').replace('%20', '')
    return e.strip(' .,;')

def clean_phone_str(p):
    if not p:
        return ""
    p_str = str(p).strip()
    return f"'{p_str}" if not p_str.startswith("'") else p_str

def resolve_domain_dns(domain, resolver):
    if domain in MAJOR_DOMAINS:
        return True, "VALID_MAJOR"
    if domain in JUNK_DOMAINS:
        return False, f"JUNK_DOMAIN_{domain}"
    if not re.match(r'^[a-z0-9-]+(\.[a-z0-9-]+)+$', domain) or domain.endswith('.local') or domain.endswith('.test'):
        return False, "INVALID_SYNTAX"
    try:
        try:
            mx_records = resolver.resolve(domain, 'MX')
            mx_hosts = [str(r.exchange).lower() for r in mx_records]
            parking_keywords = ['sedoparking', 'hugedomains', 'bodis', 'parked', 'afternic', 'domainmarket', 'parkingcrew']
            if any(any(pk in mh for pk in parking_keywords) for mh in mx_hosts):
                return False, "PARKED_DOMAIN"
            return True, "VALID_MX"
        except (dns.resolver.NoAnswer, dns.resolver.NoNameservers):
            resolver.resolve(domain, 'A')
            return True, "VALID_A_FALLBACK"
    except dns.resolver.NXDOMAIN:
        return False, "EXPIRED_NXDOMAIN"
    except (dns.resolver.NoAnswer, dns.resolver.NoNameservers):
        return False, "NO_MX_NO_A"
    except Exception as e:
        return False, f"DNS_ERROR_{type(e).__name__}"

def purge_metal_emails():
    target_csv = ROOT_DIR / "BE_METL_KBO0_2COL.csv"
    ready_csv = ROOT_DIR / "BE_METL_KBO0_ONLY_EMAILS_READY.csv"
    csdl_2col = ROOT_DIR / "csdl_mlt" / "BE_METL_KBO0_2COL.csv"
    csdl_ready = ROOT_DIR / "csdl_mlt" / "BE_METL_KBO0_ONLY_EMAILS_READY.csv"

    print("=" * 80)
    print("🇧🇪  LỌC MAIL LỖI, MAIL RÁC, DOMAIN HẾT HẠN & MAIL SERVER - BE_METL_KBO0_2COL.csv")
    print("=" * 80)

    if not target_csv.exists():
        print(f"[!] Không tìm thấy tệp {target_csv}")
        return

    with open(target_csv, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    initial_total = len(rows)
    initial_emails = sum(1 for r in rows if r.get('Email', '').strip())
    print(f"[*] Tổng số dòng hiện tại : {initial_total:,} dòng")
    print(f"[*] Số dòng có Email       : {initial_emails:,} dòng\n")

    # Thu thập domain để kiểm tra DNS
    unique_domains = set()
    for r in rows:
        em = clean_email_str(r.get('Email', ''))
        if '@' in em:
            unique_domains.add(em.split('@')[1])

    print(f"[*] Đang kiểm tra bản ghi DNS MX/A của {len(unique_domains):,} tên miền...", flush=True)
    resolver = dns.resolver.Resolver()
    resolver.timeout = 3.0
    resolver.lifetime = 4.0
    resolver.nameservers = ['1.1.1.1', '8.8.8.8']

    domain_cache = {}
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(resolve_domain_dns, d, resolver): d for d in unique_domains}
        for fut in futures:
            d = futures[fut]
            try:
                domain_cache[d] = fut.result()
            except Exception:
                domain_cache[d] = (False, "DNS_EXCEPTION")

    # Tiến hành phân loại & lọc
    flagged_records = []
    cleaned_rows = []

    for r in rows:
        comp = r.get('Công ty', '').strip()
        raw_email = r.get('Email', '').strip()
        raw_phone = clean_phone_str(r.get('SĐT', ''))

        if not raw_email:
            if raw_phone:
                r['SĐT'] = raw_phone
                cleaned_rows.append(r)
            continue

        clean_e = clean_email_str(raw_email)
        is_bad = False
        bad_reason = ""

        # 1. Cú pháp regex
        if not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', clean_e):
            is_bad = True
            bad_reason = "Cú pháp email không hợp lệ"
        elif any(clean_e.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.js', '.css', '.pdf', '.ico']):
            is_bad = True
            bad_reason = "Chứa đuôi tệp media/tài liệu"
        else:
            prefix, domain = clean_e.split('@', 1)

            # 2. Mail rác prefix
            if prefix in JUNK_PREFIXES:
                is_bad = True
                bad_reason = f"Mail rác / template demo ('{prefix}')"
            # 3. Mail server / system
            elif prefix in SYSTEM_PREFIXES or prefix.startswith('noreply') or prefix.startswith('no-reply'):
                is_bad = True
                bad_reason = f"Mail server tự động ('{prefix}')"
            # 4. Mail rác domain
            elif domain in JUNK_DOMAINS:
                is_bad = True
                bad_reason = f"Domain thư bạ / công chứng ('{domain}')"
            else:
                # 5. DNS check
                dom_ok, dom_msg = domain_cache.get(domain, (True, "OK"))
                if not dom_ok:
                    is_bad = True
                    bad_reason = f"Tên miền hết hạn / không tồn tại ({dom_msg})"

        if is_bad:
            flagged_records.append((comp, clean_e, bad_reason, bool(raw_phone)))
            r['Email'] = ''
            if raw_phone:
                r['SĐT'] = raw_phone
                cleaned_rows.append(r)
        else:
            r['Email'] = clean_e
            r['SĐT'] = raw_phone
            cleaned_rows.append(r)

    # Rule 3: Đẩy 100% doanh nghiệp có Email lên đầu
    with_email = [r for r in cleaned_rows if r.get('Email', '').strip()]
    without_email = [r for r in cleaned_rows if not r.get('Email', '').strip()]
    sorted_final = with_email + without_email

    for idx, r in enumerate(sorted_final, start=1):
        r['No.'] = idx

    # Lưu file 2COL chính và CSDL
    for target in [target_csv, csdl_2col]:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=COL_20_HEADERS)
            writer.writeheader()
            writer.writerows(sorted_final)

    # Lưu file ONLY_EMAILS_READY
    ready_rows = [dict(r) for r in with_email]
    for idx, r in enumerate(ready_rows, start=1):
        r['No.'] = idx

    for target in [ready_csv, csdl_ready]:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=COL_20_HEADERS)
            writer.writeheader()
            writer.writerows(ready_rows)

    print("\n" + "=" * 80)
    print("📋 DANH SÁCH EMAIL BỊ LOẠI BỎ CHI TIẾT:")
    for comp, em, reason, has_p in flagged_records:
        action = "Giữ lại SĐT" if has_p else "Xóa hoàn toàn"
        print(f"  ❌ [{reason}] {comp} ({em}) -> {action}")

    print("\n" + "=" * 80)
    print(f"🏆 KẾT QUẢ SAU KHI LỌC SẠCH (BE_METL):")
    print(f"   - Tổng email bị loại bỏ       : {len(flagged_records):,} email")
    print(f"   - Email chuẩn, sống, sạch 100%: {len(with_email):,} email (Xếp No. 1 -> {len(with_email):,})")
    print(f"   - Doanh nghiệp có SĐT         : {len([r for r in sorted_final if r.get('SĐT')]):,} doanh nghiệp")
    print(f"   - Tổng số doanh nghiệp còn lại: {len(sorted_final):,} doanh nghiệp")
    print(f"   - Tệp cập nhật: {target_csv.name} & {ready_csv.name}")
    print("=" * 80 + "\n")

if __name__ == '__main__':
    purge_metal_emails()

