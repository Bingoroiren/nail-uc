import csv
import sys
from pathlib import Path

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent

# 1. Đọc Mail Tracker để kiểm tra trùng
tracker_path = ROOT_DIR / "Mail Tracker - mail.csv"
tracker_emails = set()
if tracker_path.exists():
    with open(tracker_path, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            sender = row.get('Người gửi', '').strip().lower()
            if sender:
                tracker_emails.add(sender)

# 2. Đọc map phản hồi từ file (xong 23_9)
xong_path = ROOT_DIR / "(xong 23_9) nông trại áo - CleanData.csv"
reply_map = {}
if xong_path.exists():
    with open(xong_path, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            em = row.get('Email', '').strip().lower()
            rep = row.get('Trạng thái Reply', '').strip()
            if em and rep:
                reply_map[em] = rep

# 3. Đọc tệp dữ liệu cần xử lý
enr_path = ROOT_DIR / "AT_AGRI_WBIO_1ENR.csv"
with open(enr_path, encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    rows = list(reader)

total_before = len(rows)

# Kiểm tra và xóa bản ghi trùng Mail Tracker (nếu có)
rows_after_tracker = []
deleted_tracker = []
for r in rows:
    em = r.get('Email', '').strip().lower()
    if em and em in tracker_emails:
        deleted_tracker.append((r.get('Công ty'), em))
    else:
        rows_after_tracker.append(r)

# Đối chiếu chỉ 2 cột: Email và Trạng thái Reply từ file (xong 23_9)
updated_replies = []
for idx, r in enumerate(rows_after_tracker):
    em = r.get('Email', '').strip().lower()
    if em and em in reply_map:
        r['Trạng thái Reply'] = reply_map[em]
        updated_replies.append({
            'Dòng': idx + 1,
            'Công ty': r.get('Công ty'),
            'Email': r.get('Email'),
            'Trạng thái Reply': reply_map[em]
        })

# Ghi lại tệp AT_AGRI_WBIO_1ENR.csv
with open(enr_path, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows_after_tracker)

print(f"Tổng số bản ghi ban đầu: {total_before}")
print(f"Bản ghi trùng Mail Tracker bị xóa: {len(deleted_tracker)}")
print(f"Bản ghi sau khi lọc Mail Tracker: {len(rows_after_tracker)}")
print(f"Bản ghi được cập nhật Trạng thái Reply từ (xong 23-9): {len(updated_replies)}")
for item in updated_replies:
    print(f"- [Dòng {item['Dòng']}] {item['Công ty']} | Email: {item['Email']} -> Trạng thái: {item['Trạng thái Reply']}")
