from pathlib import Path
import math
import pandas as pd
from pypdf import PdfReader
import fitz  # PyMuPDF


# =========================
# Config
# =========================
BASE_DIR = Path(__file__).resolve().parent
PDF_DIR = BASE_DIR / "downloaded_files"

TEST_ROWS = 826

OUTPUT_XLSX = BASE_DIR / "additional_financial_statements_raw_text.xlsx"
OUTPUT_CSV = BASE_DIR / "additional_financial_statements_raw_text.csv"


CHUNK_SIZE = 30000


# =========================
# Helpers
# =========================
def parse_filename(file_path: Path):
    """
    Expected filename format:
    PLAN_NAME__ACK_ID__image.pdf

    Return:
        ack_id, plan_name, file_type
    """
    stem = file_path.stem
    parts = stem.split("__")

    if len(parts) >= 3:
        plan_name = "__".join(parts[:-2]).strip()
        ack_id = parts[-2].strip()
        file_type = parts[-1].strip().lower()
        return ack_id, plan_name, file_type

    return "", stem, ""


def extract_text_with_pymupdf(pdf_path: Path) -> str:
    texts = []
    try:
        doc = fitz.open(str(pdf_path))
        for page in doc:
            page_text = page.get_text("text")
            if page_text:
                texts.append(page_text)
        doc.close()
        return "\n".join(texts).strip()
    except Exception as e:
        return f"[PYMUPDF_ERROR] {e}"


def extract_text_with_pypdf(pdf_path: Path) -> str:
    texts = []
    try:
        reader = PdfReader(str(pdf_path))
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                texts.append(page_text)
        return "\n".join(texts).strip()
    except Exception as e:
        return f"[PYPDF_ERROR] {e}"


def extract_text_from_pdf(pdf_path: Path) -> str:
    """
    Try PyMuPDF first, then fallback to pypdf.
    """
    text1 = extract_text_with_pymupdf(pdf_path)
    if text1 and not text1.startswith("[PYMUPDF_ERROR]") and text1.strip():
        return text1

    text2 = extract_text_with_pypdf(pdf_path)
    if text2 and not text2.startswith("[PYPDF_ERROR]") and text2.strip():
        return text2

    return f"{text1} | {text2}"


def clean_for_excel(value: str) -> str:
    """
    Remove characters Excel/openpyxl cannot write.
    """
    if value is None:
        return ""
    value = str(value)
    return "".join(
        ch for ch in value
        if ord(ch) in (9, 10, 13) or ord(ch) >= 32
    )


def split_text_into_chunks(text: str, chunk_size: int = CHUNK_SIZE):
    """
    Split long text into chunks that fit safely in Excel cells.
    """
    text = clean_for_excel(text)
    if not text:
        return [""]

    chunks = []
    for i in range(0, len(text), chunk_size):
        chunks.append(text[i:i + chunk_size])
    return chunks


# =========================
# Main
# =========================
def main():
    if not PDF_DIR.exists():
        raise FileNotFoundError(f"PDF folder not found: {PDF_DIR}")

    pdf_files = sorted(PDF_DIR.glob("*__image.pdf"))[:TEST_ROWS]

    if not pdf_files:
        raise FileNotFoundError(f"No image PDF files found in: {PDF_DIR}")

    print(f"Testing first {len(pdf_files)} image PDF files...")

    temp_records = []
    max_chunks = 0

    for i, pdf_file in enumerate(pdf_files, start=1):
        print(f"[{i}/{len(pdf_files)}] Processing: {pdf_file.name}")

        ack_id, plan_name, file_type = parse_filename(pdf_file)

        if file_type != "image":
            continue

        raw_text = extract_text_from_pdf(pdf_file)
        raw_chunks = split_text_into_chunks(raw_text, CHUNK_SIZE)
        max_chunks = max(max_chunks, len(raw_chunks))

        temp_records.append({
            "File Path": clean_for_excel(pdf_file.name),
            "ACK ID": clean_for_excel(ack_id),
            "Plan Name": clean_for_excel(plan_name),
            "RAW_CHUNKS": raw_chunks
        })


    records = []
    for item in temp_records:
        row = {
            "File Path": item["File Path"],
            "ACK ID": item["ACK ID"],
            "Plan Name": item["Plan Name"],
        }

        chunks = item["RAW_CHUNKS"]
        for idx in range(max_chunks):
            col_name = f"RAW TEXT {idx + 1}"
            row[col_name] = chunks[idx] if idx < len(chunks) else ""

        records.append(row)

    df = pd.DataFrame(records)


    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    df.to_excel(OUTPUT_XLSX, index=False)

    print("\nDone.")
    print(f"CSV saved to: {OUTPUT_CSV}")
    print(f"Excel saved to: {OUTPUT_XLSX}")
    print(f"Maximum RAW TEXT columns used: {max_chunks}")


if __name__ == "__main__":
    main()