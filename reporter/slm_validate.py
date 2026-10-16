"""Post-generation validator for SLM text. A section is accepted only if every check passes; otherwise it is retried
once and then replaced by the deterministic template (reporter.writer). Checks:

1. JSON: the raw output parses as exactly {"note": str} / {"summary": str} within length limits.
2. Closed vocabulary: every word is either a plain function/report word (ALLOWED) or occurs in the facts of THIS
   section. A skill, tool, employer, degree or name that is not in the facts is therefore rejected, whatever it is.
3. Numbers: every number (digits or a number word) occurs in the facts; in a summary a number next to a decision
   word must equal that count, and "N of M must-have" must equal the facts.
4. Quotes: every quoted string is a verbatim (case/space-insensitive) part of an evidence quote or requirement text.
5. Decisions: a note must contain its decision word, and no claim of another decision (e.g. "not met" on MET,
   "met" on MISSING, "lacks"). not_documented may not be phrased as "does not meet".
6. Verdicts: no hiring verdict or judgement about the person (hire, reject, recommend, suitable, strong fit, ...).
"""
import json
import re

ALLOWED = set("""
a an the this that these those it its is are was were be been being has have had do does did not no nor and or but
of in on at to for from by with as about than then so also only both each all any some none one per which who what
cv requirement requirements decision decisions basis evidence quote quotes quoted text states state stated shows show
shown mention mentions mentioned mentioning document documented documents documentation say says said lists list listed
describes described describe refer refers referred notes note noted checked check checks result results summary
must must-have nice nice-to-have have-to have human reviewer reviewers review reviewed reviewing needs need needed
required requires require requiring flagged flag flags manual manually reading read
meet meets satisfy satisfies met missing uncertain unclear ambiguous partial partially supported support supports contradicted contradicts
contradict absent absence proof proves prove meaning means mean evidence-based clear clearly directly explicit
explicitly enough sufficient insufficient further confirm confirmed confirms cannot can could may might would should
which where when how whether there here out total overall count counted among other others remaining rest
item items point points case cases part parts whole set
candidate candidate's applicant person
skill skills experience experiences year years month months
other's because since however although though while yet still even just
please see seen given give gives found find finds
indicate indicates indicated assess assessed evaluate evaluated determine determined verify verified establish
established specify specified explain explains explained provide provides provided include includes included
contain contains contained appear appears appeared mark marked
anything nothing something related regarding concerning specific specifically
""".split())

NUMBER_WORDS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve "
                                            "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}

# hiring verdicts: never allowed, even if a requirement text happens to contain the word
VERDICT = re.compile(r"\b(hire[sd]?|hiring|hireable|reject(?:s|ed|ion|ing)?|recommend\w*|shortlist\w*|interview\w*|"
                     r"offer(?:s|ed)?|advance (?:to|the)|move forward|pass on|do not proceed|proceed with|"
                     r"accept(?:ed|ance)? (?:the )?(?:candidate|applicant))\b", re.I)
# judgements about the person: allowed only if the word itself is in the facts (e.g. "Strong communication skills")
JUDGEMENT = {"suitable", "unsuitable", "qualified", "unqualified", "overqualified", "underqualified", "fit", "fits",
             "strong", "weak", "excellent", "impressive", "poor", "ideal", "perfect", "best", "worst", "talented",
             "competent", "incompetent", "good", "bad", "great", "skilled", "unskilled", "promising", "capable",
             "lacks", "lack", "lacking", "deficient", "expert", "proficient", "senior", "junior"}
