"""T10 Reader multimodal: late-fusion merge (code), mode switch, Ollama fallback, review flags (no real Ollama)."""
import json

import httpx
import pytest

from conftest import needs_tesseract
from services.reader import read_cv
from services.reader import multimodal as mm


def test_agreeing_lines_are_kept():
    r = mm.late_fuse("Python developer\nSQL 2020", [90, 90, 90, 90], "Python developer\nSQL 2020", 60)
    assert r["text"] == "Python developer\nSQL 2020" and not r["low_trust_lines"] and r["stats"]["agree"] == 4


def test_disagreement_uses_ocr_word_only_when_confident():
    vision = "Skills: PostgreSQL and Docker"
    low = mm.late_fuse("Skills: P0stgreSQL and Docker", [95, 30, 95, 95], vision, 60)
    high = mm.late_fuse("Skills: P0stgreSQL and Docker", [95, 85, 95, 95], vision, 60)
    assert "PostgreSQL" in low["text"] and "P0stgreSQL" not in low["text"]
    assert "P0stgreSQL" in high["text"]


def test_vision_only_lines_are_low_trust_not_text():
    r = mm.late_fuse("EXPERIENCE\nData engineer", [90, 90, 90],
                     "EXPERIENCE\nData engineer\nLed a team of twelve engineers at Google", 60)
    assert "Google" not in r["text"]
    assert r["low_trust_lines"] == ["Led a team of twelve engineers at Google"]


def test_short_vision_fill_inside_a_line_is_kept():
    r = mm.late_fuse("Python SQL", [90, 90], "Python Spark SQL", 60)
    assert r["text"] == "Python Spark SQL" and r["stats"]["vision_kept_short"] == 1


def test_low_confidence_ocr_noise_is_dropped():
    r = mm.late_fuse("Python\n~~ %% ##\nSQL", [90, 10, 10, 10, 90], "Python\nSQL", 60)
    assert r["text"] == "Python\nSQL" and r["stats"]["ocr_dropped"] == 3


def test_confidences_that_do_not_fit_the_words_count_as_unsure():
    r = mm.late_fuse("a b c", [90], "a x c", 60)  # 3 words, 1 confidence -> all treated as 0
    assert r["text"] == "a x c"


def test_unknown_mode_is_refused(photo_png):
    with pytest.raises(Exception, match="mode"):
        read_cv(photo_png, "photo.png", mode="magic")


def _ollama(reply=None, fail=False):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        if fail:
            raise httpx.ConnectError("refused")
        return httpx.Response(200, json={"message": {"content": reply}, "done_reason": "stop", "eval_count": 9})
    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_ollama_unreachable_falls_back_to_ocr(no_image_encoding):
    client, _ = _ollama(fail=True)
    warnings = []
    page = mm.read_image_page(None, "late", ("OCR text here", 88.0, "single_column", [88, 88, 88]), warnings,
                              client=client)
    assert page["route"] == "ocr (vision fallback)" and page["text"] == "OCR text here"
    assert any("not reachable" in w for w in warnings)


@pytest.fixture
def no_image_encoding(monkeypatch):
    monkeypatch.setattr(mm, "image_b64", lambda image, max_side=None: "AAAA")


def test_mode_switch_routes(no_image_encoding):
    ocr = ("Python developer", 90.0, "single_column", [90, 90])
    client, seen = _ollama("Python developer")
    assert mm.read_image_page(None, "vision", ocr, [], client=client)["route"] == "vision"
    assert mm.read_image_page(None, "late", ocr, [], client=client)["route"] == "late"
    early = mm.read_image_page(None, "early", ocr, [], client=client)
    assert early["route"] == "early" and "Python developer" in seen[-1]["messages"][0]["content"]  # OCR in prompt
    assert seen[0]["keep_alive"] == "0" and seen[0]["messages"][0]["images"] == ["AAAA"]
    assert mm.read_image_page(None, "ocr", ocr, [], client=client)["route"] == "ocr" and len(seen) == 3


def test_fence_around_the_answer_is_removed():
    assert mm.strip_wrapping("```text\nPython\nSQL\n```") == "Python\nSQL"


@needs_tesseract
def test_photo_with_many_unclear_parts_goes_to_review(photo_png, monkeypatch):
    monkeypatch.setattr(mm, "vision_call", lambda image, prompt, model=None, client=None: {
        "text": "[unclear] [unclear] Python [unclear]", "model": "fake", "latency_s": 0.1, "eval_count": 5,
        "done_reason": "stop"})
    r = read_cv(photo_png, "photo.png", mode="vision")
    assert r.page_routes == ["vision"] and r.needs_human_review
    assert "reader:many_unclear_parts" in r.review_reasons


@needs_tesseract
def test_ocr_mode_keeps_the_old_result(photo_png):
    r = read_cv(photo_png, "photo.png")
    assert r.mode == "ocr" and r.page_routes == ["ocr"] and r.page_details == [{"route": "ocr"}]


def test_gate_sends_a_bad_image_to_review_even_with_info_pair_flags():
    from services.outcome.gate import decide
    reqs = [{"req_id": "r1", "kind": "must", "decision": "MISSING", "review_reasons": []}]
    assert decide(reqs, [], pair_flags="info").outcome == "reject"
    res = decide(reqs, ["reader:many_unclear_parts"], pair_flags="info")
    assert res.outcome == "review" and res.rule.startswith("0 review")
    assert decide(reqs, ["profile:name_not_found"], pair_flags="info").outcome == "reject"  # other pair flags: info


@needs_tesseract
def test_reader_endpoint_mode_field(photo_png, monkeypatch):
    from fastapi.testclient import TestClient
    from services import api
    monkeypatch.setattr(mm, "vision_call", lambda image, prompt, model=None, client=None: {
        "text": "Sami Trabelsi\nData Engineer", "model": "fake", "latency_s": 0.1, "eval_count": 5, "done_reason": "stop"})
    c = TestClient(api.app)
    assert c.post("/reader", files={"file": ("cv.png", photo_png)}, data={"mode": "magic"}).status_code == 422
    body = c.post("/reader", files={"file": ("cv.png", photo_png)}, data={"mode": "vision"}).json()
    assert body["mode"] == "vision" and body["read_path"] == ["vision"] and body["pages"][0]["vision_model"] == "fake"
    assert "Sami" not in json.dumps(body)  # page summaries carry no CV text
