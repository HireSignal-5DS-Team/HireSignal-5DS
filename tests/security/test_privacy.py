"""T13 A4: privacy. Identity never reaches an LLM prompt or an API response; private/ and .env are git-ignored."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from services import api

ROOT = Path(__file__).resolve().parents[2]
CV = """JOHN SMITH | Data Scientist
john.smith92@gmail.com • +216 22 345 678 • linkedin.com/in/johnsmith
Nationality: Tunisian
Date of birth: 14/03/1990

SUMMARY
Data scientist with 3 years of experience in Python. He built dashboards.

EXPERIENCE
Data Scientist, Vermeg 2021 - 2024
"""
SECRETS = ("JOHN", "SMITH", "Smith", "john.smith92", "345 678", "johnsmith", "Tunisian", "14/03/1990")


class RecordingBackend:
    """A fake plain-Qwen backend that keeps every text sent to it."""

    def __init__(self):
        self.sent = []

    def extract(self, text, template, examples):
        self.sent.append(json.dumps([text, template, examples]))
        return json.dumps({"skills": [], "education": [], "experience": []})


def test_identity_never_reaches_the_llm_or_the_response(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "PRIVATE", tmp_path)
    backend = RecordingBackend()
    monkeypatch.setattr(api, "_plain_llm", lambda max_tokens: backend)
    c = TestClient(api.app)
    reader = c.post("/reader", files={"file": ("John_Smith_CV.txt", CV.encode())}).json()
    out = c.post("/profile", json={"cv_id": reader["cv_id"]}).json()
    assert backend.sent, "the parse step did not run"
    for secret in SECRETS:
        assert all(secret not in s for s in backend.sent), f"{secret} sent to the LLM"
        assert secret not in json.dumps(reader) and secret not in json.dumps(out), f"{secret} in an API response"
    stored = json.loads((tmp_path / f"{reader['cv_id']}.json").read_text(encoding="utf-8"))
    assert stored["name"] == "JOHN SMITH"  # kept apart, locally only


def test_private_data_and_secrets_are_git_ignored():
    # T14: checked by behaviour (git check-ignore, read-only), since data/raw/ now keeps the scans folder
    import shutil
    import subprocess

    import pytest
    if not shutil.which("git") or not (ROOT / ".git").exists():
        pytest.skip("git not available")

    def ignored(path):
        return subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=ROOT).returncode == 0

    for path in ("private/x.json", ".env", ".env.local", ".n8n/database.sqlite", "tools/n8n.log", "models/x.gguf",
                 "data/raw/djinni/x.parquet", "data/raw/kaggle_resume/x.pdf", "data/raw/vanetik/x.docx",
                 "eval/outbox/reject/x.json", ".cache/n8n/x.js", ".venv/x"):
        assert ignored(path), path
    for path in ("config/.env.example", "models/MANIFEST.md", "data/raw/scans/K01.pdf"):
        assert not ignored(path), path


def test_env_example_has_only_placeholders():
    text = (ROOT / "config/.env.example").read_text(encoding="utf-8")
    for key in ("CLOUD_LLM_API_KEY", "WEBHOOK_TOKEN"):
        line = next(x for x in text.splitlines() if x.startswith(key + "="))
        assert line.split("=", 1)[1].startswith("<"), line  # a placeholder, never a real secret
