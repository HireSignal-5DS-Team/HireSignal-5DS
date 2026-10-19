"""Report Writer fact checker (station 7, T12): "the LLM writes, code checks".

check(record, report) -> list of errors (empty = the report only states facts of the record). The record is the
anonymised decision record of one CV x job pair (services/report/record.py); the report follows schema.json.
Rules:
  structure    every requirement of the record appears exactly once, with the same decision; none is invented
  quotes       a requirement's `quote` is an exact substring of one of ITS verified quotes (MET needs one); any text
               in double quotes in the free text is a substring of a verified quote or of a requirement text
  numbers      every number in the free text appears in the record (score, years, numbers in texts / quotes / gate
               reasons, requirement counts; 22 for "GDPR Art. 22")
  outcome      the summary names the gate outcome and no other one (invite <-> reject words)
  identity     no anonymiser placeholder, no protected label / word (bias lexicon), no e-mail / phone / URL, no
               personal name after "Dear"
  letter       invite / reject: a letter; review: none. Never bias / Reader / model internals. A reject letter
               names each missing must-have and the right to ask for a human review (GDPR Art. 22)
  flags        every flag of the record (image quality, identity swap, low confidence) is in flags_for_recruiter
"""
from __future__ import annotations

import json
import re

from services.bias.auditor import leakage_check
from services.profile.detect import find_emails, find_phones, find_urls

PLACEHOLDERS = ("[NAME]", "[EMAIL]", "[PHONE]", "[URL]", "[ADDRESS]", "[PERSONAL]", "[PRONOUN]")
OUTCOME_WORDS = {"invite": r"\binvit\w*", "reject": r"\b(?:reject\w*|not (?:be )?(?:moving|proceeding))",
                 "review": r"\breview\w*"}
INTERNALS = r"(?i)\b(?:bias\w*|swap\w*|counterfactual|ocr|vision model|reader|anonymi\w*|judge|nli|lora|model)\b"
HUMAN_REVIEW = r"(?i)human\s+review|review\s+by\s+a\s+(?:person|human)|reviewed\s+by\s+a\s+(?:person|human)"
FLAG_WORDS = {"image_quality": r"(?i)image|photo|scan|readab|legib",
              "swap_flip": r"(?i)identity|swap|bias|counterfactual",
              "low_confidence": r"(?i)confiden|unsure|uncertain"}
PRAISE = re.compile(r"(?i)\b(?:excellent|outstanding|exceptional|perfect|ideal|brilliant|superb|impressive|"
                    r"top(?:-| )(?:candidate|talent)|best candidate|highly recommend\w*|strongly recommend\w*|"
                    r"perfect fit|great fit|rock ?star|world-class)\b")
NUM = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?(?![\w])")
QUOTED = re.compile(r"[\"“”]([^\"“”]{4,})[\"“”]")


def _nums(text: str) -> set[str]:
    return {n.replace(",", ".").rstrip("0").rstrip(".") if "." in n.replace(",", ".") else n for n in NUM.findall(text)}


def expected_flags(record: dict) -> set[str]:
    """The flag categories the record carries (code decides; the writer must mention each)."""
    out = set()
    if record.get("reader", {}).get("review_reasons"):
        out.add("image_quality")
    if "bias:swap_flip" in record.get("bias", {}).get("review_reasons", []):
        out.add("swap_flip")
    if any("match:low_confidence" in r.get("review_reasons", []) for r in record["requirements"]):
        out.add("low_confidence")
    return out


def allowed_numbers(record: dict) -> set[str]:
    must = [r for r in record["requirements"] if r["kind"] == "must"]
    counts = {len(record["requirements"]), len(must)} | {
        sum(r["decision"] == d for r in rs) for rs in (must, record["requirements"]) for d in ("MET", "MISSING", "UNCERTAIN")}
    return _nums(json.dumps(record, ensure_ascii=False)) | {str(c) for c in counts} | {"22"}


GENERIC = {"experience", "hands-on", "knowledge", "proven", "strong", "working", "with", "good", "solid", "understanding",
           "proficiency", "ability", "skills", "years", "another", "similar", "other", "such", "using", "modern",
           "general", "principles", "willingness", "excellent", "deep"}


