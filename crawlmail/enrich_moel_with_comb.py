# -*- coding: utf-8 -*-
"""
Làm giàu dữ liệu cho KR_AGCY_MOEL_0RAW.csv từ KR_AGCY_COMB_2COL.csv:
1. So khớp chuẩn xác Tên công ty + Địa phương (cùng Thành phố/Quận/Huyện).
2. Điền bổ sung Số điện thoại (luôn có nháy đơn '), Website chính thức, Email B2B và Địa chỉ trụ sở chi tiết.
3. Phân loại và đẩy các công ty có thông tin liên hệ lên đầu danh sách.
4. Đánh lại số thứ tự No. từ 1 đến N.
5. Ghi đè trực tiếp vào KR_AGCY_MOEL_0RAW.csv với mã hóa utf-8-sig.
"""

import sys
import io
import re
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

MOEL_FILE = "KR_AGCY_MOEL_0RAW.csv"
COMB_FILE = "KR_AGCY_COMB_2COL.csv"

COLUMNS_20 = [
    'No.', 'Cong ty', 'Chuc danh', 'Nguoi lien he', 'SDT', 'Lien He', 'Email', 
    'Lien He mail', 'Dia chi', 'Luong', 'Ngay dang', 'Han tuyen', 'Check gui', 
    'Last Subject', 'Last Body HTML', 'Trang thai Reply', 'Lan Follow-up', 
    'Ngay Follow-up gan nhat', 'Mailbox da dung', 'Category'
]

def norm(name):
    if not isinstance(name, str): return ''
    n = re.sub(r'[\(\)주유회사\s㈜\.\,\-\_\[\]]', '', name)
    return n.lower()

def core_name(name):
    n = norm(name)
    n = re.sub(r'(직업소개소|인력사무소|인력개발|인력공사|인력|소개소|개발|공사)$', '', n)
    return n

def extract_city(addr):
    if not isinstance(addr, str): return ''
    m = re.search(r'(부산|울산|인천|대구|광주|대전|서울|세종|창원|김해|진주|통영|사천|밀양|거제|양산|의령|함안|창녕|고성|남해|하동|산청|함양|거창|합천|포항|경주|김천|안동|구미|영주|영천|상주|문경|경산|군위|의성|청송|영양|영덕|청도|고령|성주|칠곡|예천|봉화|울진|울릉|목포|여수|순천|나주|광양|담양|곡성|구례|고흥|보성|화순|장흥|강진|해남|영암|무안|함평|영광|장성|완도|진도|신안|전주|군산|익산|정읍|남원|김제|완주|진안|무주|장수|임실|순창|고창|부안|수원|성남|의정부|안양|부천|광명|평택|동두천|안산|고양|과천|구리|남양주|오산|시흥|군포|의왕|하남|용인|파주|이천|안성|김포|화성|광주|양주|포천|여주|연천|가평|양평|춘천|원주|강릉|동해|태백|속초|삼척|홍천|횡성|영월|평창|정선|철원|화천|양구|인제|고성|양양|청주|충주|제천|보은|옥천|영동|증평|진천|괴산|음성|단양|천안|공주|보령|아산|서산|논산|계룡|당진|금산|부여|서천|청양|홍성|예산|태안|제주|서귀포)', addr)
    return m.group(1) if m else ''

def clean_phone(p):
    if pd.isna(p) or not str(p).strip() or str(p) == 'nan':
        return ''
    p_str = str(p).replace('\n', ' ').strip()
    p_clean = re.sub(r'[^\d\+\-\s\(\)]', '', p_str).strip()
    if not p_clean:
        return ''
    return f"'{p_clean}" if not p_clean.startswith("'") else p_clean

print(f"Đang đọc dữ liệu từ {MOEL_FILE} và {COMB_FILE}...")
df_moel = pd.read_csv(MOEL_FILE, encoding='utf-8-sig')
df_comb = pd.read_csv(COMB_FILE, encoding='utf-8-sig')

df_moel['norm'] = df_moel['Cong ty'].apply(norm)
df_comb['norm'] = df_comb['Cong ty'].apply(norm)

df_moel['core'] = df_moel['Cong ty'].apply(core_name)
df_comb['core'] = df_comb['Cong ty'].apply(core_name)

df_moel['city'] = df_moel['Dia chi'].apply(extract_city)
df_comb['city'] = df_comb['Dia chi'].apply(extract_city)

# Tập hợp các bản ghi có thông tin liên hệ hợp lệ từ COMB
comb_valid = df_comb[
    (df_comb['SDT'].notna() & (df_comb['SDT'].astype(str).str.strip() != '')) |
    (df_comb['Email'].notna() & (df_comb['Email'].astype(str).str.strip() != '')) |
    (df_comb['Lien He'].notna() & (df_comb['Lien He'].astype(str).str.strip() != '') & (~df_comb['Lien He'].astype(str).str.contains('moel.go.kr', na=False)))
].copy()

enriched_count = 0
sdt_added = 0
em_added = 0
web_added = 0
addr_refined = 0

