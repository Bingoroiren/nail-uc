import os
import shutil
import glob
import re
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

def main():
    safe_print("=== CLEANUP REMAINING ROOT FILES ===")
    
    # 1. Move raw data
    f_json = os.path.join(ROOT_DIR, "bordbia_all_members_raw.json")
    if os.path.exists(f_json):
        shutil.move(f_json, os.path.join(ROOT_DIR, "data/raw", "bordbia_all_members_raw.json"))
        safe_print("Moved: bordbia_all_members_raw.json -> data/raw/")
        
    # 2. Move bat runner
    f_run = os.path.join(ROOT_DIR, "run.bat")
    if os.path.exists(f_run):
        shutil.move(f_run, os.path.join(ROOT_DIR, "runners", "run.bat"))
        safe_print("Moved: run.bat -> runners/")
        
    # 3. Move formatters & scrapers
    files_to_scrapers = [
        "scrape_gemi_agriculture.py",
        "scrape_gemi_construction.py",
        "scrape_gemi_manufacturing.py",
        "scrape_ireland_emails.py",
        "filter_wda_hot_leads.py"
    ]
    for filename in files_to_scrapers:
        f = os.path.join(ROOT_DIR, filename)
        if os.path.exists(f):
            shutil.move(f, os.path.join(ROOT_DIR, "scrapers_standalone", filename))
            safe_print(f"Moved Scraper: {filename} -> scrapers_standalone/")
            
    # 4. Move tests to scratch
    files_to_scratch = [
        "test_search.py",
        "test_suhyup.py"
    ]
    for filename in files_to_scratch:
        f = os.path.join(ROOT_DIR, filename)
        if os.path.exists(f):
            shutil.move(f, os.path.join(ROOT_DIR, "scratch", filename))
            safe_print(f"Moved Test: {filename} -> scratch/")
            
    # 5. Update paths in moved scripts
    # Update runners/run.bat
    f_run_path = os.path.join(ROOT_DIR, "runners", "run.bat")
    if os.path.exists(f_run_path):
        with open(f_run_path, "r", encoding="utf-8-sig") as f:
            content = f.read()
        content = content.replace('cd /d "%~dp0"', 'cd /d "%~dp0.."')
        # update paths inside run.bat if any
        with open(f_run_path, "w", encoding="utf-8-sig", newline="\r\n") as f:
            f.write(content)
        safe_print("[+] Updated BAT file: runners/run.bat")

    # Update scrapers_standalone/scrape_gemi_*.py
    for suffix in ["agriculture", "construction", "manufacturing"]:
        f_gemi = os.path.join(ROOT_DIR, "scrapers_standalone", f"scrape_gemi_{suffix}.py")
        if os.path.exists(f_gemi):
            with open(f_gemi, "r", encoding="utf-8-sig") as f:
                content = f.read()
            if "ROOT_DIR = " not in content:
                content = "import os\nSCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))\nROOT_DIR = os.path.dirname(SCRIPT_DIR)\n" + content
            content = content.replace(
                f'OUTPUT_CSV = "gemi_{suffix}_companies.csv"',
                f'OUTPUT_CSV = os.path.join(ROOT_DIR, "data", "raw", "gemi_{suffix}_companies.csv")'
            )
            with open(f_gemi, "w", encoding="utf-8-sig") as f:
                f.write(content)
            safe_print(f"[+] Updated Scraper Path: scrapers_standalone/scrape_gemi_{suffix}.py")

    # Update scrapers_standalone/scrape_ireland_emails.py
    f_ireland = os.path.join(ROOT_DIR, "scrapers_standalone", "scrape_ireland_emails.py")
    if os.path.exists(f_ireland):
        with open(f_ireland, "r", encoding="utf-8-sig") as f:
            content = f.read()
        if "ROOT_DIR = " not in content:
            content = "import os\nSCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))\nROOT_DIR = os.path.dirname(SCRIPT_DIR)\n" + content
        content = content.replace(
            'files = glob.glob("*(ch*)*ireland*CleanData.csv")',
            'files = glob.glob(os.path.join(ROOT_DIR, "data", "formatted", "*(ch*)*ireland*CleanData.csv"))'
        )
        with open(f_ireland, "w", encoding="utf-8-sig") as f:
            f.write(content)
        safe_print("[+] Updated Scraper Path: scrapers_standalone/scrape_ireland_emails.py")

    # Update scrapers_standalone/filter_wda_hot_leads.py
    f_wda = os.path.join(ROOT_DIR, "scrapers_standalone", "filter_wda_hot_leads.py")
    if os.path.exists(f_wda):
        with open(f_wda, "r", encoding="utf-8-sig") as f:
            content = f.read()
        if "ROOT_DIR = " not in content:
            content = content.replace(
                'SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))',
                'SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))\nROOT_DIR = os.path.dirname(SCRIPT_DIR)'
            )
        content = content.replace(
            'INPUT_CSV = os.path.join(SCRIPT_DIR, "wda_employers.csv")',
            'INPUT_CSV = os.path.join(ROOT_DIR, "data", "raw", "wda_employers.csv")'
        )
        content = content.replace(
            'OUTPUT_CSV = os.path.join(SCRIPT_DIR, "wda_hot_leads.csv")',
            'OUTPUT_CSV = os.path.join(ROOT_DIR, "data", "formatted", "wda_hot_leads.csv")'
        )
        content = content.replace(
            'OUTPUT_XLSX = os.path.join(SCRIPT_DIR, "wda_hot_leads.xlsx")',
            'OUTPUT_XLSX = os.path.join(ROOT_DIR, "data", "formatted", "wda_hot_leads.xlsx")'
        )
        with open(f_wda, "w", encoding="utf-8-sig") as f:
            f.write(content)
        safe_print("[+] Updated Scraper Path: scrapers_standalone/filter_wda_hot_leads.py")

    # Update scratch/test_suhyup.py
    f_suhyup = os.path.join(ROOT_DIR, "scratch", "test_suhyup.py")
    if os.path.exists(f_suhyup):
        with open(f_suhyup, "r", encoding="utf-8-sig") as f:
            content = f.read()
        if "ROOT_DIR = " not in content:
            content = "import os\nSCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))\nROOT_DIR = os.path.dirname(SCRIPT_DIR)\n" + content
        content = content.replace(
            'with open("suhyup_list.html", "w", encoding="utf-8") as f:',
            'with open(os.path.join(ROOT_DIR, "data", "assets", "suhyup_list.html"), "w", encoding="utf-8") as f:'
        )
        with open(f_suhyup, "w", encoding="utf-8-sig") as f:
            f.write(content)
        safe_print("[+] Updated Test Path: scratch/test_suhyup.py")

    safe_print("=== CLEANUP COMPLETE ===")

if __name__ == "__main__":
    main()
