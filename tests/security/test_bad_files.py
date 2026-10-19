"""T13 A3: bad files give a clear error (4xx) or a review flag, never a crash (5xx) or a silent decision."""
import io
import sys
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from conftest import needs_tesseract  # noqa: E402
from services import api  # noqa: E402
from services.outcome.gate import decide  # noqa: E402
from services.reader import ReaderError, read_cv  # noqa: E402
from services.reader import reader as rd  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "PRIVATE", tmp_path)
    monkeypatch.setenv("READER_MODE", "ocr")
    return TestClient(api.app)


def pdf_bytes(pages=1, text="", password=None):
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    kw = {"encryption": pymupdf.PDF_ENCRYPT_AES_256, "user_pw": password, "owner_pw": password} if password else {}
    return doc.tobytes(**kw)


@pytest.mark.parametrize("name,data,why", [
    ("cv.pdf", b"", "empty"),
    ("cv.pdf", b"%PDF-1.7\n this is not a real pdf", "Corrupt"),
    ("cv.pdf", pdf_bytes(password="secret"), "password"),
    ("cv.pdf", pdf_bytes(pages=rd.MAX_PDF_PAGES + 1, text="Python developer"), "pages"),
    ("cv.exe", b"MZ" * 200, "unsupported"),
    ("cv.jpg", b"\xff\xd8\xff not really a jpeg", "Unsupported"),
])
def test_bad_files_give_a_clear_4xx(client, name, data, why):
    r = client.post("/reader", files={"file": (name, data)})
    assert 400 <= r.status_code < 500, (r.status_code, r.text)
    assert why.lower() in r.text.lower() or r.status_code in (413, 415, 422)


def test_too_large_upload_is_413(client, monkeypatch):
    monkeypatch.setattr(api, "MAX_CV_BYTES", 1000)
    assert client.post("/reader", files={"file": ("cv.txt", b"x" * 2000)}).status_code == 413


def test_huge_image_is_refused_before_ocr():
    buf = io.BytesIO()
    Image.new("L", (8000, 6000), 255).save(buf, format="PNG")  # 48 MP > 40 MP
    with pytest.raises(ReaderError, match="megapixels"):
        read_cv(buf.getvalue(), "big.png")


@needs_tesseract
def test_pdf_without_text_and_without_ink_goes_to_review():
    r = read_cv(pdf_bytes(pages=1), "scan.pdf")  # image-only page, nothing to read
    assert r.needs_human_review and "reader:low_confidence_or_little_text" in r.review_reasons


def test_non_english_cv_goes_to_review():
    fr = ("Développeur Python avec cinq ans d'expérience dans la conception de services web et de bases de données. "
          "Compétences principales : Django, PostgreSQL, Docker, Kubernetes. Formation : master en informatique, "
          "université de Tunis. Langues : arabe, français, anglais courant. ") * 3
    r = read_cv(fr.encode("utf-8"), "cv.txt")
    assert "reader:non_english_text" in r.review_reasons
    reqs = [{"req_id": "r1", "kind": "must", "decision": "MET", "review_reasons": [], "confidence": {"MET": 1.0}}]
    assert decide(reqs, r.review_reasons, t_invite=80).outcome == "review"  # never a silent decision


def test_english_cv_is_not_flagged():
    en = "Data engineer with 5 years of experience in Python and SQL. I built ETL pipelines on Airflow for a bank. " * 4
    assert "reader:non_english_text" not in read_cv(en.encode("utf-8"), "cv.txt").review_reasons


def test_invalid_json_body_is_422_not_500(client):
    r = client.post("/match", content=b"{not json", headers={"content-type": "application/json"})
    assert r.status_code == 422


def test_oversized_json_body_is_413(client):
    big = '{"cv_text": "' + "x" * (api.MAX_JSON_BYTES + 10) + '", "requirement": {"req_id": "r1", "text": "Python"}}'
    r = client.post("/match", content=big.encode(), headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_services_listen_on_localhost_only():
    """The start scripts bind the API, llama-server and n8n to 127.0.0.1 (A5)."""
    root = Path(__file__).resolve().parents[2]
    stack = (root / "scripts/start_stack.ps1").read_text(encoding="utf-8")
    llm = (root / "scripts/start_llm.ps1").read_text(encoding="utf-8")
    n8n = (root / "scripts/start_n8n.ps1").read_text(encoding="utf-8")
    ollama = (root / "scripts/start_ollama.ps1").read_text(encoding="utf-8")
    assert '"--host", "127.0.0.1"' in stack and '"--host", "127.0.0.1"' in llm
    assert 'N8N_LISTEN_ADDRESS = "127.0.0.1"' in n8n and 'OLLAMA_HOST = "127.0.0.1:' in ollama
