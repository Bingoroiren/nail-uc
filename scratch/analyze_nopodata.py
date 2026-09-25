import csv
from collections import Counter
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

with open('NOPODATA.csv', 'r', encoding='utf-8-sig', errors='ignore') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

total = len(rows)
print(f"=== TỔNG QUAN TẬP DỮ LIỆU ===")
print(f"Tổng số bản ghi: {total}")

# 1. Trạng thái pháp lý BRREG
brreg_statuses = Counter(r['status_brreg'].strip() for r in rows)
print('\n=== 1. TRẠNG THÁI DOANH NGHIỆP (BRREG) ===')
for k, v in brreg_statuses.most_common(10):
    lbl = k if k else "[Trống]"
    print(f"{lbl:<25}: {v:>5} ({v/total*100:.1f}%)")

# 2. Loại hình pháp lý
legal_forms = Counter(r['legal_form'].strip() for r in rows)
print('\n=== 2. LOẠI HÌNH DOANH NGHIỆP (LEGAL FORM) ===')
for k, v in legal_forms.most_common(10):
    lbl = k if k else "[Trống]"
    print(f"{lbl:<25}: {v:>5} ({v/total*100:.1f}%)")

# 3. Ngành nghề NACE
nace_codes = Counter(r['nace_code'].strip() + " - " + r['nace_name'].strip() for r in rows)
print('\n=== 3. PHÂN BỐ NGÀNH NGHỀ (NACE) ===')
for k, v in nace_codes.most_common(8):
    lbl = k if k.strip(" -") else "[Trống]"
    print(f"{lbl:<60}: {v:>5} ({v/total*100:.1f}%)")

# 4. Kênh tiếp cận (Reachability)
has_email = [r for r in rows if r['email'].strip()]
has_phone = [r for r in rows if r['phone'].strip() or r['phone_all'].strip()]
has_website = [r for r in rows if r['website'].strip()]
has_contact = [r for r in rows if r['contact_name'].strip()]
has_role = [r for r in rows if r['contact_role'].strip()]

print('\n=== 4. ĐỘ PHỦ CÁC TRƯỜNG DỮ LIỆU OUTREACH ===')
print(f"Có Email                 : {len(has_email):>5} ({len(has_email)/total*100:.1f}%)")
print(f"Có Số điện thoại         : {len(has_phone):>5} ({len(has_phone)/total*100:.1f}%)")
print(f"Có Website               : {len(has_website):>5} ({len(has_website)/total*100:.1f}%)")
print(f"Có Tên Người đại diện    : {len(has_contact):>5} ({len(has_contact)/total*100:.1f}%)")
print(f"Có Chức vụ Người đại diện: {len(has_role):>5} ({len(has_role)/total*100:.1f}%)")

# 5. Phân tầng chất lượng Outreach (Quality Tiers)
active_rows = [r for r in rows if r['status_brreg'].strip().lower() == 'aktiv']
active_total = len(active_rows)

tier1 = [r for r in rows if r['email'].strip() and r['contact_name'].strip() and (r['phone'].strip() or r['phone_all'].strip())]
tier2 = [r for r in rows if r['email'].strip() and r['contact_name'].strip()]
tier3 = [r for r in rows if r['email'].strip() and not r['contact_name'].strip()]
tier4 = [r for r in rows if not r['email'].strip() and (r['phone'].strip() or r['phone_all'].strip())]
tier5 = [r for r in rows if not r['email'].strip() and not r['phone'].strip() and not r['phone_all'].strip()]

print('\n=== 5. PHÂN TẦNG KHẢ NĂNG OUTREACH (TRÊN TOÀN BỘ 4,791 BẢN GHI) ===')
print(f"Tier 1 (VIP - Email + Tên Lãnh Đạo + Phone): {len(tier1):>5} ({len(tier1)/total*100:.1f}%) -> Cold Email cá nhân hóa cực cao + Cold Call kết hợp")
print(f"Tier 2 (Email + Tên Lãnh Đạo, thiếu Phone) : {len(tier2)-len(tier1):>5} ({(len(tier2)-len(tier1))/total*100:.1f}%) -> Cold Email cá nhân hóa theo tên (Hi [Name])")
print(f"Tier 3 (Email chung, không có Tên Lãnh Đạo): {len(tier3):>5} ({len(tier3)/total*100:.1f}%) -> Email B2B theo domain chung (info@, post@)")
print(f"Tier 4 (Chỉ có Phone, KHÔNG có Email)     : {len(tier4):>5} ({len(tier4)/total*100:.1f}%) -> Phù hợp Telemarketing / SMS / Zalo-WhatsApp")
print(f"Tier 5 (Không có cả Email & Phone)         : {len(tier5):>5} ({len(tier5)/total*100:.1f}%) -> Không thể outreach trực tiếp (cần enrich thêm)")

