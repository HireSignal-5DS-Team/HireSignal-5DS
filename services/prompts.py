"""Load a versioned prompt file (prompts/<station>/v<N>.md, CLAUDE.md rule 8): the fenced block under each '## <heading>'."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prompt_blocks(path) -> dict[str, str]:
    md = (ROOT / path).read_text(encoding="utf-8")
    return {h: body for h, body in re.findall(r"^## (.+?)\s*\n+```\w*\n(.*?)\n```", md, re.S | re.M)}


def chat_prompt(path) -> tuple[str, list[dict]]:
    """(system text, few-shot examples [{input, output}]) of a prompt file with '## System' and '## Examples'."""
    blocks = prompt_blocks(path)
    return blocks["System"], json.loads(blocks.get("Examples", "[]"))
