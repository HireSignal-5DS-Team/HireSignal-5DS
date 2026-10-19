"""Job Agent prompts: prompts/job/v<N>.md (v1 = V2 job-q1, plain Qwen3-4B, requirement sections in small chunks).

Replaces V2 agents/job/prompts.py, which also held the NuExtract versions job-v1..v4 (not used here).
The production version comes from JOB_PROMPT_VERSION (.env), default PROMPT_VERSION (T15).
"""
import json
from services.config import env  # loads .env

from services.prompts import chat_prompt, prompt_blocks

CATEGORIES = ["skill", "experience", "education", "certification", "language", "other"]
FILES = {"job-v1": "prompts/job/v1.md", "job-v2": "prompts/job/v2.md"}
PROMPT_VERSION = env("JOB_PROMPT_VERSION", "job-v2")  # T15: v2 chosen on dev


def get_prompt(version: str | None = None) -> tuple[str, list[dict]]:
    """(system instructions, few-shot examples) for a prompt version."""
    version = version or PROMPT_VERSION
    if version not in FILES:
        raise ValueError(f"unknown Job Agent prompt {version!r}; choose from {sorted(FILES)}")
    return chat_prompt(FILES[version])


def title_template(version: str | None = None) -> str:
    return json.dumps(json.loads(prompt_blocks(FILES["job-v1"])["Title template"]), indent=4)