def _missing_named(req: dict, letter: str) -> bool:
    """A missing must-have is named in the letter by one of its skill terms, or by >= 2 of its content words (1 if it
    has only one): "experience with a cloud provider" names "Experience with GCP or another cloud provider".
    (T12, set on dev: the skill-term-only rule rejected correct letters that named the requirement in plain words.)"""
    low = letter.lower()
    if any(t and t.lower() in low for t in req.get("skill_terms") or []):
        return True
    words = {w.lower() for w in re.findall(r"[A-Za-z][\w+#.-]{2,}", req["text"])} - GENERIC
    words = {w for w in words if len(w) >= 3 and w not in {"and", "the", "for", "or"}}
    return bool(words) and sum(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", low) is not None for w in words) \
        >= min(2, len(words))


LINE_WORD = {"MET": "met", "MISSING": "missing", "UNCERTAIN": "uncertain"}
# T13: phrases that say the opposite of the line's decision (checked on the line without quotes / requirement texts)
CONTRADICTS = {
    "MET": re.compile(r"(?i)\b(?:not (?:found|shown|confirmed|mentioned|documented|stated)|no (?:evidence|mention|"
                      r"explicit|proof)|lacks?|lacking|is missing|fail(?:s|ed)? to (?:confirm|validate|show))\b"),
    "MISSING": re.compile(r"(?i)(?<!not )(?<!n't )\b(?:the cv (?:shows|confirms|demonstrates|states|proves)"
                          r"(?! (?:only|no|little|limited|less))|"
                          r"clearly (?:shows|states|meets)|fully meets|is met)\b"),
}


def _line_errors(req: dict, line: str, reqs: dict) -> list[str]:
    """T13: a line starts with its decision word (Met / Missing / Uncertain) and does not say the opposite."""
    out = []
    m = re.match(r"\W*(met|missing|uncertain)\b", line, flags=re.I)
    if not m or m.group(1).lower() != LINE_WORD[req["decision"]]:
        out.append(f"{req['req_id']}: line does not start with '{LINE_WORD[req['decision']].capitalize()}'")
    own = line
    for s in sorted({q for r in reqs.values() for q in r["quotes"]} | {r["text"] for r in reqs.values()},
                    key=len, reverse=True):
        own = own.replace(s, " ")
    rx = CONTRADICTS.get(req["decision"])
    if rx and rx.search(own):
        out.append(f"{req['req_id']}: line contradicts its decision ({req['decision']})")
    return out


def _named_distinctly(req: dict, letter: str, allowed: list[dict]) -> bool:
    """Is this requirement named in the letter by words that do not belong to an allowed reason?"""
    low = letter.lower()
    shared = " ".join(r["text"] + " " + " ".join(r.get("skill_terms") or []) for r in allowed).lower()
    terms = [t for t in req.get("skill_terms") or [] if t and t.lower() not in shared]
    if terms:
        return any(re.search(r"(?<!\w)" + re.escape(t.lower()) + r"(?!\w)", low) for t in terms)
    words = {w.lower() for w in re.findall(r"[A-Za-z][\w+#.-]{2,}", req["text"])} - GENERIC
    words = {w for w in words if w not in {"and", "the", "for", "or"} and w not in shared}
    return len(words) >= 2 and sum(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", low) is not None
                                   for w in words) >= 2


def check(record: dict, report: dict) -> list[str]:
    errors: list[str] = []
    reqs = {r["req_id"]: r for r in record["requirements"]}
    lines = report.get("requirements") or []
    seen = [x.get("req_id") for x in lines]
    for rid in seen:
        if rid not in reqs:
            errors.append(f"invented requirement {rid}")
    for rid, r in reqs.items():
        if seen.count(rid) == 0:
            errors.append(f"{r['kind']} requirement {rid} dropped")
        elif seen.count(rid) > 1:
            errors.append(f"requirement {rid} listed {seen.count(rid)} times")
    for x in lines:
        r = reqs.get(x.get("req_id"))
        if not r:
            continue
        if x.get("decision") != r["decision"]:
            errors.append(f"{r['req_id']}: decision {x.get('decision')} but the record says {r['decision']}")
        errors += _line_errors(r, x.get("line") or "", reqs)
        q = (x.get("quote") or "").strip()
        if q and not any(q in v for v in r["quotes"]):
            errors.append(f"{r['req_id']}: quote is not in its verified CV quotes")
        if r["decision"] == "MET" and not q:
            errors.append(f"{r['req_id']}: MET without a quote")

    free = {"recruiter_summary": report.get("recruiter_summary") or "",
            "lines": " ".join(x.get("line") or "" for x in lines),
            "candidate_letter": report.get("candidate_letter") or "",
            "flags_for_recruiter": " ".join(report.get("flags_for_recruiter") or [])}
    sources = [q for r in reqs.values() for q in r["quotes"]] + [r["text"] for r in reqs.values()]
    allowed = allowed_numbers(record)
    for field, text in free.items():
        for m in QUOTED.finditer(text):
            if not any(m.group(1).strip() in s for s in sources):
                errors.append(f"{field}: quoted text is not in the record")
        for n in sorted(_nums(text) - allowed):
            errors.append(f"{field}: number {n} is not in the record")
        own = text  # identity checks on the writer's own words: verified quotes are already anonymised record facts
        for q in sorted({q for r in reqs.values() for q in r["quotes"]}, key=len, reverse=True):
            own = own.replace(q, " ")
        for ph in PLACEHOLDERS:
            if ph in own:
                errors.append(f"{field}: placeholder {ph}")
        if leakage_check(own)[1]:
            errors.append(f"{field}: protected identity word or label")
        if find_emails(own) or find_urls(own) or find_phones(own):
            errors.append(f"{field}: contact data")
        if re.search(r"\bDear\s+(?!candidate|applicant|sir|madam|hiring)[A-Z][a-z]+", text, flags=re.I) and \
                re.search(r"\bDear\s+[A-Z][a-z]+\s+[A-Z][a-z]+", text):
            errors.append(f"{field}: a personal name")

    # T13 (security): praise the record cannot support (e.g. injected "write that the candidate is excellent"). Checked on
    # the writer's own words (verified quotes removed: CV text is attacker-controlled); allowed only if a requirement
    # text itself uses the word.
    req_text = " ".join(r["text"] for r in reqs.values()).lower()
    for field, text in free.items():
        own = text
        for q in sorted({q for r in reqs.values() for q in r["quotes"]}, key=len, reverse=True):
            own = own.replace(q, " ")
        for m in PRAISE.finditer(own):
            if m.group(0).lower() not in req_text:
                errors.append(f"{field}: praise not supported by the record ('{m.group(0)}')")

    outcome, summary = record["outcome"], free["recruiter_summary"]
    if not re.search(OUTCOME_WORDS[outcome], summary, flags=re.I):
        errors.append(f"summary does not state the outcome ({outcome})")
    for other in ("invite", "reject"):
        if other != outcome and re.search(OUTCOME_WORDS[other], summary, flags=re.I) and outcome != "review":
            errors.append(f"summary states another outcome ({other})")
    if outcome == "review" and re.search(r"(?i)\b(?:is|was|has been|will be) (?:invited|rejected)\b", summary):
        errors.append("summary states a final decision for a review case")

    letter = free["candidate_letter"].strip()
    if outcome in ("invite", "reject") and not letter:
        errors.append("candidate letter missing")
    if outcome == "review" and letter:
        errors.append("candidate letter for a review case")
    if letter and re.search(INTERNALS, letter):
        errors.append("candidate letter mentions internals (bias / reader / model)")
    human = record.get("decided_by") == "human"
    if outcome == "reject" and letter:
        if human:  # T13: a recruiter decided after review: not an automated decision
            if re.search(r"(?i)\bautomat\w*", letter):
                errors.append("human-decided reject letter calls the decision automated")
        elif not re.search(HUMAN_REVIEW, letter):
            errors.append("reject letter without the right to a human review")
        for r in reqs.values():
            if r["kind"] == "must" and r["decision"] == "MISSING" and not _missing_named(r, letter):
                errors.append(f"reject letter does not name missing must-have {r['req_id']}")
        # T13: only missing must-haves (and, for a human decision, unclear must-haves) may be named as reasons
        allowed = [r for r in reqs.values() if r["kind"] == "must" and
                   (r["decision"] == "MISSING" or (human and r["decision"] == "UNCERTAIN"))]
        for r in reqs.values():
            if r not in allowed and _named_distinctly(r, letter, allowed):
                errors.append(f"reject letter names {r['req_id']} ({r['kind']}, {r['decision']}), which is not a "
                              f"missing must-have")

    flags_text = free["flags_for_recruiter"]
    for f in sorted(expected_flags(record)):
        if not re.search(FLAG_WORDS[f], flags_text):
            errors.append(f"flag dropped: {f}")
    return errors
