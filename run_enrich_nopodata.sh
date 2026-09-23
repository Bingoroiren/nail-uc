#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "==========================================================================="
echo "  TIEN TRINH LAM GIAU DU LIEU: NOPROFF.CSV -> NOPODATA.CSV"
echo "  - Nguon 1: Open API Cuc Dang ky Doanh nghiep Na Uy (data.brreg.no)"
echo "  - Nguon 2: Cao truc tiep Email B2B tu Website doanh nghiep"
echo "  - Luu dong: Ghi de tuc thi vao NOPODATA.csv va Cache JSON"
echo "==========================================================================="
echo ""

if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

python3 "crawlmail/enrich_nopodata.py" "$@"

echo ""
echo "==========================================================================="
echo "  TIEN TRINH LAM GIAU NOPODATA DA HOAN TAT!"
echo "==========================================================================="
