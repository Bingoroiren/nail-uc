import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd

df = pd.read_csv('KR_SHIP_HIPC_0RAW.csv', encoding='utf-8-sig')

irrelevant = []
for idx, r in df.iterrows():
    cname = r['Cong ty']
    desc = str(r['Chuc danh'])
    cat = str(r['Category'])
    reasons = []
    
    # Check for pure leisure / non-industrial boats
    if '웨이크서핑보트' in desc:
        reasons.append('Thuyền lướt ván / thể thao nước (Wake surfing boat)')
    elif '세일링요트' in desc and '강선' not in desc:
        reasons.append('Thuyền buồm du lịch nhỏ (Sailing yacht FRP)')
    elif '수상레저보트' in desc:
        reasons.append('Cano giải trí nước / du thuyền mini')
    elif '오락및스포츠용 보트' in desc:
        reasons.append('Thuyền thể thao & giải trí cá nhân')
    elif '기타선(RIB보트)' in desc and '경기 양평' in str(r['Dia chi']):
        reasons.append('Xuồng hơi RIB cứu hộ vùng nội địa (Hồ sông Dương Bình)')

    if reasons:
        irrelevant.append((idx+1, cname, desc, cat, ', '.join(reasons)))

print(f"Total irrelevant detected: {len(irrelevant)}")
for item in irrelevant:
    print(f"Row {item[0]}: {item[1]} | Lý do: {item[4]}")
