import os

# Google Maps Search Settings
KEYWORDS = [
    "建築公司",
    "房屋建造商",
    "工程外判商",
    "承包商",
    "自訂房屋建築商",
    "土木工程公司",
    "建築修復服務"
]

# Output settings
OUTPUT_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw", "taiwan_construction.csv")

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