CLAIM_PATTERNS = [  # (regex, claimed decision)
    (re.compile(r"\b(?:does|do|did|is|are|was|were|has|have)\s+not\s+(?:been\s+)?(?:meet|met|satisfy|satisfied|fulfil\w*)\b"
                r"|\bnot\s+met\b|\bunmet\b|\bfalls?\s+short\b", re.I), "NOT_MET"),
    (re.compile(r"(?<!not )\b(?:is|are|was|were|been|fully|clearly)\s+met\b|(?<!not )\b(?:meets|satisfies|fulfils|fulfills)\b",
                re.I), "MET"),
    (re.compile(r"\bmissing\b", re.I), "MISSING"),
    (re.compile(r"\b(?:does|do|did)\s+not\s+(?:mention|state|document|list|describe|say)|\bnot\s+(?:mentioned|documented|"
                r"stated|listed)\b|\bno\s+(?:mention|statement|evidence)\b|\bsays\s+nothing\b", re.I), "NOT_DOCUMENTED"),
    (re.compile(r"\b(?:uncertain|unclear|ambiguous)\b", re.I), "UNCERTAIN"),
]
DECISION_WORD = re.compile(r"\b(MET|MISSING|UNCERTAIN)\b")
QUOTE = re.compile(r"\"([^\"]+)\"|“([^”]+)”|(?:(?<=\s)|^)'([^']{4,})'(?=[\s.,;:!?]|$)")
WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#'\-]*[A-Za-z0-9+#]|[A-Za-z]")
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _stem(w):
    w = w.lower().removesuffix("'s")
    for suf in ("ing", "ed", "es", "s", "ly"):
        if len(w) >= len(suf) + 2 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _variants(w):
    """w and its plausible base forms (used -> use, us; managing -> manag, manage)."""
    s = _stem(w)
    return {w.lower(), s, s + "e"}


def _norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def _flatten(o):
    if isinstance(o, dict):
        return " ".join(_flatten(v) for v in o.values())
    if isinstance(o, (list, tuple)):
        return " ".join(_flatten(v) for v in o)
    return str(o)


def _fact_vocab(facts):
    text = _flatten(facts)
    words = {w.lower() for w in WORD.findall(text)}
    for w in list(words):  # "not_documented" -> not, documented ; "C++/Go" pieces
        words.update(p for p in re.split(r"[_\-/]", w) if p)
    return text, words, {_stem(w) for w in words} | {w for w in words}


def _fact_numbers(text):
    return {float(n.replace(",", ".")) for n in NUMBER.findall(text)}


def parse(raw, kind):
    """Text of the section, or (None, reason)."""
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    try:
        obj = json.loads(s)
    except (ValueError, TypeError):
        return None, "invalid_json"
    if not isinstance(obj, dict) or set(obj) != {kind} or not isinstance(obj[kind], str):
        return None, "wrong_schema"
    t = obj[kind].strip()
    lim = (10, 300) if kind == "note" else (20, 600)
    if not lim[0] <= len(t) <= lim[1]:
        return None, "length_out_of_range"
    if kind == "note" and len(re.findall(r"[.!?](?:\s|$)", t)) > 2:
        return None, "more_than_one_sentence"
    return t, None


def check_text(text, facts, kind):
    """List of violations (empty = accepted)."""
    errs = []
    ftext, fwords, fstems = _fact_vocab(facts)
    fnums = _fact_numbers(ftext)
    quoted = [next(g for g in m.groups() if g) for m in QUOTE.finditer(text)]
    sources = [_norm(q) for q in facts.get("evidence_quotes", [])] + [_norm(facts.get("requirement", ""))] + \
              [_norm(r["requirement"]) for r in facts.get("requirements", [])]
    for q in quoted:
        if not any(_norm(q).strip(" .") in s for s in sources if s):
            errs.append(f"quote_not_in_facts:{q[:40]}")
    unquoted = QUOTE.sub(" ", text)  # quotes are checked above as verbatim facts; the rest is the SLM's own wording
    if m := re.search(r"\b[a-z]+_[a-z_]+\b", unquoted):
        errs.append(f"json_key_in_text:{m.group(0)}")
    if m := VERDICT.search(unquoted):
        errs.append(f"hiring_verdict:{m.group(0)}")
    for w in WORD.findall(unquoted):
        lw = w.lower()
        if lw in JUDGEMENT and lw not in fwords:
            errs.append(f"judgement_word:{w}")
        elif lw in NUMBER_WORDS:
            if float(NUMBER_WORDS[lw]) not in fnums:
                errs.append(f"number_not_in_facts:{w}")
        elif not any(v in ALLOWED or v in fstems or _stem(v) in fstems for v in _variants(lw)):
            errs.append(f"term_not_in_facts:{w}")
    for n in NUMBER.findall(unquoted):
        if float(n.replace(",", ".")) not in fnums:
            errs.append(f"number_not_in_facts:{n}")
    errs += _decision_errors(unquoted, facts, kind)
    return list(dict.fromkeys(errs))


