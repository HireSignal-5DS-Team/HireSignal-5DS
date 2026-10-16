"""S7 NLI Judge: label mapping, provenance, deterministic pre-checks, thresholds and configuration.

MOCK tests use a stub NLI (fixed scores) or a tiny randomly initialised DeBERTa-v2 built in a temp dir (no download):
they check the Judge's wiring, not its accuracy. The real-model test loads cross-encoder/nli-deberta-v3-xsmall at its
pinned revision and is skipped unless that checkpoint is already in the local Hugging Face cache.
"""
import pytest

from matcher import CV, Requirement
from matcher.factory import JUDGE_DEFAULT, JUDGE_MODELS, PRETRAINED_JUDGE, judge_config
from matcher.judge import (PREMISE_POLICY, SCORE_NOTE, VALIDATOR_NUMERIC, JudgeFinding, NLIJudge, hypothesis,
                           label_index, precheck)
from matcher.pipeline import aggregate
from matcher.bias_audit import check_result
from matcher.schemas import KnowledgeRef
from matcher.tests.test_pipeline import ans, validated

XSMALL = "cross-encoder/nli-deberta-v3-xsmall"
XSMALL_REV = "a150876415327c80daeff35ca6f68f5ed8cf5c24"
CV_TEXT = ("Profile\nBackend developer.\n- 5 years of professional Python experience.\n"
           "- Never used Kubernetes in production; deployments ran on managed VMs.")
CVX = CV(cv_id="c1", text=CV_TEXT)
PY = Requirement(req_id="r1", text="Python development", skill_terms=["Python"])
PY3 = Requirement(req_id="r3", text="At least 3 years of Python", category="experience", skill_terms=["Python"], min_years=3)
K8S = Requirement(req_id="r2", text="Proficiency in Kubernetes", skill_terms=["Kubernetes"])
E = {"entailment": 0.9, "neutral": 0.05, "contradiction": 0.05}
C = {"entailment": 0.02, "neutral": 0.08, "contradiction": 0.9}
N = {"entailment": 0.3, "neutral": 0.6, "contradiction": 0.1}


class StubJudge(NLIJudge):
    """NLIJudge with a scoring function instead of a forward pass; records every premise it is asked about."""

    def __init__(self, fn=lambda p, h: E, tau_pass=0.5, tau_fail=0.5, template="v1"):
        self.fn, self.tau_pass, self.tau_fail, self.name = fn, tau_pass, tau_fail, "stub-nli"
        self.model_id, self.revision, self.hypothesis_template, self.seen = "stub/model", "deadbeef", template, []

    def probs(self, pairs, batch_size=16):
        self.seen += list(pairs)
        return [self.fn(p, h) for p, h in pairs]


# ---- label mapping -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("id2label,want", [
    ({0: "contradiction", 1: "entailment", 2: "neutral"}, {"entailment": 1, "neutral": 2, "contradiction": 0}),  # xsmall
    ({"0": "entailment", "1": "neutral", "2": "contradiction"}, {"entailment": 0, "neutral": 1, "contradiction": 2}),  # base
    ({0: "ENTAILMENT", 1: "NEUTRAL", 2: "CONTRADICTION"}, {"entailment": 0, "neutral": 1, "contradiction": 2}),
])
def test_label_index_maps_by_name(id2label, want):
    assert label_index(id2label) == want


@pytest.mark.parametrize("id2label", [{0: "LABEL_0", 1: "LABEL_1", 2: "LABEL_2"},
                                      {0: "entailment", 1: "entailed", 2: "contradiction"},
                                      {0: "entailment", 1: "neutral"}])
def test_label_index_refuses_to_guess(id2label):
    with pytest.raises(ValueError):
        label_index(id2label)


