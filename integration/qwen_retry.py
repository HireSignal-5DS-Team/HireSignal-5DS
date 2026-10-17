"""V2-only bounded recovery from transient upstream Qwen server errors.

The model server can briefly return HTTP 500/502/503 when swapping plain/LoRA
models. Only one additional attempt is allowed, with a short pause.
All prompt parsing, schema grounding and evidence validation remain unchanged.
A persistent or non-transient error is raised unchanged to the caller.
No CV data, messages, outputs or credentials are logged.
"""
from __future__ import annotations

import re
import time

from agents.job.backend import BackendError, QwenChatClient

_TRANSIENT_STATUS = re.compile(r"^Qwen server error (500|502|503):")


class ResilientQwenChatClient(QwenChatClient):
    """Plain-Qwen client with one bounded retry for transient HTTP server errors."""

    def __init__(self, *args, transient_retries: int = 1, retry_wait_s: float = 2.0, **kwargs):
        if not 0 <= transient_retries <= 2:
            raise ValueError("transient_retries must be between 0 and 2")
        if not 0 <= retry_wait_s <= 10:
            raise ValueError("retry_wait_s must be between 0 and 10")
        super().__init__(*args, **kwargs)
        self.transient_retries_allowed = transient_retries
        self.retry_wait_s = retry_wait_s
        self.transient_retry_attempts = 0

    def extract(self, text: str, template: str, examples: list[dict]) -> str:
        for attempt in range(self.transient_retries_allowed + 1):
            try:
                return super().extract(text, template, examples)
            except BackendError as exc:
                # Do not retry 4xx, malformed responses, timeouts, or model errors
                # unrelated to HTTP 500/502/503. Never mask persistent failures.
                if attempt >= self.transient_retries_allowed or not _TRANSIENT_STATUS.match(str(exc)):
                    raise
                self.transient_retry_attempts += 1
                time.sleep(self.retry_wait_s)
        raise AssertionError("unreachable")
