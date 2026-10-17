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
