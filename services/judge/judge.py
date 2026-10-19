# Adapted from team V2: matcher/judge.py (feature/agent-integration @ a5a03ff)
"""NLI Judge (station 6): does the CV evidence semantically support the Matcher decision? It never changes the decision.

| Matcher decision          | premise                              | supports the decision      | opposes it                |
|---------------------------|--------------------------------------|----------------------------|---------------------------|
| MET (supported)           | verified quotes, widened to CV line  | entailment                 | contradiction or neutral  |
| MISSING (contradicted)    | verified quotes, widened to CV line  | contradiction              | entailment                |
| MISSING (not_documented)  | the whole CV, in chunks (max entail) | not entailment             | entailment                |
| UNCERTAIN                 | -                                    | NOT_APPLICABLE (review is the Matcher's / gate's job)        |

Verdict: FAIL when s(opposing) >= tau_fail and > s(supporting); PASS when s(supporting) >= tau_pass; else UNCERTAIN.
Review reasons: FAIL -> `judge:disagrees`, UNCERTAIN -> `judge:uncertain`. Scores are NLI softmax outputs, NOT
probabilities that the Matcher is right. Premises are CV text only: the Judge never receives RAG knowledge.
Changes vs V2: plain dicts (our /match output) instead of V2 pydantic results; review reasons as strings; validator
numeric reasons are recorded as notes only (they already are review reasons of /match); probabilities and verdicts are
separate steps so thresholds can be chosen offline on dev.
"""
import re
from pathlib import Path

from services.matcher.validate import find_span

LABELS = ("entailment", "neutral", "contradiction")
PREMISE_POLICY = "cv-only: verified quotes in CV line context (V2 QA-017, QA-030), whole CV chunked (V2 QA-018)"
SCORE_NOTE = "softmax NLI class scores; not probabilities that the Matcher decision is correct"
VALIDATOR_NUMERIC = ("years_below_minimum_in_evidence", "duration_not_in_evidence", "contradiction_refuted_by_evidence")
REVIEW = {"FAIL": "judge:disagrees", "UNCERTAIN": "judge:uncertain"}


HYPOTHESES = {
    # V2 v1: "meets this job requirement" frame
    "v1": lambda req: f"The candidate meets this job requirement: {req['text']}"
                      + (f" (at least {req['min_years']:g} years)" if req.get("min_years") else "") + ".",
    # V2 v2: a plain statement about the candidate (closer to MNLI hypotheses); chosen on the T07 dev split
    "v2": lambda req: f"The candidate has {req['text'][:1].lower() + req['text'][1:]}.",
}


def hypothesis(req, template="v2"):
    return HYPOTHESES[template](req)


def label_index(id2label):
    """{entailment, neutral, contradiction} -> logit index, matched by name (never by position)."""
    names = {int(k): str(v).strip().lower() for k, v in id2label.items()}
    idx = {}
    for lab in LABELS:
        hits = [i for i, v in names.items() if v == lab or v.startswith(lab[:4])]
        if len(hits) != 1:
            raise ValueError(f"NLI label {lab!r} not uniquely named in id2label {id2label}")
        idx[lab] = hits[0]
    if len(set(idx.values())) != 3:
        raise ValueError(f"NLI labels are not distinct in id2label {id2label}")
    return idx


_MARKER = re.compile(r"^[\s\-–—*•·>]+")


def quote_context(text, span, max_side=300):
    """The CV line around a [start, end) span, cut at a sentence boundary when longer than max_side; a leading list
    marker is dropped (V2 QA-030)."""
    a, b = span
    lo, hi = text.rfind("\n", 0, a) + 1, text.find("\n", b)
    hi = len(text) if hi == -1 else hi
    if a - lo > max_side:
        cut = max(text.rfind(c, a - max_side, a) for c in ".;!?")
        lo = cut + 1 if cut != -1 else a - max_side
    if hi - b > max_side:
        cut = min((i for i in (text.find(c, b, b + max_side) for c in ".;!?") if i != -1), default=-1)
        hi = cut + 1 if cut != -1 else b + max_side
    ctx = text[lo:hi].strip()
    return ctx if lo >= a else _MARKER.sub("", ctx)


def chunk_text(text, max_chars):
    """Line-aligned chunks of at most max_chars (a longer line is split hard). Nothing is dropped."""
    chunks, cur = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > max_chars:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(line[:max_chars])
            line = line[max_chars:]
        if len(cur) + len(line) > max_chars:
            chunks.append(cur)
            cur = ""
        cur += line
    return [c for c in chunks + [cur] if c.strip()]


def precheck(match, cv_text):
    """Verified (quote, span) list + notes. A stored span is trusted only if it points at the same text."""
    ok, notes = [], []
    for e in match.get("evidence") or []:
        sp = (e["start"], e["end"]) if cv_text[e["start"]:e["end"]] == e["quote"] else find_span(cv_text, e["quote"])
        if sp is None:
            notes.append("evidence_not_in_cv")
        else:
            ok.append((cv_text[sp[0]:sp[1]], sp))
    if match["decision"] == "MET" or (match["decision"] == "MISSING" and match["basis"] == "contradicted"):
        if not ok:
            notes.append("missing_evidence")
    notes += [f"validator:{r}" for r in match.get("review_reasons") or [] if r in VALIDATOR_NUMERIC]
    return ok, list(dict.fromkeys(notes))