# ---- provenance and output fields ----------------------------------------------------------------------------
def test_every_finding_carries_provenance_scores_status_and_recommendation():
    j = StubJudge(tau_pass=0.7, tau_fail=0.8, template="v2")
    items = [(validated(ans("MET", "supported", ["5 years of professional Python experience."]), PY, CVX), CVX, PY),
             (validated(ans("UNCERTAIN", "ambiguous"), K8S, CVX), CVX, K8S),
             (validated(ans("MISSING", "not_documented"), K8S, CVX), CVX, K8S)]
    for f in j.judge_many(items):
        assert f.provenance == {"model_id": "stub/model", "revision": "deadbeef", "tau_pass": 0.7, "tau_fail": 0.8,
                                "hypothesis": "v2", "premise_policy": PREMISE_POLICY, "scores": SCORE_NOTE}
        assert f.support_status in ("supports_decision", "opposes_decision", "inconclusive", "not_checked",
                                    "missing_evidence")
        assert f.recommendation == ("review" if f.requires_human_review else "no_judge_concern")
        assert set(f.to_dict()) >= {"nli_probs", "support_status", "recommendation", "provenance", "prechecks"}
    f = j.judge_many(items[:1])[0]
    assert set(f.nli_probs) == {"entailment", "neutral", "contradiction"} and f.support_status == "supports_decision"
    assert "not probabilities" in SCORE_NOTE and "NOT P(decision correct)" in JudgeFinding.__doc__


def test_separate_pass_and_fail_thresholds():
    res = validated(ans("MET", "supported", ["5 years of professional Python experience."]), PY, CVX)
    mid = {"entailment": 0.6, "neutral": 0.35, "contradiction": 0.05}
    assert StubJudge(lambda p, h: mid, tau_pass=0.5).judge_many([(res, CVX, PY)])[0].judge_verdict == "PASS"
    assert StubJudge(lambda p, h: mid, tau_pass=0.7).judge_many([(res, CVX, PY)])[0].judge_verdict == "UNCERTAIN"
    hi_n = {"entailment": 0.2, "neutral": 0.75, "contradiction": 0.05}
    assert StubJudge(lambda p, h: hi_n, tau_fail=0.7).judge_many([(res, CVX, PY)])[0].judge_verdict == "FAIL"
    assert StubJudge(lambda p, h: hi_n, tau_fail=0.8).judge_many([(res, CVX, PY)])[0].judge_verdict == "UNCERTAIN"


def test_hypothesis_templates():
    assert hypothesis(PY3) == "The candidate meets this job requirement: At least 3 years of Python (at least 3 years)."
    assert hypothesis(PY3, "v2") == "The candidate has at least 3 years of Python."
    with pytest.raises(KeyError):
        hypothesis(PY3, "v9")


# ---- deterministic pre-checks --------------------------------------------------------------------------------
def test_quote_not_in_cv_is_dropped_before_nli_and_asks_for_review():
    from types import SimpleNamespace

    res = SimpleNamespace(decision="MET", basis="supported", evidence=["Kubernetes expert", "5 years of professional Python"],
                          evidence_spans=None, review_reasons=[])
    ok, notes = precheck(res, CVX)
    assert [q for q, _ in ok] == ["5 years of professional Python"] and notes == ["evidence_not_in_cv"]
    j = StubJudge()
    f = j.judge_many([(res, CVX, PY)])[0]
    assert all("Kubernetes expert" not in p for p, _ in j.seen)
    assert f.judge_verdict == "PASS" and f.requires_human_review and f.recommendation == "review"
    assert f.prechecks == ["evidence_not_in_cv"]


def test_stale_span_is_not_trusted():
    from types import SimpleNamespace

    res = SimpleNamespace(decision="MET", basis="supported", evidence=["5 years of professional Python experience."],
                          evidence_spans=[(0, 7)], review_reasons=[])
    ok, notes = precheck(res, CVX)
    assert ok and CVX.text[ok[0][1][0]:ok[0][1][1]] == ok[0][0] and not notes


@pytest.mark.parametrize("decision,basis", [("MET", "supported"), ("MISSING", "contradicted")])
def test_missing_evidence_means_review_without_nli(decision, basis):
    from types import SimpleNamespace

    res = SimpleNamespace(decision=decision, basis=basis, evidence=["not in the cv at all"], evidence_spans=None,
                          review_reasons=[])
    j = StubJudge()
    f = j.judge_many([(res, CVX, K8S)])[0]
    assert j.seen == [] and f.nli_probs is None
    assert f.judge_verdict == "UNCERTAIN" and f.support_status == "missing_evidence" and f.requires_human_review
    assert "missing_evidence" in f.prechecks


