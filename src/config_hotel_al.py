import os

# Google Maps Search Settings (Albania Hotels & Accommodations)
KEYWORDS = [
    "hotel me 4 yje",
    "hotel me 3 yje",
    "hotel me 2 yje",
    "hotel me 5 yje",
    "Hotel",
    "Vilë",
    "Shtrat & mëngjes",
    "Ambient pushimi me qira",
    "Shtëpi për mysafirë",
    "Homestay",
    "Apartament pushues",
    "Alloggio in famiglia",
    "Holiday apartment rental",
    "Bujtinë",
    "hotel me 1 yje"
]

# Allowed Category Tags (Albanian, English & Italian) for strict accommodation filtering
ALLOWED_CATEGORIES = {
    # Albanian
    "hotel",
    "hotel me 5 yje",
    "hotel me 4 yje",
    "hotel me 3 yje",
    "hotel me 2 yje",
    "hotel me 1 yje",
    "vilë",
    "vila",
    "shtrat & mëngjes",
    "shtrat dhe mëngjes",
    "ambient pushimi me qira",
    "shtëpi për mysafirë",
    "shtëpi mysafirësh",
    "bujtinë",
    "bujtine",
    "homestay",
    "alloggio in famiglia",
    "apartament pushues",
    "apartament me qira për pushime",
    "vendpushim",
    "hotel vendpushimi",
    "motel",
    "hostel",
    "bujtina",
    # English equivalents returned by Google Maps
    "hotel",
    "5-star hotel",
    "4-star hotel",
    "3-star hotel",
    "2-star hotel",
    "1-star hotel",
    "villa",
    "bed & breakfast",
    "bed and breakfast",
    "vacation home rental",
    "guest house",
    "guesthouse",
    "holiday apartment rental",
    "resort hotel",
    "extended stay hotel",
    "lodging",
    "inn"
}

# OTA Domains to strictly exclude from official hotel websites
EXCLUDED_OTA_DOMAINS = [
    "booking.com", "agoda.com", "expedia.com", "hotels.com", 
    "tripadvisor.com", "trivago.com", "airbnb.com", "airbnb.al", 
    "kayak.com", "hostelworld.com", "vrbo.com", "albania-hotel.com", 
    "hotelscombined.com", "edreams.com", "lastminute.com", 
    "priceline.com", "facebook.com", "instagram.com", "google.com",
    "yellowpages", "albania.al"
]

# Output settings
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_CSV = os.path.join(ROOT_DIR, "data", "raw", "hotel_albania.csv")
PROGRESS_FILE = os.path.join(ROOT_DIR, "data", "progress", "scraping_progress_hotel_al.json")

# Playwright Browser Settings (Visual UI per workspace rules)
HEADLESS = False  # Headless=False for visual monitoring & Captcha alerts
SLOW_MO = 5       # Milliseconds between actions
TIMEOUT = 60000   # 60s timeout

# Delay Settings (Seconds)
MIN_DELAY = 0.1
MAX_DELAY = 0.4

# Google Maps Selectors (Hotel specific)
SELECTORS = {
    "results_container": 'div[role="feed"]',
    "listing_link": 'a.hfpxzc',
    "business_name": 'h1.DUwDvf',
    "website": 'a[data-item-id="authority"]',
    "phone": 'button[data-item-id^="phone:tel:"]',
    "address": 'button[data-item-id^="address"]',
    "rating": 'div.F7nice span[aria-hidden="true"]',
    "reviews_count": 'div.F7nice span[aria-label*="reviews"], div.F7nice span[aria-label*="recensione"], div.F7nice span[aria-label*="vlerësime"]',
    "category": 'span.mgr77e, button.DkEaCc, button.DkEaL, div.F7nice ~ span, div.F7nice ~ button',
}
