# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
import re

def norm(name):
    if not isinstance(name, str): return ''
    n = re.sub(r'[\(\)주유회사\s㈜\.\,\-\_\[\]]', '', name)
    return n.lower()

def extract_city(addr):
    if not isinstance(addr, str): return ''
    # Match Korean province / city / county
    m = re.search(r'(부산|울산|인천|대구|광주|대전|서울|세종|창원|김해|진주|통영|사천|밀양|거제|양산|의령|함안|창녕|고성|남해|하동|산청|함양|거창|합천|포항|경주|김천|안동|구미|영주|영천|상주|문경|경산|군위|의성|청송|영양|영덕|청도|고령|성주|칠곡|예천|봉화|울진|울릉|목포|여수|순천|나주|광양|담양|곡성|구례|고흥|보성|화순|장흥|강진|해남|영암|무안|함평|영광|장성|완도|진도|신안|전주|군산|익산|정읍|남원|김제|완주|진안|무주|장수|임실|순창|고창|부안|수원|성남|의정부|안양|부천|광명|평택|동두천|안산|고양|과천|구리|남양주|오산|시흥|군포|의왕|하남|용인|파주|이천|안성|김포|화성|광주|양주|포천|여주|연천|가평|양평|춘천|원주|강릉|동해|태백|속초|삼척|홍천|횡성|영월|평창|정선|철원|화천|양구|인제|고성|양양|청주|충주|제천|보은|옥천|영동|증평|진천|괴산|음성|단양|천안|공주|보령|아산|서산|논산|계룡|당진|금산|부여|서천|청양|홍성|예산|태안|제주|서귀포)', addr)
    return m.group(1) if m else ''

moel = pd.read_csv('KR_AGCY_MOEL_0RAW.csv', encoding='utf-8-sig')
comb = pd.read_csv('KR_AGCY_COMB_2COL.csv', encoding='utf-8-sig')

moel['norm'] = moel['Cong ty'].apply(norm)
comb['norm'] = comb['Cong ty'].apply(norm)

moel['city'] = moel['Dia chi'].apply(extract_city)
comb['city'] = comb['Dia chi'].apply(extract_city)

# Filter COMB with actual contact info
comb_valid = comb[
    (comb['SDT'].notna() & (comb['SDT'].astype(str).str.strip() != '')) |
    (comb['Email'].notna() & (comb['Email'].astype(str).str.strip() != '')) |
    (comb['Lien He'].notna() & (comb['Lien He'].astype(str).str.strip() != '') & (~comb['Lien He'].astype(str).str.contains('moel.go.kr', na=False)))
].copy()

# Match by norm name AND city
strict_matches = []
for idx, r_moel in moel.iterrows():
    c_norm = r_moel['norm']
    c_city = r_moel['city']
    candidates = comb_valid[comb_valid['norm'] == c_norm]
    if len(candidates) == 0:
        continue
    
    # 1. First priority: Exact city match
    city_match = candidates[candidates['city'] == c_city]
    if len(city_match) > 0:
        best = city_match.iloc[0]
        strict_matches.append((idx, r_moel, best, 'EXACT_CITY'))
    elif len(candidates) == 1 and not c_city:
        best = candidates.iloc[0]
        strict_matches.append((idx, r_moel, best, 'SINGLE_CANDIDATE'))

print(f"Tổng số cty MOEL: {len(moel)}")
print(f"Số cty khớp CHÍNH XÁC CẢ TÊN VÀ ĐỊA PHƯƠNG (City match): {len(strict_matches)}")

has_sdt = sum(1 for m in strict_matches if pd.notna(m[2]['SDT']) and str(m[2]['SDT']).strip() != '')
has_em = sum(1 for m in strict_matches if pd.notna(m[2]['Email']) and str(m[2]['Email']).strip() != '')
has_web = sum(1 for m in strict_matches if pd.notna(m[2]['Lien He']) and str(m[2]['Lien He']).strip() != '' and 'moel.go.kr' not in str(m[2]['Lien He']))

print(f"  -> Bổ sung được Số điện thoại chuẩn : {has_sdt}")
print(f"  -> Bổ sung được Email B2B            : {has_em}")
print(f"  -> Bổ sung được Website chính thức   : {has_web}")

print("\nMẫu 15 cty khớp chính xác 100%:")
for m in strict_matches[:15]:
    mo = m[1]
    co = m[2]
    print(f"  [+] {mo['Cong ty']:22} | City: {mo['city']} | SĐT: {str(co['SDT']):16} | Web: {str(co['Lien He'])[:30]} | Đ/C: {str(co['Dia chi'])[:35]}")
