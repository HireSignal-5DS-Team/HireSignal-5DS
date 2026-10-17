"""Text cleaning helpers shared by every input route (PDF, DOCX, OCR)."""

import re
import unicodedata

# Ligatures and odd characters that PDF exporters and OCR often produce.
_REPLACEMENTS = {
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
    "’": "'", "‘": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "•": "-", "●": "-", "▪": "-",
    " ": " ", "​": "", "﻿": "",
}


def clean_text(text: str) -> str:
    """Normalise unicode, fix ligatures, rejoin hyphenated words, tidy spaces.

    Line breaks are kept on purpose: the section splitter needs them.
    """
    text = unicodedata.normalize("NFKC", text)
    for bad, good in _REPLACEMENTS.items():
        text = text.replace(bad, good)

    # "develop-\nment" -> "development" (only when a lowercase letter follows)
    text = re.sub(r"(\w)-\n(?=[a-zà-ÿ])", r"\1", text)

    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    # Drop lines with no letter or digit (OCR noise like ";", "° :", "|").
    lines = [line if re.search(r"\w", line) else "" for line in lines]

    # Collapse runs of empty lines to a single empty line.
    cleaned, blank = [], False
    for line in lines:
        if line:
            cleaned.append(line)
            blank = False
        elif not blank:
            cleaned.append("")
            blank = True
    return "\n".join(cleaned).strip()
