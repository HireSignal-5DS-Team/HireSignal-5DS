"""Bias Auditor variants behind the frozen contract (`check_result(result, cv_text)`, `counterfactual(...)`,
`BiasFinding`). No variant ever changes a Matcher decision; each only adds a finding.

  rules_v1            matcher.bias_audit.check_result, unchanged (production today)
  rules_v2            bias/rules.py lexicon, no model
  reviewer            LLM reviewer only (bias/reviewer.py)
  rules_v2+reviewer   union: flagged if either flags (the auditor routes to human review, so recall comes first)

    auditor = BiasAuditor("rules_v2+reviewer", reviewer=LLMReviewer(OpenAICompatBackend(...)))
    finding = auditor.check_result(result, cv_text, requirement_text=req.text)

`requirement_text` is optional so the two-argument contract call still works; without it, the rules cannot apply the
requirement exemption and the reviewer sees the result's own `requirement_text` field.
"""
from matcher.bias_audit import BiasFinding, check_result as rules_v1_check, counterfactual, merge  # noqa: F401

from .rules import scan

VARIANTS = ("rules_v1", "rules_v2", "reviewer", "rules_v2+reviewer")


class BiasAuditor:
    def __init__(self, variant="rules_v1", reviewer=None):
        if variant not in VARIANTS:
            raise ValueError(f"unknown Bias Auditor variant {variant!r}; choose from {VARIANTS}")
        if "reviewer" in variant and reviewer is None:
            raise ValueError(f"variant {variant!r} needs a reviewer")
        self.variant, self.reviewer = variant, reviewer

    def info(self):
        return {"variant": self.variant, **({"reviewer": self.reviewer.info()} if self.reviewer else {})}

    def counterfactual(self, match_fn, cv, req, **kw):
        return counterfactual(match_fn, cv, req, **kw)

    def check_result(self, result, cv_text, requirement_text=None):
        if self.variant == "rules_v1":
            f = rules_v1_check(result, cv_text)
            f.details["auditor"] = "rules_v1"
            return f
        req_text = requirement_text if requirement_text is not None else (result.requirement_text or "")
        details, sources, attrs, terms, demo = {"auditor": self.variant}, [], [], [], False
        if self.variant in ("rules_v2", "rules_v2+reviewer"):
            s = scan(result, req_text)
            details["rules_v2"] = s
            terms, demo, attrs = s["terms"], bool(s["personal_quotes"]), list(s["attributes"])
            if s["flag"]:
                sources.append("rules_v2")
        if "reviewer" in self.variant:
            r = self.reviewer.review(result, req_text)
            details["reviewer"] = r
            v = r["verdict"]
            if v and v["flag"]:
                sources.append("reviewer")
                attrs += [a for a in v["attributes"] if a not in attrs]
                demo = demo or v["category"] == "demographic_evidence"
                if not attrs:
                    attrs = [v["category"]]
        details["flag_sources"] = sources
        flagged = bool(sources)
        return BiasFinding("FLAGGED" if flagged else "PASS", affected_attribute=",".join(attrs) if flagged else None,
                           leakage_terms=terms, demographic_evidence=demo, requires_human_review=flagged, details=details)
