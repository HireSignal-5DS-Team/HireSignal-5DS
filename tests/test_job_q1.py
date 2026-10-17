"""job-q1: the team's plain Qwen3-4B (no LoRA), shared with the Matcher."""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents.job import NuExtractClient, QwenChatClient, make_backend, run_job_agent  # noqa: E402
from agents.job import prompts  # noqa: E402
from agents.job.backend import QWEN_DEFAULT_MODEL, template_to_instructions  # noqa: E402
from agents.job.validate import parse_model_output  # noqa: E402

FIELDS = ("evidence", "skill_terms", "kind", "category", "min_years", "text")


# --------------------------------------------------------------- settings ---

def test_reads_the_same_settings_as_the_matcher(monkeypatch):
    monkeypatch.setenv("HS_LLM_BASE_URL", "https://provider.example/v1/")
    monkeypatch.setenv("HS_LLM_MODEL", "qwen3-4b-instruct-2507")
    client = QwenChatClient()
    assert client.base_url == "https://provider.example/v1"
    assert client.model == "qwen3-4b-instruct-2507"
    assert client.info()["base_url"] == "<hosted>"


def test_defaults_point_at_the_team_plain_qwen_server(monkeypatch):
    monkeypatch.delenv("HS_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("HS_LLM_MODEL", raising=False)
    client = QwenChatClient()
    assert client.base_url == "http://127.0.0.1:8080/v1" and client.model == QWEN_DEFAULT_MODEL


@pytest.mark.parametrize("model", ["Qwen/Qwen3-4B-Instruct-2507+lora", "hiresignal-qwen3-4b-matcher-LoRA"])
def test_the_matcher_lora_is_refused(model):
    with pytest.raises(ValueError, match="plain Qwen"):
        QwenChatClient(model=model)


def test_make_backend_picks_the_model_family():
    assert isinstance(make_backend("job-q1"), QwenChatClient)
    assert isinstance(make_backend("job-v4", mode="inline"), NuExtractClient)


# ---------------------------------------------------------------- payload ---

def test_q1_payload_is_instructions_then_examples_then_the_chunk():
    template, examples = prompts.get_prompt("job-q1")
    payload = QwenChatClient(base_url="http://x/v1")._payload("CHUNK", template, examples)
    roles = [m["role"] for m in payload["messages"]]
    assert roles == ["system"] + ["user", "assistant"] * len(examples) + ["user"]
    assert payload["messages"][0]["content"] == prompts.SYSTEM_Q1
    assert payload["messages"][-1]["content"] == "CHUNK"
    assert payload["temperature"] == 0 and payload["seed"] == 0
    assert payload["response_format"] == {"type": "json_object"}


def test_json_mode_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("HS_LLM_JSON_MODE", "0")
    assert "response_format" not in QwenChatClient(base_url="http://x/v1")._payload("t", "rules", [])


def test_a_nuextract_template_becomes_instructions():
    """The title call sends a typed template; Qwen gets it as instructions."""
    payload = QwenChatClient(base_url="http://x/v1")._payload("offer", prompts.title_template(), [])
    system = payload["messages"][0]["content"]
    assert '"job_title": "verbatim-string"' in system and "EXACTLY" in system
    assert template_to_instructions("{}").endswith("Answer with the JSON object only.")


def test_q1_instructions_cover_what_to_skip_and_the_format():
    for phrase in ("citizenship", "transcripts", "definitions", "duties", '{"requirements": []}',
                   "skill_terms", "52 weeks = 1", "exactly one of"):
        assert phrase in prompts.SYSTEM_Q1, phrase


def test_think_blocks_are_ignored():
    assert parse_model_output('<think>let me see</think>{"requirements": []}') == {"requirements": []}


# -------------------------------------------------- end to end, fake server ---

class _FakeQwen(BaseHTTPRequestHandler):
    """Answers like a perfect model: the gold items whose quote is in the chunk."""
    gold: list = []
    seen: list = []

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).seen.append(body)
        system, chunk = body["messages"][0]["content"], body["messages"][-1]["content"]
        if '"job_title"' in system:
            answer = {"job_title": "AI Software Engineer"}
        else:
            answer = {"requirements": [{k: r[k] for k in FIELDS} for r in type(self).gold if r["evidence"] in chunk]}
        out = json.dumps({"choices": [{"message": {"content": json.dumps(answer)}, "finish_reason": "stop"}],
                          "usage": {}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *args):
        pass


@pytest.fixture()
def fake_qwen():
    server = HTTPServer(("127.0.0.1", 0), _FakeQwen)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()


def test_q1_end_to_end_with_a_perfect_model(fake_qwen):
    gold = json.loads((ROOT / "eval/job_agent/gold/usajobs-883699600.json").read_text(encoding="utf-8"))
    post = (ROOT / "eval/job_agent/offers/usajobs-883699600.txt").read_text(encoding="utf-8")
    _FakeQwen.gold, _FakeQwen.seen = gold["requirements"], []

    card = run_job_agent(post, gold["job_id"], QwenChatClient(base_url=fake_qwen), prompt_version="job-q1")

    got = sorted((r.evidence, tuple(r.skill_terms), r.kind, r.category, r.min_years) for r in card.requirements)
    want = sorted((r["evidence"], tuple(r["skill_terms"]), r["kind"], r["category"], r["min_years"])
                  for r in gold["requirements"])
    assert got == want, card.warnings
    assert card.title == "AI Software Engineer"
    models = {b["model"] for b in _FakeQwen.seen}
    assert models == {QWEN_DEFAULT_MODEL}                      # never the "+lora" model
    assert not any("terms '" in w for w in card.warnings)      # no second call per sentence in q1
    chunk_calls = [b for b in _FakeQwen.seen if '"job_title"' not in b["messages"][0]["content"]]
    assert all(b["messages"][0]["content"] == prompts.SYSTEM_Q1 for b in chunk_calls)
