import re
import argparse
from typing import Dict, Any, Optional, List

import pandas as pd


class EmployerContributionParser:
    """
    Rule-based parser for employer contribution paragraphs extracted from Form 5500 PDFs.

    Input:
        raw paragraph text related to employer contribution
    Output:
        structured dictionary with fixed schema
    """

    def __init__(self) -> None:
        # Core keyword groups
        self.match_keywords = [
            r"\bmatch\b",
            r"\bmatches\b",
            r"\bmatching contribution\b",
            r"\bmatching contributions\b",
            r"\bsafe harbor matching\b",
            r"\bsafe harbor match\b",
            r"\bdollar[- ]for[- ]dollar\b",
        ]

        self.discretionary_keywords = [
            r"\bdiscretionary contribution\b",
            r"\bdiscretionary contributions\b",
            r"\bmay contribute\b",
            r"\bmay make contributions\b",
            r"\bemployer may contribute\b",
            r"\bemployer may make\b",
            r"\bas determined by the board\b",
            r"\bat the discretion of\b",
        ]

        self.nonelective_keywords = [
            r"\bnonelective contribution\b",
            r"\bnonelective contributions\b",
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
        ]

        self.collective_bargaining_keywords = [
            r"\bcollective bargaining\b",
            r"\bunion employees?\b",
            r"\bcovered by a collective bargaining agreement\b",
        ]

        # Eligibility patterns
        self.eligibility_patterns = [
            r"eligible after [^.]+",
            r"eligibility [^.]+",
            r"employees are eligible [^.]+",
            r"become eligible [^.]+",
            r"after one year of service",
            r"after 1 year of service",
            r"immediate(?:ly)? eligible",
            r"eligible immediately",
        ]

        # Match rate patterns
        self.match_rate_patterns = [
            r"(\d{1,3}(?:\.\d+)?%)\s+(?:of\s+)?(?:employee\s+)?(?:deferrals|contributions|elective deferrals)",
            r"matches?\s+(\d{1,3}(?:\.\d+)?%)",
            r"(\d{1,3}(?:\.\d+)?%)\s+match",
            r"dollar[- ]for[- ]dollar",
            r"100%\s+match",
        ]

        # Match cap patterns
        self.match_cap_patterns = [
            r"up to\s+(\d{1,3}(?:\.\d+)?%\s+of\s+(?:compensation|pay|salary))",
            r"up to\s+(\d{1,3}(?:\.\d+)?%)",
            r"first\s+(\d{1,3}(?:\.\d+)?%\s+of\s+(?:compensation|pay|salary))",
            r"first\s+(\d{1,3}(?:\.\d+)?%)",
            r"not in excess of\s+(\d{1,3}(?:\.\d+)?%)",
        ]

    @staticmethod
    def normalize_text(text: str) -> str:
        """Clean and normalize raw paragraph text."""
        if pd.isna(text):
            return ""

        text = str(text)
        text = text.replace("\n", " ")
        text = text.replace("\r", " ")
        text = re.sub(r"\s+", " ", text)
        text = text.strip()
        return text

    @staticmethod
    def search_any(patterns: List[str], text: str) -> bool:
        """Return True if any regex pattern matches."""
        for pattern in patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                return True
        return False

    @staticmethod
    def first_match(patterns: List[str], text: str) -> Optional[str]:
        """Return first matched string or captured group from a list of patterns."""
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                if match.lastindex:
                    return match.group(1).strip()
                return match.group(0).strip()
        return None

    def extract_match_formula_text(self, text: str) -> Optional[str]:
        """
        Extract a sentence-like snippet containing match language.
        Very simple baseline: split by punctuation and return the first sentence
        mentioning match-related keywords.
        """
        sentences = re.split(r"(?<=[.;])\s+", text)
        for sentence in sentences:
            if self.search_any(self.match_keywords, sentence):
                return sentence.strip()
        return None

    def extract_discretionary_text(self, text: str) -> Optional[str]:
        """Extract first sentence mentioning discretionary / nonelective / profit-sharing language."""
        sentences = re.split(r"(?<=[.;])\s+", text)
        for sentence in sentences:
            if (
                self.search_any(self.discretionary_keywords, sentence)
                or self.search_any(self.nonelective_keywords, sentence)
                or self.search_any(self.profit_sharing_keywords, sentence)
            ):
                return sentence.strip()
        return None

    def extract_eligibility_text(self, text: str) -> Optional[str]:
        """Extract eligibility-related text snippet."""
        for pattern in self.eligibility_patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(0).strip()
        return None

    def infer_match_type(self, text: str) -> Optional[str]:
        """Infer a rough match type from paragraph text."""
        lower_text = text.lower()

        if "safe harbor" in lower_text and "match" in lower_text:
            return "safe_harbor_match"
        if re.search(r"dollar[- ]for[- ]dollar", lower_text):
            return "dollar_for_dollar"
        if re.search(r"50%\s+match|matches?\s+50%", lower_text):
            return "partial_match"
        if re.search(r"100%\s+match|matches?\s+100%", lower_text):
            return "full_match"
        if "match" in lower_text or "matches" in lower_text:
            return "general_match"

        return None

    def extract_other_relevant_info(self, text: str) -> Optional[str]:
        """
        Save other potentially useful ER-related information that does not fit core columns.
        """
        candidates = []

        if "vesting" in text.lower():
            candidates.append("vesting mentioned")
        if "safe harbor" in text.lower() and "match" not in text.lower():
            candidates.append("safe harbor mentioned")
        if self.search_any(self.collective_bargaining_keywords, text):
            candidates.append("collective bargaining mentioned")

        if candidates:
            return "; ".join(candidates)
        return None

    def estimate_confidence(self, record: Dict[str, Any]) -> str:
        """
        Simple confidence scoring:
        - high: clear signal + concrete formula/rate/cap
        - medium: clear signal but incomplete detail
        - low: vague contribution language only
        """
        if record["er_match_indicator"] == 1 and (
            record["er_match_formula_text"] or record["er_match_rate"] or record["er_match_cap"]
        ):
            return "high"

        if (
            record["discretionary_er_contribution_indicator"] == 1
            or record["nonelective_contribution_indicator"] == 1
            or record["profit_sharing_indicator"] == 1
        ):
            if record["discretionary_er_contribution_text"]:
                return "medium"

        if (
            record["er_match_indicator"] == 0
            and record["discretionary_er_contribution_indicator"] == 0
            and record["nonelective_contribution_indicator"] == 0
            and record["profit_sharing_indicator"] == 0
        ):
            return "low"

        return "medium"

    def parse(self, plan_name: str, raw_paragraph: str, source_file: Optional[str] = None) -> Dict[str, Any]:
        """Parse one plan paragraph into structured schema."""
        text = self.normalize_text(raw_paragraph)

        no_contribution_flag = self.search_any(self.no_contribution_keywords, text)
        er_match_flag = self.search_any(self.match_keywords, text) and not no_contribution_flag
        discretionary_flag = self.search_any(self.discretionary_keywords, text) and not no_contribution_flag
        nonelective_flag = self.search_any(self.nonelective_keywords, text) and not no_contribution_flag
        profit_sharing_flag = self.search_any(self.profit_sharing_keywords, text) and not no_contribution_flag
        collective_bargaining_flag = self.search_any(self.collective_bargaining_keywords, text)

        match_formula_text = self.extract_match_formula_text(text) if er_match_flag else None
        discretionary_text = self.extract_discretionary_text(text) if (
            discretionary_flag or nonelective_flag or profit_sharing_flag
        ) else None

        match_rate = self.first_match(self.match_rate_patterns, text) if er_match_flag else None
        match_cap = self.first_match(self.match_cap_patterns, text) if er_match_flag else None
        eligibility_text = self.extract_eligibility_text(text)
        er_match_type = self.infer_match_type(text)

        record = {
            "plan_name": plan_name,
            "source_file": source_file if source_file is not None else None,
            "raw_paragraph": text,
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
            "other_relevant_er_info": self.extract_other_relevant_info(text),
            "parse_confidence": None,
        }

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
    arg_parser = argparse.ArgumentParser(description="Parse employer contribution paragraphs into structured CSV.")
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