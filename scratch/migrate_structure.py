import os
import shutil
import glob
import re
import json
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def safe_print(msg):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            print(msg.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8'), flush=True)
        except Exception:
            print(msg.encode('ascii', errors='replace').decode('ascii'), flush=True)

def create_dirs():
    dirs = [
        "data/raw",
        "data/formatted",
        "data/progress",
        "data/assets",
        "formatters",
        "scrapers_standalone",
        "runners"
    ]
    for d in dirs:
        p = os.path.join(ROOT_DIR, d)
        if not os.path.exists(p):
            os.makedirs(p)
            safe_print(f"[+] Created directory: {d}")

def migrate_files():
    # 1. Move progress files (*.json)
    for f in glob.glob(os.path.join(ROOT_DIR, "scraping_progress*.json")):
        if os.path.exists(f):
            shutil.move(f, os.path.join(ROOT_DIR, "data/progress", os.path.basename(f)))
            safe_print(f"Moved JSON: {os.path.basename(f)} -> data/progress/")
        
    # 2. Move assets (*.png, *.html)
    for ext_pattern in ["*.png", "*.html"]:
        for f in glob.glob(os.path.join(ROOT_DIR, ext_pattern)):
            if os.path.exists(f):
                shutil.move(f, os.path.join(ROOT_DIR, "data/assets", os.path.basename(f)))
                safe_print(f"Moved Asset: {os.path.basename(f)} -> data/assets/")
            
    # 3. Move runner scripts (*.bat)
    for f in glob.glob(os.path.join(ROOT_DIR, "run_*.bat")) + glob.glob(os.path.join(ROOT_DIR, "git_pull.bat")):
        if os.path.exists(f):
            shutil.move(f, os.path.join(ROOT_DIR, "runners", os.path.basename(f)))
            safe_print(f"Moved Runner: {os.path.basename(f)} -> runners/")
        
    # 4. Move formatting scripts (format_*.py, clean_korean_emails.py)
    formatters = glob.glob(os.path.join(ROOT_DIR, "format_*.py")) + [os.path.join(ROOT_DIR, "clean_korean_emails.py")]
    for f in formatters:
        if os.path.exists(f):
            shutil.move(f, os.path.join(ROOT_DIR, "formatters", os.path.basename(f)))
            safe_print(f"Moved Formatter: {os.path.basename(f)} -> formatters/")
            
    # 5. Move standalone scrapers
    scrapers = [
        "scrape_emails_korean.py",
        "scrape_kofa.py",
        "scrape_kosma_emails.py",
        "scrape_kosma_instructors.py",
        "scrape_ksa_members.py",
        "scrape_wda_employers.py",
        "download_suhyup_xls.py",
        "parse_suhyup_coops.py",
        "parse_suhyup_source.py",
        "guess_greek_hotel_emails.py"
    ]
    for filename in scrapers:
        f = os.path.join(ROOT_DIR, filename)
        if os.path.exists(f):
            shutil.move(f, os.path.join(ROOT_DIR, "scrapers_standalone", filename))
            safe_print(f"Moved Scraper: {filename} -> scrapers_standalone/")
            
    # 6. Move data files (CSV & XLSX & XLS)
    all_csvs = glob.glob(os.path.join(ROOT_DIR, "*.csv")) + glob.glob(os.path.join(ROOT_DIR, "*.xlsx")) + glob.glob(os.path.join(ROOT_DIR, "*.xls"))
    for f in all_csvs:
        if os.path.exists(f):
            filename = os.path.basename(f)
            if any(x in filename.lower() for x in ["with_emails", "formatted", "cleaned", "(chờ)", "(đang)"]):
                shutil.move(f, os.path.join(ROOT_DIR, "data/formatted", filename))
                safe_print(f"Moved Formatted Data: {filename} -> data/formatted/")
            else:
                shutil.move(f, os.path.join(ROOT_DIR, "data/raw", filename))
                safe_print(f"Moved Raw Data: {filename} -> data/raw/")

def update_bat_files():
    runners_dir = os.path.join(ROOT_DIR, "runners")
    for f_path in glob.glob(os.path.join(runners_dir, "*.bat")):
        if os.path.exists(f_path):
            with open(f_path, "r", encoding="utf-8-sig") as f:
                content = f.read()
                
            # 1. Update cd /d "%~dp0" to cd /d "%~dp0.."
            content = content.replace('cd /d "%~dp0"', 'cd /d "%~dp0.."')
            
            # 2. Update python calls to point to subfolders
            content = re.sub(r'python (?:-u )?format_([a-zA-Z_0-9]+)\.py', r'python formatters/format_\1.py', content)
            content = content.replace('python clean_korean_emails.py', 'python formatters/clean_korean_emails.py')
            
            # Standalone scrapers
            content = re.sub(r'python (?:-u )?scrape_([a-zA-Z_0-9]+)\.py', r'python scrapers_standalone/scrape_\1.py', content)
            content = re.sub(r'python (?:-u )?(parse|download)_([a-zA-Z_0-9]+)\.py', r'python scrapers_standalone/\1_\2.py', content)
            content = re.sub(r'python (?:-u )?guess_([a-zA-Z_0-9]+)\.py', r'python scrapers_standalone/guess_\1.py', content)

            # Update email_scraper.py arguments to data/raw/ and data/formatted/
            content = re.sub(r'email_scraper\.py (\S+)\.csv (\S+)\.csv', r'email_scraper.py data/raw/\1.csv data/formatted/\2.csv', content)

            with open(f_path, "w", encoding="utf-8-sig", newline="\r\n") as f:
                f.write(content)
            safe_print(f"[+] Updated BAT file: {os.path.basename(f_path)}")

def update_formatter_scripts():
    formatters_dir = os.path.join(ROOT_DIR, "formatters")
    for f_path in glob.glob(os.path.join(formatters_dir, "*.py")):
        if os.path.exists(f_path):
            with open(f_path, "r", encoding="utf-8-sig") as f:
                content = f.read()

            # 1. Define ROOT_DIR relative to script location
            if "ROOT_DIR = " not in content:
                content = content.replace(
                    'SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))',
                    'SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))\nROOT_DIR = os.path.dirname(SCRIPT_DIR)'
                )

            # 2. Redirect CANDIDATES to data/raw/ or data/formatted/
            def replace_candidate_path(match):
                filename = match.group(1)
                if any(x in filename.lower() for x in ["with_emails", "formatted", "cleaned", "(chờ)", "(đang)"]):
                    return f'os.path.join(ROOT_DIR, "data", "formatted", "{filename}")'
                else:
                    return f'os.path.join(ROOT_DIR, "data", "raw", "{filename}")'

            content = re.sub(r'os\.path\.join\(SCRIPT_DIR, "([^"]+\.csv|[^"]+\.xlsx|[^"]+\.xls)"\)', replace_candidate_path, content)

            # 3. Update BACKUP_CSV, FORMATTED_CSV etc. output path calculations to point to data/formatted/
            old_output_block = """if INPUT_CSV:
    ext = os.path.splitext(INPUT_CSV)[1]
    BACKUP_CSV = INPUT_CSV.replace(ext, f"_backup{ext}")
    FORMATTED_CSV = INPUT_CSV.replace(ext, f"_formatted{ext}")
    FORMATTED_XLSX = INPUT_CSV.replace(ext, f"_formatted.xlsx")
    FORMATTED_V2_CSV = INPUT_CSV.replace(ext, f"_formatted_v2{ext}")
    FORMATTED_V2_XLSX = INPUT_CSV.replace(ext, f"_formatted_v2.xlsx")"""

            new_output_block = """if INPUT_CSV:
    ext = os.path.splitext(INPUT_CSV)[1]
    base_name = os.path.basename(INPUT_CSV)
    BACKUP_CSV = os.path.join(ROOT_DIR, "data", "formatted", base_name.replace(ext, f"_backup{ext}"))
    FORMATTED_CSV = os.path.join(ROOT_DIR, "data", "formatted", base_name.replace(ext, f"_formatted{ext}"))
    FORMATTED_XLSX = os.path.join(ROOT_DIR, "data", "formatted", base_name.replace(ext, f"_formatted.xlsx"))
    FORMATTED_V2_CSV = os.path.join(ROOT_DIR, "data", "formatted", base_name.replace(ext, f"_formatted_v2{ext}"))
    FORMATTED_V2_XLSX = os.path.join(ROOT_DIR, "data", "formatted", base_name.replace(ext, f"_formatted_v2.xlsx"))"""

            content = content.replace(old_output_block, new_output_block)
            
            # Explicit replacements for format_korean_emails.py
            if "format_korean_emails.py" in f_path:
                content = content.replace('INPUT_CSV = "korean_agencies.csv"', 'INPUT_CSV = os.path.join(ROOT_DIR, "data", "raw", "korean_agencies.csv")')
                content = content.replace('OUTPUT_CSV = "korean_agencies_formatted.csv"', 'OUTPUT_CSV = os.path.join(ROOT_DIR, "data", "formatted", "korean_agencies_formatted.csv")')
                content = content.replace('OUTPUT_XLSX = "korean_agencies_formatted.xlsx"', 'OUTPUT_XLSX = os.path.join(ROOT_DIR, "data", "formatted", "korean_agencies_formatted.xlsx")')
                content = content.replace('PROGRESS_FILE_EMAILS = "scraping_progress_korean_emails.json"', 'PROGRESS_FILE_EMAILS = os.path.join(ROOT_DIR, "data", "progress", "scraping_progress_korean_emails.json")')

            # Explicit replacements for clean_korean_emails.py
            if "clean_korean_emails.py" in f_path:
                content = content.replace('input_file = "kofa_members_with_emails.csv"', 'input_file = os.path.join(ROOT_DIR, "data", "formatted", "kofa_members_with_emails.csv")')
                content = content.replace('output_file = "kofa_members_with_emails_cleaned.csv"', 'output_file = os.path.join(ROOT_DIR, "data", "formatted", "kofa_members_with_emails_cleaned.csv")')
                content = content.replace('output_xlsx = "kofa_members_with_emails_cleaned.xlsx"', 'output_xlsx = os.path.join(ROOT_DIR, "data", "formatted", "kofa_members_with_emails_cleaned.xlsx")')

            with open(f_path, "w", encoding="utf-8-sig") as f:
                f.write(content)
            safe_print(f"[+] Updated Formatter: {os.path.basename(f_path)}")

def update_configs():
    src_dir = os.path.join(ROOT_DIR, "src")
    for f_path in glob.glob(os.path.join(src_dir, "config_*.py")) + [os.path.join(src_dir, "config.py")]:
        if os.path.exists(f_path):
            with open(f_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 1. Update relative output CSV paths
            content = re.sub(
                r'os\.path\.join\(os\.path\.dirname\(os\.path\.dirname\(os\.path\.abspath\(__file__\)\)\), "([^"]+)"\)',
                r'os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw", "\1")',
                content
            )

            # 2. Redirect PROGRESS_FILE to data/progress/
            content = content.replace(
                'PROGRESS_FILE = os.path.join(os.path.dirname(OUTPUT_CSV),',
                'PROGRESS_FILE = os.path.join(os.path.dirname(os.path.dirname(OUTPUT_CSV)), "progress",'
            )

            # 3. Update absolute paths in config_kr.py
            if "config_kr.py" in f_path:
                content = content.replace(r'nail uc\korean_agencies.csv', r'nail uc\data\raw\korean_agencies.csv')
                content = content.replace(r'nail uc\korean_agencies.xlsx', r'nail uc\data\raw\korean_agencies.xlsx')

            with open(f_path, "w", encoding="utf-8") as f:
                f.write(content)
            safe_print(f"[+] Updated Config: {os.path.basename(f_path)}")

def update_standalone_scrapers():
    scrapers_dir = os.path.join(ROOT_DIR, "scrapers_standalone")
    for f_path in glob.glob(os.path.join(scrapers_dir, "*.py")):
        if os.path.exists(f_path):
            with open(f_path, "r", encoding="utf-8-sig") as f:
                content = f.read()

            # Define ROOT_DIR if not present
            if "ROOT_DIR = " not in content:
                if "SCRIPT_DIR = " in content:
                    content = content.replace(
                        'SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))',
                        'SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))\nROOT_DIR = os.path.dirname(SCRIPT_DIR)'
                    )
                else:
                    content = "import os\nSCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))\nROOT_DIR = os.path.dirname(SCRIPT_DIR)\n" + content

            # Update specific file paths
            replacements = [
                ('input_file = "kofa_members.csv"', 'input_file = os.path.join(ROOT_DIR, "data", "raw", "kofa_members.csv")'),
                ('output_file = "kofa_members_with_emails.csv"', 'output_file = os.path.join(ROOT_DIR, "data", "formatted", "kofa_members_with_emails.csv")'),
                ('output_xlsx = "kofa_members_with_emails.xlsx"', 'output_xlsx = os.path.join(ROOT_DIR, "data", "formatted", "kofa_members_with_emails.xlsx")'),
                
                ('csv_file = "kofa_members.csv"', 'csv_file = os.path.join(ROOT_DIR, "data", "raw", "kofa_members.csv")'),
                ('xlsx_file = "kofa_members.xlsx"', 'xlsx_file = os.path.join(ROOT_DIR, "data", "raw", "kofa_members.xlsx")'),
                
                ('input_file = "kosma_instructors.csv"', 'input_file = os.path.join(ROOT_DIR, "data", "raw", "kosma_instructors.csv")'),
                ('output_file = "kosma_instructors_with_emails.csv"', 'output_file = os.path.join(ROOT_DIR, "data", "formatted", "kosma_instructors_with_emails.csv")'),
                ('output_xlsx = "kosma_instructors_with_emails.xlsx"', 'output_xlsx = os.path.join(ROOT_DIR, "data", "formatted", "kosma_instructors_with_emails.xlsx")'),
                
                ('csv_file = "kosma_instructors.csv"', 'csv_file = os.path.join(ROOT_DIR, "data", "raw", "kosma_instructors.csv")'),
                ('xlsx_file = "kosma_instructors.xlsx"', 'xlsx_file = os.path.join(ROOT_DIR, "data", "raw", "kosma_instructors.xlsx")'),
                
                ('csv_file = "ksa_members.csv"', 'csv_file = os.path.join(ROOT_DIR, "data", "raw", "ksa_members.csv")'),
                ('xlsx_file = "ksa_members.xlsx"', 'xlsx_file = os.path.join(ROOT_DIR, "data", "raw", "ksa_members.xlsx")'),
                
                ('FILE_PATH = "(chờ) khách sạn Hy Lạp - CleanData.csv"', 'FILE_PATH = os.path.join(ROOT_DIR, "data", "formatted", "(chờ) khách sạn Hy Lạp - CleanData.csv")'),
                
                ('PROGRESS_FILE = os.path.join(SCRIPT_DIR, "scraping_progress_wda.json")', 'PROGRESS_FILE = os.path.join(ROOT_DIR, "data", "progress", "scraping_progress_wda.json")'),
                ('csv_file = "wda_employers.csv"', 'csv_file = os.path.join(ROOT_DIR, "data", "raw", "wda_employers.csv")'),
                ('xlsx_file = "wda_employers.xlsx"', 'xlsx_file = os.path.join(ROOT_DIR, "data", "raw", "wda_employers.xlsx")'),
                ('formatted_csv = "wda_employers_formatted.csv"', 'formatted_csv = os.path.join(ROOT_DIR, "data", "formatted", "wda_employers_formatted.csv")'),
                
                ('"suhyup_coops.xls"', 'os.path.join(ROOT_DIR, "data", "raw", "suhyup_coops.xls")'),
                ('"suhyup_coops.csv"', 'os.path.join(ROOT_DIR, "data", "raw", "suhyup_coops.csv")'),
                ('"suhyup_coops.xlsx"', 'os.path.join(ROOT_DIR, "data", "raw", "suhyup_coops.xlsx")'),
                
                ('"suhyup_list.html"', 'os.path.join(ROOT_DIR, "data", "assets", "suhyup_list.html")'),
            ]
            
            for old_str, new_str in replacements:
                content = content.replace(old_str, new_str)
                
            with open(f_path, "w", encoding="utf-8-sig") as f:
                f.write(content)
            safe_print(f"[+] Updated Standalone Scraper: {os.path.basename(f_path)}")

def main():
    safe_print("=== STARTING MIGRATION ===")
    create_dirs()
    migrate_files()
    update_bat_files()
    update_formatter_scripts()
    update_configs()
    update_standalone_scrapers()
    safe_print("=== MIGRATION COMPLETE ===")

if __name__ == "__main__":
    main()
