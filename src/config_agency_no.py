import os

# Google Maps Search Keywords for Norway Agricultural & Recruitment Agencies (Norge Byrå & Landbrukstjenester)
# User-specified tags in Norwegian:
# - Landbrukstjenester (Agricultural Services / Dịch vụ nông nghiệp)
# - Vikarbyrå (Employment agency / Agency môi giới lao động tạm thời)
# - Rekrutteringsbyrå (Recruitment agency / Công ty tuyển dụng)
KEYWORDS = [
    "Landbrukstjenester",
    "Vikarbyrå",
    "Rekrutteringsbyrå",
    "Bemanningsbyrå",
    "Arbeidsformidling"
]

# Allowed Category Tags for strict filtering (lowercase matching)
# Locations without at least one tag in this set will be discarded
ALLOWED_CATEGORIES = {
    "landbrukstjenester",
    "landbruksrådgiving",
    "landbruksservice",
    "landbruksorganisasjon",
    "vikarbyrå",
    "vikarbyråer",
    "rekrutteringsbyrå",
    "rekrutteringsbyråer",
    "bemanningsbyrå",
    "bemanningsbyråer",
    "bemanningsselskap",
    "arbeidsformidling",
    "rekruttering",
    "rekrutteringsselskap",
    "personalutleie",
    "personaltjenester",
    "bemanningsbyra",
    "rekrutteringsbyra",
    "vikarbyra"
}

# Dynamic Output & Progress File Paths (Cross-machine / Git compatible)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)

OUTPUT_CSV = os.path.join(ROOT_DIR, "data", "raw", "agency_norway.csv")
PROGRESS_FILE = os.path.join(ROOT_DIR, "data", "progress", "scraping_progress_agency_no.json")

# Playwright Browser Settings
HEADLESS = False   # Set to True for headless mode
SLOW_MO = 5
TIMEOUT = 60000

# Delay Settings (Seconds)
MIN_DELAY = 0.1
MAX_DELAY = 0.4

# Google Maps Selectors
SELECTORS = {
    "results_container": 'div[role="feed"]',
    "listing_link": 'a.hfpxzc',
    "business_name": 'h1.DUwDvf',
    "website": 'a[data-item-id="authority"]',
    "phone": 'button[data-item-id^="phone:tel:"]',
    "address": 'button[data-item-id^="address"]',
    "rating": 'div.F7nice span[aria-hidden="true"]',
    "reviews_count": 'div.F7nice span[aria-label*="reviews"]',
    "category": 'span.mgr77e, button.DkEaCc, button.DkEaL, div.F7nice ~ span, div.F7nice ~ button',
}
