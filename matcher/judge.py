"""NLI Judge: checks whether the CV evidence semantically supports the Matcher decision. It never changes the decision.

Formulation (premise -> hypothesis H = "The candidate meets this job requirement: <requirement text>"):

| validated decision | premise | NLI label that supports the decision | label that contradicts it |
|---|---|---|---|
| MET (supported)            | the verified CV quotes | entailment     | contradiction or neutral* |
| MISSING (contradicted)     | the verified CV quotes | contradiction  | entailment |
| MISSING (not_documented)   | the whole CV text      | not entailment (absence is not disproof) | entailment (the CV does show it) |
| UNCERTAIN                  | -                      | judge not applicable: verdict UNCERTAIN, review already required |

* For MET, "neutral" means the quote does not establish the requirement: FAIL when p(neutral) >= tau_fail.
Verdict: PASS when p(supporting) >= tau_pass, FAIL when p(opposing) >= tau_fail, else UNCERTAIN.
judge_score = probability of the label that decided the verdict (a model probability, calibration measured in
benchmark/judge_eval.py, not assumed). Thresholds come from a calibration split, never from the test split.
"""
from dataclasses import asdict, dataclass

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

    def to_dict(self):
        return asdict(self)


def hypothesis(req):
    years = f" (at least {req.min_years:g} years)" if req.min_years else ""
    return f"The candidate meets this job requirement: {req.text}{years}."


class NLIJudge:
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
        """(kind, premise text) for a validated RequirementResult, or (None, None) when the judge does not apply."""
        if result.decision == "UNCERTAIN":
            return None, None
        if result.decision == "MISSING" and result.basis == "not_documented":
            return "cv", cv.text
        return ("quotes", " ".join(result.evidence)) if result.evidence else (None, None)

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
        """items: [(validated RequirementResult, CV, Requirement)] -> [JudgeFinding] (batched NLI)."""
        kinds, pairs, pos = [], [], []
        for res, cv, req in items:
            kind, prem = self.premise(res, cv)
            kinds.append(kind)
            if kind:
                pos.append(len(pairs))
                pairs.append((prem, hypothesis(req)))
            else:
                pos.append(None)
        pr = self.probs(pairs) if pairs else []
        return [self.verdict(res, pr[p] if p is not None else None, k) for (res, _, _), k, p in zip(items, kinds, pos)]
