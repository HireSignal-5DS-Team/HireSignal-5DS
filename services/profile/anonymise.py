# Adapted from team V2: agents/profile/anonymise.py (feature/agent-integration @ a5a03ff)
"""Steps 2 and 3 of the Profile Agent: hide the identity, then check nothing leaked.

    Reader text ─► 1. find identity ─► 2. hide it ─► 3. leak check ─┬─► anonymised text + identity
                    (detect.py, ner.py)                ▲             │
                                                       └─ leak: hide ┘   (still a leak -> human review)

Hiding is privacy-first: when two findings overlap, the union is hidden. Once the
name is known, EVERY form of it is hidden: full name, each part ("SMITH", "John"),
"J. Smith", accents or capitals changed. The leak check then searches the result
again, like an attacker would: the identity values, the name glued inside a token
("johnsmith92"), the same phone written differently, and fresh pattern matches.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field

from services.profile.contracts import Identity, ParsedCV, PersonalItem, PrivacyReport

from .gender import neutralise_gender
from .detect import (AGE_RES, DOB_RE, HONORIFIC_RE, PLACEHOLDER, PRIORITY, Span, _digits, _is_particle,
                     detect_rules, find_emails, find_phones, find_urls, fold, header_region, name_parts,
                     private_regions, references_region)

NER_SOURCES = ("resume-ner", "gliner")
PROXY_KINDS = ("DOB", "AGE", "GENDER", "HONORIFIC", "NATIONALITY", "MARITAL", "BIRTHPLACE", "RELIGION")
_PLACEHOLDER_RE = re.compile(r"\[(?:NAME|EMAIL|PHONE|URL|ADDRESS|PERSONAL|PRONOUN)\]")


# ------------------------------------------------------------------ helpers ---

def merge(spans: list[Span], text: str | None = None) -> list[Span]:
    """Overlapping spans become one span covering both (kind of the higher priority)."""
    out: list[Span] = []
    for sp in sorted(spans, key=lambda s: (s.start, -s.end)):
        if out and sp.start < out[-1].end:
            last = out[-1]
            kind = max((last.kind, sp.kind), key=lambda k: PRIORITY.get(k, 3))
            end = max(last.end, sp.end)
            out[-1] = Span(last.start, end, kind, text[last.start:end] if text else "", last.source)
        else:
            out.append(sp)
    return out


def apply_masks(text: str, spans: list[Span]) -> str:
    pieces, pos = [], 0
    for sp in merge(spans):
        pieces += [text[pos:sp.start], PLACEHOLDER[sp.kind]]
        pos = sp.end
    pieces.append(text[pos:])
    out = "".join(pieces)
    # "[NAME] [NAME]" (first name and surname found separately) -> "[NAME]"
    out = re.sub(r"\[NAME\](?:[ \t\-]+\[NAME\])+", "[NAME]", out)
    out = re.sub(r"\[PERSONAL\](?:[ \t]+\[PERSONAL\])+", "[PERSONAL]", out)
    return out


def _find_all(text: str, value: str, kind: str, source: str, *, capitalised: bool = False) -> list[Span]:
    """Every whole-word occurrence of value, ignoring case and accents (same length folding)."""
    value = value.strip()
    if not value:
        return []
    words = [re.escape(w) for w in re.split(r"[\s\-]+", fold(value)) if w]
    # letters/digits only as word edges, so "John_Smith_CV.pdf" and "john.smith" are found too
    pattern = re.compile(r"(?<![^\W_])" + r"[\s\-_.]+".join(words) + r"(?![^\W_])")
    out = []
    for m in pattern.finditer(fold(text)):
        if capitalised and not text[m.start()].isupper():
            continue
        out.append(Span(m.start(), m.end(), kind, text[m.start():m.end()], source))
    return out


def name_variants(name: str) -> list[tuple[str, bool]]:
    """(variant, must_be_capitalised): full name and runs of its parts, each single part, 'J. Smith'."""
    parts = name_parts(name)
    out: list[tuple[str, bool]] = []
    for size in range(len(parts), 1, -1):                       # longest runs first
        for i in range(len(parts) - size + 1):
            run = parts[i:i + size]
            if not _is_particle(run[-1]):                          # "El Amri" yes, "Yasmine El" no
                out.append((" ".join(run), False))
    real = [p for p in parts if not _is_particle(p)]
    out += [(p, True) for p in real]
    if len(real) >= 2:                                          # "J. Smith", "J Smith"
        out += [(f"{real[0][0]}. {real[-1]}", True), (f"{real[0][0]} {real[-1]}", True),
                (f"{real[-1]} {real[0][0]}.", True)]                # "HAMDI N."
    seen, unique = set(), []
    for v, cap in out:
        if fold(v) not in seen:
            seen.add(fold(v))
            unique.append((v, cap))
    return unique


def name_spans(text: str, name: str, source: str = "variant") -> list[Span]:
    spans = []
    for variant, cap in name_variants(name):
        spans += _find_all(text, variant, "NAME", source, capitalised=cap)
    return spans


def value_spans(text: str, identity: Identity, source: str = "variant") -> list[Span]:
    """Every occurrence of every identity value already found (an email repeated in the footer...)."""
    spans = []
    for kind, values in (("EMAIL", identity.emails), ("URL", identity.urls), ("ADDRESS", identity.addresses)):
        for v in values:
            spans += _exact(text, v, kind, source)
    for p in identity.phones:
        spans += _same_phone(text, p, source)
    for item in identity.personal:
        if item.kind in ("DOB", "BIRTHPLACE", "NATIONALITY", "RELIGION") and len(item.value) >= 4:
            spans += _find_all(text, item.value, item.kind, source)
    if identity.name:
        spans += name_spans(text, identity.name, source)
    return spans


def _exact(text: str, value: str, kind: str, source: str) -> list[Span]:
    """Every whole occurrence of value (never part of a longer word; 3+ letters or digits)."""
    low, v = fold(text), fold(value.strip())
    if sum(c.isalnum() for c in v) < 3:
        return []
    out, pos = [], low.find(v)
    while pos >= 0:
        end = pos + len(v)
        cut = (pos > 0 and low[pos - 1].isalnum() and v[0].isalnum()) or (
            end < len(low) and low[end].isalnum() and v[-1].isalnum())
        if not cut:
            out.append(Span(pos, end, kind, text[pos:end], source))
        pos = low.find(v, pos + 1)
    return out


def _same_phone(text: str, phone: str, source: str) -> list[Span]:
    """The same number written another way: '+216 22 345 678' vs '22345678'."""
    key = _digits(phone)[-8:]
    return [Span(sp.start, sp.end, "PHONE", sp.text, source)
            for sp in find_phones(text) if _digits(sp.text).endswith(key)] + _exact(text, phone, "PHONE", source)


# ------------------------------------------------------------------ identity ---

def build_identity(cv_id: str, spans: list[Span], name: str | None, others: tuple[int, int] | None = None) -> Identity:
    """Only the candidate's data. Contacts inside a References section belong to other people:
    they are hidden in the text but not stored."""
    if others:
        spans = [sp for sp in spans if not others[0] <= sp.start < others[1]]

    def uniq(kind):
        seen, out = set(), []
        for sp in spans:
            if sp.kind == kind and fold(sp.text) not in seen and sp.text.strip():
                seen.add(fold(sp.text))
                out.append(sp.text.strip())
        return out

    personal, seen = [], set()
    for sp in spans:
        if sp.kind in PROXY_KINDS and (sp.kind, fold(sp.text)) not in seen:
            seen.add((sp.kind, fold(sp.text)))
            personal.append(PersonalItem(kind=sp.kind, value=sp.text.strip()))
    return Identity(cv_id=cv_id, name=name, emails=uniq("EMAIL"), phones=uniq("PHONE"),
                    urls=uniq("URL"), addresses=uniq("ADDRESS"), personal=personal)


def _pick_name(spans: list[Span], header: tuple[int, int]) -> str | None:
    order = {"label": 0, "header": 1, "email": 2}
    rule = sorted((sp for sp in spans if sp.kind == "NAME" and sp.source in order), key=lambda s: order[s.source])
    if rule and rule[0].source == "label":                  # "Prénom : Mohamed Ali" + "Nom : Ben Salah"
        return " ".join(sp.text.strip() for sp in rule if sp.source == "label")
    if rule:
        return rule[0].text.strip()
    # no rule found it: the first NER person inside the header
    ner = [sp for sp in spans if sp.kind == "NAME" and sp.source not in ("titled", "variant")
           and sp.start < header[1] and len(name_parts(sp.text)) >= 2]
    return min(ner, key=lambda s: s.start).text.strip() if ner else None


# ---------------------------------------------------------------- leak check ---

def leak_check(anon: str, identity: Identity) -> list[Span]:
    """Search the anonymised text again. Every hit is a leak (a span on `anon`)."""
    hits = [sp for sp in value_spans(anon, identity, "leak-check") if not _PLACEHOLDER_RE.fullmatch(sp.text)]
    # fresh pattern matches the first pass missed
    hits += find_emails(anon) + find_phones(anon)
    hits += [sp for sp in find_urls(anon) if not _PLACEHOLDER_RE.search(sp.text)]
    for rx, kind in [(DOB_RE, "DOB"), (HONORIFIC_RE, "HONORIFIC")] + [(rx, "AGE") for rx in AGE_RES]:
        hits += [Span(m.start("value"), m.end("value"), kind, m.group("value"), "leak-check") for m in rx.finditer(anon)]
    # the name glued inside a token: "johnsmith92", "github.com/jsmith", "@smith_j"
    if identity.name:
        real = [fold(p) for p in name_parts(identity.name) if not _is_particle(p)]
        glued = set()
        if len(real) >= 2:
            glued |= {real[0] + real[-1], real[-1] + real[0], real[0][0] + real[-1]}
        for m in re.finditer(r"\S+", anon):
            token = re.sub(r"[^a-z]", "", fold(m.group(0)))
            urlish = any(c in m.group(0) for c in "@/._")
            if any(g in token for g in glued if len(g) >= 5) or (
                    urlish and any(len(p) >= 4 and p in token for p in real)):
                if not _PLACEHOLDER_RE.fullmatch(m.group(0).strip(".,;:()")):
                    hits.append(Span(m.start(), m.end(), "NAME", m.group(0), "leak-check"))
    # never inside a placeholder: the "S" of "[ADDRESS]" is not a leak
    boxes = [m.span() for m in _PLACEHOLDER_RE.finditer(anon)]
    hits = [h for h in hits if not any(h.start < b1 and b0 < h.end for b0, b1 in boxes)]
    return merge(hits, anon)


# --------------------------------------------------------------------- agent ---

@dataclass
class AnonymisedCV:
    cv_id: str
    text: str                       # anonymised: the only text the Matcher sees
    identity: Identity              # local only
    report: PrivacyReport
    spans: list[Span] = field(default_factory=list, repr=False)   # first-pass findings, for debugging
    profile: ParsedCV | None = None   # step 4, from the anonymised text only
    bias_flags: list[dict] = field(default_factory=list)   # T11 Bias Auditor leakage check (kind / rule / line only)

    def to_matcher_cv(self, reader: dict | None = None) -> dict:
        """The team's Matcher CV {cv_id, text, structured}. Replaces integration.contract.cv_from_reader."""
        structured: dict = {"privacy": self.report.model_dump()}
        if self.profile is not None:
            structured["profile"] = self.profile.model_dump()
        if reader:
            keep = ("file_type", "pages", "page_routes", "layout", "ocr_confidence", "needs_human_review")
            structured["reader"] = {k: reader.get(k) for k in keep if k in reader}
            # the Reader's warnings can quote the CV (or the file name): hide identity there too
            structured["reader"]["warnings"] = [redact(w, self.identity) for w in reader.get("warnings", [])]
        return {"cv_id": self.cv_id, "text": self.text, "structured": structured}


