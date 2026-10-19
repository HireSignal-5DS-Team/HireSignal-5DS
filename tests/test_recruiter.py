"""T19: recruiter flow (services/recruiter.py): card validation + merge, batch (max 3, 409, same card for every
candidate), no token anywhere, identity never in logs / audit / n8n, no score-based ordering."""
import asyncio
import json
import logging
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from services import api, recruiter, ui

ROOT = recruiter.ROOT
TOKEN = "t19-secret-token-0123456789"
CARD = json.loads((ROOT / "demo/invite_P50_requirements_J4.json").read_text(encoding="utf-8"))
NAME, EMAIL = "Zyxa Qwertova", "zyxa.qwertova@example.org"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("WEBHOOK_TOKEN", TOKEN)
    monkeypatch.setattr(recruiter, "PRIVATE", tmp_path / "private")
    monkeypatch.setattr(recruiter, "OUTBOX", tmp_path / "outbox")
    monkeypatch.setattr(recruiter, "AUDIT", tmp_path / "outbox" / "decision_log.jsonl")
    monkeypatch.setattr(ui, "_lock", asyncio.Lock())
    recruiter._batch.clear()
    ui._state.clear()
    ui._state["active"] = False
    with TestClient(api.app) as c:  # one event loop for the whole test: the batch runs as a background task
        yield c


def fake_result(i: int, outcome: str, score: int) -> dict:
    return {"workflow": "HireSignal v1", "execution_id": str(100 + i), "cv_id": f"cv-0000000{i}", "outcome": outcome,
            "score": score, "decided_by": "gate", "review_form_url": None, "job_title": "Python BackEnd Developer",
            "reasons": [], "requirements": [{"req_id": "r1", "kind": "must", "text": "Python", "decision": "MET",
                                              "quotes": [{"quote": "Python", "start": 0, "end": 6}],
                                              "judge": {"verdict": "PASS"}, "review_reasons": []},
                                             {"req_id": "r2", "kind": "nice", "text": "AWS", "decision": "MISSING",
                                              "quotes": [], "judge": {"verdict": "NOT_APPLICABLE"}, "review_reasons": []}],
            "report": {"candidate_letter": f"Dear candidate,\n\nletter {outcome}.\n\nKind regards", "source": "llm"},
            "reader": {"mode": "late", "review_reasons": []}, "bias": {"swap": {}, "review_reasons": []}}


class FakeN8n:
    """Stands in for the webhook: records what is sent, answers results in a fixed order."""
    sent: list = []
    answers: list = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, files=None, data=None, headers=None):
        FakeN8n.sent.append({"headers": headers, "data": data, "files": {k: v[0] for k, v in files.items()}})
        return httpx.Response(200, json=FakeN8n.answers[len(FakeN8n.sent) - 1])


def run_batch(client, n, answers, monkeypatch):
    monkeypatch.setattr(ui.httpx, "AsyncClient", FakeN8n)
    FakeN8n.sent, FakeN8n.answers = [], answers
    files = [("cvs", (f"Firstname_Lastname_{i}.txt", b"Python developer, 5 years.", "text/plain")) for i in range(n)]
    r = client.post("/ui/batch", files=files, data={"card": json.dumps(CARD), "job_text": "Python job"})
    return r


def wait_done(client):
    for _ in range(200):
        s = client.get("/ui/batch/status").json()
        if s["state"] != "running":
            return s
        time.sleep(0.02)
    raise AssertionError("batch did not finish")


# ---------------------------------------------------------------- card ---

def test_card_validation_gives_the_webhook_format_and_clear_errors(client):
    r = client.post("/ui/card/validate", json=CARD)
    assert r.status_code == 200
    card = r.json()
    assert card["confirmed_by"] == "recruiter (UI)" and len(card["requirements"]) == len(CARD["requirements"])
    assert set(card["requirements"][0]) == {"req_id", "text", "kind", "category", "skill_terms", "min_years", "evidence"}
    bad = client.post("/ui/card/validate", json={"requirements": [{"req_id": "r1", "text": "", "kind": "maybe"},
                                                                   {"req_id": "r1", "text": "SQL", "kind": "must"}]})
    assert bad.status_code == 422 and len(bad.json()["detail"]["errors"]) >= 2
    assert client.post("/ui/card/validate", json={"requirements": []}).status_code == 422


