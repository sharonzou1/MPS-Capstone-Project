import os
import re
import csv
import PyPDF2

def clean_mojibake(text):
    """Replaces common encoding artifacts and smart quotes with standard characters."""
    replacements = {
        'Äú': '"', 'Äù': '"', 'Äô': "'", 'Äò': "'", 'Äì': "-",
        '“': '"', '”': '"', '‘': "'", '’': "'"
    }
    for bad_char, good_char in replacements.items():
        text = text.replace(bad_char, good_char)
    return text

def extract_plan_data(folder_path, output_csv):
    results = []

    # --- added for counting ---
    count_with_additional = 0
    count_without_additional = 0
    # --------------------------

    # 1. Rigorous keyword filter for the paragraphs
    keywords = [
        r'\bvesting\b',
        r'\bvested\b',
        r'\bdeferrals?\b',
        r'\bemployer contributions?\b',
        r'\bemployer matching contributions?\b',
        r'\bmatching contributions?\b',
        r'\bcompany contributions?\b',
        r'\bprofit[- ]sharing contributions?\b',
        r'\bnon[- ]elective contributions?\b',
        r'\bsafe harbor contributions?\b',
        r'\bdiscretionary contributions?\b'
    ]
    keyword_pattern = re.compile('|'.join(keywords), re.IGNORECASE)

    # 2. Structural identifiers based on your 3 observed form header patterns
    form_page_pattern = re.compile(
        r'(?:'
        r'Form\s+5500\s*\(\d{4}\)|'  
        r'Schedule\s+[a-zA-Z]+\s*[\r\n]*\s*\(Form\s+5500\)(?:\s*\d{4})?' 
        r')',
        re.IGNORECASE
    )

    # 3. Pattern to catch fill-in-the-blank form lines (4 or more dots or underscores)
    form_line_pattern = re.compile(r'_{4,}|\.{4,}')

    for filename in os.listdir(folder_path):
        if not filename.lower().endswith('.pdf'):
            continue

        filepath = os.path.join(folder_path, filename)
        
        # Extract Plan Name cleanly from the filename
        plan_name = re.sub(r'_[0-9]{4}\.pdf$', '', filename, flags=re.IGNORECASE)
        plan_name = re.sub(r'\.pdf$', '', plan_name, flags=re.IGNORECASE).strip()

        matched_paragraphs = []
        attachment_text = ""
        in_attachments = False

        try:
            with open(filepath, 'rb') as f:
                reader = PyPDF2.PdfReader(f)

                # Evaluate page-by-page
                for page in reader.pages:
                    page_text = page.extract_text()
                    if not page_text:
                        continue
                    
                    # We check the first 1000 characters of the page text 
                    is_form_page = bool(form_page_pattern.search(page_text[:1000]))

                    if not is_form_page:
                        # As soon as we hit a non-form page, we are in the attachments
                        in_attachments = True

                    # If we are in the attachment section, collect the text
                    if in_attachments:
                        attachment_text += page_text + "\n"

                # If we collected attachment text, process it
                if attachment_text:
                    attachment_text = clean_mojibake(attachment_text)
                    
                    # Split the attachments into paragraphs
                    paragraphs = re.split(r'\n(?:\s*\n)+', attachment_text)
                    
                    for para in paragraphs:
                        clean_para = re.sub(r'\s+', ' ', para).strip()
                        
                        # Check 1: Does it have our required keywords?
                        has_keywords = bool(keyword_pattern.search(clean_para))
                        
                        # Check 2: Does it contain fill-in-the-blank lines?
                        has_blanks = bool(form_line_pattern.search(clean_para))
                        
                        # Apply both filters
                        if has_keywords and not has_blanks:
                            matched_paragraphs.append(clean_para)

        except Exception as e:
            print(f"Error processing {filename}: {e}")

        # Combine matches, or leave empty if none found (or if no attachments existed)
        final_raw_paragraph = " | ".join(matched_paragraphs)

        # added for counting
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

    # Write to CSV
    with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['plan_name', 'raw_paragraph', 'source_file', 'has_additional_paragraph']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for row in results:
            writer.writerow(row)

    print(f"Successfully processed {len(results)} files.")
    print(f"Data saved to: {output_csv}")

    # summary output
    print()
    print(f"Plans WITH additional paragraphs: {count_with_additional}")
    print(f"Plans WITHOUT additional paragraphs: {count_without_additional}")

if __name__ == "__main__":
    input_directory = os.path.expanduser('~/Desktop/outputs')
    output_file = os.path.expanduser('~/Desktop/plan_paragraphs.csv')
    
    extract_plan_data(input_directory, output_file)