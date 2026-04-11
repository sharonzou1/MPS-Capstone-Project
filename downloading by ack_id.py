import re
import time
import shutil
import pandas as pd
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options


# =========================
# Config
# =========================
BASE_DIR = Path(__file__).resolve().parent
EXCEL_FILE = BASE_DIR / "filtered_401k_403b_plans_with_details.xlsx"
TXT_FILE = BASE_DIR / "2024.txt"
OUTPUT_DIR = BASE_DIR / "downloaded_files"

TEST_ROWS = 1000
WAIT_TIMEOUT = 20
INDEX_URL = "https://www.askebsa.dol.gov/BulkFOIARequest/Listings.aspx/Index"

INITIAL_INDEX_WAIT = 1
DOWNLOAD_TRIGGER_WAIT = 1.2
RETRY_INDEX_WAIT = 0.8
RETRY_TRIGGER_WAIT = 1.2


# =========================
# Helpers
# =========================
def safe_filename(name: str) -> str:
    if pd.isna(name):
        name = "UNKNOWN_PLAN"
    name = str(name).strip()
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    name = re.sub(r"\s+", " ", name)
    return name


def setup_driver(download_dir: Path):
    chrome_options = Options()

    prefs = {
        "download.default_directory": str(download_dir),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True,
        "safebrowsing.enabled": True,
    }
    chrome_options.add_experimental_option("prefs", prefs)

    # chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1400,1000")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    return webdriver.Chrome(options=chrome_options)


def snapshot_folder(folder: Path) -> dict:
    """
    Return a snapshot:
    {
        '/path/to/file.pdf': (mtime, size)
    }
    """
    snap = {}
    for p in folder.iterdir():
        if p.is_file() and p.suffix != ".crdownload":
            try:
                stat = p.stat()
                snap[str(p)] = (stat.st_mtime, stat.st_size)
            except FileNotFoundError:
                pass
    return snap


def detect_changed_file(folder: Path, before_snapshot: dict, timeout: int = WAIT_TIMEOUT):
    """
    Detect the file created or modified by the latest download.
    Returns a Path or None.

    It can detect:
    1. A brand new file
    2. An existing file whose mtime/size changed
    """
    start = time.time()

    while time.time() - start < timeout:
        current_files = list(folder.iterdir())

        has_crdownload = any(
            p.is_file() and p.suffix == ".crdownload"
            for p in current_files
        )

        candidates = []

        for p in current_files:
            if not p.is_file() or p.suffix == ".crdownload":
                continue

            try:
                stat = p.stat()
            except FileNotFoundError:
                continue

            key = str(p)
            current_info = (stat.st_mtime, stat.st_size)

            if key not in before_snapshot:
                candidates.append((p, stat.st_mtime))
            else:
                if before_snapshot[key] != current_info:
                    candidates.append((p, stat.st_mtime))

        if candidates and not has_crdownload:
            candidates.sort(key=lambda x: x[1], reverse=True)
            return candidates[0][0]

        time.sleep(0.5)

    return None


def download_via_browser(driver, url: str, download_dir: Path, final_output_path: Path):
    """
    Download one file through browser and force-rename it to final_output_path.
    """
    before_snapshot = snapshot_folder(download_dir)

    try:
        driver.get(url)
        time.sleep(DOWNLOAD_TRIGGER_WAIT)

        changed_file = detect_changed_file(
            download_dir,
            before_snapshot,
            timeout=WAIT_TIMEOUT
        )

        if changed_file is None:
            # Retry once after reopening Index
            driver.get(INDEX_URL)
            time.sleep(RETRY_INDEX_WAIT)

            before_snapshot = snapshot_folder(download_dir)

            driver.get(url)
            time.sleep(RETRY_TRIGGER_WAIT)

            changed_file = detect_changed_file(
                download_dir,
                before_snapshot,
                timeout=WAIT_TIMEOUT
            )

        if changed_file is None:
            return False, None, f"No newly changed file detected. Browser ended at: {driver.current_url}"

        ext = changed_file.suffix if changed_file.suffix else ".pdf"
        final_path = final_output_path.with_suffix(ext)

        if final_path.exists():
            final_path.unlink()

        shutil.move(str(changed_file), str(final_path))
        return True, final_path, "Downloaded successfully"

    except Exception as e:
        return False, None, f"Browser download failed: {e}"


