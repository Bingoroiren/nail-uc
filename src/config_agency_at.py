import os

# Base Directories
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SRC_DIR)

# File Paths
DATA_DIR = os.path.join(ROOT_DIR, "data")
RAW_DATA_DIR = os.path.join(DATA_DIR, "raw")
FORMATTED_DATA_DIR = os.path.join(DATA_DIR, "formatted")
PROGRESS_DIR = os.path.join(DATA_DIR, "progress")

# Output Files
RAW_CSV_PATH = os.path.join(RAW_DATA_DIR, "agency_austria.csv")
FORMATTED_CSV_PATH = os.path.join(FORMATTED_DATA_DIR, "agency_austria_with_emails_formatted.csv")
CLEAN_DEDUP_CSV_PATH = os.path.join(FORMATTED_DATA_DIR, "agency_austria_clean_dedup.csv")

# Progress Tracking Files
SCRAPER_PROGRESS_FILE = os.path.join(PROGRESS_DIR, "scraping_progress_agency_at.json")
EMAIL_PROGRESS_FILE = os.path.join(PROGRESS_DIR, "scraping_progress_agency_at_emails.json")

# Category & Keywords
CATEGORY_VN = "Agency môi giới lao động tạm thời Áo"

PRIMARY_KEYWORDS = [
    "arbeitskr%c3%a4fte%c3%bcberlassung",
    "leiharbeit",
    "personalbereitstellung",
    "personalleasing",
    "zeitarbeit"
]

AUSTRIAN_STATES = [
    "",
    "wien",
    "niederoesterreich",
    "oberoesterreich",
    "salzburg",
    "steiermark",
    "tirol",
    "vorarlberg",
    "kaernten",
    "burgenland"
]

ALPHABET_LETTERS = [
    "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
    "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z"
]

# Ensure required directories exist
for folder in [RAW_DATA_DIR, FORMATTED_DATA_DIR, PROGRESS_DIR]:
    os.makedirs(folder, exist_ok=True)
