"""T16: demo page support (services/ui.py): progress shape, token never exposed, one run at a time, contracts unchanged."""
import json
import logging

import pytest
from fastapi.testclient import TestClient

from services import api, ui

TOKEN = "t16-secret-token-0123456789"
OUTCOME_BODY = {"requirements": [{"req_id": "r1", "kind": "must", "decision": "MISSING"}]}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("WEBHOOK_TOKEN", TOKEN)
    ui._state.clear()
    ui._state["active"] = False
    ui._last.clear()
    return TestClient(api.app)


class FakeAsyncClient:
    sent = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, files=None, data=None, headers=None):
        FakeAsyncClient.sent.append({"url": url, "headers": headers, "data": data, "files": list(files)})
        import httpx
        return httpx.Response(200, json={"outcome": "reject", "score": 14, "requirements": [], "workflow": "HireSignal v1"})


def test_page_is_served_offline(client):
    r = client.get("/ui/")
    assert r.status_code == 200 and "Agent timeline" in r.text
    assert "http://" not in r.text.replace("http://127.0.0.1", "") and "https://" not in r.text  # no CDN, no internet
    assert TOKEN not in r.text and "WEBHOOK_TOKEN" not in r.text


def test_progress_shape(client):
    p = client.get("/ui/progress").json()
    assert p == {"active": False, "stages": {}}
    ui._reset(3)
    p = client.get("/ui/progress").json()
    assert p["active"] is True and p["total_requirements"] == 3 and p["stages"] == {} and "elapsed_s" in p


def test_run_forwards_with_the_token_and_never_returns_it(client, monkeypatch, caplog):
    monkeypatch.setattr(ui.httpx, "AsyncClient", FakeAsyncClient)
    FakeAsyncClient.sent.clear()
    card = json.dumps({"requirements": [{"req_id": "r1"}, {"req_id": "r2"}]})
    with caplog.at_level(logging.DEBUG):
        r = client.post("/ui/run", files={"cv": ("cv.txt", b"Python developer", "text/plain"),
                                          "requirements": ("card.json", card.encode(), "application/json")},
                        data={"job_text": "Requirements: Python"})
    assert r.status_code == 200 and r.json()["outcome"] == "reject"
    sent = FakeAsyncClient.sent[0]
    assert sent["headers"] == {"X-HireSignal-Token": TOKEN}           # the server adds it ...
    assert sent["data"]["requirements"] == card and sent["url"].endswith("/webhook/hiresignal")
    assert TOKEN not in r.text and TOKEN not in json.dumps(dict(r.headers))  # ... and it never comes back
    p = client.get("/ui/progress")
    assert TOKEN not in p.text and p.json()["total_requirements"] == 2 and p.json()["active"] is False
    assert TOKEN not in client.get("/ui/last-result").text
    assert all(TOKEN not in rec.getMessage() for rec in caplog.records)


def test_one_run_at_a_time(client, monkeypatch):
    class Busy:
        def locked(self):
            return True
    monkeypatch.setattr(ui, "_lock", Busy())
    r = client.post("/ui/run", files={"cv": ("cv.txt", b"x", "text/plain")}, data={"job_text": "job"})
    assert r.status_code == 409 and r.json()["detail"] == "A run is already in progress"


def test_bad_card_and_missing_job_are_clear_errors(client):
    r = client.post("/ui/run", files={"cv": ("cv.txt", b"x", "text/plain")}, data={"job_text": " "})
    assert r.status_code == 422
    r = client.post("/ui/run", files={"cv": ("cv.txt", b"x", "text/plain"), "requirements": ("c.json", b"{", "application/json")},
                    data={"job_text": "job"})
    assert r.status_code == 422


def test_middleware_records_a_stage_and_keeps_the_response_identical(client):
    before = client.post("/outcome", json=OUTCOME_BODY)
    ui._reset(1)
    during = client.post("/outcome", json=OUTCOME_BODY)
    assert during.status_code == before.status_code == 200
    assert during.json() == before.json()                         # contract unchanged
    s = client.get("/ui/progress").json()["stages"]["outcome"]
    assert s["status"] == "done" and s["summary"].startswith("reject") and s["calls"] == 1


def test_middleware_records_nothing_outside_a_ui_run(client):
    client.post("/outcome", json=OUTCOME_BODY)
    assert client.get("/ui/progress").json()["stages"] == {}


def test_summaries_carry_no_cv_text():
    line, _ = ui.summarise("profile", {"anonymised_text": "SECRET CV TEXT", "profile": {"skills": [1, 2], "experience": [],
                                                                                       "education": [1]}}, None)
    assert "SECRET" not in line and line.startswith("anonymised; 2 skills")
    line, extra = ui.summarise("match", {"req_id": "r7", "decision": "MET", "evidence": [{"quote": "SECRET"}]}, None)
    assert line == "r7: MET" and extra == {"req_id": "r7"}
