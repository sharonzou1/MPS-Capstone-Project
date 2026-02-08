import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

def download_2024_file(download_path):
    """
    Navigates to the fixed URL, searches for the 2024 row, 
    and downloads the file to the specified path.
    """
    
    # --- CONFIGURATION ---
    TARGET_URL = "https://www.efast.dol.gov/5500Search/ " 
    TARGET_YEAR = "2024"
    
    # --- BROWSER SETUP ---
    options = webdriver.ChromeOptions()
    
    # Set the download directory preference
    prefs = {"download.default_directory": download_path}
    options.add_experimental_option("prefs", prefs)

    # Initialize Driver
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        print(f"Navigating to {TARGET_URL}...")
        driver.get(TARGET_URL)

        # --- WAIT FOR TABLE ---
        wait = WebDriverWait(driver, 20)
        print("Waiting for table data to load...")
        
        table_rows = wait.until(EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, "table.afs-table-spec tbody tr")
        ))
        
        print(f"Table loaded. Scanning {len(table_rows)} rows for '{TARGET_YEAR}'...")

        file_found = False

        # --- FIND AND CLICK ---
        for row in table_rows:
            cols = row.find_elements(By.TAG_NAME, "td")

            # Check the Year column
            year_text = cols[2].text.strip()
            
            if TARGET_YEAR in year_text:
                print(f"Match found for {TARGET_YEAR}! Initiating download...")
                
                # Find the download icon (SVG) in the first column
                download_btn = cols[0].find_element(By.TAG_NAME, "svg")
                
                # Scroll into view (helper for small screens)
                driver.execute_script("arguments[0].scrollIntoView();", download_btn)
                time.sleep(1) 
                
                # Force click via JavaScript (more reliable for SVGs)
                driver.execute_script("arguments[0].dispatchEvent(new Event('click', {bubbles: true}));", download_btn)
                
                file_found = True
                
                # Wait for download to start
                print("Download clicked. Waiting for transfer to start...")
                time.sleep(5) 
                break 

        if not file_found:
            print(f"Warning: No row found containing the year {TARGET_YEAR}.")

    except Exception as e:
        print(f"An error occurred: {e}")

    finally:
        print("Closing browser...")
        driver.quit()