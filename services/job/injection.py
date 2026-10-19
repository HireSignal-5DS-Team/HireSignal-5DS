# Adapted from team V2: integration/upstream.py (injected_sentences) and matcher/validate.py (_INJECT) (feature/agent-integration @ a5a03ff)
"""Prompt-injection filter for untrusted text (job offers, CVs): sentences that address instructions to the model."""
import re

_INJECT = re.compile(r"ignore\s+(all\s+)?(the\s+)?(previous|prior|above|earlier)\s+instructions|^\W*system\s*:|"
                     r"mark\s+(every|all|each|this)\s+requirements?\s+(as\s+)?met", re.I | re.M)
# V1's injection pattern plus instructions addressed to the model ("assistant, ignore your rules").
_INJECT_EXTRA = re.compile(r"\b(ignore|disregard|forget)\s+(all\s+)?(your|the|these|previous|prior)\s+(rules|instructions|prompt)|"
                           r"\b(assistant|AI|model|system)\s*[,:]\s*(ignore|disregard|forget|add|mark|output)", re.I)


# T13 (security tests): messages addressed to an automated screener / report writer, and orders about this candidate
_INJECT_T13 = re.compile(r"\b(?:notes?|messages?|instructions?)\s+(?:to|for)\s+(?:the\s+|any\s+)?(?:ai|llm|model|"
                         r"assistant|system|screener|screening\s+(?:system|tool)|report\s+writer|recruit\w*\s+(?:bot|ai|system))\b|"
                         r"\b(?:report\s+writer|screening\s+(?:system|ai|tool)|ai\s+(?:recruiter|screener|system)|llm|chatgpt)\s*[:,]|"
                         r"\b(?:invite|hire|select|shortlist|accept)\s+this\s+(?:candidate|applicant|person)\b|"
                         r"\b(?:write|say|state|report)\s+that\s+(?:the|this)\s+(?:candidate|applicant)\b", re.I)


def injected_sentences(text):
    """Sentences (or lines) of untrusted text that address instructions to the model."""
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p for p in parts if _INJECT.search(p) or _INJECT_EXTRA.search(p) or _INJECT_T13.search(p)]


def sanitise_injection(text):
    """T14: (text without the detected injection sentences, the removed sentences). Applied to the anonymised CV text
    before the Matcher, the Judge and the Report Writer see it; the pair still goes to review (gate rule 0)."""
    removed = [x.strip() for x in injected_sentences(text) if x.strip()]
    out = text
    for sentence in sorted(set(removed), key=len, reverse=True):
        out = out.replace(sentence, "")
    out = re.sub(r"[ \t]+\n", "\n", out)          # spaces left at a line end
    out = re.sub(r"\n{3,}", "\n\n", out).strip()   # empty lines left by a removed line
    return (out if removed else text), removed
