import os

# Google Maps Search Settings (31 tags, excluding 公司辦公室 as requested)
KEYWORDS = [
    "工廠設備供應商",
    "家具製造商",
    "電子產品製造商",
    "電子零件供應商",
    "玩具製造商",
    "食品製造商",
    "食品調味料製造商",
    "冷凍食品製造商",
    "化學工廠",
    "化學品製造商",
    "機械製造商",
    "機械廠",
    "機械零件製造商",
    "汽車零件製造商",
    "塑料製造公司",
    "塑膠製品供應商",
    "紡織廠",
    "紗廠",
    "服裝與布料製造商",
    "布產品製造商",
    "電池製造商",
    "玻璃製造商",
    "玻璃纖維供應商",
    "鞋廠",
    "汽車工廠",
    "造紙廠",
    "半導體供應商",
    "橡膠製品供應商",
    "扣件供應商",
    "製造商",
    "電子公司"
]

# Google Maps Category Filter (32 tags, including 公司辦公室 as requested)
ALLOWED_CATEGORIES = [
    "工廠設備供應商",
    "家具製造商",
    "電子產品製造商",
    "電子零件供應商",
    "玩具製造商",
    "食品製造商",
    "食品調味料製造商",
    "冷凍食品製造商",
    "化學工廠",
    "化學品製造商",
    "機械製造商",
    "機械廠",
    "機械零件製造商",
    "汽車零件製造商",
    "塑料製造公司",
    "塑膠製品供應商",
    "紡織廠",
    "紗廠",
    "服裝與布料製造商",
    "布產品製造商",
    "電池製造商",
    "玻璃製造商",
    "玻璃纖維供應商",
    "鞋廠",
    "汽車工廠",
    "造紙廠",
    "半導體供應商",
    "橡膠製品供應商",
    "扣件供應商",
    "製造商",
    "電子公司",
    "公司辦公室"
]

# Output settings
OUTPUT_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "taiwan_factories.csv")

# Playwright Browser Settings
HEADLESS = False  # Set to True to run the browser hidden in the background
SLOW_MO = 5       # Introduce a tiny delay (ms) between actions
TIMEOUT = 60000   # Timeout for page loading and element matching (60 seconds)

# Delay Settings (Seconds)
MIN_DELAY = 0.1
MAX_DELAY = 0.4

# Google Maps Selectors
SELECTORS = {
    # Left pane containing search results (scrollable list container)
    "results_container": 'div[role="feed"]',
    
    # Anchor tag for each business listing in the search results
    "listing_link": 'a.hfpxzc',
    
    # Detail panel elements
    "business_name": 'h1.DUwDvf',
    "website": 'a[data-item-id="authority"]',
    "phone": 'button[data-item-id^="phone:tel:"]',
    "address": 'button[data-item-id^="address"]',
    
    # Extra information (Rating and Review count)
    "rating": 'div.F7nice span[aria-hidden="true"]',
    "reviews_count": 'div.F7nice span[aria-label*="reviews"]',
    "category": 'button.DkEaCc, button.DkEaL, button[jsaction*="category"], button[jsaction*="hotelclass"], [jsaction*="category"], [jsaction*="hotelclass"]',
}
