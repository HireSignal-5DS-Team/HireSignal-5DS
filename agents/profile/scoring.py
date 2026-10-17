"""Scores for step 4 against parse_gold (see eval/profile_agent/PARSE_RULES.md)."""

from __future__ import annotations

import re

from .detect import fold


def _k(s) -> str:
    return re.sub(r"[\s\-_.]+", " ", fold(str(s or ""))).strip()


def _prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(p, 3), "recall": round(r, 3),
            "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0}


def score_skills(pred: list[str], gold: list[list[str]], optional: list[str]) -> dict:
    pred_k = {_k(p) for p in pred}
    gold_k = [{_k(a) for a in alts} for alts in gold]
    opt_k = {_k(o) for o in optional}
    tp = sum(1 for alts in gold_k if alts & pred_k)
    known = set().union(*gold_k) | opt_k if gold_k else opt_k
    fp = len([p for p in pred_k if p not in known])
    out = _prf(tp, fp, len(gold_k) - tp)
    out["missed"] = [sorted(a)[0] for a in gold_k if not a & pred_k]
    out["extra"] = sorted(p for p in pred_k if p not in known)
    return out


def _same(a, b) -> bool:
    a, b = _k(a), _k(b)
    return bool(a and b) and (a in b or b in a)


def score_items(pred: list[dict], gold: list[dict], key: str, alt_key: str, fields: list[str]) -> dict:
    """Match each gold item to one predicted item (on key, else alt_key), then check fields."""
    free = list(range(len(pred)))
    pairs = []
    for g in gold:
        hit = next((i for i in free if _same(pred[i].get(key), g.get(key))), None)
        if hit is None:
            hit = next((i for i in free if _same(pred[i].get(alt_key), g.get(alt_key))), None)
        if hit is not None:
            free.remove(hit)
            pairs.append((g, pred[hit]))
    out = _prf(len(pairs), len(free), len(gold) - len(pairs))
    for f in fields:
        right = 0
        for g, p in pairs:
            if f in ("start", "end"):
                right += (p.get(f) or None) == (g.get(f) or None)
            else:
                right += _same(p.get(f), g.get(f)) or (g.get(f) is None and p.get(f) is None)
        out[f"{f}_accuracy"] = round(right / len(pairs), 3) if pairs else None
    out["field_errors"] = [{"gold": g, "got": {f: p.get(f) for f in fields}} for g, p in pairs
                           if any((p.get(f) or None) != (g.get(f) or None) if f in ("start", "end")
                                  else not (_same(p.get(f), g.get(f)) or (g.get(f) is None and p.get(f) is None))
                                  for f in fields)]
    return out


def score_parsed(parsed: dict, gold: dict) -> dict:
    return {
        "skills": score_skills([s["name"] for s in parsed["skills"]], gold["skills"], gold.get("skills_optional", [])),
        "experience": score_items(parsed["experience"], gold["experience"], "company", "title",
                                  ["title", "start", "end"]),
        "education": score_items(parsed["education"], gold["education"], "institution", "degree",
                                 ["degree", "field", "end"]),
    }
