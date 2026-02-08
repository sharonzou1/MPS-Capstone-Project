# main.py
# -*- coding: utf-8 -*-

"""
Form 5500 Pipeline Orchestrator (System Architect)

Current available modules:
- STEP 1: Get_data.py  -> process_form5500(file_path) -> produces filtered_401k_403b_plans.csv
- STEP 3: DownloadFile.py -> download_2024_file(download_path)

STEP 2 is not received yet, so it is kept as a placeholder.
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ----------------------------
# Config
# ----------------------------
@dataclass
class PipelineConfig:
    # Step 1
    form5500_csv: Path
    step1_output_csv: Path
    step1_script: Path  # Get_data.py

    # Step 2 (placeholder)
    step2_script: Optional[Path]
    step2_output_csv: Path

    # Step 3
    step3_script: Path  # DownloadFile.py
    download_dir: Path

    # Runtime
    force_rerun: bool = False


# ----------------------------
# Logging
# ----------------------------
def setup_logger(verbosity: int) -> logging.Logger:
    """
    verbosity:
      0 -> WARNING
      1 -> INFO
      2+ -> DEBUG
    """
    level = logging.WARNING if verbosity <= 0 else logging.INFO if verbosity == 1 else logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger("form5500_pipeline")


# ----------------------------
# Helpers
# ----------------------------
def ensure_dir(p: Path) -> None:
    """Ensure directory exists."""
    p.mkdir(parents=True, exist_ok=True)


def assert_exists(p: Path, label: str) -> None:
    """Fail fast if file/dir is missing."""
    if not p.exists():
        raise FileNotFoundError(f"[{label}] Not found: {p}")


def load_module(py_path: Path, module_name: str):
    """
    Dynamically import a .py file as a module without requiring it to be a package.
    This is ideal for 'system architect' orchestration across teammate scripts.
    """
    spec = importlib.util.spec_from_file_location(module_name, str(py_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module spec: {py_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod


# ----------------------------
# STEP 1: get plan names + cleaning (dedupe)
# ----------------------------
def step1_get_plan_names(cfg: PipelineConfig, logger: logging.Logger) -> Path:
    """
    What STEP 1 does:
    1) Read Form 5500 CSV
    2) Filter plan names containing 401(k) or 403(b) (case-insensitive)
    3) Data cleaning: drop duplicates
    4) Output: a CSV with one column Full_Plan_Name (unique plan names)

    Implementation detail:
    - Your Get_data.py currently writes to 'filtered_401k_403b_plans.csv' in current working directory.
      We copy it to cfg.step1_output_csv as the pipeline's official artifact.
    """
    logger.info("STEP 1 | Extract + clean plan names (dedupe)")

    assert_exists(cfg.form5500_csv, "STEP 1 input CSV")
    assert_exists(cfg.step1_script, "STEP 1 script")

    if cfg.step1_output_csv.exists() and not cfg.force_rerun:
        logger.info("STEP 1 | Output exists, skipping: %s", cfg.step1_output_csv)
        return cfg.step1_output_csv

    mod = load_module(cfg.step1_script, "step1_get_data_mod")

    if not hasattr(mod, "process_form5500"):
        raise AttributeError("STEP 1 script must define: process_form5500(file_path)")

    # Call teammate function (no interactive input needed)
    mod.process_form5500(str(cfg.form5500_csv))  # type: ignore

    # Collect produced file
    produced = Path.cwd() / "filtered_401k_403b_plans.csv"
    assert_exists(produced, "STEP 1 produced output")

    ensure_dir(cfg.step1_output_csv.parent)
    cfg.step1_output_csv.write_bytes(produced.read_bytes())
    logger.info("STEP 1 | Saved official output -> %s", cfg.step1_output_csv)

    return cfg.step1_output_csv


# ----------------------------
# STEP 2: placeholder (search efast)
# ----------------------------
def step2_search_efast(cfg: PipelineConfig, step1_csv: Path, logger: logging.Logger) -> Path:
    """
    What STEP 2 will do (once received):
    1) Read unique plan names from step1_csv
    2) For each plan, search on https://www.efast.dol.gov/5500Search/
    3) Output a structured CSV of search results for downloading

    Current status: teammate script not received -> placeholder only.
    """
    logger.info("STEP 2 | Search efast (placeholder)")

    if cfg.step2_output_csv.exists() and not cfg.force_rerun:
        logger.info("STEP 2 | Output exists, skipping: %s", cfg.step2_output_csv)
        return cfg.step2_output_csv

    if cfg.step2_script is None or not cfg.step2_script.exists():
        logger.warning("STEP 2 | Script not provided yet. Skipping STEP 2.")
        return cfg.step2_output_csv

    # Once you send me step2 script, I will bind it here (import+call or subprocess).
    raise NotImplementedError("STEP 2 binding pending teammate implementation.")


# ----------------------------
# STEP 3: download (your exported DownloadFile.py)
# ----------------------------
def step3_download(cfg: PipelineConfig, logger: logging.Logger) -> Path:
    """
    What STEP 3 does (based on your current DownloadFile.py):
    1) Launch Selenium Chrome
    2) Open efast page
    3) Find the row for year=2024
    4) Click download icon
    5) Save file into cfg.download_dir

    NOTE:
    - This step currently downloads a single 2024 file (dataset-like),
      NOT "download PDFs for all plans" (that will be the future real STEP 3).
    """
    logger.info("STEP 3 | Download (from DownloadFile.py)")

    assert_exists(cfg.step3_script, "STEP 3 script")
    ensure_dir(cfg.download_dir)

    mod = load_module(cfg.step3_script, "step3_download_mod")

    if not hasattr(mod, "download_2024_file"):
        raise AttributeError("STEP 3 script must define: download_2024_file(download_path)")

    # Call teammate function
    mod.download_2024_file(str(cfg.download_dir))  # type: ignore

    logger.info("STEP 3 | Triggered download. Check folder: %s", cfg.download_dir)
    return cfg.download_dir


# ----------------------------
# Pipeline Runner
# ----------------------------
def run_pipeline(cfg: PipelineConfig, logger: logging.Logger) -> int:
    try:
        # STEP 1
        step1_csv = step1_get_plan_names(cfg, logger)
        logger.info("STEP 1 DONE | %s", step1_csv)

        # STEP 2 (optional)
        step2_csv = step2_search_efast(cfg, step1_csv, logger)
        if step2_csv.exists():
            logger.info("STEP 2 DONE | %s", step2_csv)
        else:
            logger.warning("STEP 2 skipped or not produced.")

        # STEP 3
        outdir = step3_download(cfg, logger)
        logger.info("STEP 3 DONE | %s", outdir)

        logger.info("PIPELINE DONE")
        return 0

    except Exception as e:
        logger.exception("PIPELINE FAILED: %s", e)
        return 1


# ----------------------------
# CLI
# ----------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Form 5500 pipeline orchestrator")

    p.add_argument("--form5500-csv", required=True, help="Path to Form 5500 dataset CSV")
    p.add_argument("--step1-script", default="Get_data.py", help="Step1 script filename (Get_data.py)")
    p.add_argument("--step1-output", default="outputs/filtered_401k_403b_plans.csv")

    p.add_argument("--step2-script", default="", help="Step2 script path (not received yet)")
    p.add_argument("--step2-output", default="outputs/search_results.csv")

    p.add_argument("--step3-script", default="DownloadFile.py", help="Step3 script filename (DownloadFile.py)")
    p.add_argument("--download-dir", default="outputs/downloads")

    p.add_argument("--force", action="store_true", help="Rerun even if outputs exist")
    p.add_argument("-v", "--verbose", action="count", default=1, help="Increase verbosity (-v, -vv)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    logger = setup_logger(args.verbose)

    cfg = PipelineConfig(
        form5500_csv=Path(args.form5500_csv).expanduser().resolve(),
        step1_output_csv=Path(args.step1_output).expanduser().resolve(),
        step1_script=Path(args.step1_script).expanduser().resolve(),
        step2_script=Path(args.step2_script).expanduser().resolve() if args.step2_script else None,
        step2_output_csv=Path(args.step2_output).expanduser().resolve(),
        step3_script=Path(args.step3_script).expanduser().resolve(),
        download_dir=Path(args.download_dir).expanduser().resolve(),
        force_rerun=args.force,
    )

    return run_pipeline(cfg, logger)


if __name__ == "__main__":
    raise SystemExit(main())
