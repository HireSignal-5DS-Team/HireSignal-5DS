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
    + r")\s*(?:\(\s*\d+\s*\)\s*)?\+?\s*(?:-\s*\d+\s*)?(?:full\s+|complete\s+|pleine\s+)?(years?|yrs?|ans|an|annees?|months?|mois|weeks?|semaines?)\b",
    re.IGNORECASE,
)
_PER_YEAR = {"month": 12, "months": 12, "mois": 12, "week": 52, "weeks": 52, "semaine": 52, "semaines": 52}


@dataclass
class CheckReport:
    requirements: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    uncertain: list[str] = field(default_factory=list)
    dropped: int = 0
    repaired: int = 0
    split: int = 0  # compound items turned into one requirement per skill


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
    """All durations mentioned, in years: '3+ years' -> [3], 'trois ans' -> [3], '52 weeks' -> [1]."""
    found = []
    for match in _YEARS.finditer(_fold(text)):
        token = match.group(1).replace(",", ".")
        value = float(token) if token[0].isdigit() else float(_NUMBER_WORDS.get(token, 0))
        value = round(value / _PER_YEAR.get(match.group(2).lower(), 1), 2)  # "52 weeks" -> 1.0
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

    # The quote wraps a real line with extra words, e.g. a heading glued on:
    # "Nice to have: Experience with Docker ..." -> keep the real line only.
    squashed_quote = _squash(quote).lower()
    contained = [line for line in _candidate_lines(post)
                 if len(line) >= 15 and _squash(line).lower() in squashed_quote]
    if contained:
        return max(contained, key=len), "contained"

    # A small copying slip ("Experiance", missing final period): closest line.
    best, best_ratio = None, 0.0
    for line in _candidate_lines(post):
        ratio = SequenceMatcher(None, _squash(quote).lower(), line.lower()).ratio()
        if ratio > best_ratio:
            best, best_ratio = line, ratio
    if best is not None and best_ratio >= FUZZY_MIN_RATIO:
        return best, f"fuzzy {best_ratio:.2f}"
    return None, f"not found (closest {best_ratio:.2f})"


_CATEGORY_RULES = [
    ("certification", r"\b(certifi\w*|certificate|license|licence)\b"),
    ("education", r"\b(degree|bachelor\w*|master\w*|ph\.?d|doctora\w*|diplom\w*|licence|ingenieur|"
                  r"semester hours|coursework|graduate|baccalaureate)\b"),
    ("language", r"\b(english|french|arabic|german|spanish|anglais|francais|arabe|allemand|espagnol|"
                 r"fluent|bilingual|bilingue)\b"),
    ("experience", r"\b(experience|experiences|years?|ans|annees?)\b"),
]


def infer_category(evidence: str) -> str:
    """Category from the wording, for when the model answers a value outside the list."""
    folded = _fold(evidence)
    for category, pattern in _CATEGORY_RULES:
        if re.search(pattern, folded):
            return category
    return "skill"


# --------------------------------------------------------------- parsing ---

def salvage_cut_json(raw: str) -> tuple[dict, int] | None:
    """Recover the complete requirements of an answer that was cut off mid-way.

    '{"requirements": [{...}, {...}, {"evidence": "half a sent' -> the first two items.
    Returns (data, number of items kept) or None.
    """
    start = raw.find("{")
    if start == -1:
        return None
    body = raw[start:]
    cut = len(body)
    while True:
        cut = body.rfind("}", 0, cut)
        if cut == -1:
            return None
        for closing in ("]}", "]}}"):
            try:
                data = json.loads(body[:cut + 1] + closing)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and isinstance(data.get("requirements"), list):
                return data, len(data["requirements"])


