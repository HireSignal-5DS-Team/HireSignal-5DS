"""NLI Judge: checks whether the CV evidence semantically supports the Matcher decision. It never changes the decision.

Formulation (premise -> hypothesis H, see `hypothesis` for the templates):

| validated decision | premise | NLI label that supports the decision | label that contradicts it |
|---|---|---|---|
| MET (supported)            | the verified CV quotes | entailment     | contradiction or neutral* |
| MISSING (contradicted)     | the verified CV quotes | contradiction  | entailment |
| MISSING (not_documented)   | the whole CV text      | not entailment (absence is not disproof) | entailment (the CV does show it) |
| UNCERTAIN                  | -                      | judge not applicable: verdict NOT_APPLICABLE, review already required |

* For MET, "neutral" means the quote does not establish the requirement: FAIL when score(neutral) >= tau_fail.

Deterministic pre-checks run before any NLI call (`precheck`):
- every quote must be an exact CV substring (`matcher.validate.find_span`, the validator's own check, reused): a quote
  that is not in the CV is dropped from the premise and the finding asks for review;
- MET or MISSING/contradicted without any verified quote -> verdict UNCERTAIN, review, no NLI call (missing evidence
  is never read as support or as disproof);
- premises are built from `CV.text` only. RAG/knowledge text is never a premise: the Judge does not receive the
  knowledge refs at all, and every premise part is asserted to be a CV substring;
- numeric/duration checks belong to the validator. When the validated result carries a numeric reason
  (`VALIDATOR_NUMERIC`), the finding records it and recommends review whatever the NLI says: a Judge PASS never
  clears a validator flag (the pipeline review reasons are a union, and the Judge only adds findings).
Quote premises are read in context: each quote is widened to its CV line (bounded), so a negation the Matcher left
out of a partial quote ("Never used | Kubernetes in production") is visible to the Judge (QA-017); list markers are
dropped (QA-030). A whole-CV premise is split into chunks that fit the model window and the chunk with the highest
entailment decides (QA-018). An NLI failure yields an UNCERTAIN finding with `error`, never a crash (QA-019).

Verdict: PASS when s(supporting) >= tau_pass, FAIL when s(opposing) >= tau_fail (and > s(supporting)), else UNCERTAIN.
The scores are the softmax outputs of the NLI head over (entailment, neutral, contradiction). They are NOT
probabilities that the Matcher decision is correct; their calibration as such is measured in benchmark/judge_eval.py
(ECE), never assumed. Thresholds come from train-dev (train case index % 5 == 0), never from val or test.
See docs/JUDGE.md.
"""
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .validate import find_span

LABELS = ("entailment", "neutral", "contradiction")
PREMISE_POLICY = "cv-only/v2: verified quotes in CV line context (QA-017, QA-030), whole CV chunked (QA-018)"
SCORE_NOTE = "softmax NLI class scores of the model; not probabilities that the Matcher decision is correct"
# validator reasons that are numeric/duration checks: the Judge defers to them and never overrides them
VALIDATOR_NUMERIC = ("years_below_minimum_in_evidence", "duration_not_verified", "contradiction_refuted_by_evidence")
SUPPORT = {"PASS": "supports_decision", "FAIL": "opposes_decision", "UNCERTAIN": "inconclusive",
           "NOT_APPLICABLE": "not_checked"}


@dataclass
class JudgeFinding:
    """One Judge finding for one validated requirement result. Adds information only; never a decision.

    judge_verdict          PASS | FAIL | UNCERTAIN | NOT_APPLICABLE
    judge_score            score of the label that decided the verdict (NLI softmax; NOT P(decision correct))
    judge_disagrees        verdict == FAIL
    requires_human_review  the Judge's review recommendation as a bool (== recommendation == "review")
    nli_probs              {entailment, neutral, contradiction} softmax scores (NOT P(decision correct)); None if no NLI
    premise_kind           quotes | cv | None
    model                  display name of the Judge
    error                  NLI failure message (QA-019), else None
    support_status         supports_decision | opposes_decision | inconclusive | missing_evidence | not_checked
    recommendation         review | no_judge_concern  ("no_judge_concern" is not an approval: validator and bias
                           reasons still apply)
    prechecks              deterministic pre-check notes (evidence_not_in_cv, missing_evidence, numeric reasons kept)
    provenance             model id, revision, tau_pass, tau_fail, hypothesis template, premise policy, score note
    """
    judge_verdict: str
    judge_score: float | None
    judge_disagrees: bool
    requires_human_review: bool
    nli_probs: dict | None
    premise_kind: str | None
    model: str
    error: str | None = None
    support_status: str | None = None
    recommendation: str | None = None
    prechecks: list = field(default_factory=list)
    provenance: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.support_status is None:
            self.support_status = SUPPORT.get(self.judge_verdict)
        if self.recommendation is None:
            self.recommendation = "review" if self.requires_human_review else "no_judge_concern"

    def to_dict(self):
        return asdict(self)