# 6. Phân tích chất lượng Email (Domain breakdown)
generic_domains = {'gmail.com', 'hotmail.com', 'yahoo.com', 'outlook.com', 'live.no', 'online.no', 'icloud.com', 'mail.com', 'yahoo.no', 'live.com'}
emails = [r['email'].strip().lower() for r in has_email]
custom_domain_emails = [e for e in emails if '@' in e and e.split('@')[1] not in generic_domains]
generic_domain_emails = [e for e in emails if '@' in e and e.split('@')[1] in generic_domains]

print('\n=== 6. CHẤT LƯỢNG EMAIL ===')
print(f"Tổng số Email tìm được: {len(emails)}")
print(f"Email tên miền riêng công ty (Business Domain): {len(custom_domain_emails)} ({len(custom_domain_emails)/len(emails)*100:.1f}%) -> Độ uy tín và tỷ lệ vào Inbox rất cao")
print(f"Email miễn phí (Gmail/Hotmail/Yahoo/Online.no) : {len(generic_domain_emails)} ({len(generic_domain_emails)/len(emails)*100:.1f}%) -> Thường là chủ hộ kinh doanh cá thể ENK")

# Phổ biến nhất ở email prefix
prefix_types = Counter()
for e in custom_domain_emails:
    prefix = e.split('@')[0]
    if prefix in ['post', 'info', 'kontakt', 'firmapost', 'support', 'mail', 'office']:
        prefix_types['Chung (post@, info@, kontakt@,...)'] += 1
    elif '.' in prefix or '_' in prefix or len(prefix) > 4:
        prefix_types['Cá nhân hóa theo tên nhân sự (john.doe@, ole@,...)'] += 1
    else:
        prefix_types['Khác'] += 1

print('Phân bổ loại hòm thư công ty:')
for k, v in prefix_types.items():
    print(f"  - {k:<45}: {v:>4} ({v/len(custom_domain_emails)*100:.1f}%)")

# 7. Phân tích chức danh người đại diện (Contact Roles)
roles = Counter(r['contact_role'].strip() for r in rows if r['contact_role'].strip())
print('\n=== 7. CHỨC VỤ NGƯỜI LIÊN HỆ ===')
for k, v in roles.most_common(6):
    print(f"{k:<30}: {v:>5} ({v/len(has_role)*100:.1f}%)")

# 8. Check gui
check_gui = Counter(r['Check gui'].strip() for r in rows)
print('\n=== 8. TRẠNG THÁI "Check gui" HIỆN TẠI ===')
for k, v in check_gui.items():
    lbl = k if k else "[Trống / Chưa đánh dấu]"
    print(f"{lbl:<25}: {v:>5} ({v/total*100:.1f}%)")

# 9. Quy mô nhân sự (Employees) & Doanh thu
has_emp = [r for r in rows if r['employees'].strip() and r['employees'].strip() != '0']
print('\n=== 9. QUY MÔ DOANH NGHIỆP ===')
print(f"Có dữ liệu nhân viên (>0): {len(has_emp)} ({len(has_emp)/total*100:.1f}%)")
emp_counts = []
for r in has_emp:
    try:
        emp_counts.append(int(r['employees']))
    except ValueError:
        pass
if emp_counts:
    micro = sum(1 for x in emp_counts if 1 <= x <= 9)
    small = sum(1 for x in emp_counts if 10 <= x <= 49)
    medium = sum(1 for x in emp_counts if 50 <= x <= 249)
    large = sum(1 for x in emp_counts if x >= 250)
    print(f"  - Siêu nhỏ (1 - 9 nhân viên)  : {micro:>4} ({micro/len(emp_counts)*100:.1f}%)")
    print(f"  - Nhỏ (10 - 49 nhân viên)     : {small:>4} ({small/len(emp_counts)*100:.1f}%)")
    print(f"  - Vừa (50 - 249 nhân viên)    : {medium:>4} ({medium/len(emp_counts)*100:.1f}%)")
    print(f"  - Lớn (>= 250 nhân viên)      : {large:>4} ({large/len(emp_counts)*100:.1f}%)")
