"""Bias Auditor (station 5, T11): the decision must not depend on who the candidate is. Plain code ("the LLM judges,
code counts"); the live swap test reuses the Matcher and the Judge, no new model.

1. Leakage check (every CV, fast): on the ANONYMISED text, before the Matcher sees it (applied in /profile):
   - a line that starts with a protected label (nationality, date of birth, marital status, native language,
     pronouns, religion, photo ...; config/bias_lexicon.json) is removed;
   - a line left with only placeholders ([NAME], [ADDRESS], ...; optionally behind a short label such as
     "Location:") is removed: it carries nothing job-relevant, and its form can still tell groups apart;
   - protected words in running text ("married", "years old", religion words ...) are masked as [PERSONAL].
   Flags never carry the removed text (it is the protected signal): only kind, rule and line number.
2. Live swap test (only when the gate would decide automatically: invite or reject): build ONE counterfactual of the
   raw CV (the candidate's name replaced, or a name added, with the other gender and another origin + pronouns), run
   it through the same Reader -> anonymiser -> leakage check. If the Matcher input is byte-identical to the original
   one, the decisions cannot change (same input, temperature 0): no LLM call. Otherwise re-run /match + /judge on the
   must-have requirements; any changed decision -> review reason `bias:swap_flip` (the gate then answers review).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEXICON = ROOT / "config" / "bias_lexicon.json"
SWAP_FLIP = "bias:swap_flip"
# counterfactual identities for the live swap (T11, documented): the other gender and another origin than the
# candidate's (when unknown, the default is a female Arab name: a group often disadvantaged in hiring)
SWAP_DEFAULT = ("Fatma Trabelsi", "she/her")
SWAP_IF_FEMALE = ("James Miller", "he/him")
FEMALE_HINT = re.compile(r"(?i)\b(?:she/her|she|her|hers|herself|mrs|ms|miss|madame|mme)\b")


@lru_cache(maxsize=4)
def lexicon(path: str = str(LEXICON)) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _label_re(lex: dict) -> re.Pattern:
    labels = sorted({w for ws in lex["labels"].values() for w in ws}, key=len, reverse=True)
    return re.compile(r"(?i)^[ \t]*(?:[-•*·][ \t]*)?(?P<label>" + "|".join(re.escape(x) for x in labels) +
                      r")[ \t]*[:：\-–]")


def _word_re(lex: dict) -> re.Pattern:
    words = sorted({w for ws in lex["words"].values() for w in ws}, key=len, reverse=True)
    return re.compile(r"(?i)(?<![\w\[])(?:" + "|".join(re.escape(x) for x in words) + r")(?![\w\]])")


def _kind_of(lex: dict, part: str, value: str) -> str:
    value = value.lower()
    return next((k for k, ws in lex[part].items() if value in [w.lower() for w in ws]), "other")


def _placeholder_only(line: str, lex: dict) -> bool:
    rest = line
    for ph in lex["placeholders"]:
        rest = rest.replace(ph, " ")
    if rest == line:
        return False  # no placeholder at all
    rest = re.sub(r"^[ \t]*[\w .'’\-]{1,30}?[ \t]*[:：][ \t]*", "", rest)  # a short label: "Location: [ADDRESS]"
    return not re.sub(r"[\s|•·,;/()\-–—:.]", "", rest)


def leakage_check(text: str, lex: dict | None = None) -> tuple[str, list[dict]]:
    """(text with protected lines removed and protected words masked, flags [{kind, rule, line, action}])."""
    lex = lex or lexicon()
    label_re, word_re = _label_re(lex), _word_re(lex)
    out, flags = [], []
    for n, line in enumerate(text.split("\n"), 1):
        m = label_re.match(line)
        if m:
            flags.append({"kind": _kind_of(lex, "labels", m.group("label")), "rule": "protected label line",
                          "line": n, "action": "line removed"})
            continue
        if _placeholder_only(line, lex):
            flags.append({"kind": "identity placeholder", "rule": "placeholder-only line", "line": n,
                          "action": "line removed"})
            continue
        hits = list(word_re.finditer(line))
        for h in hits:
            flags.append({"kind": _kind_of(lex, "words", h.group(0)), "rule": "protected word", "line": n,
                          "action": "masked [PERSONAL]"})
        out.append(word_re.sub("[PERSONAL]", line) if hits else line)
    return "\n".join(out), flags


def counterfactual(raw_text: str, name: str | None) -> tuple[str, dict]:
    """The raw CV with another identity: the candidate's name replaced everywhere (and pronoun lines changed), or,
    when no name was found, a name + pronouns header added at the top."""
    female = bool(FEMALE_HINT.search(raw_text[:400]))
    cf_name, pronouns = SWAP_IF_FEMALE if female else SWAP_DEFAULT
    if name and name in raw_text:
        text = raw_text.replace(name, cf_name)
        text = re.sub(r"(?im)^(pronouns[ \t]*[:：][ \t]*).*$", lambda m: m.group(1) + pronouns, text)
        how = "name replaced"
    else:
        text = f"{cf_name}\nPronouns: {pronouns}\n{raw_text}"
        how = "name + pronouns added"
    return text, {"counterfactual": "male_western" if female else "female_arab", "how": how}


def swap_decision(original: dict[str, str], swapped: dict[str, str]) -> list[str]:
    """Must-have req_ids whose decision changed under the swap."""
    return [r for r, d in original.items() if r in swapped and swapped[r] != d]
