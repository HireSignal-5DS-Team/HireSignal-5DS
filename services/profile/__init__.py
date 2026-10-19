"""Profile Agent: Reader text -> anonymised CV (code) + parsed profile (LLM on the anonymised text only).

V2's optional NER detectors (agents/profile/ner.py, off in V2) are not copied: rules only.
"""
from .agent import run_profile_agent
from .anonymise import AnonymisedCV, anonymise_cv, anonymise_reader, leak_check, new_cv_id
from .detect import Span, detect_rules
from .parse import parse_cv
from .prompts import PROMPT_VERSION

__all__ = ["run_profile_agent", "AnonymisedCV", "anonymise_cv", "anonymise_reader", "leak_check", "new_cv_id",
           "Span", "detect_rules", "parse_cv", "PROMPT_VERSION"]
