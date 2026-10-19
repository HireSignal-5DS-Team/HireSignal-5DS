"""Station settings from the environment (.env, see config/.env.example). No secret is ever logged or returned."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def llm_settings() -> dict:
    """The OpenAI-compatible LLM endpoint: local llama-server, or the free cloud backup (LLM_BACKEND=cloud)."""
    backend = env("LLM_BACKEND", "local")
    if backend == "cloud":
        return {"backend": "cloud", "base_url": env("CLOUD_LLM_BASE_URL", ""), "model": env("CLOUD_LLM_MODEL", ""),
                "api_key": os.environ.get("CLOUD_LLM_API_KEY") or None, "timeout": float(env("LLM_TIMEOUT_S", "180"))}
    return {"backend": "local", "base_url": env("LLM_BASE_URL", "http://127.0.0.1:8090/v1"),
            "model": env("LLM_MODEL", "qwen3-4b"), "api_key": None, "timeout": float(env("LLM_TIMEOUT_S", "180"))}
