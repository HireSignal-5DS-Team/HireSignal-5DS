# Request from S4 (Bias Auditor) to S2 (pipeline) and S6 (orchestrator)

Date: 2026-10-16. Branch `session/s4-bias-auditor`. Evidence: `docs/BIAS_AUDITOR.md` §5.1 (DETERMINISTIC).

1. **S2, `matcher/pipeline.py` and `matcher/factory.py`.** Allow a `BiasAuditor` from `bias/auditor.py` to be
   injected, selected by `HS_BIAS_AUDITOR = rules_v1 | rules_v2 | rules_v2+reviewer`.
   - Proposed default: `rules_v2`.
   - The reviewer reuses `HS_FALLBACK_URL` (the base model at :8080).
   - Call shape: `auditor.check_result(res, cv.text, requirement_text=req.text)` in place of
     `check_result(res, cv.text)`. The `BiasFinding` shape is unchanged.
   - `aggregate()` already names the reason from `affected_attribute`.
   - Until this lands, production keeps rules v1 and nothing in the pipeline changes.
2. **S6, merge gate.** Add `bias/tests` to the gate command:
   `pytest matcher benchmark/tests tests/qa bias/tests`.
3. **S6, window 1 queue.** S4's live steps are in `bias/run_window1.sh`. The minimum is `reviewer lora-core`, about
   1.5 h at the measured Matcher latency. They need the :8081 LoRA server and the :8080 base server, plus
   `HIRESIGNAL_RAG_DIR` (BM25, the same setting as the base-Matcher bias run).

4. **QA-016 and QA-020 (S4 owner): fixed** in `matcher/bias_audit.py`, following `docs/qa/patches/S4-bias-audit.patch`.
   - QA-016 additionally makes `merge()` keep `NOT_TESTED`, and makes `benchmark/bias_eval.py` exclude untested
     cells from flip rates and from the paired test.
   - Both `tests/qa/test_qa_bias.py` tests XPASSed. As `docs/qa/README.md` prescribes, I removed their two
     `@defect` lines. That is the only edit to an S5 file.
   - S5: please mark QA-016 and QA-020 as fixed in `docs/qa/FAILURES.md`.
   - Regression test: `bias/tests/test_bias_auditor.py::test_untested_cells_qa016_are_not_passes_and_not_counted`.

5. **Exact wiring for the prompted reviewer (S2, `matcher/factory.py` and `matcher/pipeline.py`; S4 does not edit them).**
   - `HS_BIAS_AUDITOR` = `rules_v1` | `rules_v2` | `rules_v2+reviewer`. Default `rules_v2`, which makes no model call.
     The reviewer is **opt-in**: `rules_v2+reviewer` adds one LLM call per result (LIVE p50 11.2 s, p95 14.0 s).
   - The reviewer's server is `HS_BIAS_REVIEWER_URL`, default `HS_FALLBACK_URL` (`http://127.0.0.1:8080/v1`, the
     original Qwen3-4B-Instruct-2507 Q4_K_M). Its model is `HS_BIAS_REVIEWER_MODEL`, default
     `Qwen/Qwen3-4B-Instruct-2507`. Never point it at the LoRA endpoint: the reviewer was measured on the base model
     only, and the Matcher LoRA is not a fairness model.
   - Construction:
     `BiasAuditor("rules_v2+reviewer", reviewer=LLMReviewer(OpenAICompatBackend(base_url=..., model=..., timeout=..., max_tokens=160)))`.
     The auditor is then called as `auditor.check_result(res, cv.text, requirement_text=req.text)`.
   - Fail-open: if the reviewer server is down, the rules verdict stands and `details.reviewer.error` records it. The
     result is not routed to review for that reason alone. If you prefer fail-closed, add a review reason
     `bias:reviewer_unavailable` in `aggregate()`.
   - Provenance: add `auditor.info()` to `MatchReport.backend`.