def test_rag_text_is_never_a_premise():
    """The Judge never receives knowledge refs; a quote copied from RAG text (not in the CV) is dropped, and every
    premise the model sees is CV text."""
    ref = KnowledgeRef(source_type="esco", source_id="esco:k8s", title="Kubernetes",
                       text="Kubernetes is a container orchestration system used in production.", retrieval="fixture")
    res = validated(ans("MET", "supported", [ref.text, "5 years of professional Python experience."]), PY, CVX)
    assert ref.text not in res.evidence  # the validator already drops it
    from types import SimpleNamespace

    raw = SimpleNamespace(decision="MET", basis="supported", evidence=[ref.text], evidence_spans=None, review_reasons=[])
    j = StubJudge()
    j.judge_many([(res, CVX, PY), (raw, CVX, K8S),
                  (validated(ans("MISSING", "not_documented"), K8S, CVX), CVX, K8S)])
    assert len(j.seen) == 2 and all(p in CVX.text for p, _ in j.seen)  # one quote premise, one whole-CV chunk
    assert all(ref.text not in p and "orchestration" not in p for p, _ in j.seen)
    import inspect

    assert list(inspect.signature(NLIJudge.judge_many).parameters) == ["self", "items"]


def test_judge_pass_never_clears_a_validator_numeric_check():
    """Numeric/duration checks stay in the validator: a MISSING/contradicted kept with
    contradiction_refuted_by_evidence stays in review even when the NLI agrees with the decision."""
    cv = CV(cv_id="c2", text="Experience\n- Python developer 2016 - 2024, not a senior role.")
    res = validated(ans("MISSING", "contradicted", ["Python developer 2016 - 2024, not a senior role."]), PY3, cv)
    assert "contradiction_refuted_by_evidence" in res.review_reasons and res.decision == "MISSING"
    f = StubJudge(lambda p, h: C).judge_many([(res, cv, PY3)])[0]
    assert f.judge_verdict == "PASS" and f.requires_human_review and f.recommendation == "review"
    assert "validator:contradiction_refuted_by_evidence" in f.prechecks
    row = aggregate(res, check_result(res, cv.text), f)
    assert row["final_decision"] == "MISSING" and row["requires_human_review"]
    assert "validator:contradiction_refuted_by_evidence" in row["review_reasons"]
    assert set(VALIDATOR_NUMERIC) == {"years_below_minimum_in_evidence", "duration_not_verified",
                                      "contradiction_refuted_by_evidence"}


def test_judge_never_changes_the_decision_object():
    res = validated(ans("MET", "supported", ["Kubernetes in production"]), K8S, CVX)
    before = res.model_dump()
    StubJudge(lambda p, h: C).judge_many([(res, CVX, K8S)])
    assert res.model_dump() == before


# ---- configuration -------------------------------------------------------------------------------------------
def test_judge_config_env_and_pins(tmp_path):
    assert judge_config({"HS_JUDGE": "off"}) is None
    d = judge_config({})
    assert d.model == JUDGE_DEFAULT and d.revision == JUDGE_MODELS[JUDGE_DEFAULT]["revision"]
    assert (d.tau_pass, d.tau_fail, d.hypothesis) == tuple(JUDGE_MODELS[JUDGE_DEFAULT][k] for k in ("tau_pass", "tau_fail", "hypothesis"))
    x = judge_config({"HS_JUDGE_MODEL": XSMALL})
    assert x.revision == XSMALL_REV and x.model == XSMALL
    o = judge_config({"HS_JUDGE_MODEL": XSMALL, "HS_JUDGE_REVISION": "abc", "HS_JUDGE_TAU_PASS": "0.6",
                      "HS_JUDGE_TAU_FAIL": "0.9", "HS_JUDGE_HYPOTHESIS": "v1"})
    assert (o.revision, o.tau_pass, o.tau_fail, o.hypothesis) == ("abc", 0.6, 0.9, "v1")
    assert judge_config({"HS_JUDGE_MODEL": XSMALL, "HS_JUDGE_TAU": "0.7"})[1:2] == (0.7,)
    missing = judge_config({"HS_JUDGE_DIR": str(tmp_path / "missing")})
    assert missing.model == PRETRAINED_JUDGE[0] and "missing" in missing.name
    local = tmp_path / "ft"
    local.mkdir()
    (local / "judge_calibration.json").write_text('{"tau_pass": 0.55, "tau_fail": 0.6, "hypothesis": "v1"}')
    lc = judge_config({"HS_JUDGE_MODEL": str(local)})
    assert (lc.model, lc.revision, lc.tau_pass, lc.tau_fail) == (str(local), None, 0.55, 0.6)
    with pytest.raises(ValueError):
        judge_config({"HS_JUDGE_MODEL": XSMALL, "HS_JUDGE_HYPOTHESIS": "v9"})