def extract_links_for_targets(txt_path: Path, target_ack_ids: set) -> dict:
    """
    Return:
    {
        ACK_ID: {
            "image": full GetImage URL or "",
            "facsimile": full GetFacsimile URL or ""
        }
    }
    """
    result = {
        ack_id: {"image": "", "facsimile": ""}
        for ack_id in target_ack_ids
    }

    with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = [line.strip() for line in f]

    for i, line in enumerate(lines):
        if not line:
            continue

        prefix = line.split("|", 1)[0].strip() if "|" in line else ""
        if prefix not in target_ack_ids:
            continue

        ack_id = prefix

        line1 = lines[i] if i < len(lines) else ""
        line2 = lines[i + 1] if i + 1 < len(lines) else ""
        line3 = lines[i + 2] if i + 2 < len(lines) else ""

        block = " ".join([line1, line2, line3])

        image_pattern = re.compile(
            rf'https://www\.askebsa\.dol\.gov/BulkFOIARequest/Listings\.aspx/GetImage\?\s*ack_id={re.escape(ack_id)}&year=2024',
            re.IGNORECASE
        )
        facsimile_pattern = re.compile(
            rf'https://www\.askebsa\.dol\.gov/BulkFOIARequest/Listings\.aspx/GetFacsimile\?\s*ack_id={re.escape(ack_id)}&year=2024',
            re.IGNORECASE
        )

        image_match = image_pattern.search(block)
        facsimile_match = facsimile_pattern.search(block)

        if image_match:
            result[ack_id]["image"] = re.sub(r"\s+", "", image_match.group(0))

        if facsimile_match:
            result[ack_id]["facsimile"] = re.sub(r"\s+", "", facsimile_match.group(0))

    return result


# =========================
# Main
# =========================
def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    if not EXCEL_FILE.exists():
        raise FileNotFoundError(f"Excel file not found: {EXCEL_FILE}")

    if not TXT_FILE.exists():
        raise FileNotFoundError(f"TXT file not found: {TXT_FILE}")

    print("Reading Excel...")
    df = pd.read_excel(EXCEL_FILE, dtype=str).head(TEST_ROWS)
    print(f"Testing only first {len(df)} rows...")

    required_cols = ["ACK_ID", "PLAN_NAME"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column in Excel: {col}")

    df["ACK_ID"] = df["ACK_ID"].astype(str).str.strip()
    df["PLAN_NAME"] = df["PLAN_NAME"].astype(str).str.strip()

    target_ack_ids = set(df["ACK_ID"])

    print("Parsing 2024.txt...")
    ack_to_links = extract_links_for_targets(TXT_FILE, target_ack_ids)

    total_with_both = sum(
        1 for _, links in ack_to_links.items()
        if links["image"] and links["facsimile"]
    )
    print(f"Found {total_with_both} ACK_ID(s) with both image and facsimile links")

    driver = setup_driver(OUTPUT_DIR)

    print("Opening Index page once to establish session...")
    driver.get(INDEX_URL)
    time.sleep(INITIAL_INDEX_WAIT)

    results = []

    try:
        for idx, row in df.iterrows():
            ack_id = row["ACK_ID"]
            plan_name_raw = row["PLAN_NAME"]
            plan_name = safe_filename(plan_name_raw)

            print(f"\n[{idx + 1}/{len(df)}] Processing ACK_ID: {ack_id}")
            print(f"  Plan Name: {plan_name_raw}")

            links = ack_to_links.get(ack_id, {"image": "", "facsimile": ""})
            image_url = links.get("image", "")
            facsimile_url = links.get("facsimile", "")

            # Only download if both links exist
            if not (image_url and facsimile_url):
                print("  Skip: this ACK_ID does not have both image and facsimile links")
                results.append({
                    "ACK_ID": ack_id,
                    "PLAN_NAME": plan_name_raw,
                    "Link_Type": "",
                    "Download_URL": "",
                    "Saved_File": "",
                    "Status": "SKIPPED_ONLY_ONE_LINK"
                })
                continue

            download_tasks = [
                ("image", image_url),
                ("facsimile", facsimile_url)
            ]

            for link_type, url in download_tasks:
                print(f"  {link_type.upper()} URL: {url}")

                final_output_path = OUTPUT_DIR / f"{plan_name}__{ack_id}__{link_type}.pdf"

                if final_output_path.exists() and final_output_path.stat().st_size > 0:
                    print(f"    File already exists, skipping: {final_output_path.name}")
                    results.append({
                        "ACK_ID": ack_id,
                        "PLAN_NAME": plan_name_raw,
                        "Link_Type": link_type,
                        "Download_URL": url,
                        "Saved_File": final_output_path.name,
                        "Status": "ALREADY_EXISTS"
                    })
                    continue

                success, saved_path, message = download_via_browser(
                    driver=driver,
                    url=url,
                    download_dir=OUTPUT_DIR,
                    final_output_path=final_output_path
                )

                if success:
                    print(f"    Downloaded: {saved_path.name}")
                    results.append({
                        "ACK_ID": ack_id,
                        "PLAN_NAME": plan_name_raw,
                        "Link_Type": link_type,
                        "Download_URL": url,
                        "Saved_File": saved_path.name,
                        "Status": "DOWNLOADED"
                    })
                else:
                    print(f"    Download failed: {message}")
                    results.append({
                        "ACK_ID": ack_id,
                        "PLAN_NAME": plan_name_raw,
                        "Link_Type": link_type,
                        "Download_URL": url,
                        "Saved_File": "",
                        "Status": f"DOWNLOAD_FAILED: {message}"
                    })

    finally:
        driver.quit()

    result_df = pd.DataFrame(results)
    result_file = BASE_DIR / "download_results.csv"
    result_df.to_csv(result_file, index=False)

    print("\nDone.")
    print(f"Downloaded files folder: {OUTPUT_DIR}")
    print(f"Result log saved to: {result_file}")


if __name__ == "__main__":
    main()