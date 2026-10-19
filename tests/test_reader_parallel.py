"""T10b: late fusion with OCR and the vision call in parallel = the sequential result (fake Ollama, real Tesseract)."""
import time

import pytest

from conftest import needs_tesseract
from services.reader import ReaderError, read_cv
from services.reader import multimodal as mm
from services.reader import reader as rd


def _fake_vision(text="John Smith\nData Engineer\nPython, SQL, Airflow", delay=0.0):
    calls = []

    def call(image, prompt, model=None, client=None):
        calls.append(prompt)
        time.sleep(delay)
        return {"text": text, "model": "fake", "latency_s": delay, "eval_count": 9, "done_reason": "stop"}
    return call, calls


def _same(a, b):
    strip = lambda d: [{k: v for k, v in p.items() if k != "vision_latency_s"} for p in d]  # noqa: E731
    return (a.text, a.page_routes, a.warnings, a.review_reasons, a.needs_human_review, strip(a.page_details)) == \
           (b.text, b.page_routes, b.warnings, b.review_reasons, b.needs_human_review, strip(b.page_details))


@needs_tesseract
def test_parallel_late_fusion_equals_sequential(photo_png, monkeypatch):
    call, calls = _fake_vision()
    monkeypatch.setattr(mm, "vision_call", call)
    monkeypatch.setenv("READER_PARALLEL", "0")
    seq = read_cv(photo_png, "photo.png", mode="late")
    monkeypatch.setenv("READER_PARALLEL", "1")
    par = read_cv(photo_png, "photo.png", mode="late")
    assert _same(seq, par) and seq.page_routes == ["late"] and len(calls) == 2


@needs_tesseract
def test_vision_failure_in_parallel_falls_back_to_ocr_like_sequential(photo_png, monkeypatch):
    def down(image, prompt, model=None, client=None):
        raise mm.VisionUnavailable("ReadTimeout: timed out")
    monkeypatch.setattr(mm, "vision_call", down)
    monkeypatch.setenv("READER_PARALLEL", "0")
    seq = read_cv(photo_png, "photo.png", mode="late")
    monkeypatch.setenv("READER_PARALLEL", "1")
    par = read_cv(photo_png, "photo.png", mode="late")
    assert par.page_routes == ["ocr (vision fallback)"] and any("not reachable" in w for w in par.warnings)
    assert _same(seq, par)


@needs_tesseract
def test_reader_parallel_0_uses_the_sequential_path(photo_png, monkeypatch):
    call, _ = _fake_vision()
    monkeypatch.setattr(mm, "vision_call", call)
    monkeypatch.setattr(rd, "_late_page_parallel", lambda *a: (_ for _ in ()).throw(AssertionError("parallel used")))
    monkeypatch.setenv("READER_PARALLEL", "0")
    assert read_cv(photo_png, "photo.png", mode="late").page_routes == ["late"]


def test_ocr_error_in_parallel_is_raised_after_the_vision_call(photo_png, monkeypatch):
    call, calls = _fake_vision(delay=0.3)
    monkeypatch.setattr(mm, "vision_call", call)
    monkeypatch.setattr(rd, "_ocr_with_cleanup", lambda image, warnings: (_ for _ in ()).throw(
        ReaderError("Tesseract is not installed or not found.")))
    monkeypatch.setattr(rd, "_prepare_photo", lambda image: image)
    monkeypatch.setenv("READER_PARALLEL", "1")
    with pytest.raises(ReaderError, match="Tesseract"):
        read_cv(photo_png, "photo.png", mode="late")
    assert len(calls) == 1  # the vision call ran to its end; no thread left behind


@needs_tesseract
def test_parallel_runs_the_two_readers_at_the_same_time(photo_png, monkeypatch):
    call, _ = _fake_vision(delay=1.0)
    monkeypatch.setattr(mm, "vision_call", call)
    timings = {}
    for flag in ("0", "1"):
        monkeypatch.setenv("READER_PARALLEL", flag)
        t = time.perf_counter()
        read_cv(photo_png, "photo.png", mode="late")
        timings[flag] = time.perf_counter() - t
    assert timings["1"] < timings["0"] - 0.3  # the 1 s vision wait overlaps the OCR