HYPOTHESES = {
    # v1: the original template (finetune/train_judge.py, the base-model calibrations up to S5 used it)
    "v1": lambda req: f"The candidate meets this job requirement: {req.text}"
                      + (f" (at least {req.min_years:g} years)" if req.min_years else "") + ".",
    # v2: a plain statement about the candidate, closer to SNLI/MNLI hypotheses (no meta "meets requirement" frame);
    # the duration stays in the requirement text, the validator checks it
    "v2": lambda req: f"The candidate has {req.text[:1].lower() + req.text[1:]}.",
}


def hypothesis(req, template="v1"):
    return HYPOTHESES[template](req)


def label_index(id2label):
    """{entailment, neutral, contradiction} -> logit index from a checkpoint's id2label. Names are matched exactly or
    by their 4-letter prefix ("ENTAILMENT", "entail", "contra"...). Raises when the mapping is not one-to-one, e.g.
    for generic LABEL_0/1/2 names: guessing an order would silently invert the Judge."""
    names = {int(k): str(v).strip().lower() for k, v in id2label.items()}
    idx = {}
    for lab in LABELS:
        hits = [i for i, v in names.items() if v == lab or v.startswith(lab[:4])]
        if len(hits) != 1:
            raise ValueError(f"NLI label {lab!r} not uniquely named in id2label {id2label}; set labels explicitly")
        idx[lab] = hits[0]
    if len(set(idx.values())) != 3:
        raise ValueError(f"NLI labels are not distinct in id2label {id2label}")
    return idx


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


def precheck(result, cv):
    """Deterministic checks before NLI. Returns (verified [(quote, span)], notes). Reuses the validator's exact
    substring check (find_span); a stored span is trusted only if it points at the same text."""
    spans = list(getattr(result, "evidence_spans", None) or [])
    ok, notes = [], []
    for i, q in enumerate(result.evidence or []):
        sp = tuple(spans[i]) if i < len(spans) and spans[i] else None
        if sp is None or cv.text[sp[0]:sp[1]] != q.strip():
            sp = find_span(cv.text, q)
        if sp is None:
            notes.append("evidence_not_in_cv")
        else:
            ok.append((cv.text[sp[0]:sp[1]], sp))
    if result.decision == "MET" or (result.decision == "MISSING" and result.basis == "contradicted"):
        if not ok:
            notes.append("missing_evidence")
    notes += [f"validator:{r}" for r in getattr(result, "review_reasons", None) or [] if r in VALIDATOR_NUMERIC]
    return ok, list(dict.fromkeys(notes))


def _revision_of(model_dir, revision):
    """Best-effort pinned revision for provenance: the explicit one, a HF snapshot directory name, or 'local'."""
    if revision:
        return revision
    p = Path(str(model_dir))
    if p.exists():
        return p.name if p.parent.name == "snapshots" else "local:" + str(p)
    return None


