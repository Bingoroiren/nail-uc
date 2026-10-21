# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
import re

def norm(name):
    if not isinstance(name, str): return ''
    n = re.sub(r'[\(\)주유회사\s㈜\.\,\-\_\[\]]', '', name)
    return n.lower()

def core_name(name):
    n = norm(name)
    # Remove common agency suffixes
    n = re.sub(r'(직업소개소|인력사무소|인력개발|인력공사|인력|소개소|개발|공사)$', '', n)
    return n

def extract_city(addr):
    if not isinstance(addr, str): return ''
    m = re.search(r'(부산|울산|인천|대구|광주|대전|서울|세종|창원|김해|진주|통영|사천|밀양|거제|양산|의령|함안|창녕|고성|남해|하동|산청|함양|거창|합천|포항|경주|김천|안동|구미|영주|영천|상주|문경|경산|군위|의성|청송|영양|영덕|청도|고령|성주|칠곡|예천|봉화|울진|울릉|목포|여수|순천|나주|광양|담양|곡성|구례|고흥|보성|화순|장흥|강진|해남|영암|무안|함평|영광|장성|완도|진도|신안|전주|군산|익산|정읍|남원|김제|완주|진안|무주|장수|임실|순창|고창|부안|수원|성남|의정부|안양|부천|광명|평택|동두천|안산|고양|과천|구리|남양주|오산|시흥|군포|의왕|하남|용인|파주|이천|안성|김포|화성|광주|양주|포천|여주|연천|가평|양평|춘천|원주|강릉|동해|태백|속초|삼척|홍천|횡성|영월|평창|정선|철원|화천|양구|인제|고성|양양|청주|충주|제천|보은|옥천|영동|증평|진천|괴산|음성|단양|천안|공주|보령|아산|서산|논산|계룡|당진|금산|부여|서천|청양|홍성|예산|태안|제주|서귀포)', addr)
    return m.group(1) if m else ''

moel = pd.read_csv('KR_AGCY_MOEL_0RAW.csv', encoding='utf-8-sig')
comb = pd.read_csv('KR_AGCY_COMB_2COL.csv', encoding='utf-8-sig')

moel['norm'] = moel['Cong ty'].apply(norm)
comb['norm'] = comb['Cong ty'].apply(norm)
moel['core'] = moel['Cong ty'].apply(core_name)
comb['core'] = comb['Cong ty'].apply(core_name)

moel['city'] = moel['Dia chi'].apply(extract_city)
comb['city'] = comb['Dia chi'].apply(extract_city)

comb_valid = comb[
    (comb['SDT'].notna() & (comb['SDT'].astype(str).str.strip() != '')) |
    (comb['Email'].notna() & (comb['Email'].astype(str).str.strip() != '')) |
    (comb['Lien He'].notna() & (comb['Lien He'].astype(str).str.strip() != '') & (~comb['Lien He'].astype(str).str.contains('moel.go.kr', na=False)))
].copy()

matches = []
matched_indices = set()

# Pass 1: Exact norm + exact city
for idx, r in moel.iterrows():
    c_norm = r['norm']
    c_city = r['city']
    cand = comb_valid[(comb_valid['norm'] == c_norm) & (comb_valid['city'] == c_city)]
    if len(cand) > 0:
        matches.append((idx, cand.iloc[0], 'EXACT_NORM_CITY'))
        matched_indices.add(idx)

# Pass 2: Core name + exact city (for remaining)
for idx, r in moel.iterrows():
    if idx in matched_indices: continue
    c_core = r['core']
    c_city = r['city']
    if len(c_core) >= 2 and c_city:
        cand = comb_valid[(comb_valid['core'] == c_core) & (comb_valid['city'] == c_city)]
        if len(cand) == 1:
            matches.append((idx, cand.iloc[0], 'CORE_NAME_CITY'))
            matched_indices.add(idx)

print(f"Tổng số cty MOEL khớp với COMB (cùng địa phương): {len(matches)}")
has_sdt = sum(1 for m in matches if pd.notna(m[1]['SDT']) and str(m[1]['SDT']).strip() != '')
has_em = sum(1 for m in matches if pd.notna(m[1]['Email']) and str(m[1]['Email']).strip() != '')
has_web = sum(1 for m in matches if pd.notna(m[1]['Lien He']) and str(m[1]['Lien He']).strip() != '' and 'moel.go.kr' not in str(m[1]['Lien He']))

print(f"  -> Bổ sung được Số điện thoại chuẩn : {has_sdt}")
print(f"  -> Bổ sung được Email B2B            : {has_em}")
print(f"  -> Bổ sung được Website chính thức   : {has_web}")
print(f"  -> Bổ sung được Địa chỉ chi tiết     : {len(matches)}")
