"""Prompt for one requirement. Shared by inference, benchmark and LoRA training (one format everywhere)."""
import json

PROMPT_VERSION = "p2"

# p2: no copyable placeholder values (p1 models echoed "MET|MISSING|UNCERTAIN" and "exact quote copied from the CV").
SYSTEM = (
    "You check ONE job requirement against ONE anonymized CV. Reply with a single JSON object and nothing else, "
    "with exactly these keys:\n"
    '- "decision": one of MET, MISSING, UNCERTAIN\n'
    '- "basis": one of supported, contradicted, not_documented, ambiguous\n'
    '- "evidence": a list of up to 3 strings, each copied character for character from the CV text; [] if none\n'
    '- "explanation": one or two short sentences\n'
    "Rules:\n"
    "- MET with supported: the CV clearly shows the requirement. Copy the CV line that proves it.\n"
    "- MISSING with contradicted: the CV shows the requirement is not met (too few years, or says no experience). Copy that line.\n"
    "- MISSING with not_documented: the CV says nothing about it. evidence is [].\n"
    "- UNCERTAIN with ambiguous: unclear, partial, only implied, or the duration cannot be confirmed.\n"
    "- A related but different skill does not count (another database, programming language, cloud or certificate).\n"
    "- Knowledge entries explain what a skill means and its other names. They are NOT evidence about the candidate.\n"
    "- Never invent skills, years, degrees or certificates. Never quote the requirement or the knowledge as evidence."
)


def format_knowledge(refs, max_chars=300):
    if not refs:
        return "(none retrieved)"
    return "\n".join(f"[{r.source_id.rsplit('/', 1)[-1][:12]}] {r.text[:max_chars]}" for r in refs)


def user_message(cv, req, refs):
    years = f" (minimum {req.min_years:g} years)" if req.min_years else ""
    return (f"CV:\n<<<\n{cv.text}\n>>>\n\n"
            f"Requirement ({req.kind}-have, {req.category}){years}: {req.text}\n\n"
            f"Knowledge (terminology only, not candidate evidence):\n{format_knowledge(refs)}\n\nJSON:")


def messages(cv, req, refs):
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_message(cv, req, refs)}]


def target(answer):
    """Training target string for a gold ModelAnswer (same key order as SYSTEM)."""
    return json.dumps(answer.model_dump(), ensure_ascii=False)
