# -*- coding: utf-8 -*-
"""
CẤU HÌNH CHIẾN DỊCH CÀO GOOGLE MAPS: TIỆM NAIL & LÀM ĐẸP TẠI PHÁP (FRANCE NAIL SALONS)
=====================================================================================
Thị trường: Pháp (France - FR)
Ngành nghề: Tiệm nail / Thẩm mỹ viện (Institut de beauté, Salon de manucure, Bar à ongles)
Quy chuẩn đặt tên 17 ký tự (Rule 10): FR_NAIL_GMAP_0RAW.csv
"""

import os

# Danh sách từ khóa người dùng yêu cầu & các biến thể đặc thù ngành nail/làm đẹp tại Pháp
KEYWORDS = [
    "Institut de beauté",
    "Salon de manucure",
    "Bar à ongles",
    "Onglerie",
    "Nail salon"
]

# Danh mục Google Maps hợp lệ cho Tiệm Nail & Thẩm mỹ viện tại Pháp
ALLOWED_CATEGORIES = [
    "Institut de beauté",
    "Salon de manucure",
    "Bar à ongles",
    "Onglerie",
    "Salon de beauté",
    "Salon de coiffure",
    "Esthéticienne",
    "Spa et bien-être",
    "Centre d'esthétique",
    "Centre de bien-être",
    "Soins des ongles",
    "Nail salon",
    "Beauty salon",
    "Day spa",
    "Beautician"
]

# Cấu hình đường dẫn xuất tệp chuẩn Rule 1, Rule 10
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_CSV = os.path.join(ROOT_DIR, "data", "raw", "FR_NAIL_GMAP_0RAW.csv")
ROOT_OUTPUT_CSV = os.path.join(ROOT_DIR, "FR_NAIL_GMAP_0RAW.csv")

# Cấu hình Playwright Browser
HEADLESS = False  # Bắt buộc False theo Rule 4 để người dùng quan sát trực quan và gỡ Captcha nếu cần
SLOW_MO = 5       # Độ trễ nhẹ giữa các thao tác (ms)
TIMEOUT = 60000   # Timeout tải trang và phần tử (60s)

# Thời gian chờ ngẫu nhiên giữa các thao tác cuộn/click (giây)
MIN_DELAY = 0.1
MAX_DELAY = 0.4

# Bộ SELECTORS chuẩn của Google Maps
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
    "reviews_count": 'div.F7nice span[aria-label*="reviews"], div.F7nice span[aria-label*="avis"]',
    "category": 'button.DkEaCc, button.DkEaL, button[jsaction*="category"], [jsaction*="category"]',
}
