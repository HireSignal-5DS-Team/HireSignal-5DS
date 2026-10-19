# Adapted from team V2: agents/job/scoring.py (feature/agent-integration @ a5a03ff)
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


# ------------------------------------------------- two-level scoring ---
# The strict score above needs the right sentence AND a shared skill name. The model
# often finds the right sentence but leaves skill_terms empty, so one miss is counted
# twice (an extra AND a missed requirement). The two questions are scored separately:
#   1. sentences: was each requirement SENTENCE of the offer found?   (one-to-one on unique quotes)
#   2. skills:    on the sentences found, were the skill names right? (term level)


@dataclass
class TermScore:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def add(self, other: "TermScore") -> "TermScore":
        self.tp, self.fp, self.fn = self.tp + other.tp, self.fp + other.fp, self.fn + other.fn
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


def _by_evidence(reqs: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for r in reqs:
        groups.setdefault(r["evidence"], []).append(r)
    return groups


def score_sentences(pred_reqs: list[dict], gold_reqs: list[dict]) -> tuple[Score, list[tuple[str, str]]]:
    """Requirement SENTENCES found, ignoring skill names. Returns the score and matched (pred, gold) quotes."""
    pred_q, gold_q = list(_by_evidence(pred_reqs)), list(_by_evidence(gold_reqs))
    candidates = sorted(((_ratio(p, g), i, j) for i, p in enumerate(pred_q) for j, g in enumerate(gold_q)
                         if _evidence_overlap(p, g)), reverse=True)
    used_p, used_g, pairs = set(), set(), []
    for _, i, j in candidates:
        if i not in used_p and j not in used_g:
            used_p.add(i)
            used_g.add(j)
            pairs.append((pred_q[i], gold_q[j]))

    pred_g, gold_g = _by_evidence(pred_reqs), _by_evidence(gold_reqs)
    score = Score(tp=len(pairs), fp=len(pred_q) - len(pairs), fn=len(gold_q) - len(pairs))
    for p, g in pairs:  # attributes compared on the first requirement of each sentence
        pr, gr = pred_g[p][0], gold_g[g][0]
        score.kind_ok += pr["kind"] == gr["kind"]
        score.category_ok += pr["category"] == gr["category"]
        score.years_ok += _same_years(pr["min_years"], gr["min_years"])
    score.unmatched_pred = [q for k, q in enumerate(pred_q) if k not in used_p]
    score.unmatched_gold = [q for k, q in enumerate(gold_q) if k not in used_g]
    return score, pairs


def score_skill_terms(pred_reqs: list[dict], gold_reqs: list[dict],
                      pairs: list[tuple[str, str]]) -> TermScore:
    """On the sentences found: were the skill names right? (all terms of a sentence together)"""
    pred_g, gold_g = _by_evidence(pred_reqs), _by_evidence(gold_reqs)
    total = TermScore()
    for p, g in pairs:
        pt = {_norm(t) for r in pred_g[p] for t in r["skill_terms"]}
        gt = {_norm(t) for r in gold_g[g] for t in r["skill_terms"]}
        tp = len(pt & gt)
        total.add(TermScore(tp=tp, fp=len(pt) - tp, fn=len(gt) - tp))
    return total
