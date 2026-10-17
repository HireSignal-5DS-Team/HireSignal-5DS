"""FastAPI contract tests (MOCK models): /api/v2/analyze end to end, its failure modes, and /api/v1/match regression."""
import base64

import pytest
from fastapi.testclient import TestClient

import backend.main as api
from agents.job.backend import BackendError, FakeBackend
from integration import upstream
from integration.tests.test_upstream import CV, JOB, fake_llm, pipeline


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api, "_build_pipeline", lambda: pipeline())
    monkeypatch.setattr(upstream, "upstream_llm", lambda env=None: FakeBackend(fake_llm))
    monkeypatch.setattr("backend.reporter_adapter.render_report", lambda out, title: {"mock_reporter": True, "title": title})
    return TestClient(api.app)


def test_v2_text_cv(client):
    r = client.post("/api/v2/analyze", json={"cv_text": CV, "job_text": JOB})
    assert r.status_code == 200, r.text
    out = r.json()
    assert [s["stage"] for s in out["stages"]] == ["reader", "profile", "job_agent", "matcher_pipeline", "reporter"]
    assert len(out["requirements"]) == 2 and out["reporter"]["mock_reporter"]
    assert "Amira" not in r.text


def test_v2_file_cv_base64(client):
    b64 = base64.b64encode(CV.encode()).decode()
    r = client.post("/api/v2/analyze", json={"cv_file_b64": b64, "cv_file_name": "cv.txt", "job_text": JOB})
    assert r.status_code == 200, r.text
    assert r.json()["stages"][0]["file_type"] == "text"


@pytest.mark.parametrize("body,code", [
    ({"cv_text": CV}, 400),                                                     # no job text
    ({"cv_text": CV, "cv_file_b64": "eA==", "job_text": JOB}, 400),             # both CV inputs
    ({"cv_file_b64": "%%%", "cv_file_name": "cv.pdf", "job_text": JOB}, 400),   # bad base64
    ({"cv_file_b64": "eA==", "cv_file_name": "cv.exe", "job_text": JOB}, 422),  # unsupported type
    ({"cv_file_b64": base64.b64encode(b"%PDF-1.4 junk").decode(), "cv_file_name": "cv.pdf", "job_text": JOB}, 422),
])
def test_v2_bad_inputs(client, body, code):
    assert client.post("/api/v2/analyze", json=body).status_code == code


def test_v2_model_down_returns_stages_and_no_result(client, monkeypatch):
    class Down:
        def extract(self, *a):
            raise BackendError("connection refused")

        def info(self):
            return {"model": "down"}

    monkeypatch.setattr(upstream, "upstream_llm", lambda env=None: Down())
    r = client.post("/api/v2/analyze", json={"cv_text": CV, "job_text": JOB})
    assert r.status_code == 502
    body = r.json()
    assert body["stages"][-1]["status"] == "failed" and "requirements" not in body


def test_v1_match_still_works(client):
    from integration.tests.test_contract import EX
    import json
    r = client.post("/api/v1/match", json={"cv": json.loads((EX / "cv.json").read_text()),
                                           "job": json.loads((EX / "job.json").read_text())})
    assert r.status_code == 200, r.text
    from integration.contract import validate_output
    validate_output(r.json())
    assert "stages" not in r.json() and len(r.json()["requirements"]) == 3

def test_v2_progress_tracks_stages_without_storing_candidate_text(client):
    import uuid
    token = str(uuid.uuid4())
    before = client.get(f"/api/v2/progress/{token}")
    assert before.status_code == 404
    response = client.post("/api/v2/analyze", json={"cv_text": CV, "job_text": JOB, "progress_id": token})
    assert response.status_code == 200, response.text
    progress = client.get(f"/api/v2/progress/{token}")
    assert progress.status_code == 200, progress.text
    data = progress.json()
    assert data["status"] == "completed"
    assert [x["stage"] for x in data["stages"]] == [
        "reader", "profile", "job_agent", "matcher_pipeline", "reporter"
    ]
    assert all(x["status"] == "ok" for x in data["stages"])
    assert "Amira" not in progress.text and "Python" not in progress.text


def test_v2_progress_rejects_invalid_tokens(client):
    response = client.post("/api/v2/analyze", json={
        "cv_text": CV, "job_text": JOB, "progress_id": "fake"
    })
    assert response.status_code == 422
    assert client.get("/api/v2/progress/fake").status_code == 404


def test_v2_progress_records_failure_without_cv_content(client, monkeypatch):
    import uuid
    from agents.job.backend import BackendError
    class Down:
        def extract(self, *_args):
            raise BackendError("connection refused")
    monkeypatch.setattr(upstream, "upstream_llm", lambda env=None: Down())
    token = str(uuid.uuid4())
    response = client.post("/api/v2/analyze", json={
        "cv_text": CV, "job_text": JOB, "progress_id": token,
    })
    assert response.status_code == 502
    progress = client.get(f"/api/v2/progress/{token}").json()
    assert progress["status"] == "failed"
    assert progress["stages"][0]["stage"] == "reader"
    assert progress["stages"][1]["status"] == "failed"
    assert "Amira" not in str(progress)


def test_v2_recovers_from_one_qwen_500_with_real_adapter_contract(client, monkeypatch):
    from agents.job.backend import QwenChatClient
    from integration.qwen_retry import ResilientQwenChatClient

    calls = []
    def transient_then_valid(self, text, template, examples):
        calls.append(1)
        if len(calls) == 1:
            raise BackendError("Qwen server error 500: Internal Server Error")
        self.last_call = {"finish_reason": "stop"}
        return fake_llm(text, template)

    monkeypatch.setattr(QwenChatClient, "extract", transient_then_valid)
    monkeypatch.setattr(upstream, "upstream_llm",
                        lambda env=None: ResilientQwenChatClient(
                            base_url="http://127.0.0.1:8082/v1",
                            model="Qwen/Qwen3-4B-Instruct-2507",
                            retry_wait_s=0,
                        ))
    response = client.post("/api/v2/analyze", json={"cv_text": CV, "job_text": JOB})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["stages"][1]["status"] == "ok"
    assert body["stages"][1]["transient_server_retries"] == 1
    assert body["stages"][2]["transient_server_retries"] == 0
    assert all(stage["status"] == "ok" for stage in body["stages"])
    assert "Amira" not in response.text


def test_v2_still_fails_on_persistent_qwen_500(client, monkeypatch):
    from agents.job.backend import QwenChatClient
    from integration.qwen_retry import ResilientQwenChatClient

    calls = []
    def always_fails(self, text, template, examples):
        calls.append(1)
        raise BackendError("Qwen server error 500: Internal Server Error")

    monkeypatch.setattr(QwenChatClient, "extract", always_fails)
    monkeypatch.setattr(upstream, "upstream_llm",
                        lambda env=None: ResilientQwenChatClient(
                            base_url="http://127.0.0.1:8082/v1",
                            model="Qwen/Qwen3-4B-Instruct-2507",
                            retry_wait_s=0,
                        ))
    response = client.post("/api/v2/analyze", json={"cv_text": CV, "job_text": JOB})
    assert response.status_code == 502
    assert len(calls) == 2
    body = response.json()
    assert body["stages"][1]["status"] == "failed"
    assert not body.get("requirements")
