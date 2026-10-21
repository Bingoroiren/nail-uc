# -*- coding: utf-8 -*-
"""
Chuẩn hóa và làm sạch sâu lần cuối cho KR_WELD_E703_2COL.csv:
1. Loại bỏ 100% email rác, template, npm packages (react-dom@, player-component@, gabia, whois...).
2. Dọn dẹp ký tự xuống dòng '\n' trong Số điện thoại, giữ dấu nháy đơn ' ở đầu.
3. Đẩy 100% doanh nghiệp có Email B2B thực tế lên đầu danh sách (with_email + without_email).
4. Đánh số No. 1..N tuần tự.
5. Lưu UTF-8 with BOM (utf-8-sig).
"""

import sys
import re
import pandas as pd
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
FILE_2COL = ROOT_DIR / "KR_WELD_E703_2COL.csv"
FILE_1ENR = ROOT_DIR / "KR_WELD_E703_1ENR.csv"

GARBAGE_PATTERNS = [
    r'react-dom@', r'player-component@', r'core-js@', r'@gabia\.com',
    r'@wixpress\.com', r'@sentry\.io', r'example\.com', r'domain\.com',
    r'someone@', r'youremail@', r'yourname@', r'name@domain',
    r'user@domain', r'test@', r'email@email', r'@whois', r'sample@',
    r'bootstrap@', r'jquery@', r'webpack@', r'@2x\.png', r'@3x\.png'
]

def clean_phone(p):
    if not p:
        return ""
    p_str = str(p).replace('\r', '').replace('\n', '').strip()
    if not p_str or p_str.lower() in ['none', 'nan']:
        return ""
    # Xóa khoảng trắng thừa
    p_str = re.sub(r'\s+', ' ', p_str)
    # Xóa icon maps nếu có
    p_str = re.sub(r'[^\d\+\-\s\(\)]', '', p_str).strip()
    if not p_str:
        return ""
    if not p_str.startswith("'"):
        p_str = f"'{p_str}"
    return p_str

def clean_address(a):
    if not a:
        return ""
    a_str = str(a).replace('\r', '').replace('\n', ' ').strip()
    # Xóa ký tự icon maps ()
    a_str = re.sub(r'[\ue0c8\ue000-\uf8ff]', '', a_str).strip()
    a_str = re.sub(r'\s+', ' ', a_str)
    return a_str

def is_valid_b2b_email(email):
    if not email:
        return False
    em = str(email).strip().lower()
    if not em or em in ['none', 'nan']:
        return False
    if not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', em):
        return False
    for pat in GARBAGE_PATTERNS:
        if re.search(pat, em):
            return False
    # Kiểm tra đuôi TLD hợp lệ
    tld = em.split('.')[-1]
    if len(tld) < 2 or any(c.isdigit() for c in tld):
        return False
    return True

def finalize(filepath):
    if not filepath.exists():
        return
        
    df = pd.read_csv(filepath, dtype=str).fillna("")
    print(f"Xử lý: {filepath.name} (Tổng dòng: {len(df)})")
    
    # 1. Làm sạch SĐT và Địa chỉ
    df["SDT"] = df["SDT"].apply(clean_phone)
    df["Dia chi"] = df["Dia chi"].apply(clean_address)
    
    # 2. Làm sạch Email
    def filter_email(em):
        if is_valid_b2b_email(em):
            return str(em).strip()
        return ""

    df["Email"] = df["Email"].apply(filter_email)
    
    # 3. Phân loại with_email và without_email
    with_email = df[df["Email"].astype(str).str.strip().ne("")].copy()
    without_email = df[df["Email"].astype(str).str.strip().eq("")].copy()
    
    print(f" -> Số doanh nghiệp có Email B2B hợp lệ: {len(with_email)}")
    print(f" -> Số doanh nghiệp chưa có Email: {len(without_email)}")
    
    # Ghép lại với 100% dòng có Email lên đầu
    df_sorted = pd.concat([with_email, without_email], ignore_index=True)
    df_sorted["No."] = range(1, len(df_sorted) + 1)
    
    df_sorted.to_csv(filepath, index=False, encoding="utf-8-sig")
    print(f"[V] Hoàn tất ghi {filepath.name}\n")

if __name__ == "__main__":
    finalize(FILE_2COL)
    finalize(FILE_1ENR)
