Purpose:
    Read downloaded Form 5500 PDFs, detect attachment sections,
    broadly extract employer-contribution-related text,
    then clean/filter irrelevant financial-statement content.

Main idea in this revised version:
    Step 1: broad extraction
    Step 2: cleaning / filtering

Output CSV columns:
    - plan_name
    - raw_paragraph
    - source_file
    - has_additional_paragraph
"""

import os
import re
import csv
import PyPDF2


def clean_mojibake(text):
    """
    Replace common encoding artifacts and smart quotes with standard characters.
    """
    replacements = {
        'Äú': '"',
        'Äù': '"',
        'Äô': "'",
        'Äò': "'",
        'Äì': "-",
        '“': '"',
        '”': '"',
        '‘': "'",
        '’': "'"
    }

    for bad_char, good_char in replacements.items():
        text = text.replace(bad_char, good_char)

    return text


def normalize_text(text):
    """
    Normalize whitespace and line breaks.
    """
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_into_paragraphs(text):
    """
    Split attachment text into paragraph-like chunks using blank lines.
    """
    paragraphs = re.split(r"\n\s*\n+", text)
    cleaned = []

    for para in paragraphs:
        para = re.sub(r"\s+", " ", para).strip()
        if para:
            cleaned.append(para)

    return cleaned


def is_form_page(page_text):
    """
    Detect whether a page is still part of the standard Form 5500 / schedules.
    Once we hit a non-form page, we treat the rest as attachments.
    """
    form_page_pattern = re.compile(
        r'(?:'
        r'Form\s+5500\s*\(\d{4}\)|'
        r'Schedule\s+[a-zA-Z]+\s*[\r\n]*\s*\(Form\s+5500\)(?:\s*\d{4})?'
        r')',
        re.IGNORECASE
    )

    return bool(form_page_pattern.search(page_text[:1000]))


def has_fill_in_blanks(text):
    """
    Exclude fill-in-the-blank style form fragments.
    """
    form_line_pattern = re.compile(r'_{4,}|\.{4,}')
    return bool(form_line_pattern.search(text))


def is_noise_paragraph(text):
    """
    Detect obvious financial statement / investment account noise.
    These are the kinds of paragraphs Louisa wanted removed.
    """
    noise_patterns = [
        r"\bdividends?\b",
        r"\bnet appreciation\b",
        r"\binterest income\b",
        r"\brealized gain\b",
        r"\bunrealized gain\b",
        r"\bfair market value\b",
        r"\bassets available for benefits\b",
        r"\bnotes to financial statements\b",
        r"\bstatement of net assets\b",
        r"\bnet assets\b",
        r"\binvestment[s]?\b",
        r"\binvestment income\b",
        r"\bcommon stock\b",
        r"\bmutual fund\b",
    ]

    for pattern in noise_patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True

    return False


def is_candidate_paragraph(text):
    """
    Broad extraction rule:
    We intentionally make this wider than the previous version so that
    we do not miss relevant contribution language that appears later.
    """
    keyword_patterns = [
        # Match / employer contribution
        r"\bemployer contributions?\b",
        r"\bemployer matching contributions?\b",
        r"\bmatching contributions?\b",
        r"\bmatch\b",
        r"\bmatches\b",
        r"\bdollar[- ]for[- ]dollar\b",

        # Safe harbor / nonelective / discretionary / profit sharing
        r"\bsafe harbor\b",
        r"\bsafe[- ]harbor\b",
        r"\bnon[- ]elective contributions?\b",
        r"\bnonelective contributions?\b",
        r"\bdiscretionary contributions?\b",
        r"\bprofit[- ]sharing contributions?\b",
        r"\bprofit[- ]sharing\b",

        # Vesting / eligibility / exception language
        r"\bvesting\b",
        r"\bvested\b",
        r"\beligible\b",
        r"\beligibility\b",
        r"\bcollective bargaining\b",
        r"\bunion employees?\b",

        # Contribution formula context
        r"\bdeferrals?\b",
        r"\belective deferrals?\b",
        r"\bcompensation\b",
        r"\bpay\b",
        r"\bsalary\b",
        r"\bfirst\s+\d{1,3}(?:\.\d+)?%",
        r"\bnext\s+\d{1,3}(?:\.\d+)?%",
        r"\bup to\s+\d{1,3}(?:\.\d+)?%",
        r"\b100%\b",
        r"\b50%\b",
        r"\b3%\b",
        r"\b4%\b",
    ]

    for pattern in keyword_patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True

    return False


def looks_like_continuation(text):
    """
    Some relevant formula details may continue in the next paragraph even if
    that next paragraph does not strongly match the keywords.
    """
    continuation_patterns = [
        r"^(then|and|provided|subject to|however|in addition)\b",
        r"\bfirst\s+\d{1,3}(?:\.\d+)?%",
        r"\bnext\s+\d{1,3}(?:\.\d+)?%",
        r"\bup to\s+\d{1,3}(?:\.\d+)?%",
        r"\b100%\b",
        r"\b50%\b",
        r"\b3%\b",
        r"\b4%\b",
        r"\bcompensation\b",
        r"\bdeferrals?\b",
        r"\beligible\b",
        r"\bvesting\b",
    ]

    for pattern in continuation_patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True

    return False


def clean_candidate_paragraph(text):
    """
    Light cleaning after broad extraction.
    We do not aggressively rewrite the paragraph because the parser
    still needs the original language.
    """
    text = clean_mojibake(text)
    text = normalize_text(text)

    # Remove repeated separators or excessive punctuation spacing
    text = re.sub(r"\s*;\s*;\s*", "; ", text)
    text = re.sub(r"\s*\|\s*", " | ", text)

    return text.strip()


def extract_plan_data(folder_path, output_csv):
    """
    Main PDF-to-CSV extraction routine.
    """
    results = []

    count_with_additional = 0
    count_without_additional = 0

    for filename in os.listdir(folder_path):
        if not filename.lower().endswith(".pdf"):
            continue

        filepath = os.path.join(folder_path, filename)

        # Extract plan name from filename
        plan_name = re.sub(r'_[0-9]{4}\.pdf$', '', filename, flags=re.IGNORECASE)
        plan_name = re.sub(r'\.pdf$', '', plan_name, flags=re.IGNORECASE).strip()

        matched_paragraphs = []
        attachment_pages_text = []
        in_attachments = False

        try:
            with open(filepath, "rb") as f:
                reader = PyPDF2.PdfReader(f)

                # --------------------------------------------------------------
                # First collect only attachment text
                # --------------------------------------------------------------
                for page in reader.pages:
                    page_text = page.extract_text()
                    if not page_text:
                        continue

                    if not is_form_page(page_text):
                        in_attachments = True

                    if in_attachments:
                        attachment_pages_text.append(page_text)

                attachment_text = "\n\n".join(attachment_pages_text).strip()

                # If attachment text exists, process it
                if attachment_text:
                    attachment_text = clean_mojibake(attachment_text)
                    attachment_text = normalize_text(attachment_text)

                    paragraphs = split_into_paragraphs(attachment_text)

                    i = 0
                    while i < len(paragraphs):
                        para = paragraphs[i]
                        para = clean_candidate_paragraph(para)

                        # Skip obvious non-useful form fragments
                        if not para or has_fill_in_blanks(para):
                            i += 1
                            continue

                        # Broad extraction first
                        candidate = is_candidate_paragraph(para)

                        # If current paragraph is relevant, optionally merge the next
                        # paragraph when it looks like a continuation.
                        if candidate and not is_noise_paragraph(para):
                            combined = para

                            if i + 1 < len(paragraphs):
                                nxt = clean_candidate_paragraph(paragraphs[i + 1])

                                if nxt and not has_fill_in_blanks(nxt):
                                    if looks_like_continuation(nxt) and not is_noise_paragraph(nxt):
                                        combined = combined + " " + nxt
                                        i += 1

                            matched_paragraphs.append(combined)

                        i += 1

        except Exception as e:
            print(f"Error processing {filename}: {e}")

        # ------------------------------------------------------------------
        # Final paragraph string
        # We join multiple matched chunks with " | " because your parser already
        # expects one raw_paragraph field per plan.
        # ------------------------------------------------------------------
        final_raw_paragraph = " | ".join(matched_paragraphs)

        has_additional_paragraph = "Yes" if final_raw_paragraph else "No"

        if has_additional_paragraph == "Yes":
            count_with_additional += 1
        else:
            count_without_additional += 1

        results.append({
            "plan_name": plan_name,
            "raw_paragraph": final_raw_paragraph,
            "source_file": filename,
            "has_additional_paragraph": has_additional_paragraph
        })

    # ----------------------------------------------------------------------
    # Write results to CSV
    # ----------------------------------------------------------------------
    with open(output_csv, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["plan_name", "raw_paragraph", "source_file", "has_additional_paragraph"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for row in results:
            writer.writerow(row)

    print(f"Successfully processed {len(results)} files.")
    print(f"Data saved to: {output_csv}")
    print()
    print(f"Plans WITH additional paragraphs: {count_with_additional}")
    print(f"Plans WITHOUT additional paragraphs: {count_without_additional}")


if __name__ == "__main__":
    input_directory = os.path.expanduser("~/Desktop/outputs")
    output_file = os.path.expanduser("~/Desktop/plan_paragraphs.csv")

    extract_plan_data(input_directory, output_file)
