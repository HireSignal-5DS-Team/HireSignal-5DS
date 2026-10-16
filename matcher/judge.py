"""NLI Judge: checks whether the CV evidence semantically supports the Matcher decision. It never changes the decision.

Formulation (premise -> hypothesis H = "The candidate meets this job requirement: <requirement text>"):

| validated decision | premise | NLI label that supports the decision | label that contradicts it |
|---|---|---|---|
| MET (supported)            | the verified CV quotes | entailment     | contradiction or neutral* |
| MISSING (contradicted)     | the verified CV quotes | contradiction  | entailment |
| MISSING (not_documented)   | the whole CV text      | not entailment (absence is not disproof) | entailment (the CV does show it) |
| UNCERTAIN                  | -                      | judge not applicable: verdict UNCERTAIN, review already required |

* For MET, "neutral" means the quote does not establish the requirement: FAIL when p(neutral) >= tau_fail.
Quote premises are read in context: each quote is widened to its CV line (bounded), so a negation the Matcher left
out of a partial quote ("Never used | Kubernetes in production") is visible to the Judge (QA-017). A whole-CV premise
is split into chunks that fit the model window and the chunk with the highest entailment decides (QA-018). An NLI
failure yields an UNCERTAIN finding with `error`, never a crash (QA-019). See docs/qa/FAILURES.md.
Verdict: PASS when p(supporting) >= tau_pass, FAIL when p(opposing) >= tau_fail, else UNCERTAIN.
judge_score = probability of the label that decided the verdict (a model probability, calibration measured in
benchmark/judge_eval.py, not assumed). Thresholds come from a calibration split, never from the test split.
"""
import re
from dataclasses import asdict, dataclass

from .validate import find_span

LABELS = ("entailment", "neutral", "contradiction")


@dataclass
class JudgeFinding:
    judge_verdict: str  # PASS | FAIL | UNCERTAIN | NOT_APPLICABLE
    judge_score: float | None
    judge_disagrees: bool
    requires_human_review: bool
    nli_probs: dict | None
    premise_kind: str | None
    model: str
    error: str | None = None

    def to_dict(self):
        return asdict(self)


def hypothesis(req):
    years = f" (at least {req.min_years:g} years)" if req.min_years else ""
    return f"The candidate meets this job requirement: {req.text}{years}."


_MARKER = re.compile(r"^[\s\-–—*•·>]+")


def quote_context(text, span, max_side=300):
    """The CV line around a [start, end) span, cut at a sentence boundary when the line is longer than max_side.
    A leading list marker ('- ', '– ', '* ', '• ') is dropped: it carries no meaning but moves NLI scores (QA-030)."""
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


class NLIJudge:
    max_premise_chars = 1500  # ~350-400 DeBERTa tokens: premise + hypothesis stay inside max_length=512

    def __init__(self, model_dir, tau_pass=0.5, tau_fail=0.5, device="cpu", max_length=512, name=None):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(model_dir)
        # explicit fp32: the checkpoint config says float16, which transformers 5 honours (slow + unstable on CPU)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir, dtype=torch.float32).to(device).eval()
        id2label = {int(k): v.lower() for k, v in self.model.config.id2label.items()}
        self.idx = {lab: next(i for i, v in id2label.items() if v.startswith(lab[:4])) for lab in LABELS}
        self.tau_pass, self.tau_fail, self.device, self.max_length = tau_pass, tau_fail, device, max_length
        self.name = name or str(model_dir)

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

    @staticmethod
    def premise(result, cv):
        """(kind, premise text) for a validated RequirementResult, or (None, None) when the judge does not apply.
        Quotes are widened to their CV line context (QA-017). The whole-CV premise is returned unchunked here;
        `premises` splits it to fit the model window."""
        if result.decision == "UNCERTAIN":
            return None, None
        if result.decision == "MISSING" and result.basis == "not_documented":
            return "cv", cv.text
        if not result.evidence:
            return None, None
        spans = list(getattr(result, "evidence_spans", None) or [find_span(cv.text, q) for q in result.evidence])
        ctx = [quote_context(cv.text, sp) if sp else q for q, sp in zip(result.evidence, spans)]
        return "quotes", " ".join(dict.fromkeys(ctx))

    def premises(self, result, cv):
        """(kind, [premise, ...]): one premise for quotes, window-sized chunks for the whole CV (QA-018)."""
        kind, prem = self.premise(result, cv)
        if kind is None:
            return None, []
        return kind, chunk_text(prem, self.max_premise_chars) if kind == "cv" else [prem]

    def item_probs(self, items_pairs):
        """items_pairs: [[(premise, hypothesis), ...] per item] -> [probs | None]. For several chunks of one item the
        chunk with the highest entailment decides (only entailment can contradict a not_documented decision)."""
        flat = [p for pairs in items_pairs for p in pairs]
        pr = iter(self.probs(flat) if flat else [])
        out = []
        for pairs in items_pairs:
            got = [next(pr) for _ in pairs]
            out.append(max(got, key=lambda d: d["entailment"]) if got else None)
        return out

    def verdict(self, result, probs, kind):
        if kind is None:
            return JudgeFinding("NOT_APPLICABLE", None, False, result.decision == "UNCERTAIN", None, None, self.name)
        e, n, c = probs["entailment"], probs["neutral"], probs["contradiction"]
        if result.decision == "MET":
            sup, opp = e, max(c, n)
        elif kind == "quotes":  # MISSING contradicted
            sup, opp = c, e
        else:  # MISSING not_documented: only a CV that entails the requirement disagrees
            sup, opp = 1 - e, e
        if opp >= self.tau_fail and opp > sup:
            v, score = "FAIL", opp
        elif sup >= self.tau_pass:
            v, score = "PASS", sup
        else:
            v, score = "UNCERTAIN", max(sup, opp)
        return JudgeFinding(v, round(score, 4), v == "FAIL", v != "PASS", {k: round(x, 4) for k, x in probs.items()},
                            kind, self.name)

    def judge_many(self, items):
        """items: [(validated RequirementResult, CV, Requirement)] -> [JudgeFinding] (batched NLI).
        An NLI failure gives UNCERTAIN findings with `error` (review required); decisions are untouched (QA-019)."""
        kinds, pairs = [], []
        for res, cv, req in items:
            kind, prems = self.premises(res, cv)
            kinds.append(kind)
            pairs.append([(p, hypothesis(req)) for p in prems])
        try:
            pr = self.item_probs(pairs)
        except Exception as e:  # noqa: BLE001  any model/runtime failure must not stop the pipeline
            err = f"{type(e).__name__}: {str(e)[:200]}"
            return [self.verdict(res, None, None) if k is None else
                    JudgeFinding("UNCERTAIN", None, False, True, None, k, self.name, error=err)
                    for (res, _, _), k in zip(items, kinds)]
        return [self.verdict(res, p, k) for (res, _, _), k, p in zip(items, kinds, pr)]
