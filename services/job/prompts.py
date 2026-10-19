"""Job Agent prompt: prompts/job/v1.md (= V2 job-q1, plain Qwen3-4B, requirement sections in small chunks).

Replaces V2 agents/job/prompts.py, which also held the NuExtract versions job-v1..v4 (not used here).
"""
import json

from services.prompts import chat_prompt, prompt_blocks

CATEGORIES = ["skill", "experience", "education", "certification", "language", "other"]
PROMPT_VERSION = "job-v1"
FILES = {"job-v1": "prompts/job/v1.md"}


def get_prompt(version: str | None = None) -> tuple[str, list[dict]]:
    """(system instructions, few-shot examples) for a prompt version."""
    return chat_prompt(FILES[version or PROMPT_VERSION])


def title_template(version: str | None = None) -> str:
    return json.dumps(json.loads(prompt_blocks(FILES[version or PROMPT_VERSION])["Title template"]), indent=4)