for idx in df_moel.index:
    c_norm = df_moel.at[idx, 'norm']
    c_core = df_moel.at[idx, 'core']
    c_city = df_moel.at[idx, 'city']
    
    match_row = None
    # 1. Khớp chính xác tên chuẩn hóa + cùng thành phố
    cands = comb_valid[(comb_valid['norm'] == c_norm) & (comb_valid['city'] == c_city)]
    if len(cands) > 0:
        match_row = cands.iloc[0]
    # 2. Khớp tên cốt lõi + cùng thành phố (nếu chỉ có duy nhất 1 ứng viên)
    elif len(c_core) >= 2 and c_city:
        cands_core = comb_valid[(comb_valid['core'] == c_core) & (comb_valid['city'] == c_city)]
        if len(cands_core) == 1:
            match_row = cands_core.iloc[0]
            
    if match_row is not None:
        enriched = False
        # Điền SĐT nếu có
        comb_sdt = clean_phone(match_row.get('SDT'))
        if comb_sdt and (pd.isna(df_moel.at[idx, 'SDT']) or not str(df_moel.at[idx, 'SDT']).strip()):
            df_moel.at[idx, 'SDT'] = comb_sdt
            sdt_added += 1
            enriched = True
            
        # Điền Email nếu có
        comb_em = str(match_row.get('Email', '')).strip()
        if comb_em and comb_em != 'nan' and (pd.isna(df_moel.at[idx, 'Email']) or not str(df_moel.at[idx, 'Email']).strip()):
            df_moel.at[idx, 'Email'] = comb_em
            em_added += 1
            enriched = True
            
        # Điền Website nếu có
        comb_web = str(match_row.get('Lien He', '')).strip()
        if comb_web and comb_web != 'nan' and 'moel.go.kr' not in comb_web:
            if pd.isna(df_moel.at[idx, 'Lien He']) or 'moel.go.kr' in str(df_moel.at[idx, 'Lien He']):
                df_moel.at[idx, 'Lien He'] = comb_web
                web_added += 1
                enriched = True
                
        # Cập nhật địa chỉ chi tiết hơn từ Naver (có tên đường, số nhà, tầng, toà nhà)
        comb_addr = str(match_row.get('Dia chi', '')).strip().replace('\ue0c8', '').replace('\n', ' ')
        if comb_addr and len(comb_addr) > len(str(df_moel.at[idx, 'Dia chi'])):
            df_moel.at[idx, 'Dia chi'] = comb_addr
            addr_refined += 1
            enriched = True
            
        if enriched:
            enriched_count += 1

# Sắp xếp: Ưu tiên công ty có Email lên hàng đầu, tiếp theo là công ty có SĐT, sau đó là các công ty còn lại
df_moel['has_email'] = df_moel['Email'].notna() & (df_moel['Email'].astype(str).str.strip() != '') & (df_moel['Email'].astype(str) != 'nan')
df_moel['has_sdt'] = df_moel['SDT'].notna() & (df_moel['SDT'].astype(str).str.strip() != '') & (df_moel['SDT'].astype(str) != 'nan')

part_email = df_moel[df_moel['has_email']].copy()
part_sdt_only = df_moel[~df_moel['has_email'] & df_moel['has_sdt']].copy()
part_remaining = df_moel[~df_moel['has_email'] & ~df_moel['has_sdt']].copy()

sorted_moel = pd.concat([part_email, part_sdt_only, part_remaining], ignore_index=True)
sorted_moel['No.'] = range(1, len(sorted_moel) + 1)
sorted_moel = sorted_moel[COLUMNS_20]

# Ghi đè trực tiếp vào KR_AGCY_MOEL_0RAW.csv
sorted_moel.to_csv(MOEL_FILE, index=False, encoding='utf-8-sig')

print("=" * 65)
print("KẾT QUẢ LÀM GIÀU DỮ LIỆU TỪ KR_AGCY_COMB_2COL.CSV")
print("=" * 65)
print(f"- Tổng số công ty được làm giàu liên hệ  : {enriched_count}")
print(f"  * Số điện thoại chuẩn bổ sung           : {sdt_added}")
print(f"  * Email B2B bổ sung                    : {em_added}")
print(f"  * Website chính thức bổ sung           : {web_added}")
print(f"  * Địa chỉ được nâng cấp chi tiết hơn    : {addr_refined}")
print(f"- File ghi đè trực tiếp                 : {MOEL_FILE}")
print(f"- Đã sắp xếp 100% công ty có Email & SĐT lên các hàng đầu tiên!")

print("\nMẫu 10 doanh nghiệp được làm giàu đứng đầu danh sách:")
for idx, r in sorted_moel.head(10).iterrows():
    c = r['Cong ty']
    sdt = r['SDT']
    em = r['Email']
    web = str(r['Lien He'])[:30]
    addr = str(r['Dia chi'])[:40]
    print(f"  {idx+1:2d}. {c:22} | SĐT: {str(sdt):16} | Email: {str(em):22} | Đ/C: {addr}")
