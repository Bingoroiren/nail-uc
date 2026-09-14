import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import config_agency_at as config

print("RAW_CSV_PATH:", config.RAW_CSV_PATH)
os.makedirs(os.path.dirname(config.RAW_CSV_PATH), exist_ok=True)
with open(config.RAW_CSV_PATH, "w", encoding="utf-8-sig") as f:
    f.write("Business_Name,Phone,Email,Website,Address,Category,Detail_URL\n")
print("Written successfully. Exists:", os.path.exists(config.RAW_CSV_PATH))
