"""Prompt for one requirement. Shared by inference, benchmark and LoRA training (one format everywhere)."""
import json

PROMPT_VERSION = "p1"

SYSTEM = (
    "You check ONE job requirement against ONE anonymized CV. Reply with a single JSON object and nothing else:\n"
    '{"decision": "MET|MISSING|UNCERTAIN", "basis": "supported|contradicted|not_documented|ambiguous", '
    '"evidence": ["exact quote copied from the CV"], "explanation": "one or two sentences"}\n'
    "Rules:\n"
    "- MET + supported: the CV clearly shows the requirement. Quote the CV word for word.\n"
    "- MISSING + contradicted: the CV shows the requirement is not met (e.g. fewer years). Quote it.\n"
    "- MISSING + not_documented: the CV says nothing about it. evidence = [].\n"
    "- UNCERTAIN + ambiguous: unclear, partial or only implied.\n"
    "- Knowledge entries explain what a skill means and its other names. They are NOT evidence about the candidate.\n"
    "- Never invent skills, years, degrees or certificates."
)


def format_knowledge(refs, max_chars=300):
    if not refs:
        return "(none retrieved)"
    return "\n".join(f"[{r.source_id.rsplit('/', 1)[-1][:12]}] {r.text[:max_chars]}" for r in refs)


def fence_safe(text):
    """CV text cannot close or reopen the CV block (prompt injection, QA-007): delimiter runs are neutralised."""
    return text.replace("<<<", "\u2039\u2039\u2039").replace(">>>", "\u203a\u203a\u203a")


def user_message(cv, req, refs):
    years = f" (minimum {req.min_years:g} years)" if req.min_years else ""
    return (f"CV:\n<<<\n{fence_safe(cv.text)}\n>>>\n\n"
            f"Requirement ({req.kind}-have, {req.category}){years}: {req.text}\n\n"
            f"Knowledge (terminology only, not candidate evidence):\n{format_knowledge(refs)}\n\nJSON:")


def messages(cv, req, refs):
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_message(cv, req, refs)}]


def target(answer):
    """Training target string for a gold ModelAnswer (same key order as SYSTEM)."""
    return json.dumps(answer.model_dump(), ensure_ascii=False)
