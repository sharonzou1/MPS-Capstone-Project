# In[1]:

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager


# In[2]:

def close_try_later_modal(driver, timeout=5):
    """
    Detects the 'Please try back later...' modal and closes it if present.
    Returns True if modal was found and closed, False otherwise.
    """
    try:

        modal_heading = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located(
                (By.XPATH, "//span[contains(text(),'Please try back later')]")
            )
        )

        close_button = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//button[contains(@class,'usa-modal__close')] | //button[.//span[text()='Close']]"
            ))
        )

        driver.execute_script("arguments[0].click();", close_button)
        print("Modal closed automatically.")
        return True

    except TimeoutException:
        return False


# In[3]:

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

DOWNLOAD_DIR = BASE_DIR / "outputs"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

DOWNLOAD_DIR = str(DOWNLOAD_DIR)

options = webdriver.ChromeOptions()
options.add_argument("--start-maximized")

prefs = {
    "download.default_directory": DOWNLOAD_DIR,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "plugins.always_open_pdf_externally": True 
}
options.add_experimental_option("prefs", prefs)

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)


wait = WebDriverWait(driver, 20)  

driver.get("https://www.efast.dol.gov/5500Search/")

# Step 1: Close modal if it appears
close_try_later_modal(driver)

# Step 2: Click 'Show Filters'
wait.until(
    EC.element_to_be_clickable(
        (By.XPATH, "//button[.//span[normalize-space(text())='Show Filters']]")
    )
).click()

# Step 3: Open 'Plan Years' accordion
wait.until(
    EC.element_to_be_clickable(
        (By.XPATH, "//button[contains(@class,'filter-category-button') and normalize-space(text())='Plan Years']")
    )
).click()

# Step 4: Select 2024
wait.until(
    EC.element_to_be_clickable(
        (By.XPATH, "//div[@id='planYearList']//a[starts-with(normalize-space(text()), '2024')]")
    )
).click()


# In[4]:

import pandas as pd
import time
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
import os
import time
import re


def sanitize_filename(name, max_len=150):
    """Make a string safe for filenames."""
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:max_len]

def get_latest_pdf(folder, wait_time=10):
    """Wait for and return the most recently downloaded PDF."""
    end_time = time.time() + wait_time
    while time.time() < end_time:
        pdfs = [
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if f.lower().endswith(".pdf")
        ]
        if pdfs:
            return max(pdfs, key=os.path.getctime)
        time.sleep(0.5)
    return None

# --- HELPER FUNCTION TO CLEAR SEARCH BAR BEFORE NEXT PLAN ---
def clear_plan_name_only(driver, wait, retries=2):
    """
    Clears the second breadcrumb X button (Plan Name) robustly.
    """
    for attempt in range(retries):
        try:
            plan_name_clear_btn = wait.until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    "(//button[contains(@class,'breadcrumb-delete-btn')])[2]"
                ))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", plan_name_clear_btn)
            driver.execute_script("arguments[0].click();", plan_name_clear_btn)
            return True
        except TimeoutException:
            time.sleep(0.3)
    return False


data_file = "filtered_401k_403b_plans.csv"
#df = pd.read_csv(data_file,nrows=100)
df = pd.read_csv(data_file, skiprows=range(1,101), nrows=350)
plan_names = df['Full_Plan_Name'].dropna().tolist()

for plan in plan_names:
    clean_plan = ' '.join(plan.strip().replace("\xa0", " ").split())
    print(f"\nSearching for: {clean_plan}")

    driver.execute_script("""
        const modal = document.querySelector('.mmodal');
        if (modal) modal.remove();
    """)

    search_input = wait.until(EC.element_to_be_clickable((By.ID, "search-field")))
    search_input.clear()
    search_input.send_keys(clean_plan)
    driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", search_input)
    search_input.send_keys("\n") 
    time.sleep(0.5) 

    # Click "Go!" 
    try:
        go_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[.//span[text()='Go!']]")))
        driver.execute_script("arguments[0].click();", go_button)
    except TimeoutException:
        pass

    # --- CHECK IF PLAN EXISTS ---
    found = False
    try:
        WebDriverWait(driver, 10).until(
            lambda d: any(
                clean_plan.lower() in row.text.lower()
                for row in d.find_elements(By.CSS_SELECTOR, "table tbody tr")
            )
        )
        found = True
    except (TimeoutException, StaleElementReferenceException):
        found = False

    if found:
        print("Plan exists")

        # --- DOWNLOAD PDF FOR 2024 ---
        rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
        downloaded = False
        for row in rows:
            cols = row.find_elements(By.TAG_NAME, "td")
            year_text = cols[2].text.strip()
            if "2024" in year_text:
                try:
                    download_btn = cols[0].find_element(By.TAG_NAME, "svg")
                    driver.execute_script("arguments[0].scrollIntoView();", download_btn)
                    time.sleep(0.5)
                    driver.execute_script(
                        "arguments[0].dispatchEvent(new Event('click', {bubbles: true}));", download_btn
                    )
                    time.sleep(3) 
                    latest_pdf = get_latest_pdf(DOWNLOAD_DIR)
                    if latest_pdf:
                        safe_name = sanitize_filename(clean_plan)
                        new_path = os.path.join(DOWNLOAD_DIR, f"{safe_name}_2024.pdf")
                        os.rename(latest_pdf, new_path)
                        print(f"Download: {new_path}")
                    else:
                        print("Downloaded PDF not found for renaming.")

                    downloaded = True
                    break
                except Exception as e:
                    print(f"Could not download PDF for {clean_plan}: {e}")
        if not downloaded:
            print(f"No 2024 PDF found for {clean_plan}")

    else:
        print("❌Plan NOT found")

    # --- CLEAR PLAN NAME FOR NEXT ITERATION ---
    try:
        search_input.clear()
        clear_plan_name_only(driver, wait)
        time.sleep(0.5)
    except:
        pass