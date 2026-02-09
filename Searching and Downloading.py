#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pandas as pd
import time
import re
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager


def sanitize_filename(name: str, max_len: int = 120) -> str:
    name = re.sub(r"\s+", " ", str(name)).strip()
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    return name[:max_len]


def build_search_query(plan_name: str, max_words: int = 8) -> str:
    s = " ".join(str(plan_name).strip().replace("\xa0", " ").split())
    for ch in ["&", "(", ")", ","]:
        s = s.replace(ch, " ")
    s = re.sub(r"\s+", " ", s).strip()

    drop_words = {
        "INC", "INC.", "LLC", "L.L.C.", "CO", "CO.", "CORP", "CORPORATION",
        "LTD", "LIMITED", "TRUST", "PLAN", "PROFIT", "SHARING", "SAVINGS",
        "RETIREMENT", "EMPLOYEE", "BENEFIT"
    }
    words = [w for w in s.split() if w.upper() not in drop_words]
    return " ".join(words[:max_words]) if words else s


def list_pdfs(folder: Path) -> set[str]:
    return {p.name for p in folder.glob("*.pdf")}


def move_new_pdf(download_dir: Path, before: set[str], target_path: Path) -> bool:
    for _ in range(80): 
        if any(p.suffix == ".crdownload" for p in download_dir.glob("*.crdownload")):
            time.sleep(0.5)
            continue

        after = list_pdfs(download_dir)
        new_files = list(after - before)
        if new_files:
            new_pdf = download_dir / new_files[0]
            target_path.parent.mkdir(parents=True, exist_ok=True)

            if target_path.exists():
                target_path.unlink()

            new_pdf.rename(target_path)
            return True

        time.sleep(0.5)

    return False


def clear_plan_name_only(driver, wait, retries: int = 3) -> bool:
    for _ in range(retries):
        try:
            btn = wait.until(
                EC.element_to_be_clickable((By.XPATH, "(//button[contains(@class,'breadcrumb-delete-btn')])[2]"))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", btn)
            driver.execute_script("arguments[0].click();", btn)
            return True
        except TimeoutException:
            time.sleep(0.4)
    return False


def close_try_later_modal(driver, timeout: int = 3) -> bool:
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, "//span[contains(text(),'Please try back later')]"))
        )
        close_btn = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//button[contains(@class,'usa-modal__close')] | //button[.//span[text()='Close']]"
            ))
        )
        driver.execute_script("arguments[0].click();", close_btn)
        return True
    except TimeoutException:
        return False


def apply_year_filter(driver, wait, year: str):
    wait.until(EC.element_to_be_clickable(
        (By.XPATH, "//button[.//span[normalize-space(text())='Show Filters']]")
    )).click()

    wait.until(EC.element_to_be_clickable(
        (By.XPATH, "//button[contains(@class,'filter-category-button') and normalize-space(text())='Plan Years']")
    )).click()

    wait.until(EC.element_to_be_clickable(
        (By.XPATH, f"//div[@id='planYearList']//a[starts-with(normalize-space(text()), '{year}')]")
    )).click()


def has_year_row(driver, year: str) -> bool:
    rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
    for row in rows:
        tds = row.find_elements(By.TAG_NAME, "td")
        if len(tds) < 3:
            continue
        if year in tds[2].text.strip():
            return True
    return False


def click_download_for_year(driver, year: str) -> bool:
    for _ in range(3):
        try:
            rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
            for row in rows:
                tds = row.find_elements(By.TAG_NAME, "td")
                if len(tds) < 3:
                    continue

                if year in tds[2].text.strip():
                    icon = tds[0].find_element(By.TAG_NAME, "svg")
                    driver.execute_script("arguments[0].scrollIntoView();", icon)
                    time.sleep(0.3)
                    driver.execute_script(
                        "arguments[0].dispatchEvent(new Event('click', {bubbles: true}));",
                        icon
                    )
                    return True
            return False
        except StaleElementReferenceException:
            time.sleep(0.8)

    return False


TARGET_URL = "https://www.efast.dol.gov/5500Search/"
TARGET_YEAR = "2024"

csv_file = "filtered_401k_403b_plans.csv"

TEMP_DOWNLOAD_DIR = Path("outputs_tmp_downloads").resolve()
TEMP_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_DIR = Path("outputs").resolve()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

LIMIT = 10


def main():
    df = pd.read_csv(csv_file)
    if "Full_Plan_Name" not in df.columns:
        raise ValueError(
            f"Missing 'Full_Plan_Name' in {csv_file}. Columns: {df.columns.tolist()}"
        )

    plan_names = df["Full_Plan_Name"].dropna().astype(str).tolist()[:LIMIT]

    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_experimental_option("prefs", {"download.default_directory": str(TEMP_DOWNLOAD_DIR)})

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    wait = WebDriverWait(driver, 20)

    try:
        driver.get(TARGET_URL)
        close_try_later_modal(driver)
        apply_year_filter(driver, wait, TARGET_YEAR)

        for raw_plan in plan_names:
            query = build_search_query(raw_plan)
            plan_slug = sanitize_filename(raw_plan)

            print(f"\nSearching: {query}")

            search_box = wait.until(EC.element_to_be_clickable((By.ID, "search-field")))
            search_box.clear()
            search_box.send_keys(query)
            driver.execute_script(
                "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));",
                search_box
            )
            time.sleep(0.4)

            try:
                go_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[.//span[text()='Go!']]")))
                driver.execute_script("arguments[0].click();", go_btn)
            except TimeoutException:
                pass

            try:
                WebDriverWait(driver, 10).until(
                    lambda d: len(d.find_elements(By.CSS_SELECTOR, "table tbody tr")) > 0
                )
            except TimeoutException:
                print("Not found")
                if not clear_plan_name_only(driver, wait):
                    driver.refresh()
                    close_try_later_modal(driver)
                    apply_year_filter(driver, wait, TARGET_YEAR)
                continue

            if not has_year_row(driver, TARGET_YEAR):
                print("Not found")
                if not clear_plan_name_only(driver, wait):
                    driver.refresh()
                    close_try_later_modal(driver)
                    apply_year_filter(driver, wait, TARGET_YEAR)
                continue

            before = list_pdfs(TEMP_DOWNLOAD_DIR)
            clicked = click_download_for_year(driver, TARGET_YEAR)

            target_pdf = OUTPUT_DIR / f"{plan_slug}__{TARGET_YEAR}.pdf"
            moved = False

            if clicked:
                moved = move_new_pdf(TEMP_DOWNLOAD_DIR, before, target_pdf)

            if moved:
                print("Found")
                print(f"Saved: {target_pdf}")
            else:
                print("Not found")

            if not clear_plan_name_only(driver, wait):
                driver.refresh()
                close_try_later_modal(driver)
                apply_year_filter(driver, wait, TARGET_YEAR)

            time.sleep(0.4)

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
