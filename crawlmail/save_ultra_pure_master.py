import sys
import os
import csv
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
MASTER_FILE = ROOT_DIR / "KR_AGCY_SHIP_2COL.csv"
FMT_FILE = ROOT_DIR / "data" / "formatted" / "KR_AGCY_SHIP_2COL.csv"

COLUMNS = [
    "No.", "Công ty", "Chức danh", "Người liên hệ", "SĐT", "Liên Hệ",
    "Email", "Liên Hệ mail", "Địa chỉ", "Lương", "Ngày đăng", "Hạn tuyển",
    "Check gửi", "Last Subject", "Last Body HTML", "Trạng thái Reply",
    "Lần Follow-up", "Ngày Follow-up gần nhất", "Mailbox đã dùng", "Category"
]

with open(MASTER_FILE, 'r', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))

email_rows = [r for r in rows if r['Email'].strip()]
no_email_rows = [r for r in rows if not r['Email'].strip()]

HARD_EXCLUDE = [
    'hshi.co.kr', 'hhi.co.kr', 'samsungshi.com', 'hanwha-ocean.com', 'hjsc.co.kr',
    '노무법인', '공인노무사', '산재', '손해사정', '컨설팅', '코칭', '특강', '운동본부',
    '소중지대', 'gfc', '음악', '♬', '선생', '쌤', '아카데미', '스터디', '정보',
    '사이트', '플랫폼', '자산', '세무', '회계', '공기업', 'ncs', '자소서', '면접',
    '이직', '부동산', '중개사', '치과', '의원', '병원', '호텔', '투어', '여행',
    '골프', '축구', '체대', '입시', '학원', '어린이', '유치원', '냥', '고양이',
    '강아지', '보험', '재테크', '주식', '코인', '뉴스', '일보', '신문', '방송',
    'tv', '유튜브', '일상', '맛집', '뷰티', '패션', '철도', '코레일', '군청', '시청'
]

ultra_pure = []
for r in email_rows:
    cname = r['Công ty'].strip()
    em = r['Email'].strip().lower()
    
    if any(bad in cname.lower() or bad in em for bad in HARD_EXCLUDE):
        continue
        
    is_target = any(k in cname.lower() for k in ['행정사', '비자', 'visa', '인력', '소개', '선원', '해무', '마린', 'marine', '해사', '송출', '송입'])
    if not is_target:
        is_target = any(k in em for k in ['visa', 'admin', 'ship', 'marine', 'job', 'recruit'])
        
    if is_target:
        ultra_pure.append(r)

# Clean company names if they have weird prefixes
for r in ultra_pure:
    c = r['Công ty']
    c = c.replace('*', '').strip()
    if c.startswith('♬'):
        c = c.lstrip('♬').strip()
    r['Công ty'] = c

# Sort ultra_pure by Category, Company
ultra_pure.sort(key=lambda x: (x.get('Category', ''), x.get('Công ty', '')))

# Combine with no_email_rows
combined = ultra_pure + no_email_rows

# Renumber No. sequentially
for idx, r in enumerate(combined, 1):
    r['No.'] = idx

# Write to both files
for path in [MASTER_FILE, FMT_FILE]:
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(combined)
    print(f"[OK] Saved {len(combined)} rows to {path}")

print(f"\n[DONE] Đã thanh lọc tuyệt đối: {len(ultra_pure)} Email Ultra Pure tại Top (Hàng 1 đến {len(ultra_pure)}).")
