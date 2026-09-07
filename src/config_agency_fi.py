import os

# Source Directory Page for Finland Staffing & Recruitment Agencies Association (Henkilöstöala HELA)
SOURCE_URL = "https://henkilostoala.fi/jasenpalvelut/lista-jasenyrityksista/"

# Dynamic Output & Progress File Paths (Cross-machine / Git compatible)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)

OUTPUT_CSV = os.path.join(ROOT_DIR, "data", "raw", "agency_finland.csv")
PROGRESS_FILE = os.path.join(ROOT_DIR, "data", "progress", "scraping_progress_agency_fi.json")

# Default Category Translation
DEFAULT_CATEGORY_FI = "Rekrytointi- ja henkilöstöpalvelut"
DEFAULT_CATEGORY_VN = "Agency tuyển dụng & cung ứng nhân sự"

# Crawl Settings
TIMEOUT = 30000
