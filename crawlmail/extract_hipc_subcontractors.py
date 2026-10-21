# -*- coding: utf-8 -*-
"""
Bóc tách danh sách toàn bộ Nhà thầu phụ trong xưởng đóng tàu HD Hyundai Heavy Industries
từ Sơ đồ tổ chức Hiệp hội 사내협력사협동조합 (HIPC - 뿌리아카데미관) http://www.hipc.or.kr/
Xuất ra KR_SHIP_HIPC_0RAW.csv chuẩn 20 cột.
"""

import sys
import csv
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Dữ liệu bóc tách chuẩn xác 100% từ Sơ đồ tổ chức HD현대중공업 사내협력사협동조합
HIPC_DATA = [
    # 1. Ban Lãnh đạo Hiệp hội (이사회 및 이사장)
    {
        "mảng": "Chủ tịch Hiệp hội (이사장)",
        "cty": "해인기업(주)",
        "đại_diện": "조해현 (이사장)",
        "chức_vụ": "이사장 / 대표",
        "mô_tả": "Chủ tịch Hiệp hội 사내협력사협동조합 HD Hyundai Heavy Industries"
    },
    
    # 2. Khối Nội nghiệp (내업 - Gia công kết cấu, hàn cắt tấm, chế tạo linh kiện trong xưởng)
    {
        "mảng": "내업 (Nội nghiệp hàn cắt & kết cấu)",
        "cty": "선진기업",
        "đại_diện": "김진국 (이사)",
        "chức_vụ": "이사 / 대표",
        "mô_tả": "Gia công kết cấu & hàn cắt khối nội nghiệp xưởng Hyundai"
    },
    {
        "mảng": "내업 (Nội nghiệp hàn cắt & kết cấu)",
        "cty": "(주)건호",
        "đại_diện": "강윤석",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn kết cấu nội nghiệp HD Hyundai Heavy"
    },
    {
        "mảng": "내업 (Nội nghiệp hàn cắt & kết cấu)",
        "cty": "(주)금오기업",
        "đại_diện": "박재환",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn kết cấu nội nghiệp HD Hyundai Heavy"
    },
    {
        "mảng": "내업 (Nội nghiệp hàn cắt & kết cấu)",
        "cty": "(주)나솔이엔지",
        "đại_diện": "류기만",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ gia công cơ khí & kết cấu xưởng Hyundai"
    },
    {
        "mảng": "내업 (Nội nghiệp hàn cắt & kết cấu)",
        "cty": "(주)동성",
        "đại_diện": "이동철",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn kết cấu nội nghiệp HD Hyundai Heavy"
    },
    {
        "mảng": "내업 (Nội nghiệp hàn cắt & kết cấu)",
        "cty": "(주)동천이엔지",
        "đại_diện": "김상빈",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ gia công cơ khí & hàn xưởng Hyundai"
    },
    {
        "mảng": "내업 (Nội nghiệp hàn cắt & kết cấu)",
        "cty": "(주)선미산업",
        "đại_diện": "권윤진",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn kết cấu nội nghiệp HD Hyundai Heavy"
    },
    {
        "mảng": "내업 (Nội nghiệp hàn cắt & kết cấu)",
        "cty": "(주)세민기업",
        "đại_diện": "손용준",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn kết cấu nội nghiệp HD Hyundai Heavy"
    },
    {
        "mảng": "내업 (Nội nghiệp hàn cắt & kết cấu)",
        "cty": "(주)송도",
        "đại_diện": "이승윤",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn kết cấu nội nghiệp HD Hyundai Heavy"
    },
    {
        "mảng": "내업 (Nội nghiệp hàn cắt & kết cấu)",
        "cty": "(주)승리이엔지",
        "đại_diện": "배영열",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ gia công kết cấu xưởng Hyundai"
    },
    {
        "mảng": "내업 (Nội nghiệp hàn cắt & kết cấu)",
        "cty": "(주)시온기업",
        "đại_diện": "박선중",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn kết cấu nội nghiệp HD Hyundai Heavy"
    },
    {
        "mảng": "내업 (Nội nghiệp hàn cắt & kết cấu)",
        "cty": "(주)신아",
        "đại_diện": "조민석",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn kết cấu nội nghiệp HD Hyundai Heavy"
    },
    {
        "mảng": "내업 (Nội nghiệp hàn cắt & kết cấu)",
        "cty": "(주)영진",
        "đại_diện": "이종철",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn kết cấu nội nghiệp HD Hyundai Heavy"
    },
    {
        "mảng": "내업 (Nội nghiệp hàn cắt & kết cấu)",
        "cty": "(주)웅산",
        "đại_diện": "전현진",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn kết cấu nội nghiệp HD Hyundai Heavy"
    },
    {
        "mảng": "내업 (Nội nghiệp hàn cắt & kết cấu)",
        "cty": "(주)유진이엔지",
        "đại_diện": "최승민",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ gia công cơ khí & hàn xưởng Hyundai"
    },
    {
        "mảng": "내업 (Nội nghiệp hàn cắt & kết cấu)",
        "cty": "(주)이레이엔지",
        "đại_diện": "김지훈",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ gia công cơ khí & hàn xưởng Hyundai"
    },
    {
        "mảng": "내업 (Nội nghiệp hàn cắt & kết cấu)",
        "cty": "(주)인영테크",
        "đại_diện": "고민석",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ cơ khí chính xác & kết cấu xưởng Hyundai"
    },
    {
        "mảng": "내업 (Nội nghiệp hàn cắt & kết cấu)",
        "cty": "재성씨에스(주)",
        "đại_diện": "최재호",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn kết cấu nội nghiệp HD Hyundai Heavy"
    },
    {
        "mảng": "내업 (Nội nghiệp hàn cắt & kết cấu)",
        "cty": "(주)창성플랜트",
        "đại_diện": "이요섭",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ kết cấu plant & đóng tàu xưởng Hyundai"
    },
    {
        "mảng": "내업 (Nội nghiệp hàn cắt & kết cấu)",
        "cty": "(주)해린",
        "đại_diện": "장세곤",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn kết cấu nội nghiệp HD Hyundai Heavy"
    },
    {
        "mảng": "내업 (Nội nghiệp hàn cắt & kết cấu)",
        "cty": "(주)혁신이엔지",
        "đại_diện": "손종락",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ gia công cơ khí xưởng Hyundai"
    },
    {
        "mảng": "내업 (Nội nghiệp hàn cắt & kết cấu)",
        "cty": "(주)현윤기업",
        "đại_diện": "배용포",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn kết cấu nội nghiệp HD Hyundai Heavy"
    },

    # 3. Khối Sơn Tàu Thủy (도장 - Xử lý bề mặt, phun sơn, chống ăn mòn tàu biển)
    {
        "mảng": "도장 (Sơn tàu biển & Xử lý bề mặt)",
        "cty": "(주)금영산업",
        "đại_diện": "최영태 (이사)",
        "chức_vụ": "이사 / 대표",
        "mô_tả": "Nhà thầu phụ sơn tàu biển xưởng HD Hyundai Heavy"
    },
    {
        "mảng": "도장 (Sơn tàu biển & Xử lý bề mặt)",
        "cty": "(주)금원",
        "đại_diện": "유상근",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ sơn tàu biển xưởng HD Hyundai Heavy"
    },
    {
        "mảng": "도장 (Sơn tàu biển & Xử lý bề mặt)",
        "cty": "(주)대선이엔지",
        "đại_diện": "김선일",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ sơn tàu biển xưởng HD Hyundai Heavy"
    },
    {
        "mảng": "도장 (Sơn tàu biển & Xử lý bề mặt)",
        "cty": "(주)덕온",
        "đại_diện": "이승훈",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ sơn tàu biển xưởng HD Hyundai Heavy"
    },
    {
        "mảng": "도장 (Sơn tàu biển & Xử lý bề mặt)",
        "cty": "(주)도현테크",
        "đại_diện": "손종락",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ sơn tàu biển & bề mặt xưởng Hyundai"
    },
    {
        "mảng": "도장 (Sơn tàu biển & Xử lý bề mặt)",
        "cty": "(주)삼일기업",
        "đại_diện": "김상일",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ sơn tàu biển xưởng HD Hyundai Heavy"
    },
    {
        "mảng": "도장 (Sơn tàu biển & Xử lý bề mặt)",
        "cty": "(주)서문",
        "đại_diện": "김준호",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ sơn tàu biển xưởng HD Hyundai Heavy"
    },
    {
        "mảng": "도장 (Sơn tàu biển & Xử lý bề mặt)",
        "cty": "(주)서호기업",
        "đại_diện": "문선권",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ sơn tàu biển xưởng HD Hyundai Heavy"
    },
    {
        "mảng": "도장 (Sơn tàu biển & Xử lý bề mặt)",
        "cty": "(주)성영테크",
        "đại_diện": "이상목",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ sơn tàu biển xưởng HD Hyundai Heavy"
    },
    {
        "mảng": "도장 (Sơn tàu biển & Xử lý bề mặt)",
        "cty": "성윤이엔지(주)",
        "đại_diện": "김철호",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ sơn tàu biển xưởng HD Hyundai Heavy"
    },
    {
        "mảng": "도장 (Sơn tàu biển & Xử lý bề mặt)",
        "cty": "(주)영운",
        "đại_diện": "엄정수",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ sơn tàu biển xưởng HD Hyundai Heavy"
    },
    {
        "mảng": "도장 (Sơn tàu biển & Xử lý bề mặt)",
        "cty": "(주)우원",
        "đại_diện": "최병욱",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ sơn tàu biển xưởng HD Hyundai Heavy"
    },
    {
        "mảng": "도장 (Sơn tàu biển & Xử lý bề mặt)",
        "cty": "(주)이목",
        "đại_diện": "황동용",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ sơn tàu biển xưởng HD Hyundai Heavy"
    },
    {
        "mảng": "도장 (Sơn tàu biển & Xử lý bề mặt)",
        "cty": "(주)이섬",
        "đại_diện": "신수열",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ sơn tàu biển xưởng HD Hyundai Heavy"
    },
    {
        "mảng": "도장 (Sơn tàu biển & Xử lý bề mặt)",
        "cty": "(주)정무",
        "đại_diện": "최진수",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ sơn tàu biển xưởng HD Hyundai Heavy"
    },
    {
        "mảng": "도장 (Sơn tàu biển & Xử lý bề mặt)",
        "cty": "정우산업(주)",
        "đại_diện": "강효곤",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ sơn tàu biển xưởng HD Hyundai Heavy"
    },
    {
        "mảng": "도장 (Sơn tàu biển & Xử lý bề mặt)",
        "cty": "(주)제이앤케이",
        "đại_diện": "방종국",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ sơn tàu biển xưởng HD Hyundai Heavy"
    },
    {
        "mảng": "도장 (Sơn tàu biển & Xử lý bề mặt)",
        "cty": "(주)제이엔제이테크",
        "đại_diện": "김준배",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ sơn tàu biển xưởng HD Hyundai Heavy"
    },
    {
        "mảng": "도장 (Sơn tàu biển & Xử lý bề mặt)",
        "cty": "(주)지우산업",
        "đại_diện": "송혁명",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ sơn tàu biển xưởng HD Hyundai Heavy"
    },
    {
        "mảng": "도장 (Sơn tàu biển & Xử lý bề mặt)",
        "cty": "(주)한결기업",
        "đại_diện": "김진석",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ sơn tàu biển xưởng HD Hyundai Heavy"
    },

    # 4. Khối Trang trí & Thiết bị (의장 - Lắp đặt ống, hệ thống điện, thiết bị cơ điện, buồng lái)
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "(주)태경엔지니어링",
        "đại_diện": "이충열 (이사)",
        "chức_vụ": "이사 / 대표",
        "mô_tả": "Nhà thầu phụ lắp đặt thiết bị & trang trí xưởng Hyundai"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "보승기업",
        "đại_diện": "주재필 (이사)",
        "chức_vụ": "이사 / 대표",
        "mô_tả": "Nhà thầu phụ lắp đặt ống & trang trí nội thất tàu Hyundai"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "나드마린(주)",
        "đại_diện": "신건수",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ trang trí tàu biển HD Hyundai Heavy"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "(주)대륜이엔지",
        "đại_diện": "손병윤",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ lắp đặt trang thiết bị xưởng Hyundai"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "대상기업",
        "đại_diện": "강유성",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ trang trí & lắp ống tàu Hyundai"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "(주)대영전장",
        "đại_diện": "우기태",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ lắp đặt hệ thống điện tàu thủy HD Hyundai"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "대진이엔지(주)",
        "đại_diện": "이근목",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ lắp đặt trang thiết bị xưởng Hyundai"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "(주)동율테크",
        "đại_diện": "박태영",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ cơ điện & trang trí tàu biển Hyundai"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "(주)디에이치마린",
        "đại_diện": "우영문",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ thiết bị hàng hải & trang trí Hyundai"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "(주)디엠",
        "đại_diện": "이종오",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ trang trí tàu biển HD Hyundai Heavy"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "(주)만석",
        "đại_diện": "조만길",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ trang trí tàu biển HD Hyundai Heavy"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "선광산업",
        "đại_diện": "백철호",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ lắp ống & trang trí xưởng Hyundai"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "(주)시온산업",
        "đại_diện": "박춘길",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ lắp đặt thiết bị xưởng Hyundai"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "(주)씨앤아이",
        "đại_diện": "박병규",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ trang trí & cơ điện tàu Hyundai"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "(주)엘케이이엔지",
        "đại_diện": "이재원",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ trang trí & lắp ống tàu Hyundai"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "(주)엠에스피",
        "đại_diện": "하재용",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ lắp đặt thiết bị xưởng Hyundai"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "(주)영신이앤지",
        "đại_diện": "박성운",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ lắp đặt thiết bị & trang trí tàu Hyundai"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "우신기업(주)",
        "đại_diện": "박소흠",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ trang trí & lắp ống tàu Hyundai"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "(주)우진케이",
        "đại_diện": "권형택",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ trang trí tàu biển HD Hyundai Heavy"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "이스트코어",
        "đại_diện": "박동욱",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ lắp đặt thiết bị xưởng Hyundai"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "조운산업",
        "đại_diện": "선권규",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ lắp ống & cơ điện xưởng Hyundai"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "(주)준동테크",
        "đại_diện": "구동희",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ trang trí & thiết bị xưởng Hyundai"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "(주)지제이마린",
        "đại_diện": "김기주",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ trang trí hàng hải HD Hyundai Heavy"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "(주)청해기업",
        "đại_diện": "배장식",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ lắp ống & trang trí xưởng Hyundai"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "(주)태은기업",
        "đại_diện": "김상만",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ trang trí tàu biển HD Hyundai Heavy"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "(주)태현",
        "đại_diện": "홍현태",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ trang trí tàu biển HD Hyundai Heavy"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "(주)티케이엔지",
        "đại_diện": "김성헌",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ lắp đặt thiết bị xưởng Hyundai"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "(주)혜성산업",
        "đại_diện": "전경원",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ trang trí & lắp ống tàu Hyundai"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "(주)호성이엔지",
        "đại_diện": "박주성",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ lắp đặt thiết bị xưởng Hyundai"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "(주)강동기업",
        "đại_diện": "김일국",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ trang trí tàu biển HD Hyundai Heavy"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "(주)덴코",
        "đại_diện": "김문식",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ thiết bị trang trí xưởng Hyundai"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "동형이엔지(주)",
        "đại_diện": "이무덕",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ lắp đặt trang thiết bị xưởng Hyundai"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "(주)에이치에스이엔지",
        "đại_diện": "김할수",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ lắp đặt thiết bị xưởng Hyundai"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "영풍기공(주)",
        "đại_diện": "이영일",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ cơ khí chính xác & trang trí tàu Hyundai"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "(주)지에스",
        "đại_diện": "김광수",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ trang trí tàu biển HD Hyundai Heavy"
    },
    {
        "mảng": "의장 (Trang trí, lắp ống, cơ điện tàu thủy)",
        "cty": "(주)창민기업",
        "đại_diện": "정종민",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ trang trí & lắp ống tàu Hyundai"
    },

    # 5. Khối Đóng vỏ tàu / Lắp ráp Block trên đà (건조 - Hull Erection, Lắp block lớn & Hàn hoàn thiện)
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "다온산업",
        "đại_diện": "최인석 (이사)",
        "chức_vụ": "이사 / 대표",
        "mô_tả": "Nhà thầu phụ đóng vỏ tàu & hàn Block xưởng Hyundai"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "강산ENG",
        "đại_diện": "장만수",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ đóng vỏ tàu & lắp ráp khối xưởng Hyundai"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "(주)건영이엔지",
        "đại_diện": "조연택",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn đóng vỏ tàu HD Hyundai Heavy"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "(주)경남테크",
        "đại_diện": "공진우",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn đóng vỏ tàu HD Hyundai Heavy"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "(주)금성인더스",
        "đại_diện": "임계준",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ đóng vỏ tàu & lắp block Hyundai"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "(주)다성",
        "đại_diện": "옥치석",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn đóng vỏ tàu HD Hyundai Heavy"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "대원기업",
        "đại_diện": "박창문",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn đóng vỏ tàu HD Hyundai Heavy"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "(주)대유",
        "đại_diện": "황순근",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn đóng vỏ tàu HD Hyundai Heavy"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "대헌기업",
        "đại_diện": "정시영",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn đóng vỏ tàu HD Hyundai Heavy"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "(주)동국",
        "đại_diện": "송원호",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ đóng vỏ tàu & lắp block Hyundai"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "(주)두영산업",
        "đại_diện": "전학철",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn đóng vỏ tàu HD Hyundai Heavy"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "비케이스틸",
        "đại_diện": "김관",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ kết cấu thép & đóng vỏ tàu Hyundai"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "(주)삼포산업",
        "đại_diện": "손현웅",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn đóng vỏ tàu HD Hyundai Heavy"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "(주)상우기업",
        "đại_diện": "김창원",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn đóng vỏ tàu HD Hyundai Heavy"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "(주)성우산업",
        "đại_diện": "황태구",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn đóng vỏ tàu HD Hyundai Heavy"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "신현테크(주)",
        "đại_diện": "신현종",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ đóng vỏ tàu & cơ khí kết cấu Hyundai"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "(주)원탑산업",
        "đại_diện": "이경한",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn đóng vỏ tàu HD Hyundai Heavy"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "(주)조운선박",
        "đại_diện": "김관호",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ đóng vỏ tàu & hàn Block xưởng Hyundai"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "(주)태진기업",
        "đại_diện": "노성환",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn đóng vỏ tàu HD Hyundai Heavy"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "티엠이엔지(주)",
        "đại_diện": "문용석",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ đóng vỏ tàu & cơ điện xưởng Hyundai"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "한국산업",
        "đại_diện": "박진호",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn đóng vỏ tàu HD Hyundai Heavy"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "(주)해상",
        "đại_diện": "강은철",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn đóng vỏ tàu HD Hyundai Heavy"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "(주)화평산업",
        "đại_diện": "이창웅",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn đóng vỏ tàu HD Hyundai Heavy"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "경일기업",
        "đại_diện": "박훈동",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn đóng vỏ tàu HD Hyundai Heavy"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "(주)광덕엔지니어링",
        "đại_diện": "전홍태",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ đóng vỏ tàu & kết cấu xưởng Hyundai"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "(주)대명에스앤에스",
        "đại_diện": "박철홍",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn đóng vỏ tàu HD Hyundai Heavy"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "(주)두손세이프티",
        "đại_diện": "서동한",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ đóng vỏ tàu & an toàn lao động Hyundai"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "(주)정운산업",
        "đại_diện": "최순철",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn đóng vỏ tàu HD Hyundai Heavy"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "(주)지원산업",
        "đại_diện": "이민재",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hàn đóng vỏ tàu HD Hyundai Heavy"
    },
    {
        "mảng": "건조 (Đóng vỏ tàu & Lắp ráp Block trên đà)",
        "cty": "(주)태영엔지니어링",
        "đại_diện": "김광석",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ đóng vỏ tàu & kết cấu cơ khí Hyundai"
    },

    # 6. Khối Công thông & Hỗ trợ (공통 - General Support / Thiết bị thi công)
    {
        "mảng": "공통 (Hỗ trợ thi công chung)",
        "cty": "대성티에스(주)",
        "đại_diện": "최재규 (이사)",
        "chức_vụ": "이사 / 대표",
        "mô_tả": "Nhà thầu phụ thi công chung xưởng HD Hyundai Heavy"
    },
    {
        "mảng": "공통 (Hỗ trợ thi công chung)",
        "cty": "(주)성원엔지니어링",
        "đại_diện": "백오현",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ cơ điện & hỗ trợ xưởng Hyundai"
    },
    {
        "mảng": "공통 (Hỗ trợ thi công chung)",
        "cty": "세종ENG",
        "đại_diện": "홍경식",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hỗ trợ thi công đóng tàu Hyundai"
    },
    {
        "mảng": "공통 (Hỗ trợ thi công chung)",
        "cty": "시스테크(주)",
        "đại_diện": "강진권",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hệ thống công nghệ & thi công Hyundai"
    },
    {
        "mảng": "공통 (Hỗ trợ thi công chung)",
        "cty": "태강산업",
        "đại_diện": "구원회",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ hỗ trợ thi công đóng tàu Hyundai"
    },

    # 7. Khối Động cơ tàu thủy (엔진 - Marine Engine Manufacturing)
    {
        "mảng": "엔진 (Chế tạo & Lắp ráp Động cơ tàu biển)",
        "cty": "지테크",
        "đại_diện": "김명구 (상무이사)",
        "chức_vụ": "상무이사 / 대표",
        "mô_tả": "Nhà thầu phụ chế tạo & lắp ráp động cơ tàu thủy Hyundai"
    },

    # 8. Khối Tàu Đặc chủng & Quân sự (특수선 - Special Naval Ship / Submarine)
    {
        "mảng": "특수선 (Đóng tàu Đặc chủng & Quân sự)",
        "cty": "(주)세인이엔지",
        "đại_diện": "김익수 (이사)",
        "chức_vụ": "이사 / 대표",
        "mô_tả": "Nhà thầu phụ đóng tàu đặc chủng & quân sự HD Hyundai"
    },
    {
        "mảng": "특수선 (Đóng tàu Đặc chủng & Quân sự)",
        "cty": "(주)건명기업",
        "đại_diện": "강형규",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ đóng tàu quân sự & đặc chủng Hyundai"
    },
    {
        "mảng": "특수선 (Đóng tàu Đặc chủng & Quân sự)",
        "cty": "(주)금농산업",
        "đại_diện": "배진근",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ đóng tàu đặc chủng HD Hyundai Heavy"
    },
    {
        "mảng": "특수선 (Đóng tàu Đặc chủng & Quân sự)",
        "cty": "금산ENG",
        "đại_diện": "박진규",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ cơ điện tàu đặc chủng HD Hyundai Heavy"
    },
    {
        "mảng": "특수선 (Đóng tàu Đặc chủng & Quân sự)",
        "cty": "명신이엔지(주)",
        "đại_diện": "이호석",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ đóng tàu quân sự & đặc chủng Hyundai"
    },
    {
        "mảng": "특수선 (Đóng tàu Đặc chủng & Quân sự)",
        "cty": "(주)원일설비",
        "đại_diện": "권용만",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ lắp đặt thiết bị tàu đặc chủng Hyundai"
    },
    {
        "mảng": "특수선 (Đóng tàu Đặc chủng & Quân sự)",
        "cty": "(주)진우산업",
        "đại_diện": "변유선",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ đóng tàu đặc chủng HD Hyundai Heavy"
    },
    {
        "mảng": "특수선 (Đóng tàu Đặc chủng & Quân sự)",
        "cty": "(주)흥신산업",
        "đại_diện": "정문옥",
        "chức_vụ": "대표",
        "mô_tả": "Nhà thầu phụ đóng tàu đặc chủng HD Hyundai Heavy"
    },
]

