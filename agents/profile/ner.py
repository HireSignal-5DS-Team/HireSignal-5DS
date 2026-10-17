"""Optional NER detectors for the Profile Agent (CPU, loaded once, on first use).

- ResumeNER : oksomu/resume-ner (65M, English CVs) through `transformers`.
- GlinerPII : urchade/gliner_multi_pii-v1 (multilingual, EN + FR) through `gliner`.

Both return `Span`s on the original text, like the rule detectors. They catch what
rules miss: names outside the header (e.g. a referee "Dr. Leila Haddad"), addresses
without a label. If the library or the model is missing, the detector says so in
`self.error` and returns nothing: the rules still run, and the agent flags the CV.

Install on the laptop (CPU is enough, no GPU needed):
    pip install -r requirements-profile.txt
The models download from Hugging Face on the first run (~260 MB and ~1.2 GB).
"""

from __future__ import annotations

import os
import re

from .detect import Span

# NER label word -> our kind, so B-NAME / PERSON / "phone number" / "date of birth" all work.
LABEL_MAP = [
    ({"email", "mail"}, "EMAIL"),
    ({"phone", "mobile", "tel", "telephone"}, "PHONE"),
    ({"url", "link", "linkedin", "github", "social", "handle"}, "URL"),
    ({"birth", "dob"}, "DOB"),
    ({"address", "postal", "location", "loc"}, "ADDRESS"),
    ({"name", "person", "per"}, "NAME"),
]
# labels that are CV facts, not identity ("College Name", "Companies worked at", "Years of Experience")
NOT_IDENTITY = {"college", "university", "school", "company", "companies", "organization", "organisation",
                "org", "degree", "skill", "skills", "designation", "experience", "graduation", "job", "title"}


def map_label(label: str) -> str | None:
    low = label.lower()
    low = low[2:] if re.match(r"^[bies]-", low) else low
    words = set(re.findall(r"[a-z]+", low))
    if words & NOT_IDENTITY:
        return None
    for keys, kind in LABEL_MAP:
        if words & keys:
            return kind
    return None


def chunks(text: str, size: int = 1200) -> list[tuple[int, str]]:
    """Split on line ends into pieces of ~size characters: [(offset, piece), ...]."""
    out, start = [], 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            cut = text.rfind("\n", start + size // 2, end)
            end = cut + 1 if cut > 0 else end
        out.append((start, text[start:end]))
        start = end
    return out


class _Detector:
    name = "ner"
    # Only names and places come from the models: emails, phones and links are found more
    # cleanly by the rules (resume-ner writes "x. y @ gmail. com"). Places are only trusted
    # in the header / contact block (anonymise.py), elsewhere they are CV facts ("IHEC Carthage").
    KINDS = {"NAME", "ADDRESS"}

    def __init__(self, threshold: float):
        self.threshold = threshold
        self.error: str | None = None
        self._model = None

    def _load(self):
        raise NotImplementedError

    def _predict(self, piece: str) -> list[tuple[int, int, str, float]]:
        raise NotImplementedError

    def __call__(self, text: str) -> list[Span]:
        if self._model is None and self.error is None:
            try:
                self._model = self._load()
            except Exception as exc:  # missing library, no internet, wrong model name ...
                self.error = f"{self.name} not available: {type(exc).__name__}: {exc}"
        if self._model is None:
            return []
        out = []
        for offset, piece in chunks(text):
            for s, e, label, score in self._predict(piece):
                kind = map_label(label)
                if kind not in self.KINDS or score < self.threshold:
                    continue
                s, e = _trim(piece, s, e)
                if _usable(piece, s, e):
                    out.append(Span(offset + s, offset + e, kind, piece[s:e], self.name, round(float(score), 3)))
        return out


def _usable(piece: str, s: int, e: int) -> bool:
    """Drop word pieces ('##s'), tiny spans and spans that cut a word in half ('Analy|s|te')."""
    if e <= s or sum(c.isalpha() for c in piece[s:e]) < 3:
        return False
    if s > 0 and piece[s - 1].isalnum() or e < len(piece) and piece[e].isalnum():
        return False
    return "##" not in piece[s:e]


def _trim(piece: str, s: int, e: int) -> tuple[int, int]:
    while s < e and not piece[s].isalnum() and piece[s] not in "+@(":
        s += 1
    while e > s and not piece[e - 1].isalnum():
        e -= 1
    return s, e


class ResumeNER(_Detector):
    name = "resume-ner"

    def __init__(self, model: str | None = None, threshold: float = 0.6):
        super().__init__(threshold)
        self.model_name = model or os.environ.get("HS_RESUME_NER_MODEL", "oksomu/resume-ner")

    def _load(self):
        from transformers import pipeline
        return pipeline("token-classification", model=self.model_name, aggregation_strategy="simple", device=-1)

    def _predict(self, piece):
        return [(r["start"], r["end"], r.get("entity_group") or r.get("entity", ""), r["score"])
                for r in self._model(piece)]


class GlinerPII(_Detector):
    name = "gliner"
    LABELS = ["person", "email", "phone number", "address", "postal code", "date of birth", "social media handle"]

    def __init__(self, model: str | None = None, threshold: float = 0.5):
        super().__init__(threshold)
        self.model_name = model or os.environ.get("HS_GLINER_MODEL", "urchade/gliner_multi_pii-v1")

    def _load(self):
        from gliner import GLiNER
        return GLiNER.from_pretrained(self.model_name)

    def _predict(self, piece):
        return [(r["start"], r["end"], r["label"], r["score"])
                for r in self._model.predict_entities(piece, self.LABELS, threshold=self.threshold)]


def make_detectors(names: list[str]) -> list[_Detector]:
    """'resume-ner', 'gliner' -> detector objects (unknown names are refused)."""
    table = {"resume-ner": ResumeNER, "gliner": GlinerPII}
    bad = [n for n in names if n not in table]
    if bad:
        raise ValueError(f"unknown NER detector(s) {bad}; choose from {sorted(table)}")
    return [table[n]() for n in names]
