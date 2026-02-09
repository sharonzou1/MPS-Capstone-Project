#Edited
# main.py
# -*- coding: utf-8 -*-

"""
Simple main orchestrator.

Run with:
    python main.py

Pipeline:
1. Step 1: Get_data.py
   - Read form5500.csv
   - Filter 401(k) / 403(b)
   - Deduplicate
   - Output: filtered_401k_403b_plans.csv

2. Step 2: Selenium search + download
   - Read filtered_401k_403b_plans.csv
   - Search each plan on efast
   - Download 2024 PDFs
"""

import importlib.util
import subprocess
import sys
from pathlib import Path


# ---------- helper ----------
def load_module(py_path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(py_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod


# ---------- STEP 1 ----------
def run_step1():
    print("\n===== STEP 1: Extract & clean plan names =====")


    form5500_csv = Path("f_5500_2024_all.csv")

    if not form5500_csv.exists():
        raise FileNotFoundError("form5500.csv not found in project directory")

    step1_script = Path("Get_data.py")


    if not step1_script.exists():
        raise FileNotFoundError("Get_data.py not found")

    mod = load_module(step1_script, "get_data")

    mod.process_form5500(str(form5500_csv)) 
    
    out_csv = Path("filtered_401k_403b_plans.csv")
    if not out_csv.exists():
        raise RuntimeError("STEP 1 failed: output CSV not generated")

    print("STEP 1 completed.")


# ---------- STEP 2 ----------
def run_step2():
    print("\n===== STEP 2: Search & download on efast =====")

    base_dir = Path(__file__).resolve().parent
    step2_script = base_dir / "Searching and Downloading.py"
    if not step2_script.exists():
        raise FileNotFoundError(f"Step 2 script not found: {step2_script}")

    subprocess.run([sys.executable, str(step2_script)], cwd=str(base_dir), check=True)
    print("STEP 2 finished (check browser / downloads).")



# ---------- MAIN ----------
def main():
    print("\n========== PIPELINE START ==========")
    run_step1()
    run_step2()
    print("\n========== PIPELINE END ==========")


if __name__ == "__main__":
    main()

