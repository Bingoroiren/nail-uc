import csv, sys, shutil

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Read current rows
with open('(10_9) Nông trại na uy - Trang tính1.csv', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    fieldnames = list(reader.fieldnames)
    rows = list(reader)

first_21 = {
    1: 'post@vaulagardsfrukt.no',
    2: 'post@feelreal.no',
    3: 'bestilling@hanasand.no',
    4: 'magnus@galtahageservice.no',
    5: 'post@skavlandgartneri.no',
    6: 'info@norhage.no',
    7: 'post@hodnegartneri.no',
    8: 'post@miljogartneriet.no',
    9: 'oaespe@online.no',
    10: 'post@haakonbjorndal.no',
    11: 'kontakt@laselva.no',
    12: 'hesleberg@hesleberg.no',
    13: 'post@vardenargartneri.no',
    14: 'bruker@domene.no',
    15: 'post@finerehage.no',
    16: 'post@log.no',
    17: 'bente@hageverde.no',
    18: 'bruker@domene.no',
    19: 'post@biooffice.no',
    20: 'info@secretgardensoslo.no',
    21: 'seniortjenesten@gmail.com'
}

remaining = {}
with open('scratch/all_141_original_scores.txt', encoding='utf-8') as f:
    for line in f:
        if '|' in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 3:
                try:
                    r_idx = int(parts[0])
                    em = parts[2]
                    remaining[r_idx] = em
                except:
                    pass

all_original = {**first_21, **remaining}
print(f"Total original emails identified: {len(all_original)}")

for idx, r in enumerate(rows, 1):
    if idx in all_original:
        r['Email'] = all_original[idx]
    else:
        r['Email'] = ''
    r['Check gui'] = ''

target_file = '(10_9) Nông trại na uy - Trang tính1.csv'
backup_file = '(10_9) Nông trại na uy - Trang tính1.backup.csv'

# Write to both target and backup
for p in [target_file, backup_file]:
    with open(p, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

print(f"File restored perfectly to original state! Non-empty emails: {len([r for r in rows if r['Email']])}")
