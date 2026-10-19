"""Profile Agent parse prompts: prompts/profile/v<N>.md (v1 = V2 profile-q1, plain Qwen3-4B).

The production version comes from PROFILE_PROMPT_VERSION (.env), default below (T15).
"""
from services.config import env  # loads .env
from services.prompts import chat_prompt

FILES = {"profile-v1": "prompts/profile/v1.md", "profile-v2": "prompts/profile/v2.md", "profile-v3": "prompts/profile/v3.md"}
PROMPT_VERSION = env("PROFILE_PROMPT_VERSION", "profile-v3")  # T15: v3 chosen on dev


def get_prompt(version: str = PROMPT_VERSION) -> tuple[str, list[dict]]:
    if version not in FILES:
        raise ValueError(f"unknown Profile Agent prompt {version!r}; choose from {sorted(FILES)}")
    return chat_prompt(FILES[version])
