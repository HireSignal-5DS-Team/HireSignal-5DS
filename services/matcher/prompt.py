# Adapted from team V2: matcher/prompt.py (format_knowledge, fence_safe, user_message) (feature/agent-integration @ a5a03ff)
"""Matcher prompt matcher-v1 (prompts/matcher/v1.md): load it, fill the user template, parse the reply strictly.

Moved here from scripts/smoke_matcher.py (T02b/T03) so the station API and the eval scripts share one copy.
"""
import json

from services.prompts import prompt_blocks

CLASSES = ("MET", "MISSING", "UNCERTAIN")
BASES = ("supported", "contradicted", "not_documented", "ambiguous")
KEYS = {"decision", "basis", "evidence", "explanation"}
# V2 decoding for the Matcher: matcher/backends_api.py:124-125 (temperature 0, top_p 1, seed 0), max_tokens 192
# (backends_api.py:56; run config of qwen3-4b-q4+hslora-rag-val). repeat_penalty 1.1 = the llama-cpp-python server
# default V2 ran with (llama_cpp/server/types.py:64-65); set explicitly because llama-server's default differs.
DECODING = {"temperature": 0, "top_p": 1, "seed": 0, "max_tokens": 192, "repeat_penalty": 1.1}


def load_prompt(path="prompts/matcher/v1.md"):
    """System text and user template from the fenced blocks under '## System' and '## User template'."""
    blocks = prompt_blocks(path)
    return blocks["System"], blocks["User template"]


def format_knowledge(refs, max_chars=300):
    if not refs:
        return "(none retrieved)"
    return "\n".join(f"[{r['source_id'].rsplit('/', 1)[-1][:12]}] {r['text'][:max_chars]}" for r in refs)


def fence_safe(text):
    return text.replace("<<<", "‹‹‹").replace(">>>", "›››")


def user_message(template, cv_text, req, refs):
    years = f" (minimum {req['min_years']:g} years)" if req.get("min_years") else ""
    return (template.replace("{cv}", fence_safe(cv_text)).replace("{kind}", req["kind"])
            .replace("{category}", req["category"]).replace("{years}", years)
            .replace("{requirement}", req["text"]).replace("{knowledge}", format_knowledge(refs)))


def parse_strict(raw):
    """Valid = the whole reply is one JSON object with exactly the 4 keys, valid labels, <=3 string quotes."""
    try:
        obj = json.loads(raw.strip())
    except (json.JSONDecodeError, AttributeError):
        return None
    ok = (isinstance(obj, dict) and set(obj) == KEYS and obj["decision"] in CLASSES and obj["basis"] in BASES
          and isinstance(obj["evidence"], list) and len(obj["evidence"]) <= 3
          and all(isinstance(q, str) for q in obj["evidence"])
          and isinstance(obj["explanation"], str) and len(obj["explanation"]) <= 600)
    return obj if ok else None