def test_merge_joins_texts_with_or_and_unions_terms():
    reqs = [{"req_id": "r1", "text": "Experience with Pyro", "kind": "must", "skill_terms": ["Pyro"], "min_years": None},
            {"req_id": "r2", "text": "Experience with PyMC3", "kind": "must", "skill_terms": ["PyMC3", "Pyro"], "min_years": 2},
            {"req_id": "r3", "text": "SQL", "kind": "nice", "skill_terms": ["SQL"], "min_years": None}]
    out = recruiter.merge_requirements(reqs, ["r1", "r2"])
    assert [r["req_id"] for r in out] == ["r1", "r3"]
    assert out[0]["text"] == "Experience with Pyro or Experience with PyMC3"
    assert out[0]["skill_terms"] == ["Pyro", "PyMC3"] and out[0]["min_years"] == 2 and out[0]["kind"] == "must"
    with pytest.raises(ValueError):
        recruiter.merge_requirements(reqs, ["r1"])


# --------------------------------------------------------------- batch ---

def test_batch_max_three_and_409_when_busy(client, monkeypatch):
    r = client.post("/ui/batch", files=[("cvs", (f"c{i}.txt", b"x" * 300, "text/plain")) for i in range(4)],
                    data={"card": json.dumps(CARD)})
    assert r.status_code == 422

    class Busy:
        def locked(self):
            return True
    monkeypatch.setattr(ui, "_lock", Busy())
    r = client.post("/ui/batch", files=[("cvs", ("c.txt", b"x" * 300, "text/plain"))], data={"card": json.dumps(CARD)})
    assert r.status_code == 409
    r = client.post("/ui/run", files={"cv": ("c.txt", b"x", "text/plain")}, data={"job_text": "job"})
    assert r.status_code == 409  # /ui/run is blocked by a running batch (same lock)


def test_batch_sends_the_same_card_to_every_candidate_and_no_file_names(client, monkeypatch, caplog):
    with caplog.at_level(logging.DEBUG):
        r = run_batch(client, 3, [fake_result(1, "reject", 90), fake_result(2, "invite", 10),
                                  fake_result(3, "review", 50)], monkeypatch)
        assert r.status_code == 202
        s = wait_done(client)
    assert s["state"] == "done" and [c["status"] for c in s["candidates"]] == ["done"] * 3
    cards = {c["data"]["requirements"] for c in FakeN8n.sent}
    assert len(FakeN8n.sent) == 3 and len(cards) == 1                              # the SAME card for all
    assert json.loads(cards.pop())["confirmed_by"] == "recruiter (UI)"
    assert all(c["headers"] == {"X-HireSignal-Token": TOKEN} for c in FakeN8n.sent)
    assert all("Firstname" not in c["files"]["cv"] for c in FakeN8n.sent)        # file names never forwarded
    body = json.dumps(s)
    assert TOKEN not in body and "Firstname" not in body
    folder = recruiter.PRIVATE / "batches" / s["batch_id"]
    summary = (folder / "batch_summary.json").read_text(encoding="utf-8")
    assert "Firstname" not in summary and TOKEN not in summary and (folder / "A.json").exists()
    assert all(TOKEN not in rec.getMessage() for rec in caplog.records)


def test_columns_follow_the_gate_outcome_then_upload_order_never_the_score(client, monkeypatch):
    run_batch(client, 3, [fake_result(1, "reject", 99), fake_result(2, "invite", 1), fake_result(3, "invite", 80)],
              monkeypatch)
    s = wait_done(client)
    assert s["order"] == ["B", "C", "A"]  # invite (B before C: upload order, although C's score is higher), reject
    cands = [{"label": "A", "index": 0, "outcome": "review"}, {"label": "B", "index": 1, "outcome": "review"}]
    assert recruiter.column_order(cands) == ["A", "B"]
    assert "score" not in s["candidates"][0]  # the status carries counts, never the score


