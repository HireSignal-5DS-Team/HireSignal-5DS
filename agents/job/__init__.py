"""Job Agent: job offer -> requirements card, with NuExtract-2.0-2B (job-v*) or the team's Qwen3-4B (job-q*)."""

from .agent import JobAgentError, run_job_agent
from .backend import BackendError, FakeBackend, NuExtractClient, QwenChatClient, make_backend
from .prompts import PROMPT_VERSION, VERSIONS

__all__ = ["run_job_agent", "JobAgentError", "NuExtractClient", "FakeBackend",
           "BackendError", "PROMPT_VERSION", "VERSIONS", "QwenChatClient", "make_backend"]
