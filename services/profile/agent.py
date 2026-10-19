# Adapted from team V2: agents/profile/agent.py (feature/agent-integration @ a5a03ff)
"""The whole Profile Agent: Reader text -> (Matcher CV, identity file).

    1. find identity ─► 2. hide it ─► 3. leak check ─► 4. parse the anonymised text with Qwen
"""

from __future__ import annotations

from .anonymise import AnonymisedCV, anonymise_cv
from .parse import CHUNK_CHARS, parse_cv
from .prompts import PROMPT_VERSION


def run_profile_agent(text: str, cv_id: str | None = None, backend=None, sections: dict | None = None,
                      detectors: list | tuple = (), prompt_version: str = PROMPT_VERSION,
                      chunk_chars: int = CHUNK_CHARS, audit=None) -> AnonymisedCV:
    """Steps 1-3 always; step 4 when a backend (the shared plain Qwen) is given.
    audit (T11): the Bias Auditor's leakage check, text -> (text, flags), applied to the anonymised text before
    step 4 and before the Matcher.

    Step 4 only ever sees `result.text`, the anonymised CV."""
    result = anonymise_cv(text, cv_id=cv_id, sections=sections, detectors=detectors)
    if audit is not None:
        result.text, result.bias_flags = audit(result.text)
    if backend is not None:
        result.profile = parse_cv(result.text, result.cv_id, backend, prompt_version, chunk_chars=chunk_chars)
    return result