def premises(match, cv_text, max_chars=1500):
    """(kind, [premise, ...]): kind quotes | cv | none (needs evidence, none verified) | None (not applicable)."""
    if match["decision"] == "UNCERTAIN":
        return None, []
    if match["decision"] == "MISSING" and match["basis"] == "not_documented":
        return "cv", chunk_text(cv_text, max_chars)
    ok, _ = precheck(match, cv_text)
    if not ok:
        return "none", []
    ctx = list(dict.fromkeys(quote_context(cv_text, sp) for _, sp in ok))
    assert all(c in cv_text for c in ctx), "Judge premise must be CV text"
    return "quotes", [" ".join(ctx)]


def verdict(match, kind, probs, tau_pass, tau_fail):
    """PASS / FAIL / UNCERTAIN / NOT_APPLICABLE and the score that decided it (pure function: used offline too)."""
    if kind is None:
        return "NOT_APPLICABLE", None
    if kind == "none" or probs is None:
        return "UNCERTAIN", None
    e, n, c = probs["entailment"], probs["neutral"], probs["contradiction"]
    if match["decision"] == "MET":
        sup, opp = e, max(c, n)
    elif kind == "quotes":  # MISSING contradicted
        sup, opp = c, e
    else:  # MISSING not_documented: only a CV that entails the requirement disagrees
        sup, opp = 1 - e, e
    if opp >= tau_fail and opp > sup:
        return "FAIL", round(opp, 4)
    if sup >= tau_pass:
        return "PASS", round(sup, 4)
    return "UNCERTAIN", round(max(sup, opp), 4)


class NLIJudge:
    max_premise_chars = 1500  # ~350-400 DeBERTa tokens: premise + hypothesis stay inside max_length=512

    def __init__(self, model_dir, tau_pass, tau_fail, device="cpu", max_length=512, template="v2"):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(model_dir)
        # explicit fp32 (V2: some configs say float16, which transformers 5 honours)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir, dtype=torch.float32).to(device).eval()
        self.idx = label_index(self.model.config.id2label)
        self.tau_pass, self.tau_fail, self.device, self.max_length = tau_pass, tau_fail, device, max_length
        self.model_dir = str(Path(model_dir).name)
        if template not in HYPOTHESES:
            raise ValueError(f"unknown hypothesis template {template!r}")
        self.template = template

    def probs(self, pairs, batch_size=16):
        out = []
        for i in range(0, len(pairs), batch_size):
            p, h = zip(*pairs[i:i + batch_size])
            enc = self.tok(list(p), list(h), truncation="only_first", max_length=self.max_length, padding=True,
                           return_tensors="pt").to(self.device)
            with self.torch.no_grad():
                pr = self.torch.softmax(self.model(**enc).logits, -1).tolist()
            out += [{lab: row[self.idx[lab]] for lab in LABELS} for row in pr]
        return out

    def score_many(self, items):
        """items: [(cv_text, requirement, match)] -> [(kind, probs | None, notes)]. Several chunks: max entailment."""
        kinds, pairs, notes = [], [], []
        for cv_text, req, match in items:
            kind, prems = premises(match, cv_text, self.max_premise_chars)
            kinds.append(kind)
            notes.append(precheck(match, cv_text)[1] if kind is not None else [])
            pairs.append([(p, hypothesis(req, self.template)) for p in prems])
        flat = iter(self.probs([p for ps in pairs for p in ps]) if any(pairs) else [])
        out = []
        for kind, ps, nt in zip(kinds, pairs, notes):
            got = [next(flat) for _ in ps]
            best = max(got, key=lambda d: d["entailment"]) if got else None
            out.append((kind, {k: round(v, 4) for k, v in best.items()} if best else None, nt))
        return out

    def judge(self, cv_text, req, match):
        """One finding (dict). An NLI failure gives UNCERTAIN with `error`, never a crash (V2 QA-019)."""
        error = None
        try:
            kind, probs, notes = self.score_many([(cv_text, req, match)])[0]
        except Exception as e:  # noqa: BLE001
            kind, probs, notes, error = "error", None, [], f"{type(e).__name__}: {str(e)[:200]}"
        v, score = ("UNCERTAIN", None) if error else verdict(match, kind, probs, self.tau_pass, self.tau_fail)
        return {"verdict": v, "score": score, "nli_probs": probs, "premise_kind": kind, "notes": notes, "error": error,
                "review_reasons": [REVIEW[v]] if v in REVIEW else [],
                "provenance": {"model": self.model_dir, "tau_pass": self.tau_pass, "tau_fail": self.tau_fail,
                               "hypothesis": self.template, "premise_policy": PREMISE_POLICY, "scores": SCORE_NOTE}}
