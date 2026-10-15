"""Checks and safe repairs on NuExtract's answer (the agent's guardrails).

The model output is never trusted directly. For each requirement:
  1. evidence  must be found in the job offer      -> repaired to the real text, or dropped
  2. min_years must match a number in the evidence -> corrected, or set to null
  3. kind      must agree with cue words           -> corrected
  4. skill_terms must appear in the evidence       -> unknown terms removed
Every change is recorded as a warning, so nothing is silently altered.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .prompts import CATEGORIES

FUZZY_MIN_RATIO = 0.90  # a quote this close to a real line is a copying slip, not an invention

NICE_CUES = [
    "a plus", "is a plus", "nice to have", "preferred", "preferably", "desirable",
    "would be appreciated", "appreciated", "bonus", "advantage", "an asset", "ideally",
    "un plus", "un atout", "atout", "serait apprecie", "apprecie", "souhaite", "souhaitable",
    "idealement", "de preference", "est un avantage",
]
MUST_CUES = [
    "required", "requirement", "must", "mandatory", "essential", "minimum", "at least",
    "obligatoire", "exige", "indispensable", "requis", "imperatif",
]

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "fifteen": 15,
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
}
_YEARS = re.compile(
    r"(?<![a-z0-9])(\d+(?:[.,]\d+)?|" + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True))
    + r")\s*\+?\s*(?:-\s*\d+\s*)?(?:years?|yrs?|ans|an|annees?)\b",
    re.IGNORECASE,
)


@dataclass
class CheckReport:
    requirements: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    uncertain: list[str] = field(default_factory=list)
    dropped: int = 0
    repaired: int = 0


# ------------------------------------------------------------ text helpers ---

def _fold(text: str) -> str:
    """Lowercase and strip accents: 'Expérience' -> 'experience'."""
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _has_cue(text: str, cues: list[str]) -> bool:
    folded = " " + re.sub(r"[^a-z0-9 ]+", " ", _fold(text)) + " "
    return any(f" {cue} " in folded for cue in cues)


def years_in(text: str) -> list[float]:
    """All numbers of years mentioned: '3+ years' -> [3], 'trois ans' -> [3]."""
    found = []
    for match in _YEARS.finditer(_fold(text)):
        token = match.group(1).replace(",", ".")
        value = float(token) if token[0].isdigit() else float(_NUMBER_WORDS.get(token, 0))
        if value:
            found.append(value)
    return found


def _candidate_lines(post: str) -> list[str]:
    """Lines and sentences of the job offer, as places a quote could come from."""
    pieces = []
    for line in post.splitlines():
        line = line.strip().lstrip("-*•·–").strip()
        if line:
            pieces.append(line)
            pieces += [s.strip() for s in re.split(r"(?<=[.;!?])\s+", line) if s.strip()]
    return pieces


def locate_evidence(quote: str, post: str) -> tuple[str | None, str]:
    """Find the quote in the job offer. Returns (exact text from the offer, how)."""
    quote = quote.strip()
    if not quote:
        return None, "empty"
    if quote in post:
        return quote, "exact"

    # Same words, different spaces/line breaks/case: map back to the real span.
    words = [re.escape(w) for w in quote.split()]
    if words:
        match = re.search(r"\s+".join(words), post, flags=re.IGNORECASE)
        if match:
            return match.group(0), "spacing"

    # A small copying slip ("Experiance", missing final period): closest line.
    best, best_ratio = None, 0.0
    for line in _candidate_lines(post):
        ratio = SequenceMatcher(None, _squash(quote).lower(), line.lower()).ratio()
        if ratio > best_ratio:
            best, best_ratio = line, ratio
    if best is not None and best_ratio >= FUZZY_MIN_RATIO:
        return best, f"fuzzy {best_ratio:.2f}"
    return None, f"not found (closest {best_ratio:.2f})"


# --------------------------------------------------------------- parsing ---

def parse_model_output(raw: str) -> dict:
    """NuExtract should answer pure JSON; tolerate code fences or extra text around it."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("no JSON object in the model answer")
        data = json.loads(raw[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("the model answer is not a JSON object")
    return data


# ---------------------------------------------------------------- checks ---

def check_requirements(items: list, post: str) -> CheckReport:
    """Validate and repair each requirement proposed by the model."""
    report = CheckReport()
    seen: set[tuple[str, str]] = set()

    for index, item in enumerate(items if isinstance(items, list) else [], start=1):
        label = f"item {index}"
        if not isinstance(item, dict):
            report.dropped += 1
            report.warnings.append(f"{label}: not an object, dropped")
            continue

        text = _squash(str(item.get("text") or ""))
        label = f"'{text[:50]}'" if text else label

        # 1. Evidence must come from the job offer.
        evidence, how = locate_evidence(str(item.get("evidence") or ""), post)
        if evidence is None:
            report.dropped += 1
            report.warnings.append(f"{label}: quote {how} in the job offer, dropped as invented")
            continue
        if how != "exact":
            report.repaired += 1
            report.warnings.append(f"{label}: quote repaired ({how})")
        if not text:
            text = _squash(evidence)

        # 2. Kind must agree with the wording.
        kind = item.get("kind") if item.get("kind") in ("must", "nice") else None
        nice, must = _has_cue(evidence, NICE_CUES), _has_cue(evidence, MUST_CUES)
        if nice and not must and kind != "nice":
            report.repaired += 1
            report.warnings.append(f"{label}: kind '{kind}' -> 'nice' (wording says optional)")
            kind = "nice"
        elif must and not nice and kind != "must":
            report.repaired += 1
            report.warnings.append(f"{label}: kind '{kind}' -> 'must' (wording says required)")
            kind = "must"
        elif nice and must:
            report.uncertain.append(f"{label}: wording is both required and optional")
        if kind is None:
            kind = "must"
            report.warnings.append(f"{label}: no valid kind, defaulted to 'must'")

        # 3. Category must be a known value.
        category = item.get("category")
        if category not in CATEGORIES:
            report.warnings.append(f"{label}: unknown category '{category}', set to 'other'")
            category = "other"

        # 4. Years must match the quote.
        stated = years_in(evidence)
        min_years = item.get("min_years")
        try:
            min_years = float(min_years) if min_years not in (None, "") else None
        except (TypeError, ValueError):
            min_years = None
        if stated:
            if min_years not in stated:
                report.repaired += 1
                report.warnings.append(f"{label}: min_years {min_years} -> {min(stated)} (from the quote)")
                min_years = min(stated)
        elif min_years is not None:
            report.repaired += 1
            report.warnings.append(f"{label}: min_years {min_years} removed (no years in the quote)")
            min_years = None
        if min_years is not None and float(min_years).is_integer():
            min_years = int(min_years)

        # 5. Skill terms must appear in the quote.
        terms = []
        for term in item.get("skill_terms") or []:
            term = _squash(str(term))
            if term and _fold(term) in _fold(evidence) and term not in terms:
                terms.append(term)
            elif term:
                report.warnings.append(f"{label}: skill term '{term}' not in the quote, removed")

        key = (_fold(text), _fold(evidence))
        if key in seen:
            report.warnings.append(f"{label}: duplicate, dropped")
            continue
        seen.add(key)

        report.requirements.append({
            "text": text, "evidence": evidence, "kind": kind, "category": category,
            "skill_terms": terms, "min_years": min_years, "chunk_ids": [],
        })
    return report


def detect_language(text: str) -> str:
    """Rough guess from common words: 'en', 'fr' or 'other'."""
    words = re.findall(r"[a-zà-ÿ']+", text.lower())
    if not words:
        return "other"
    fr = sum(w in {"le", "la", "les", "des", "et", "en", "de", "du", "une", "pour", "avec", "nous", "vous"}
             for w in words)
    en = sum(w in {"the", "and", "of", "to", "with", "for", "you", "we", "in", "a", "is", "are", "our"}
             for w in words)
    if max(fr, en) < 3:
        return "other"
    return "fr" if fr > en else "en"
