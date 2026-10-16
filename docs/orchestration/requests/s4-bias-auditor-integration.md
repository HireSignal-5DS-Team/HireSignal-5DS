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
