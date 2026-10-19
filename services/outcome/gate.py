"""Outcome gate (station 8): one pair's requirement results -> invite / review / reject, in plain code.

"The LLM judges, code counts" (CLAUDE.md rule 2): the stations give per-requirement decisions and flags; this code
counts. Rules, in this order (T08):
  score   = round(100 * sum(w * v) / sum(w)), w: must 2, nice 1; v: MET 1, UNCERTAIN 0.5, MISSING 0 (Decision 5).
  1. reject  if a must-have is MISSING and carries no outcome-relevant flag (a clean, checked gap);
  2. review  if a must-have carries an outcome-relevant flag (the doubt could change the outcome):
               - MET with judge:disagrees / judge:uncertain or a validator evidence flag  (possible false invite)
               - MISSING with judge:disagrees (the Judge finds the CV entails it) or
                 contradiction_refuted_by_evidence                                        (possible false reject)
               - UNCERTAIN (incl. match:low_confidence)
  3. invite  if every must-have is MET without such a flag and score >= t_invite;
  4. review  otherwise (score below t_invite).
Pair-level flags (e.g. profile:partial_extraction_requires_review): `pair_flags="block"` sends the pair to review
(before rule 1), `"info"` only lists them. Flags on nice-to-haves and info_flags never block; they are listed.
Exception (rule 0): some pair reasons always send the pair to review, whatever `pair_flags` says (ALWAYS_REVIEW):
the Reader's input-quality reasons (T10, READER_QUALITY: a bad photo or scan: a wrong text must never give a silent
invite or reject) and the Bias Auditor's `bias:swap_flip` (T11: a must-have decision changed when only the
candidate's identity was swapped). None of the 52 gold pairs carries one, so the T08/T08b numbers do not change.

Judge options for rule 2 (T08b, chosen on dev): `judge="none"` -> Judge reasons never count (listed only);
`judge_met_max_conf=X` -> a Judge doubt on a MET must-have counts only if p(MET) < X; `judge_max_support=Y` -> it
counts only if the Judge's supporting (entailment) score < Y; `judge_skip_proven=True` -> it never counts for
`language`, nor for `experience` whose verified years (evidence_years) reach min_years. Validator flags always count.
"""
from dataclasses import asdict, dataclass, field

W = {"must": 2, "nice": 1}
V = {"MET": 1.0, "UNCERTAIN": 0.5, "MISSING": 0.0}
JUDGE = ("judge:disagrees", "judge:uncertain")
VALIDATOR_EVIDENCE = ("evidence_not_in_cv", "evidence_too_short", "duration_not_in_evidence",
                      "model_output_truncated", "inconsistent_decision_basis")
REJECT_SENTENCE = "You can request a human review of this decision."
READER_QUALITY = ("reader:low_confidence_or_little_text", "reader:many_unclear_parts", "reader:many_low_trust_lines",
                  "reader:vision_output_truncated", "reader:non_english_text")
BIAS_REVIEW = ("bias:swap_flip",)
# T13 (security): a suspected prompt injection in the CV or in the job post is never decided automatically
INJECTION = ("profile:possible_prompt_injection", "job_agent:possible_prompt_injection")
ALWAYS_REVIEW = READER_QUALITY + BIAS_REVIEW + INJECTION


@dataclass
class GateResult:
    outcome: str                       # invite | review | reject
    rule: str                          # which rule fired
    score: int
    reasons: list = field(default_factory=list)          # why (outcome-relevant)
    listed_flags: list = field(default_factory=list)     # shown, not blocking (nice-to-have flags, info flags)
    must: dict = field(default_factory=dict)             # counts of must-have decisions
    settings: dict = field(default_factory=dict)
    message: str | None = None

    def to_dict(self):
        return asdict(self)


def judge_counts(r, judge="all", judge_met_max_conf=None, judge_max_support=None, judge_skip_proven=False):
    """Does the Judge's doubt on this result count for the outcome (rule 2 variants)?"""
    if judge == "none":
        return False
    if r["decision"] != "MET":
        return True  # the variants only concern MET must-haves (possible false invites)
    conf = (r.get("confidence") or {}).get("MET")
    if judge_met_max_conf is not None and conf is not None and conf >= judge_met_max_conf:
        return False
    support = ((r.get("judge") or {}).get("nli_probs") or {}).get("entailment")
    if judge_max_support is not None and support is not None and support >= judge_max_support:
        return False
    if judge_skip_proven:
        if r.get("category") == "language":
            return False
        ey, my = r.get("evidence_years"), r.get("min_years")
        if r.get("category") == "experience" and ey is not None and my and ey >= my:
            return False
    return True


