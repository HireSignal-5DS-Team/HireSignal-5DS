"""Profile Agent parse prompt: prompts/profile/v1.md (= V2 profile-q1, plain Qwen3-4B)."""
from services.prompts import chat_prompt

PROMPT_VERSION = "profile-v1"
FILES = {"profile-v1": "prompts/profile/v1.md"}


def get_prompt(version: str = PROMPT_VERSION) -> tuple[str, list[dict]]:
    if version not in FILES:
        raise ValueError(f"unknown Profile Agent prompt {version!r}; choose from {sorted(FILES)}")
    return chat_prompt(FILES[version])