def _decision_errors(text, facts, kind):
    errs = []
    if kind == "note":
        d, basis = facts["decision"], facts["basis"]
        words = set(DECISION_WORD.findall(text))
        if d not in words:
            errs.append(f"decision_word_absent:{d}")
        if words - {d}:
            errs.append(f"decision_mismatch:{','.join(sorted(words - {d}))}")
        allowed = {"MET": {"MET"}, "MISSING": {"MISSING"} | ({"NOT_MET"} if basis == "contradicted" else set()),
                   "UNCERTAIN": {"UNCERTAIN"}}[d]
        if basis == "not_documented":
            allowed = allowed | {"NOT_DOCUMENTED"}
        for rx, claim in CLAIM_PATTERNS:
            if rx.search(text) and claim not in allowed:
                errs.append(f"decision_claim:{claim}")
        errs += _review_errors(text, facts["needs_human_review"])
        return errs
    return _summary_errors(text, facts)


_CLAUSE = re.compile(r"[.;:,]|\band\b|\bwhile\b|\bwhereas\b|\bbut\b", re.I)
_DEC_WORDS = {"MET": re.compile(r"(?<!not )\bmet\b", re.I), "MISSING": re.compile(r"\bmissing\b|\bnot met\b", re.I),
              "UNCERTAIN": re.compile(r"\buncertain\b|\bunclear\b|\bambiguous\b", re.I)}


def _num(tok):
    t = tok.lower()
    if t.isdigit():
        return int(t)
    if t in ("no", "none"):
        return 0
    return NUMBER_WORDS.get(t)


def _summary_errors(text, facts):
    """Every count in the summary must equal the fact it describes. The text is cut into clauses; each number in a
    clause is read against the clause's subject: must-have / nice-to-have / human review / a decision word /
    requirements in total. "N of M" reads N against the subject and M against the matching total."""
    reqs = facts["requirements"]
    total = facts["requirements_checked"]
    errs = []
    for clause in _CLAUSE.split(text):
        toks = re.findall(r"\d+|[A-Za-z][A-Za-z-]*", clause)
        nums = [(i, _num(t)) for i, t in enumerate(toks) if _num(t) is not None]
        if not nums:
            continue
        low = clause.lower()
        decs = [d for d, rx in _DEC_WORDS.items() if rx.search(clause)]
        if "must" in low:
            pool, scope = [r for r in reqs if r["kind"] == "must-have"], "must-have"
        elif "nice" in low:
            pool, scope = [r for r in reqs if r["kind"] != "must-have"], "nice-to-have"
        else:
            pool, scope = reqs, "all"
        if "review" in low:
            want = [facts["need_human_review"]] if scope == "all" else None
            label = "need human review"
        elif decs:
            want = [sum(r["decision"] == d for r in pool) for d in decs]
            label = f"{scope} {'/'.join(decs)}"
        elif scope != "all" or "requirement" in low or "checked" in low:
            want, label = [len(pool)], f"{scope} requirements"
        else:
            continue  # a number with no countable subject: already checked against the facts' numbers
        n = nums[0][1]
        if (toks[nums[0][0]].lower() in ("no", "none")) and not (decs or "review" in low):
            continue
        if want is not None and any(n != w for w in want):
            errs.append(f"count_mismatch:'{clause.strip()}' but the facts give {label} = {'/'.join(map(str, want))}")
        if len(nums) > 1 and toks[nums[0][0] + 1:nums[1][0]] and toks[nums[0][0] + 1].lower() in ("of", "out"):
            m = nums[1][1]
            if m != len(pool) and not (scope == "all" and m == total):
                errs.append(f"count_mismatch:'{clause.strip()}' but the facts give {len(pool)} {scope} requirements")
    if re.search(r"\b(?:no|not|without|never)\b[^.;]{0,30}\breview", text, re.I) and facts["need_human_review"]:
        errs.append("review_claim_mismatch:says no review, but some requirements need review")
    return errs


def _review_errors(text, needed):
    negated = re.search(r"\b(?:no|not|without|never)\b[^.;]{0,30}\breview", text, re.I)
    mentioned = re.search(r"\breview", text, re.I)
    if negated and needed:
        return ["review_claim_mismatch:says no review, but review is required"]
    if mentioned and not negated and not needed:
        return ["review_claim_mismatch:says review, but none is required"]
    return []


def validate(raw, facts, kind):
    """(text or None, violations)."""
    text, err = parse(raw, kind)
    if err:
        return None, [err]
    errs = check_text(text, facts, kind)
    return (None, errs) if errs else (text, [])