def parse_model_output(raw: str) -> dict:
    """NuExtract should answer pure JSON; tolerate code fences or extra text around it."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        try:
            if start == -1 or end <= start:
                raise ValueError("no JSON object in the model answer")
            data = json.loads(raw[start:end + 1])
        except (ValueError, json.JSONDecodeError):
            saved = salvage_cut_json(raw)
            if saved is None or saved[1] == 0:
                raise ValueError("no JSON object in the model answer") from None
            data = saved[0]
            data["_salvaged"] = saved[1]
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
        raw_quote = str(item.get("evidence") or "")
        evidence, how = locate_evidence(raw_quote, post)
        if evidence is None:
            report.dropped += 1
            report.warnings.append(f"{label}: quote {how} in the job offer, dropped as invented "
                                   f"(model quoted: \"{_squash(raw_quote)[:100]}\")")
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
            guessed = infer_category(evidence)
            report.warnings.append(f"{label}: unknown category '{category}', inferred '{guessed}'")
            category = guessed

        # 4. Years must match the quote.
        stated = years_in(evidence)
        min_years = item.get("min_years")
        try:
            min_years = float(min_years) if min_years not in (None, "") else None
        except (TypeError, ValueError):
            min_years = None
        if stated and min_years is None and category != "experience":
            pass  # "degree completed within the last two years" is a deadline, not experience
        elif stated:
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

        base = {"text": text, "evidence": evidence, "kind": kind, "category": category,
                "skill_terms": terms, "min_years": min_years, "chunk_ids": []}
        parts = split_compound(base)
        if len(parts) > 1:
            report.split += 1

        for part in parts:
            key = (_fold(part["text"]), _fold(part["evidence"]))
            if key in seen:
                report.warnings.append(f"'{part['text'][:50]}': duplicate, dropped")
                continue
            seen.add(key)
            report.requirements.append(part)
    return report


# --------------------------------------------------- compound requirements ---

_ALTERNATIVE = re.compile(r"\b(or|ou|either|soit)\b|/")
# A list introduced by these words gives EXAMPLES, so any one of them is enough:
# "ETL tools such as Pentaho, AWS Glue and Airflow" is one requirement, not four.
_EXAMPLE_MARKER = re.compile(
    r"(?:\b(?:such as|including|to include|like|for example|for instance|"
    r"notamment|tels? que|telles? que|comme|par exemple)\b|\be\.?g\.?)[\s:,(]*$"
)
_EXAMPLE_IN_GAP = re.compile(
    r"\b(such as|including|to include|like|for example|for instance|notamment|tels? que|telles? que|"
    r"par exemple)\b|\be\.?g\.?"
)
_NO_SPLIT_CATEGORIES = {"education", "other"}
_CLAUSE_BREAK = re.compile(r"[;\n]|\.\s")


def _split_by_clause(req: dict) -> list[dict]:
    """Two requirements share one line: give each skill its own clause.

    "Fluent French; good written English." -> "Fluent French" + "good written English"
    (not "Fluent English"). Each clause keeps its own years and must/nice wording.
    """
    clauses = [c.strip().rstrip(".;:,").strip()
               for c in re.split(r"[;\n]|(?<=\.)\s+", req["evidence"])]
    clauses = [c for c in clauses if c]
    groups: dict[str, list[str]] = {}
    for term in req["skill_terms"]:
        home = next((c for c in clauses if term.lower() in c.lower()), None)
        if home is None:
            return [req]  # cannot place a term: keep the line whole rather than guess
        groups.setdefault(home, []).append(term)

    parts = []
    for clause, terms in groups.items():
        years = years_in(clause)
        kind = req["kind"]
        if _has_cue(clause, NICE_CUES) and not _has_cue(clause, MUST_CUES):
            kind = "nice"
        elif _has_cue(clause, MUST_CUES) and not _has_cue(clause, NICE_CUES):
            kind = "must"
        sub = {**req, "text": clause, "evidence": clause, "skill_terms": terms, "kind": kind,
               "min_years": (int(min(years)) if min(years).is_integer() else min(years)) if years else None}
        parts += split_compound(sub) if len(terms) > 1 else [sub]
    return parts


def _term_positions(evidence: str, terms: list[str]) -> list[tuple[int, int]] | None:
    """(start, end) of each term in the evidence, if they appear in this order."""
    low, pos, found = evidence.lower(), 0, []
    for term in terms:
        start = low.find(term.lower(), pos)
        if start == -1:
            return None
        found.append((start, start + len(term)))
        pos = start + len(term)
    return found


# Words BETWEEN two terms that mean "the second one is a detail of the first":
# "git (particularly GitLab)" is one requirement.
_ELABORATION = re.compile(r"\(|\b(particularly|especially|notably|in particular|surtout|en particulier)\b")


def split_compound(req: dict) -> list[dict]:
    """One requirement per skill when skills are joined by 'and' / 'et' / commas.

    "3 years with Java and Spring Boot" -> "3 years with Java", "3 years with Spring Boot"
    "PostgreSQL or Oracle" stays ONE requirement: either skill satisfies it.
    """
    terms = req["skill_terms"]
    if len(terms) < 2 or req["category"] in _NO_SPLIT_CATEGORIES:
        return [req]

    ev = req["evidence"]
    positions = _term_positions(ev, terms)
    span = (positions[0][0], positions[-1][1]) if positions else None
    # Only the words BETWEEN the terms decide (the "/" inside "CI/CD" must not count).
    gaps = [_fold(ev[a[1]:b[0]]) for a, b in zip(positions, positions[1:])] if positions else []
    if any(_CLAUSE_BREAK.search(g) for g in gaps):
        return _split_by_clause(req)  # "Fluent French; good written English."
    if any(_ALTERNATIVE.search(g) for g in gaps):
        return [req]  # alternatives: any one of them is enough
    if any(_ELABORATION.search(g) for g in gaps):
        return [req]  # "git (particularly GitLab)": one requirement
    if any(_EXAMPLE_IN_GAP.search(g) for g in gaps):
        return [req]  # "data science, such as deep learning and LLMs": examples of the first term
    if span and _EXAMPLE_MARKER.search(_fold(ev[:span[0]])):
        return [req]  # "such as A, B and C": examples, any one is enough

    parts = []
    for term in terms:
        if span:
            ev = req["evidence"]
            text = (ev[:span[0]] + term + ev[span[1]:]).strip().rstrip(".;:,")
        else:
            text = f"{req['text']} ({term})"
        parts.append({**req, "text": _squash(text), "skill_terms": [term]})
    return parts


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