class NLIJudge:
    max_premise_chars = 1500  # ~350-400 DeBERTa tokens: premise + hypothesis stay inside max_length=512
    hypothesis_template = "v1"
    model_id = None
    revision = None

    def __init__(self, model_dir, tau_pass=0.5, tau_fail=0.5, device="cpu", max_length=512, name=None, revision=None,
                 hypothesis_template="v1", num_threads=None):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch = torch
        if num_threads:
            torch.set_num_threads(int(num_threads))
        kw = {"revision": revision} if revision and not Path(str(model_dir)).exists() else {}
        self.tok = AutoTokenizer.from_pretrained(model_dir, **kw)
        # explicit fp32: some checkpoint configs say float16, which transformers 5 honours (slow + unstable on CPU)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir, dtype=torch.float32, **kw).to(device).eval()
        self.idx = label_index(self.model.config.id2label)
        if hypothesis_template not in HYPOTHESES:
            raise ValueError(f"unknown hypothesis template {hypothesis_template!r}; one of {sorted(HYPOTHESES)}")
        self.tau_pass, self.tau_fail, self.device, self.max_length = tau_pass, tau_fail, device, max_length
        self.hypothesis_template = hypothesis_template
        self.model_id = str(model_dir)
        self.revision = _revision_of(model_dir, revision or getattr(self.model.config, "_commit_hash", None))
        self.name = name or str(model_dir)

    def provenance(self):
        return {"model_id": getattr(self, "model_id", None) or getattr(self, "name", None),
                "revision": getattr(self, "revision", None), "tau_pass": self.tau_pass, "tau_fail": self.tau_fail,
                "hypothesis": getattr(self, "hypothesis_template", "v1"), "premise_policy": PREMISE_POLICY,
                "scores": SCORE_NOTE}

    def hyp(self, req):
        return hypothesis(req, getattr(self, "hypothesis_template", "v1"))

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
        kind "none": the decision needs evidence and no quote is verified in the CV (no NLI; review).
        Quotes are widened to their CV line context (QA-017). The whole-CV premise is returned unchunked here;
        `premises` splits it to fit the model window. Only CV text is ever used (never RAG/knowledge text)."""
        if result.decision == "UNCERTAIN":
            return None, None
        if result.decision == "MISSING" and result.basis == "not_documented":
            return "cv", cv.text
        ok, _ = precheck(result, cv)
        if not ok:
            return "none", None
        ctx = list(dict.fromkeys(quote_context(cv.text, sp) for _, sp in ok))
        assert all(c in cv.text for c in ctx), "Judge premise must be CV text"
        return "quotes", " ".join(ctx)

    def premises(self, result, cv):
        """(kind, [premise, ...]): one premise for quotes, window-sized chunks for the whole CV (QA-018)."""
        kind, prem = self.premise(result, cv)
        if kind in (None, "none"):
            return kind, []
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

    def _finding(self, verdict, score, review, probs, kind, notes=(), error=None, status=None):
        return JudgeFinding(verdict, score, verdict == "FAIL", review, probs, kind, self.name, error=error,
                            support_status=status, prechecks=list(notes), provenance=self.provenance())

    def verdict(self, result, probs, kind, notes=None):
        notes = list(notes or [])
        if kind is None:
            return self._finding("NOT_APPLICABLE", None, result.decision == "UNCERTAIN" or bool(notes), None, None, notes)
        if kind == "none" or probs is None:
            return self._finding("UNCERTAIN", None, True, None, None, notes or ["missing_evidence"],
                                 status="missing_evidence")
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
        return self._finding(v, round(score, 4), v != "PASS" or bool(notes), {k: round(x, 4) for k, x in probs.items()},
                             kind, notes)

    def judge_many(self, items):
        """items: [(validated RequirementResult, CV, Requirement)] -> [JudgeFinding] (batched NLI).
        The Judge never receives knowledge refs: premises are CV text only.
        An NLI failure gives UNCERTAIN findings with `error` (review required); decisions are untouched (QA-019)."""
        kinds, pairs, notes = [], [], []
        for res, cv, req in items:
            kind, prems = self.premises(res, cv)
            kinds.append(kind)
            notes.append(precheck(res, cv)[1] if kind is not None else [])
            pairs.append([(p, self.hyp(req)) for p in prems])
        try:
            pr = self.item_probs(pairs)
        except Exception as e:  # noqa: BLE001  any model/runtime failure must not stop the pipeline
            err = f"{type(e).__name__}: {str(e)[:200]}"
            return [self.verdict(res, None, k, nt) if k in (None, "none") else
                    self._finding("UNCERTAIN", None, True, None, k, nt, error=err, status="inconclusive")
                    for (res, _, _), k, nt in zip(items, kinds, notes)]
        return [self.verdict(res, p, k, nt) for (res, _, _), k, p, nt in zip(items, kinds, pr, notes)]
