"""Profile Agent: Reader text -> anonymised CV for the Matcher + identity file kept local.

    1. find identity ─► 2. hide it ─► 3. leak check ─► 4. parse skills / education / experience (Qwen)
"""

from .agent import run_profile_agent

from .anonymise import AnonymisedCV, anonymise_cv, anonymise_reader, leak_check, new_cv_id
from .detect import Span, detect_rules
from .ner import GlinerPII, ResumeNER, make_detectors
from .parse import parse_cv
from .prompts import PROMPT_VERSION

__all__ = ["run_profile_agent", "AnonymisedCV", "anonymise_cv", "anonymise_reader", "leak_check", "new_cv_id", "Span",
           "detect_rules", "GlinerPII", "ResumeNER", "make_detectors", "parse_cv", "PROMPT_VERSION"]
