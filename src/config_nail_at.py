# -*- coding: utf-8 -*-
"""
CẤU HÌNH CHIẾN DỊCH CÀO GOOGLE MAPS: TIỆM NAIL ÁO (AUSTRIA NAIL SALONS)
=============================================================================
Thị trường: Áo (Austria - AT)
Ngành nghề: Tiệm nail / Chăm sóc móng (Nagelstudio)
Quy chuẩn đặt tên: AT_NAIL_GMAP_0RAW.csv (Rule 10)
"""

import os

# Google Maps Search Settings (Austria Nail Salons)
KEYWORDS = [
    "Nagelstudio"
]

# Google Maps Category Filter (Chấp nhận các danh mục liên quan trực tiếp đến nail/làm đẹp)
ALLOWED_CATEGORIES = [
    "Nagelstudio",
    "Kosmetikstudio",
    "Schönheitssalon",
    "Fußpflege",
    "Nail salon",
    "Beauty salon",
    "Permanent Make-up Studio",
    "Kosmetikerin"
]

# Output settings
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_CSV = os.path.join(ROOT_DIR, "data", "raw", "AT_NAIL_GMAP_0RAW.csv")
ROOT_OUTPUT_CSV = os.path.join(ROOT_DIR, "AT_NAIL_GMAP_0RAW.csv")

# Playwright Browser Settings
HEADLESS = False  # Bắt buộc False theo Rule 4 để người dùng quan sát và gỡ Captcha nếu cần
SLOW_MO = 5       # Độ trễ nhẹ giữa các thao tác (ms)
TIMEOUT = 60000   # Timeout tải trang và phần tử (60s)

# Delay Settings (Seconds)
MIN_DELAY = 0.1
MAX_DELAY = 0.4

# Google Maps Selectors chuẩn
SELECTORS = {
    # Khung cuộn danh sách kết quả bên trái
    "results_container": 'div[role="feed"]',
    
    # Thẻ a cho từng địa điểm trong danh sách
    "listing_link": 'a.hfpxzc',
    
    # Các thành phần trong bảng chi tiết
    "business_name": 'h1.DUwDvf',
    "website": 'a[data-item-id="authority"]',
    "phone": 'button[data-item-id^="phone:tel:"]',
    "address": 'button[data-item-id^="address"]',
    
    # Thông tin đánh giá
    "rating": 'div.F7nice span[aria-hidden="true"]',
    "reviews_count": 'div.F7nice span[aria-label*="reviews"]',
    "category": 'button.DkEaCc, button.DkEaL, button[jsaction*="category"], button[jsaction*="hotelclass"], [jsaction*="category"], [jsaction*="hotelclass"]',
}