# ---- tiny real transformers model (MOCK weights) -------------------------------------------------------------
@pytest.fixture(scope="module")
def tiny_dir(tmp_path_factory):
    torch = pytest.importorskip("torch")
    pytest.importorskip("transformers")
    from tokenizers import Tokenizer, models, pre_tokenizers, processors
    from transformers import DebertaV2Config, DebertaV2ForSequenceClassification, PreTrainedTokenizerFast

    d = tmp_path_factory.mktemp("tiny_nli")
    words = "the candidate has meets this job requirement python never used kubernetes years of professional".split()
    vocab = {t: i for i, t in enumerate(["[PAD]", "[UNK]", "[CLS]", "[SEP]"] + words)}
    tk = Tokenizer(models.WordLevel(vocab, unk_token="[UNK]"))
    tk.pre_tokenizer = pre_tokenizers.Whitespace()
    tk.post_processor = processors.TemplateProcessing(single="[CLS] $A [SEP]", pair="[CLS] $A [SEP] $B [SEP]",
                                                      special_tokens=[("[CLS]", 2), ("[SEP]", 3)])
    PreTrainedTokenizerFast(tokenizer_object=tk, pad_token="[PAD]", unk_token="[UNK]", cls_token="[CLS]",
                            sep_token="[SEP]", model_max_length=64).save_pretrained(d)
    torch.manual_seed(0)
    cfg = DebertaV2Config(vocab_size=len(vocab), hidden_size=16, num_hidden_layers=1, num_attention_heads=2,
                          intermediate_size=32, max_position_embeddings=64, type_vocab_size=0, num_labels=3,
                          id2label={0: "contradiction", 1: "entailment", 2: "neutral"},
                          label2id={"contradiction": 0, "entailment": 1, "neutral": 2})
    DebertaV2ForSequenceClassification(cfg).save_pretrained(d)
    return d


def test_tiny_model_loads_fp32_maps_labels_and_records_local_revision(tiny_dir):
    j = NLIJudge(str(tiny_dir), tau_pass=0.6, tau_fail=0.7, max_length=64, name="tiny")
    assert next(j.model.parameters()).dtype == j.torch.float32
    assert j.idx == {"entailment": 1, "neutral": 2, "contradiction": 0}
    assert j.revision == f"local:{tiny_dir}"
    pr = j.probs([("never used kubernetes", "the candidate has kubernetes")] * 3)
    assert len(pr) == 3 and all(abs(sum(p.values()) - 1) < 1e-5 for p in pr)
    res = validated(ans("MET", "supported", ["5 years of professional Python experience."]), PY, CVX)
    f = j.judge_many([(res, CVX, PY)])[0]
    assert f.provenance["model_id"] == str(tiny_dir) and f.provenance["tau_fail"] == 0.7 and f.nli_probs


# ---- real checkpoint (skipped unless cached) -----------------------------------------------------------------
def _xsmall_cached():
    try:
        from huggingface_hub import try_to_load_from_cache

        return isinstance(try_to_load_from_cache(XSMALL, "model.safetensors", revision=XSMALL_REV), str)
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _xsmall_cached(), reason="cross-encoder/nli-deberta-v3-xsmall@a150876 not in the HF cache")
def test_real_xsmall_label_mapping_entailment_and_contradiction(monkeypatch):
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    j = NLIJudge(XSMALL, revision=XSMALL_REV, hypothesis_template="v2")
    assert j.revision == XSMALL_REV
    assert j.idx == {"entailment": 1, "neutral": 2, "contradiction": 0}  # id2label: 0 contradiction, 1 entail, 2 neutral
    ent, con = j.probs([("A man is eating pizza", "A man eats something"),
                        ("Never used Kubernetes in production.", "The candidate has used Kubernetes in production.")])
    assert max(ent, key=ent.get) == "entailment" and ent["entailment"] > 0.8
    assert max(con, key=con.get) == "contradiction" and con["contradiction"] > 0.8
    cv = CV(cv_id="k", text="Skills\n- Never used Kubernetes in production.")
    req = Requirement(req_id="k", text="Used Kubernetes in production", skill_terms=["Kubernetes"])
    res = validated(ans("MET", "supported", ["Kubernetes in production"]), req, cv)
    f = j.judge_many([(res, cv, req)])[0]
    assert res.decision == "MET"  # the validator only flags the negation (review), the Judge must catch it
    assert f.judge_verdict == "FAIL" and f.nli_probs["contradiction"] > 0.5 and res.decision == "MET"
