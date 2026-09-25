import csv
from collections import Counter
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

with open('NOPODATA.csv', 'r', encoding='utf-8-sig', errors='ignore') as f:
    rows = list(csv.DictReader(f))

total = len(rows)
has_email = [r for r in rows if r['email'].strip()]
no_email = [r for r in rows if not r['email'].strip()]

raw_emails = [r['email'].strip() for r in has_email]
emails_lower = [e.lower() for e in raw_emails]
unique_emails = set(emails_lower)

# Email counts
email_counts = Counter(emails_lower)
duplicated_emails = {k: v for k, v in email_counts.items() if v > 1}

# Active status of email rows
email_active = [r for r in has_email if r['status_brreg'].strip().lower() == 'aktiv']
email_closed = [r for r in has_email if r['status_brreg'].strip().lower() != 'aktiv']

# Email breakdown
generic_domains = {'gmail.com', 'hotmail.com', 'yahoo.com', 'outlook.com', 'live.no', 'online.no', 'icloud.com', 'mail.com', 'yahoo.no', 'live.com'}
custom_domain_emails = [e for e in emails_lower if '@' in e and e.split('@')[1] not in generic_domains]
free_domain_emails = [e for e in emails_lower if '@' in e and e.split('@')[1] in generic_domains]

# Prefix analysis (Direct decision maker vs General inbox)
named_inbox = []
generic_inbox = []
for e in custom_domain_emails:
    prefix = e.split('@')[0]
    if prefix in ['post', 'info', 'kontakt', 'firmapost', 'support', 'mail', 'office', 'admin', 'service', 'booking', 'faktura']:
        generic_inbox.append(e)
    else:
        named_inbox.append(e)

# Personalization fields attached to emails
with_name = [r for r in has_email if r['contact_name'].strip()]
with_role = [r for r in has_email if r['contact_role'].strip()]
with_web = [r for r in has_email if r['website'].strip()]
with_city = [r for r in has_email if r['city'].strip()]
with_emp = [r for r in has_email if r['employees'].strip() and r['employees'].strip() != '0']

# Missing email potential
no_email_has_web = [r for r in no_email if r['website'].strip()]
no_email_no_web = [r for r in no_email if not r['website'].strip()]

print(f"=== BÁO CÁO CHUYÊN SÂU: EMAIL COLD OUTREACH ===")
print(f"Tổng số hàng trong file: {total:,}")
print(f"Số hàng CÓ Email: {len(has_email):,} ({len(has_email)/total*100:.2f}%)")
print(f"Số hàng CHƯA CÓ Email: {len(no_email):,} ({len(no_email)/total*100:.2f}%)")
print(f"Số Email duy nhất (Unique Emails): {len(unique_emails):,}")
print(f"Số Email trùng lặp (nhiều chi nhánh dùng chung): {len(duplicated_emails):,} (chiếm {sum(duplicated_emails.values()):,} dòng)")

print(f"\n--- 1. TÌNH TRẠNG PHÁP LÝ CỦA TẬP CÓ EMAIL ---")
print(f"Doanh nghiệp đang hoạt động bình thường (Aktiv): {len(email_active):,} ({len(email_active)/len(has_email)*100:.1f}%)")
print(f"Doanh nghiệp phá sản/giải thể (Konkurs/Avvikling): {len(email_closed):,} ({len(email_closed)/len(has_email)*100:.1f}%)")

print(f"\n--- 2. CHẤT LƯỢNG HÒM THƯ (INBOX DELIVERABILITY) ---")
print(f"1. Email Doanh Nghiệp (Domain riêng @company.no / .com): {len(custom_domain_emails):,} ({len(custom_domain_emails)/len(has_email)*100:.1f}%)")
print(f"   • Hòm thư đích danh nhân sự/lãnh đạo (ole@, john.doe@): {len(named_inbox):,} ({len(named_inbox)/len(custom_domain_emails)*100:.1f}%)")
print(f"   • Hòm thư nghiệp vụ công ty (post@, info@, kontakt@):   {len(generic_inbox):,} ({len(generic_inbox)/len(custom_domain_emails)*100:.1f}%)")
print(f"2. Email Cá Nhân / Miễn phí (@gmail, @hotmail, @online.no): {len(free_domain_emails):,} ({len(free_domain_emails)/len(has_email)*100:.1f}%)")

print(f"\n--- 3. KHẢ NĂNG CÁ NHÂN HÓA COLD EMAIL (HIỆU QUẢ PHẢN HỒI) ---")
print(f"• Có Tên Người nhận (Full Name lãnh đạo): {len(with_name):,} ({len(with_name)/len(has_email)*100:.1f}%) -> Cá nhân hóa 'Hi [Name]'")
print(f"• Có Chức vụ (Daglig leder / CEO):        {len(with_role):,} ({len(with_role)/len(has_email)*100:.1f}%)")
print(f"• Có Tên Công ty (Company Name):          {len(has_email):,} (100.0%) -> 'Dear team at [Company]'")
print(f"• Có Thành phố / Địa phương:              {len(with_city):,} ({len(with_city)/len(has_email)*100:.1f}%) -> Đề cập vị trí tại Na Uy")
print(f"• Có Quy mô nhân viên thực tế:            {len(with_emp):,} ({len(with_emp)/len(has_email)*100:.1f}%)")

print(f"\n--- 4. DỮ LIỆU ĐỂ ENRICH (MỞ RỘNG EMAIL) ---")
print(f"• Số công ty thiếu email nhưng ĐÃ CÓ sẵn Website: {len(no_email_has_web):,} cty")
print(f"• Số công ty thiếu cả email và website:            {len(no_email_no_web):,} cty")