def relevant_flag(r, **judge_opts):
    """The outcome-relevant reason on ONE must-have result, or None."""
    reasons = r.get("review_reasons") or []
    if not judge_counts(r, **judge_opts):
        reasons = [x for x in reasons if x not in JUDGE]
    d = r["decision"]
    if d == "UNCERTAIN":
        return "must UNCERTAIN" + (" (low confidence)" if "match:low_confidence" in reasons else "")
    if d == "MET":
        hit = [x for x in reasons if x in JUDGE or x in VALIDATOR_EVIDENCE]
        return f"must MET doubted ({', '.join(hit)}): possible false invite" if hit else None
    if d == "MISSING":
        hit = [x for x in reasons if x == "judge:disagrees" or x == "contradiction_refuted_by_evidence"]
        return f"must MISSING doubted ({', '.join(hit)}): possible false reject" if hit else None
    return None


def decide(requirements, pair_review_reasons=(), pair_info_flags=(), t_invite=80, pair_flags="info", **judge_opts):
    """requirements: [{req_id, kind, decision, review_reasons, info_flags, + optional category, confidence (normalized
    label probabilities), judge {verdict, nli_probs}, evidence_years, min_years}] (the /match + /judge results).
    judge_opts: judge ("all" | "none"), judge_met_max_conf, judge_max_support, judge_skip_proven (see module doc)."""
    if not requirements:
        raise ValueError("no requirement results")
    if pair_flags not in ("block", "info"):
        raise ValueError("pair_flags must be 'block' or 'info'")
    score = round(100 * sum(W[r["kind"]] * V[r["decision"]] for r in requirements) / sum(W[r["kind"]] for r in requirements))
    must = [r for r in requirements if r["kind"] == "must"]
    flagged = {r["req_id"]: f for r in must if (f := relevant_flag(r, **judge_opts))}
    listed = [f"{r['req_id']} (nice): {x}" for r in requirements if r["kind"] == "nice" for x in r.get("review_reasons") or []]
    listed += [f"{r['req_id']} (must, not outcome-relevant): {x}" for r in must if r["req_id"] not in flagged
               for x in r.get("review_reasons") or []]
    listed += [f"{r['req_id']}: {x}" for r in requirements for x in r.get("info_flags") or []]
    listed += [f"pair: {x}" for x in pair_info_flags]
    counts = {d: sum(r["decision"] == d for r in must) for d in V}
    settings = {"t_invite": t_invite, "pair_flags": pair_flags, **judge_opts}

    def res(outcome, rule, reasons):
        return GateResult(outcome, rule, score, reasons, listed, counts, settings,
                          REJECT_SENTENCE if outcome == "reject" else None)

    always = [x for x in pair_review_reasons if x in ALWAYS_REVIEW]
    if always:
        rule = ("0 review: identity swap changed a must-have" if any(x in BIAS_REVIEW for x in always)
                else "0 review: possible prompt injection" if any(x in INJECTION for x in always)
                else "0 review: CV image too poor to decide")
        return res("review", rule, [f"pair: {x}" for x in always])
    if pair_flags == "block" and pair_review_reasons:
        return res("review", "pair flag blocks", [f"pair: {x}" for x in pair_review_reasons])
    listed += [f"pair: {x} (info only)" for x in pair_review_reasons]
    clean_missing = [r["req_id"] for r in must if r["decision"] == "MISSING" and r["req_id"] not in flagged]
    if clean_missing:
        return res("reject", "1 reject: must-have MISSING", [f"{x}: must-have MISSING" for x in clean_missing])
    if flagged:
        return res("review", "2 review: outcome-relevant flag on a must-have", [f"{k}: {v}" for k, v in flagged.items()])
    if must and all(r["decision"] == "MET" for r in must) and score >= t_invite:
        return res("invite", "3 invite: all must-haves MET, score >= t_invite", [f"score {score} >= {t_invite}"])
    return res("review", "4 review: score below t_invite", [f"score {score} < {t_invite}"])
