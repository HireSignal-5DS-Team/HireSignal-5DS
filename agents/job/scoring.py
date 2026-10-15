"""Compare a predicted requirements card with a gold card (Job Agent evaluation).

A predicted requirement matches a gold one when
  - their quotes overlap: one contains the other, or they are >= 60% similar, AND
  - they share a skill term (when the gold item has terms), or their texts are similar.
Matching is one-to-one, best pairs first.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

EVIDENCE_MIN_RATIO = 0.60
TEXT_MIN_RATIO = 0.50


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = text.replace("‑", "-")  # non-breaking hyphen used by some offers
    return re.sub(r"[^a-z0-9+#/.\- ]+", " ", re.sub(r"\s+", " ", text)).strip()


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _evidence_overlap(pred: str, gold: str) -> bool:
    p, g = _norm(pred), _norm(gold)
    return bool(p and g) and (p in g or g in p or _ratio(pred, gold) >= EVIDENCE_MIN_RATIO)


def _terms_ok(pred: dict, gold: dict) -> bool:
    gold_terms = {_norm(t) for t in gold["skill_terms"]}
    pred_terms = {_norm(t) for t in pred["skill_terms"]}
    if gold_terms:
        return bool(gold_terms & pred_terms) or any(
            g in p or p in g for g in gold_terms for p in pred_terms if len(p) > 2 and len(g) > 2)
    return _ratio(pred["text"], gold["text"]) >= TEXT_MIN_RATIO or _norm(gold["text"]) in _norm(pred["evidence"])


@dataclass
class Score:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    kind_ok: int = 0
    category_ok: int = 0
    years_ok: int = 0
    pairs: list[tuple[str, str]] = field(default_factory=list)       # (pred req_id, gold req_id)
    unmatched_pred: list[str] = field(default_factory=list)
    unmatched_gold: list[str] = field(default_factory=list)

    def add(self, other: "Score") -> "Score":
        for name in ("tp", "fp", "fn", "kind_ok", "category_ok", "years_ok"):
            setattr(self, name, getattr(self, name) + getattr(other, name))
        return self

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    def accuracy(self, name: str) -> float:
        return getattr(self, name) / self.tp if self.tp else 0.0


def _same_years(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) < 1e-6


def score_card(pred_reqs: list[dict], gold_reqs: list[dict]) -> Score:
    """Match predicted requirements to gold ones and count."""
    candidates = []
    for p in pred_reqs:
        for g in gold_reqs:
            if _evidence_overlap(p["evidence"], g["evidence"]) and _terms_ok(p, g):
                candidates.append((_ratio(p["text"], g["text"]) + _ratio(p["evidence"], g["evidence"]),
                                   p["req_id"], g["req_id"]))
    candidates.sort(reverse=True)

    used_p, used_g, score = set(), set(), Score()
    by_p = {p["req_id"]: p for p in pred_reqs}
    by_g = {g["req_id"]: g for g in gold_reqs}
    for _, pid, gid in candidates:
        if pid in used_p or gid in used_g:
            continue
        used_p.add(pid)
        used_g.add(gid)
        p, g = by_p[pid], by_g[gid]
        score.tp += 1
        score.kind_ok += p["kind"] == g["kind"]
        score.category_ok += p["category"] == g["category"]
        score.years_ok += _same_years(p["min_years"], g["min_years"])
        score.pairs.append((pid, gid))

    score.unmatched_pred = [p["req_id"] for p in pred_reqs if p["req_id"] not in used_p]
    score.unmatched_gold = [g["req_id"] for g in gold_reqs if g["req_id"] not in used_g]
    score.fp, score.fn = len(score.unmatched_pred), len(score.unmatched_gold)
    return score
