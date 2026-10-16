"""Real Qwen3-0.6B (pinned GGUF). Skipped unless llama-cpp-python is installed and the model is cached."""
import pytest

from reporter import to_markdown, write
from reporter.slm import MODEL, SLMUnavailable, find_gguf
from reporter.slm_prompt import chatml, messages
from reporter.slm_validate import validate
from reporter.build import facts_for_requirement, facts_for_summary

from _fixtures import pipeline_output

llama_cpp = pytest.importorskip("llama_cpp")
try:
    GGUF = find_gguf({})
except SLMUnavailable as e:
    pytest.skip(f"Qwen3-0.6B GGUF not cached: {e}", allow_module_level=True)


@pytest.fixture(scope="module")
def slm():
    from reporter.slm import LlamaCppSLM
    return LlamaCppSLM(GGUF)


def test_manual_chatml_equals_the_gguf_template_with_thinking_disabled(slm):
    from jinja2.sandbox import ImmutableSandboxedEnvironment

    tpl = slm.llm.metadata["tokenizer.chat_template"]
    msgs = messages("note", {"requirement": "x", "decision": "MET"})
    ref = ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True).from_string(tpl).render(
        messages=msgs, add_generation_prompt=True, enable_thinking=False)
    assert chatml(msgs) == ref


def test_real_model_pinned_and_every_accepted_section_passes_the_validator(slm):
    assert slm.sha256 == MODEL["gguf_sha256"]
    out = pipeline_output()
    rep = write(out, slm=slm)
    assert rep.provenance.slm["gguf_revision"] == MODEL["gguf_revision"] and rep.provenance.slm["prompt_sha256"]
    facts = [facts_for_summary(out)] + [facts_for_requirement(r) for r in out["requirements"]]
    for t, f, k in zip([rep.executive_summary] + [r.plain_note for r in rep.requirements], facts,
                       ["summary"] + ["note"] * 4):
        assert t.writer in ("slm", "deterministic_fallback")
        if t.writer == "slm":
            import json
            assert validate(json.dumps({k: t.text}), f, k) == (t.text, [])
    assert "<think>" not in to_markdown(rep)