def redact(text: str, identity: Identity) -> str:
    return apply_masks(text, value_spans(text, identity)) if text else text


def new_cv_id() -> str:
    """Random, so it says nothing about the person (a file name often holds the name)."""
    return "cv-" + secrets.token_hex(4)


def anonymise_cv(text: str, cv_id: str | None = None, sections: dict | None = None,
                 detectors: list | tuple = ()) -> AnonymisedCV:
    """Reader text -> anonymised text + identity + privacy report."""
    cv_id = cv_id or new_cv_id()
    warnings: list[str] = []
    header = header_region(text, sections)

    # 1. find
    spans = detect_rules(text, sections)
    used = ["rules"]
    for det in detectors:
        found = det(text)
        if getattr(det, "error", None):
            warnings.append(f"{getattr(det, 'name', 'ner')} did not run (model or library missing)")
        else:
            used.append(getattr(det, "name", "ner"))
            regions = private_regions(text, sections)
            rule_spans = [sp for sp in spans if sp.source not in NER_SOURCES]
            spans += [sp for sp in found
                      if (sp.kind != "ADDRESS" or any(r0 <= sp.start < r1 for r0, r1 in regions))
                      # where a rule already found something, the rule wins (more precise kind and edges)
                      and not any(sp.start < r.end and r.start < sp.end for r in rule_spans)]
    name = _pick_name(spans, header)
    if not name:
        warnings.append("candidate name not found: check the anonymised text by hand")
    identity = build_identity(cv_id, spans, name, references_region(text))

    # 2. hide: what was found + every other occurrence of it
    spans_all = spans + value_spans(text, identity)
    anon = apply_masks(text, spans_all)

    # 3. leak check, hide what it finds, check again
    leaks = leak_check(anon, identity)
    fixed = 0
    for _ in range(2):
        if not leaks:
            break
        fixed += len(leaks)
        anon = apply_masks(anon, leaks)
        leaks = leak_check(anon, identity)
    if leaks:
        warnings.append(f"{len(leaks)} possible identity leak(s) left: check the anonymised text by hand")
    if fixed:
        warnings.append(f"leak check hid {fixed} extra piece(s) the first pass missed")

    # 4. gendered pronouns, honorifics and role words in running text (our Decision 17 fix; not in V2)
    anon, gendered = neutralise_gender(anon)

    counts: dict[str, int] = {}
    if gendered.get("neutral role words"):
        counts["neutral role words"] = gendered["neutral role words"]
    for m in _PLACEHOLDER_RE.finditer(anon):
        counts[m.group(0)] = counts.get(m.group(0), 0) + 1
    asked = [getattr(d, "name", "ner") for d in detectors]
    report = PrivacyReport(
        placeholders=counts, detectors=used, name_found=bool(name), leaks_fixed=fixed, leaks_left=len(leaks),
        needs_human_review=bool(leaks) or not name or len(used) - 1 < len(asked), warnings=warnings)
    return AnonymisedCV(cv_id=cv_id, text=anon, identity=identity, report=report, spans=spans)


def anonymise_reader(reader: dict, cv_id: str | None = None, detectors: list | tuple = ()) -> AnonymisedCV:
    """Same, from the Reader's ReaderResult.to_dict()."""
    return anonymise_cv(reader["text"], cv_id=cv_id, sections=reader.get("sections"), detectors=detectors)
