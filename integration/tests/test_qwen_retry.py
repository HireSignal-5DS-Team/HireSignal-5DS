"""No-GPU resilience tests for transient HTTP errors in the V2 Qwen adapter."""
import pytest

from agents.job.backend import BackendError, QwenChatClient
from integration.qwen_retry import ResilientQwenChatClient


def client(retries=1):
    return ResilientQwenChatClient(
        base_url="http://127.0.0.1:8082/v1",
        model="Qwen/Qwen3-4B-Instruct-2507",
        max_tokens=768, timeout=180,
        transient_retries=retries, retry_wait_s=0,
    )


@pytest.mark.parametrize("status", (500, 502, 503))
def test_transient_server_error_is_retried_once_then_succeeds(monkeypatch, status):
    calls = []

    def fake_extract(self, text, template, examples):
        calls.append(len(calls))
        if len(calls) == 1:
            raise BackendError(f"Qwen server error {status}: Internal Server Error")
        self.last_call = {"finish_reason": "stop", "completion_tokens": 3}
        return '{"skills": [], "education": [], "experience": []}'

    monkeypatch.setattr(QwenChatClient, "extract", fake_extract)
    llm = client()
    assert llm.extract("synthetic", "JSON only", []) == '{"skills": [], "education": [], "experience": []}'
    assert len(calls) == 2
    assert llm.transient_retry_attempts == 1
    assert llm.last_call["finish_reason"] == "stop"


def test_persistent_500_stays_an_error(monkeypatch):
    calls = []

    def server_down(self, text, template, examples):
        calls.append(1)
        raise BackendError("Qwen server error 500: Internal Server Error")

    monkeypatch.setattr(QwenChatClient, "extract", server_down)
    llm = client()
    with pytest.raises(BackendError, match="server error 500"):
        llm.extract("synthetic", "JSON only", [])
    assert len(calls) == 2
    assert llm.transient_retry_attempts == 1


@pytest.mark.parametrize("reason", [
    "Qwen server error 400: context too long",
    "Qwen server error 422: wrong format",
    "Cannot reach Qwen at http://127.0.0.1:8082/v1 (timed out). Is the server running?",
])
def test_non_transient_errors_are_never_retried(monkeypatch, reason):
    calls = []

    def non_transient(self, text, template, examples):
        calls.append(1)
        raise BackendError(reason)

    monkeypatch.setattr(QwenChatClient, "extract", non_transient)
    llm = client()
    with pytest.raises(BackendError):
        llm.extract("synthetic", "JSON only", [])
    assert len(calls) == 1
    assert llm.transient_retry_attempts == 0


def test_retry_can_be_disabled(monkeypatch):
    calls = []

    def server_down(self, text, template, examples):
        calls.append(1)
        raise BackendError("Qwen server error 500: Internal Server Error")

    monkeypatch.setattr(QwenChatClient, "extract", server_down)
    with pytest.raises(BackendError):
        client(retries=0).extract("synthetic", "JSON only", [])
    assert len(calls) == 1