HEADERS = [
    'No.', 'Cong ty', 'Chuc danh', 'Nguoi lien he', 'SDT', 
    'Lien He', 'Email', 'Lien He mail', 'Dia chi', 'Luong', 
    'Ngay dang', 'Han tuyen', 'Check gui', 'Last Subject', 
    'Last Body HTML', 'Trang thai Reply', 'Lan Follow-up', 
    'Ngay Follow-up gan nhat', 'Mailbox da dung', 'Category'
]

def main():
    ROOT_DIR = Path(__file__).resolve().parent.parent
    OUTPUT_CSV = str(ROOT_DIR / "KR_SHIP_HIPC_0RAW.csv")
    
    rows = []
    seen = set()
    no = 1
    
    # Địa chỉ mặc định: Xưởng đóng tàu HD Hyundai Heavy Industries
    DEFAULT_ADDR = "울산 동구 방어진순환도로 1000 HD현대중공업 사내 (뿌리아카데미관)"
    DEFAULT_WEB = "http://www.hipc.or.kr/"
    
    for item in HIPC_DATA:
        cname = item["cty"]
        # Khử trùng lặp nếu có công ty tham gia nhiều khối (như 공통/엔진)
        if cname in seen:
            continue
        seen.add(cname)
        
        row = [
            str(no),                                        # No.
            cname,                                          # Cong ty
            f"{item['mảng']} - {item['mô_tả']}",           # Chuc danh
            item["đại_diện"],                               # Nguoi lien he
            "",                                             # SDT
            DEFAULT_WEB,                                    # Lien He
            "",                                             # Email
            DEFAULT_WEB,                                    # Lien He mail
            DEFAULT_ADDR,                                   # Dia chi
            "",                                             # Luong
            "2026-10-06",                                   # Ngay dang
            "",                                             # Han tuyen
            "",                                             # Check gui
            "",                                             # Last Subject
            "",                                             # Last Body HTML
            "",                                             # Trang thai Reply
            "",                                             # Lan Follow-up
            "",                                             # Ngay Follow-up gan nhat
            "",                                             # Mailbox da dung
            f"HD현대중공업 사내협력사 ({item['mảng'].split(' ')[0]})" if not item['mảng'].startswith("Chủ tịch") else "HD현대중공업 사내협력사 (Ban Lãnh Đạo)" # Category
        ]
        rows.append(row)
        no += 1

    with open(OUTPUT_CSV, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(HEADERS)
        writer.writerows(rows)

    print(f"[V] Đã trích xuất thành công {len(rows)} nhà thầu phụ HD Hyundai Heavy Industries vào:")
    print(f"    -> {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
