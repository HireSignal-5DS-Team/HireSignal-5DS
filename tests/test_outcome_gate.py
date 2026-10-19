"""Outcome gate (station 8): rules in order, which flags count, pair flags block vs info, /outcome endpoint."""
import pytest
from fastapi.testclient import TestClient

from services import api
from services.outcome.gate import REJECT_SENTENCE, decide, relevant_flag


def req(rid, kind="must", decision="MET", reasons=(), info=()):
    return {"req_id": rid, "kind": kind, "decision": decision, "review_reasons": list(reasons), "info_flags": list(info)}


ALL_MET = [req("r1"), req("r2"), req("r3", "nice")]


def test_score_is_the_decision_5_formula():
    rs = [req("r1"), req("r2", decision="UNCERTAIN"), req("r3", "nice", "MISSING")]
    assert decide(rs).score == round(100 * (2 * 1 + 2 * 0.5 + 0) / 5)  # 60


def test_invite_when_every_must_is_met_clean_and_the_score_is_high():
    r = decide(ALL_MET, t_invite=80)
    assert r.outcome == "invite" and r.rule.startswith("3") and r.message is None


def test_clean_missing_must_rejects_and_carries_the_review_sentence():
    r = decide([req("r1"), req("r2", decision="MISSING")])
    assert r.outcome == "reject" and r.rule.startswith("1") and r.message == REJECT_SENTENCE
    assert r.reasons == ["r2: must-have MISSING"]


def test_reject_wins_over_flags_on_other_musts():
    r = decide([req("r1", decision="UNCERTAIN"), req("r2", decision="MISSING")])
    assert r.outcome == "reject"


@pytest.mark.parametrize("r,why", [
    (req("r1", decision="MET", reasons=["judge:disagrees"]), "false invite"),
    (req("r1", decision="MET", reasons=["duration_not_in_evidence"]), "false invite"),
    (req("r1", decision="MISSING", reasons=["judge:disagrees"]), "false reject"),
    (req("r1", decision="MISSING", reasons=["contradiction_refuted_by_evidence"]), "false reject"),
    (req("r1", decision="UNCERTAIN", reasons=["match:low_confidence"]), "low confidence"),
])
def test_outcome_relevant_flags_on_must_haves_send_to_review(r, why):
    out = decide([r, req("r2")])
    assert out.outcome == "review" and out.rule.startswith("2") and why in out.reasons[0]


def test_flags_that_cannot_change_the_outcome_never_block():
    rs = [req("r1"), req("r2", reasons=["some_other_reason"]),
          req("r3", "nice", "MISSING", reasons=["judge:disagrees"]), req("r4", info=["some info"])]
    out = decide(rs, t_invite=0)
    assert out.outcome == "invite"
    assert "r3 (nice): judge:disagrees" in out.listed_flags and "r4: some info" in out.listed_flags
    assert "r2 (must, not outcome-relevant): some_other_reason" in out.listed_flags


def test_a_missing_must_without_a_doubt_is_not_rescued_by_a_judge_pass():
    assert relevant_flag(req("r1", decision="MISSING", reasons=["judge:uncertain"])) is None


def test_low_score_goes_to_review_not_invite():
    rs = [req("r1")] + [req(f"n{i}", "nice", "MISSING") for i in range(6)]
    out = decide(rs, t_invite=80)
    assert out.outcome == "review" and out.rule.startswith("4")


def test_pair_flags_block_or_info():
    blocked = decide(ALL_MET, ["profile:partial_extraction_requires_review"], pair_flags="block")
    assert blocked.outcome == "review" and blocked.rule == "pair flag blocks"
    info = decide(ALL_MET, ["profile:partial_extraction_requires_review"], pair_flags="info")
    assert info.outcome == "invite" and any("info only" in x for x in info.listed_flags)


def test_bad_input_is_refused():
    with pytest.raises(ValueError):
        decide([])
    with pytest.raises(ValueError):
        decide(ALL_MET, pair_flags="maybe")


def test_outcome_endpoint(monkeypatch):
    monkeypatch.setenv("OUTCOME_T_INVITE", "80")
    monkeypatch.setenv("OUTCOME_PAIR_FLAGS", "info")
    c = TestClient(api.app)
    body = {"requirements": [req("r1"), req("r2", decision="MISSING") | {"extra": "ignored"}], "cv_id": "cv-0123abcd",
            "job_id": "J2"}
    r = c.post("/outcome", json=body).json()
    assert r["outcome"] == "reject" and r["message"] == REJECT_SENTENCE and r["cv_id"] == "cv-0123abcd"
    assert c.post("/outcome", json={"requirements": []}).status_code == 422


# ------------------------------------------------- T08b: rule-2 variants ---

def met_doubted(p_met, entail=0.01, category="skill", ey=None, my=None):
    return req("r1", reasons=["judge:disagrees"]) | {"confidence": {"MET": p_met}, "category": category,
                                                      "judge": {"verdict": "FAIL", "nli_probs": {"entailment": entail}},
                                                      "evidence_years": ey, "min_years": my}


def test_variant_b_judge_counts_only_below_the_confidence_level():
    assert decide([met_doubted(0.9995), req("r2")], t_invite=0, judge_met_max_conf=0.999).outcome == "invite"
    assert decide([met_doubted(0.9985), req("r2")], t_invite=0, judge_met_max_conf=0.999).outcome == "review"


def test_variant_c_judge_counts_only_with_low_support():
    assert decide([met_doubted(0.5, entail=0.6), req("r2")], t_invite=0, judge_max_support=0.5).outcome == "invite"
    assert decide([met_doubted(0.5, entail=0.1), req("r2")], t_invite=0, judge_max_support=0.5).outcome == "review"


def test_variant_d_language_and_proven_years_skip_the_judge():
    assert decide([met_doubted(0.5, category="language"), req("r2")], t_invite=0, judge_skip_proven=True).outcome == "invite"
    assert decide([met_doubted(0.5, category="experience", ey=5, my=3), req("r2")], t_invite=0,
                  judge_skip_proven=True).outcome == "invite"
    assert decide([met_doubted(0.5, category="experience", ey=2, my=3), req("r2")], t_invite=0,
                  judge_skip_proven=True).outcome == "review"


def test_variant_f_no_judge_but_validator_flags_still_count():
    out = decide([met_doubted(0.5), req("r2")], t_invite=0, judge="none")
    assert out.outcome == "invite" and any("judge:disagrees" in x for x in out.listed_flags)
    assert decide([req("r1", reasons=["duration_not_in_evidence"]), req("r2")], t_invite=0, judge="none").outcome == "review"


def test_endpoint_uses_the_dev_chosen_defaults(monkeypatch):
    for k in ("OUTCOME_T_INVITE", "OUTCOME_JUDGE_MET_MAX_CONF", "OUTCOME_JUDGE", "OUTCOME_PAIR_FLAGS"):
        monkeypatch.delenv(k, raising=False)
    body = {"requirements": [met_doubted(0.9995), req("r2")]}
    r = TestClient(api.app).post("/outcome", json=body).json()
    assert r["outcome"] == "invite" and r["settings"]["judge_met_max_conf"] == 0.999 and r["settings"]["t_invite"] == 85
