#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "==========================================================================="
echo "  TIEN TRINH CAO DANH SACH CONG TY TU PROFF.NO (NA UY) -> NOPROFF.CSV"
echo "  - Nganh nghe: Arbeidskrafttjenester (Nhan luc, Tuyen dung, Viec lam)"
echo "  - Quy mo: ~5.958 cong ty tren 239 trang ket qua"
echo "  - Thu thap: Orgnr, Ten cty, SDT, Email, Website, Dia chi, Nhan vien, Doanh thu"
echo "==========================================================================="
echo ""

if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

python3 "crawlmail/crawl_proff_no.py" "$@"

echo ""
echo "==========================================================================="
echo "  TIEN TRINH CAO PROFF.NO DA HOAN TAT!"
echo "==========================================================================="
