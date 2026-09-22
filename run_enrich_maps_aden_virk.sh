#!/bin/bash
set -e

# Chuyển về thư mục chứa script
cd "$(dirname "$0")"

echo "==========================================================================="
echo "  LAM GIAU DU LIEU CHO ADENVIRK.CSV -> ADENVMAP.CSV (GOOGLE MAPS DAN MACH)"
echo "  - Muc tieu: Cac ban ghi CHUA CO EMAIL tu ADENVIRK.csv"
echo "  - Quy tac so khop ten nghiem ngat (Exact, Ngoac don, Gach ngang)"
echo "  - Trinh duyet: Google Chrome / Chromium (hl=da)"
echo "  - Luu file dong tuc thi vao ADENVMAP.csv va Cache JSON"
echo "==========================================================================="
echo ""

# Kích hoạt virtualenv nếu có
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

# Chạy script làm giàu dữ liệu
python3 "crawlmail/enrich_maps_aden_virk.py" "$@"

echo ""
echo "==========================================================================="
echo "  TIEN TRINH DA HOAN TAT HOAC DA LUU TRANG THAI TIEN DO THANH CONG!"
echo "==========================================================================="
