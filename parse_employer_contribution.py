Purpose:
    Parse employer-contribution-related raw text into a structured table.

What this version improves:
    1. No longer relies only on the first keyword hit.
    2. Extracts broader candidate sentences first, then parses structure.
    3. Better handles safe harbor and tiered match formulas.
    4. Adds extra fields requested by the team while keeping old columns for compatibility.

Input CSV required columns:
    - plan_name
    - raw_paragraph
Optional:
    - source_file

Example:
    python parse_employer_contribution.py --input plan_paragraphs.csv --output employer_contribution_table.csv
"""

import re
import argparse
from typing import Dict, Any, Optional, List, Tuple

import pandas as pd


class EmployerContributionParser:
    """
    Rule-based parser for employer contribution paragraphs extracted from Form 5500 PDFs.
    """

    def __init__(self) -> None:
        # ------------------------------------------------------------------
        # Core keyword groups
        # ------------------------------------------------------------------
        self.match_keywords = [
            r"\bmatch\b",
            r"\bmatches\b",
            r"\bmatching contribution\b",
            r"\bmatching contributions\b",
            r"\bemployer matching contribution\b",
            r"\bemployer matching contributions\b",
            r"\bdollar[- ]for[- ]dollar\b",
            r"\bsafe harbor match\b",
            r"\bsafe harbor matching\b",
        ]

        self.safe_harbor_keywords = [
            r"\bsafe harbor\b",
            r"\bsafe[- ]harbor\b",
        ]

        self.discretionary_keywords = [
            r"\bdiscretionary contribution\b",
            r"\bdiscretionary contributions\b",
            r"\bemployer may contribute\b",
            r"\bemployer may make contributions\b",
            r"\bmay contribute\b",
            r"\bmay make contributions\b",
            r"\bas determined by the board\b",
            r"\bat the discretion of\b",
            r"\bboard of directors\b",
            r"\bannually determined\b",
            r"\bif declared by the employer\b",
        ]

        self.nonelective_keywords = [
            r"\bnonelective contribution\b",
            r"\bnonelective contributions\b",
            r"\bnon[- ]elective contribution\b",
            r"\bnon[- ]elective contributions\b",
            r"\bsafe harbor nonelective\b",
        ]

        self.profit_sharing_keywords = [
            r"\bprofit[- ]sharing\b",
            r"\bprofit sharing contribution\b",
            r"\bprofit sharing contributions\b",
        ]

        self.no_contribution_keywords = [
            r"\bno employer contributions\b",
            r"\bemployer does not contribute\b",
            r"\bno contributions are made\b",
            r"\bno matching contributions\b",
            r"\bthe employer does not make contributions\b",
            r"\bno employer matching contributions\b",
        ]

        self.collective_bargaining_keywords = [
            r"\bcollective bargaining\b",
            r"\bcollective bargaining agreement\b",
            r"\bunion employees?\b",
            r"\bcovered by a collective bargaining agreement\b",
            r"\bcba\b",
        ]

        self.vesting_keywords = [
            r"\bvesting\b",
            r"\bvested\b",
            r"\bfully vested\b",
            r"\bvests\b",
            r"\bvest\b",
        ]

        # ------------------------------------------------------------------
        # Sentence-level noise patterns
        # These are financial-statement / investment-account topics that
        # Louisa specifically wanted filtered away if they appear.
        # ------------------------------------------------------------------
        self.noise_keywords = [
            r"\bdividends?\b",
            r"\bnet appreciation\b",
            r"\binterest income\b",
            r"\brealized gain\b",
            r"\bunrealized gain\b",
            r"\bfair market value\b",
            r"\basset[s]?\b",
            r"\bliabilit(?:y|ies)\b",
            r"\binvestment\b",
            r"\binvestments\b",
            r"\bnotes to financial statements\b",
        ]

        # ------------------------------------------------------------------
        # Eligibility patterns
        # These are used for both general eligibility and discretionary eligibility.
        # ------------------------------------------------------------------
        self.eligibility_patterns = [
            r"eligible after [^.]+",
            r"eligibility [^.]+",
            r"employees are eligible [^.]+",
            r"become eligible [^.]+",
            r"after one year of service",
            r"after 1 year of service",
            r"immediate(?:ly)? eligible",
            r"eligible immediately",
            r"must complete [^.]+ hours",
            r"must work [^.]+ hours",
            r"last day of the plan year",
            r"employed on the last day [^.]*",
            r"attained age \d+",
            r"completed \d+ year[s]? of service",
        ]

        # ------------------------------------------------------------------
        # Regex patterns for percentage / dollar / match formula extraction
        # ------------------------------------------------------------------
        self.percent_pattern = re.compile(r"\b\d{1,3}(?:\.\d+)?%")
        self.dollar_pattern = re.compile(r"\$\s*\d[\d,]*(?:\.\d{2})?")

        # Tiered / formula-like patterns
        self.formula_patterns = [
            r"100%\s+on\s+the\s+first\s+\d{1,3}(?:\.\d+)?%\s*,?\s*then\s+50%\s+on\s+the\s+next\s+\d{1,3}(?:\.\d+)?%",
            r"100%\s+on\s+the\s+first\s+\d{1,3}(?:\.\d+)?%",
            r"50%\s+on\s+the\s+first\s+\d{1,3}(?:\.\d+)?%",
            r"matches?\s+\d{1,3}(?:\.\d+)?%\s+of\s+(?:employee\s+)?(?:deferrals|contributions|elective deferrals)",
            r"dollar[- ]for[- ]dollar\s+up\s+to\s+\d{1,3}(?:\.\d+)?%",
            r"\d{1,3}(?:\.\d+)?%\s+non[- ]elective contribution",
            r"safe harbor [^.]*",
        ]

    # ----------------------------------------------------------------------
    # Basic text helpers
    # ----------------------------------------------------------------------
    @staticmethod
    def normalize_text(text: str) -> str:
        """Clean and normalize raw paragraph text."""
        if pd.isna(text):
            return ""

        text = str(text)
        text = text.replace("\n", " ")
        text = text.replace("\r", " ")
        text = text.replace(" | ", ". ")
        text = re.sub(r"\s+", " ", text)
        text = text.strip()
        return text

    @staticmethod
    def split_sentences(text: str) -> List[str]:
        """
        Split text into sentence-like pieces.
        We keep this simple and robust for messy PDF extraction text.
        """
        if not text:
            return []
        parts = re.split(r"(?<=[.;:])\s+|\s+\|\s+", text)
        return [p.strip() for p in parts if p and p.strip()]

    @staticmethod
    def search_any(patterns: List[str], text: str) -> bool:
        """Return True if any regex pattern matches."""
        for pattern in patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                return True
        return False

    @staticmethod
    def find_all_matches(pattern: str, text: str) -> List[str]:
        """Return all regex matches for one pattern."""
        return re.findall(pattern, text, flags=re.IGNORECASE)

    def is_noise_sentence(self, sentence: str) -> bool:
        """Check whether a sentence is mostly financial/accounting noise."""
        return self.search_any(self.noise_keywords, sentence)

    # ----------------------------------------------------------------------
    # Candidate extraction
    # ----------------------------------------------------------------------
    def collect_relevant_sentences(self, text: str) -> List[str]:
        """
        Collect all potentially relevant sentences instead of stopping at first hit.
        This is the main shift from the older, more brittle logic.
        """
        sentences = self.split_sentences(text)
        selected: List[str] = []

        for i, sentence in enumerate(sentences):
            sentence_lower = sentence.lower()

            # Decide whether the sentence is contribution-relevant
            contribution_related = (
                self.search_any(self.match_keywords, sentence)
                or self.search_any(self.safe_harbor_keywords, sentence)
                or self.search_any(self.discretionary_keywords, sentence)
                or self.search_any(self.nonelective_keywords, sentence)
                or self.search_any(self.profit_sharing_keywords, sentence)
                or self.search_any(self.collective_bargaining_keywords, sentence)
                or self.search_any(self.vesting_keywords, sentence)
                or self.search_any(self.eligibility_patterns, sentence)
            )

            # Also keep formula-looking sentences even if keywords are light
            formula_like = bool(
                re.search(r"\b(first|next|up to|not in excess of|100%|50%|3%|4%)\b", sentence_lower)
                and (
                    "%" in sentence_lower
                    or "deferral" in sentence_lower
                    or "contribution" in sentence_lower
                    or "compensation" in sentence_lower
                    or "salary" in sentence_lower
                    or "pay" in sentence_lower
                )
            )

            if (contribution_related or formula_like) and not self.is_noise_sentence(sentence):
                selected.append(sentence)

                # Keep the next sentence too if it looks like a continuation.
                if i + 1 < len(sentences):
                    nxt = sentences[i + 1]
                    nxt_lower = nxt.lower()

                    continuation = (
                        nxt_lower.startswith(("then ", "and ", "plus ", "however ", "provided ", "subject to "))
                        or "%" in nxt_lower
                        or "first" in nxt_lower
                        or "next" in nxt_lower
                        or "up to" in nxt_lower
                        or "safe harbor" in nxt_lower
                        or "vesting" in nxt_lower
                        or "eligible" in nxt_lower
                    )

                    if continuation and not self.is_noise_sentence(nxt):
                        selected.append(nxt)

        # Remove duplicates while preserving order
        deduped: List[str] = []
        seen = set()
        for sentence in selected:
            if sentence not in seen:
                deduped.append(sentence)
                seen.add(sentence)

        return deduped

    def build_cleaned_text(self, text: str) -> str:
        """
        Create a cleaned ER-focused text block from all relevant sentences.
        """
        sentences = self.collect_relevant_sentences(text)
        return " ; ".join(sentences)

    # ----------------------------------------------------------------------
    # Type / indicator inference
    # ----------------------------------------------------------------------
    def infer_match_flags(self, text: str) -> Dict[str, int]:
        """
        Infer match subtypes as indicator variables.
        We keep old er_match_type for compatibility, but also add separate flags.
        """
        lower_text = text.lower()

        safe_harbor = int("safe harbor" in lower_text or "safe-harbor" in lower_text)

        # Full match examples:
        # - 100% match
        # - dollar for dollar
        full_match = int(
            bool(
                re.search(r"100%\s+match", lower_text)
                or re.search(r"matches?\s+100%", lower_text)
                or re.search(r"dollar[- ]for[- ]dollar", lower_text)
                or re.search(r"100%\s+on\s+the\s+first", lower_text)
            )
        )

        # Partial match examples:
        # - 50% match
        # - then 50% on the next 2%
        # - any explicit less-than-full tier
        partial_match = int(
            bool(
                re.search(r"50%\s+match", lower_text)
                or re.search(r"matches?\s+50%", lower_text)
                or re.search(r"50%\s+on\s+the\s+first", lower_text)
                or re.search(r"50%\s+on\s+the\s+next", lower_text)
                or re.search(r"\b25%\b", lower_text)
                or re.search(r"\b75%\b", lower_text)
            )
        )

        general_match = int(
            self.search_any(self.match_keywords, lower_text) or safe_harbor == 1
        )

        # If safe harbor match is present, we want that separate flag too
        safe_harbor_match = int(safe_harbor == 1 and general_match == 1)

        return {
            "er_match_full_indicator": full_match,
            "er_match_general_indicator": general_match,
            "er_match_partial_indicator": partial_match,
            "er_match_safe_harbor_indicator": safe_harbor_match,
        }

    def infer_match_type(self, text: str) -> Optional[str]:
        """
        Keep old single-column er_match_type for backward compatibility.
        If multiple types appear, store them as a semicolon-separated label string.
        """
        flags = self.infer_match_flags(text)
        labels = []

        if flags["er_match_safe_harbor_indicator"] == 1:
            labels.append("safe_harbor_match")
        if flags["er_match_full_indicator"] == 1:
            labels.append("full_match")
        if flags["er_match_partial_indicator"] == 1:
            labels.append("partial_match")
        if flags["er_match_general_indicator"] == 1 and not labels:
            labels.append("general_match")

        return "; ".join(labels) if labels else None

    # ----------------------------------------------------------------------
    # Formula extraction
    # ----------------------------------------------------------------------
    def extract_formula_sentences(self, text: str) -> List[str]:
        """
        Extract all sentence-like chunks that look like ER match formulas.
        """
        sentences = self.collect_relevant_sentences(text)
        selected = []

        for sentence in sentences:
            lower = sentence.lower()

            formula_like = (
                self.search_any(self.match_keywords, sentence)
                or "safe harbor" in lower
                or "non-elective" in lower
                or "nonelective" in lower
                or bool(re.search(r"\b(first|next|up to|not in excess of)\b", lower))
                or "%" in sentence
                or "$" in sentence
            )

            if formula_like and not self.is_noise_sentence(sentence):
                selected.append(sentence)

        # Remove duplicates while preserving order
        deduped = []
        seen = set()
        for s in selected:
            if s not in seen:
                deduped.append(s)
                seen.add(s)

        return deduped

    def extract_match_formula_text(self, text: str) -> Optional[str]:
        """
        Return a broader formula text rather than just the first sentence.
        """
        formula_sentences = self.extract_formula_sentences(text)

        # Keep only match-related / safe-harbor-related sentences for this field
        kept = []
        for s in formula_sentences:
            if (
                self.search_any(self.match_keywords, s)
                or self.search_any(self.safe_harbor_keywords, s)
                or self.search_any(self.nonelective_keywords, s)
                or "%" in s
                or "$" in s
            ):
                kept.append(s)

        if kept:
            return " ; ".join(kept)
        return None

    def extract_percent_values(self, text: str) -> List[str]:
        """Extract all percentage values in appearance order."""
        return self.percent_pattern.findall(text)

    def extract_dollar_values(self, text: str) -> List[str]:
        """Extract all dollar values in appearance order."""
        return self.dollar_pattern.findall(text)

    def extract_match_rate_and_cap(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Old output had only er_match_rate and er_match_cap.
        We keep them, but store more information in a compact string form.

        Convention used here:
            - er_match_rate: all rate-like percentages joined by '; '
            - er_match_cap: all cap-like percentages joined by '; '
        """
        lower_text = text.lower()
        percentages = self.extract_percent_values(text)

        if not percentages:
            return None, None

        rate_values: List[str] = []
        cap_values: List[str] = []

        # Simple heuristics:
        # - rates often near "match", "matches", "dollar-for-dollar"
        # - caps often near "first", "next", "up to", "of compensation/pay/salary"
        for pct in percentages:
            # Search the local context around the percentage
            escaped_pct = re.escape(pct)
            window_match = re.search(rf".{{0,40}}{escaped_pct}.{{0,40}}", lower_text, flags=re.IGNORECASE)
            context = window_match.group(0) if window_match else ""

            if re.search(r"\b(match|matches|matching|dollar[- ]for[- ]dollar)\b", context):
                rate_values.append(pct)

            if re.search(r"\b(first|next|up to|of compensation|of pay|of salary|not in excess of)\b", context):
                cap_values.append(pct)

        # Fallback if we failed to separate nicely
        if not rate_values and percentages:
            rate_values = percentages[:1]

        if not cap_values and len(percentages) >= 2:
            cap_values = percentages[1:]
        elif not cap_values and len(percentages) == 1:
            cap_values = percentages

        rate_text = "; ".join(dict.fromkeys(rate_values)) if rate_values else None
        cap_text = "; ".join(dict.fromkeys(cap_values)) if cap_values else None
        return rate_text, cap_text

    def extract_min_max_dollar(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract min/max dollar values from a text chunk.
        Keep them as string values to avoid accidental numeric conversion issues.
        """
        dollars = self.extract_dollar_values(text)
        if not dollars:
            return None, None

        # Convert for min/max comparison
        numeric_pairs = []
        for d in dollars:
            num = float(d.replace("$", "").replace(",", "").strip())
            numeric_pairs.append((d, num))

        numeric_pairs.sort(key=lambda x: x[1])
        return numeric_pairs[0][0], numeric_pairs[-1][0]

    # ----------------------------------------------------------------------
    # Discretionary / eligibility / vesting extraction
    # ----------------------------------------------------------------------
    def extract_discretionary_text(self, text: str) -> Optional[str]:
        """
        Extract all discretionary / nonelective / profit-sharing sentences.
        """
        sentences = self.collect_relevant_sentences(text)
        kept = []

        for sentence in sentences:
            if (
                self.search_any(self.discretionary_keywords, sentence)
                or self.search_any(self.nonelective_keywords, sentence)
                or self.search_any(self.profit_sharing_keywords, sentence)
            ):
                kept.append(sentence)

        if kept:
            return " ; ".join(kept)
        return None

    def extract_eligibility_text(self, text: str) -> Optional[str]:
        """
        Extract all eligibility-related snippets from the text.
        """
        hits = []

        for pattern in self.eligibility_patterns:
            matches = re.findall(pattern, text, flags=re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = " ".join(match)
                match = str(match).strip()
                if match:
                    hits.append(match)

        # Remove duplicates while preserving order
        deduped = []
        seen = set()
        for h in hits:
            if h not in seen:
                deduped.append(h)
                seen.add(h)

        if deduped:
            return " ; ".join(deduped)
        return None

    def extract_discretionary_min_max(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract min/max discretionary contribution values.
        This can be % or $ depending on the paragraph language.
        """
        values = []

        for pct in self.extract_percent_values(text):
            values.append((pct, float(pct.replace("%", "")), "percent"))

        for d in self.extract_dollar_values(text):
            values.append((d, float(d.replace("$", "").replace(",", "").strip()), "dollar"))

        if not values:
            return None, None

        # Prefer not to mix % and $. If both appear, keep textual min/max by numeric value anyway.
        values.sort(key=lambda x: x[1])
        return values[0][0], values[-1][0]

    def extract_vesting_text(self, text: str) -> Optional[str]:
        """Extract vesting-related sentences."""
        sentences = self.collect_relevant_sentences(text)
        kept = [s for s in sentences if self.search_any(self.vesting_keywords, s)]
        if kept:
            return " ; ".join(kept)
        return None

    def extract_other_relevant_info(self, text: str) -> Optional[str]:
        """
        Save other potentially useful ER-related information that does not fit core columns.
        """
        candidates = []

        if self.search_any(self.nonelective_keywords, text):
            candidates.append("nonelective contribution mentioned")

        if self.search_any(self.profit_sharing_keywords, text):
            candidates.append("profit sharing mentioned")

        if self.search_any(self.collective_bargaining_keywords, text):
            candidates.append("collective bargaining mentioned")

        if self.search_any(self.vesting_keywords, text):
            candidates.append("vesting mentioned")

        if candidates:
            return "; ".join(candidates)
        return None

    # ----------------------------------------------------------------------
    # Confidence scoring
    # ----------------------------------------------------------------------
    def estimate_confidence(self, record: Dict[str, Any]) -> str:
        """
        Simple confidence scoring:
        - high: clear signal + useful formula details
        - medium: clear signal but incomplete structure
        - low: vague or almost no signal
        """
        if record["er_match_indicator"] == 1 and (
            record["er_match_formula_text"]
            or record["er_match_rate"]
            or record["er_match_cap"]
            or record["er_match_type"]
        ):
            return "high"

        if (
            record["discretionary_er_contribution_indicator"] == 1
            or record["nonelective_contribution_indicator"] == 1
            or record["profit_sharing_indicator"] == 1
            or record["vesting_indicator"] == 1
        ):
            return "medium"

        return "low"

    # ----------------------------------------------------------------------
    # Main parse function
    # ----------------------------------------------------------------------
    def parse(self, plan_name: str, raw_paragraph: str, source_file: Optional[str] = None) -> Dict[str, Any]:
        """
        Parse one raw ER paragraph block into structured output.
        """
        raw_text = self.normalize_text(raw_paragraph)
        cleaned_text = self.build_cleaned_text(raw_text)

        # If cleaned text becomes empty, fall back to raw text
        working_text = cleaned_text if cleaned_text else raw_text

        no_contribution_flag = self.search_any(self.no_contribution_keywords, working_text)

        er_match_flag = self.search_any(self.match_keywords, working_text) and not no_contribution_flag
        discretionary_flag = self.search_any(self.discretionary_keywords, working_text) and not no_contribution_flag
        nonelective_flag = self.search_any(self.nonelective_keywords, working_text) and not no_contribution_flag
        profit_sharing_flag = self.search_any(self.profit_sharing_keywords, working_text) and not no_contribution_flag
        collective_bargaining_flag = self.search_any(self.collective_bargaining_keywords, working_text)
        vesting_flag = self.search_any(self.vesting_keywords, working_text)

        match_formula_text = self.extract_match_formula_text(working_text) if er_match_flag or nonelective_flag else None
        discretionary_text = self.extract_discretionary_text(working_text) if (
            discretionary_flag or nonelective_flag or profit_sharing_flag
        ) else None

        match_rate, match_cap = self.extract_match_rate_and_cap(working_text) if er_match_flag else (None, None)
        er_match_type = self.infer_match_type(working_text)
        eligibility_text = self.extract_eligibility_text(working_text)

        er_match_min_dollar_value, er_match_max_dollar_value = (
            self.extract_min_max_dollar(match_formula_text if match_formula_text else working_text)
            if er_match_flag
            else (None, None)
        )

        min_discretionary_er_contribution, max_discretionary_er_contribution = (
            self.extract_discretionary_min_max(discretionary_text if discretionary_text else working_text)
            if (discretionary_flag or nonelective_flag or profit_sharing_flag)
            else (None, None)
        )

        discretionary_er_contribution_eligibility = (
            self.extract_eligibility_text(discretionary_text) if discretionary_text else eligibility_text
        )

        vesting_text = self.extract_vesting_text(working_text)

        # Old schema-compatible fields + new fields requested by you
        record = {
            # ------------------------------------------------------------------
            # Original / existing fields
            # ------------------------------------------------------------------
            "plan_name": plan_name,
            "source_file": source_file if source_file is not None else None,
            "raw_paragraph": working_text,
            "er_match_indicator": int(er_match_flag),
            "er_match_formula_text": match_formula_text,
            "er_match_rate": match_rate,
            "er_match_cap": match_cap,
            "er_match_type": er_match_type,
            "discretionary_er_contribution_indicator": int(discretionary_flag),
            "discretionary_er_contribution_text": discretionary_text,
            "nonelective_contribution_indicator": int(nonelective_flag),
            "profit_sharing_indicator": int(profit_sharing_flag),
            "eligibility_text": eligibility_text,
            "collective_bargaining_exception_indicator": int(collective_bargaining_flag),
            "other_relevant_er_info": self.extract_other_relevant_info(working_text),
            "parse_confidence": None,

            # ------------------------------------------------------------------
            # New requested fields
            # ------------------------------------------------------------------
            "er_match_full_indicator": None,
            "er_match_general_indicator": None,
            "er_match_partial_indicator": None,
            "er_match_safe_harbor_indicator": None,
            "er_match_min_dollar_value": er_match_min_dollar_value,
            "er_match_max_dollar_value": er_match_max_dollar_value,
            "min_discretionary_er_contribution": min_discretionary_er_contribution,
            "max_discretionary_er_contribution": max_discretionary_er_contribution,
            "discretionary_er_contribution_eligibility": discretionary_er_contribution_eligibility,
            "vesting_indicator": int(vesting_flag),
            "vesting_text": vesting_text,
        }

        # Fill match subtype indicators
        match_flags = self.infer_match_flags(working_text)
        record.update(match_flags)

        # Confidence score at the end
        record["parse_confidence"] = self.estimate_confidence(record)

        return record


def parse_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Parse an input DataFrame with at least:
        - plan_name
        - raw_paragraph
    Optional:
        - source_file
    """
    required_cols = {"plan_name", "raw_paragraph"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    parser = EmployerContributionParser()
    output_rows = []

    for _, row in df.iterrows():
        parsed = parser.parse(
            plan_name=row["plan_name"],
            raw_paragraph=row["raw_paragraph"],
            source_file=row["source_file"] if "source_file" in df.columns else None,
        )
        output_rows.append(parsed)

    return pd.DataFrame(output_rows)


def main() -> None:
    """
    Command-line entry point.
    """
    arg_parser = argparse.ArgumentParser(
        description="Parse employer contribution paragraphs into structured CSV."
    )
    arg_parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="Path to input CSV file containing plan_name and raw_paragraph columns.",
    )
    arg_parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Path to output CSV file.",
    )

    args = arg_parser.parse_args()

    df = pd.read_csv(args.input)
    parsed_df = parse_dataframe(df)
    parsed_df.to_csv(args.output, index=False)

    print(f"Done. Parsed {len(parsed_df)} rows.")
    print(f"Saved output to: {args.output}")


if __name__ == "__main__":
    main()
