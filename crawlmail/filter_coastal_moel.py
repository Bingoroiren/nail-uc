# -*- coding: utf-8 -*-
"""
Lọc tệp KR_AGCY_MOEL_0RAW.csv:
Chỉ giữ lại các công ty có địa chỉ ở các khu vực có biển, có tàu thuyền (các tỉnh/thành phố ven biển, cảng biển, xưởng đóng tàu)
và các doanh nghiệp chuyên về hàng hải/đóng tàu/thủy sản.
Không tạo backup, ghi đè trực tiếp theo yêu cầu người dùng.
Đánh lại số thứ tự No. từ 1 đến N.
Mã hóa chuẩn UTF-8 with BOM (utf-8-sig).
"""

import sys
import io
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

CSV_FILE = "KR_AGCY_MOEL_0RAW.csv"

# Danh mục các địa phương ven biển, có cảng biển, có tàu thuyền / đóng tàu / hàng hải
COASTAL_REGIONS = [
    # 1. Các thủ phủ đóng tàu & cảng biển lớn
    '울산', '거제', '통영', '영암', '목포', '여수', '군산', '포항', '창원', '부산',
    '사천', '고성', '해남', '광양', '고흥', '완도', '진도', '신안', '서천', '남해',
    # 2. Cảng biển miền Đông & duyên hải Gangwon / Gyeongbuk
    '동해', '속초', '강릉', '삼척', '양양', '울진', '영덕', '울릉',
    # 3. Vùng cảng biển Tây, Incheon, ven biển Gyeonggi, cảng biển Chungnam, ven biển Jeonbuk/Jeonnam
    '인천', '평택', '화성', '안산', '시흥', '당진', '서산', '보령', '태안', '홍성', '부안', '고창',
    '김포', '강진', '보성', '장흥', '영광', '함평', '무안', '순천',
    # 4. Đảo Jeju
    '제주', '서귀포'
]

MARITIME_NAME_KEYWORDS = ['해양', '선박', '항만', '조선', '수산', '마린', '해운', '어업', '항해', '도선', '선원']

df = pd.read_csv(CSV_FILE, encoding='utf-8-sig')
initial_count = len(df)
print(f"Tổng số dòng ban đầu trong {CSV_FILE}: {initial_count}")

def is_target(row):
    addr = str(row.get('Dia chi', ''))
    name = str(row.get('Cong ty', ''))
    
    # 1. Địa chỉ thuộc khu vực có biển, có tàu thuyền, hải cảng
    if any(k in addr for k in COASTAL_REGIONS):
        return True
    # 2. Tên doanh nghiệp chuyên về hàng hải, đóng tàu, thủy sản
    if any(k in name for k in MARITIME_NAME_KEYWORDS):
        return True
        
    return False

df_filtered = df[df.apply(is_target, axis=1)].copy()

# Đánh lại số thứ tự No. từ 1 đến N
df_filtered['No.'] = range(1, len(df_filtered) + 1)

# Ghi đè trực tiếp vào file gốc mà không tạo backup
df_filtered.to_csv(CSV_FILE, index=False, encoding='utf-8-sig')

final_count = len(df_filtered)
removed_count = initial_count - final_count

print("=" * 65)
print("HOÀN TẤT LỌC VÙNG CÓ BIỂN / CẢNG BIỂN / TÀU THUYỀN")
print("=" * 65)
print(f"- Số dòng ban đầu     : {initial_count}")
print(f"- Đã loại bỏ (nội địa): {removed_count} công ty (Seoul, Daegu, Daejeon, Chungbuk...)")
print(f"- Số lượng GIỮ LẠI    : {final_count} công ty ven biển & cảng tàu thuyền")
print(f"- File ghi đè trực tiếp: {CSV_FILE}")

print("\nPhân bố các địa phương ven biển tiêu biểu:")
for loc, count in df_filtered['Dia chi'].value_counts().head(20).items():
    print(f"  * {loc:25} : {count:4d} văn phòng")