def test_facts_are_counts():
    f = recruiter.candidate_facts(fake_result(1, "invite", 90))
    assert f == {"must_total": 1, "must_met": 1, "must_unclear": 0, "nice_total": 1, "nice_met": 0, "all_must_met": True}


# ------------------------------------------------------ letters, identity ---

def test_approve_reveal_identity_only_after_approve_and_never_in_logs_or_audit(client, monkeypatch, caplog):
    run_batch(client, 1, [fake_result(1, "invite", 90)], monkeypatch)
    s = wait_done(client)
    bid = s["batch_id"]
    (recruiter.PRIVATE / "cv-00000001.json").write_text(json.dumps({"cv_id": "cv-00000001", "name": NAME,
                                                                    "emails": [EMAIL], "phones": [], "urls": [],
                                                                    "addresses": [], "personal": []}), "utf-8")
    with caplog.at_level(logging.DEBUG):
        assert client.post("/ui/identity", json={"batch_id": bid, "label": "A"}).status_code == 403  # not approved yet
        lt = client.post("/ui/letter", json={"batch_id": bid, "label": "A", "decision": "invite"}).json()
        assert "letter invite" in lt["letter"] and "gate" in lt["how"]
        ap = client.post("/ui/approve", json={"batch_id": bid, "label": "A", "decision": "invite", "letter": lt["letter"]})
        assert ap.status_code == 200 and ap.json()["letter_file"].endswith(f"recruiter_{bid}_A.json")
        idn = client.post("/ui/identity", json={"batch_id": bid, "label": "A"}).json()
        assert idn["name"] == NAME and idn["email"] == EMAIL
    audit = recruiter.AUDIT.read_text(encoding="utf-8")
    assert NAME not in audit and EMAIL not in audit and '"identity_revealed": true' in audit
    assert all(NAME not in rec.getMessage() and EMAIL not in rec.getMessage() for rec in caplog.records)
    assert all(NAME not in json.dumps(c) and EMAIL not in json.dumps(c) for c in FakeN8n.sent)  # never to n8n
    letter_file = (recruiter.OUTBOX / "invite" / f"recruiter_{bid}_A.json").read_text(encoding="utf-8")
    assert NAME not in letter_file and EMAIL not in letter_file


def test_hold_writes_no_letter_and_allows_no_identity(client, monkeypatch):
    run_batch(client, 1, [fake_result(1, "reject", 10)], monkeypatch)
    bid = wait_done(client)["batch_id"]
    ap = client.post("/ui/approve", json={"batch_id": bid, "label": "A", "decision": "hold"}).json()
    assert ap["letter_file"] is None and ap["recruiter_decision"] == "hold"
    assert client.post("/ui/identity", json={"batch_id": bid, "label": "A"}).status_code == 403


def test_review_case_waits_for_the_recruiter_form(client, monkeypatch):
    res = fake_result(1, "review", 50)
    res["review_form_url"] = "http://localhost:5678/form-waiting/101"
    run_batch(client, 1, [res], monkeypatch)
    bid = wait_done(client)["batch_id"]
    lt = client.post("/ui/letter", json={"batch_id": bid, "label": "A", "decision": "invite"}).json()
    assert lt["needs_form"] and lt["letter"] == "" and lt["review_form_url"].endswith("/101")


def test_pages_hold_no_token_and_no_ranking(client):
    page = client.get("/ui/recruiter.html")
    assert page.status_code == 200 and TOKEN not in page.text
    low = page.text.lower()
    for word in ("best match", "leaderboard", "rank #", "top candidate", ".sort((a, b) => b.score", "sort(by score"):
        assert word not in low, word
    assert "b.score" not in low and "score -" not in low  # nothing is ordered by the score
    assert "recruiter.html" in client.get("/ui/").text  # link between the two pages
