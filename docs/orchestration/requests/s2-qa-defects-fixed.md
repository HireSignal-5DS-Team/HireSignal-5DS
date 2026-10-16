# Request from S2 to S5 / S6: S2 defects fixed, strict xfail markers now XPASS

After merging the integration branch (validator v2) into `session/s2-matcher-lora-integration`, these `tests/qa`
tests fail only because they are `xfail(strict=True)` and now pass. S5 owns `tests/qa/` and `docs/qa/FAILURES.md`, so
S2 did not touch them. Please remove the markers and mark the defects fixed:

| defect | test(s) now passing | fix |
|---|---|---|
| QA-013 | `test_qa_contracts.py::test_match_report_routes_fallback_results_to_review` | `Matcher.build_report` routes the Matcher review reasons (`matcher:fallback_model_used`, …) into the MatchReport; per-result provenance is in `backend["results"]` |
| QA-015 | `test_qa_fallback.py::test_backend_exception_does_not_crash_the_pipeline`, `test_unhandled_malformed_server_responses_do_not_crash[*]` (3) | `OpenAICompatBackend.chat` treats `[]`, `{"choices": null}` and non-string content as a call error; `FallbackBackend._call` turns any backend exception into a recorded error, then falls back |
| QA-028 | `test_qa_val_regressions.py::test_final_report_explanations_are_requirement_specific_and_grounded` | the row's `explanation` is now the grounded explanation (requirement text + validated decision + verified quotes + cited titles); the model text is kept in `explanation_model`; the frozen MatchReport keeps the model text |
| QA-024 | (flaky, unmarked) `matcher/tests/test_pipeline.py::test_api_backend_success_timeout_and_unavailable` | stub server is now `ThreadingHTTPServer`, as proposed; 15/15 isolated runs pass |

QA-014 (`test_production_provenance_is_complete`) still xfails, now only on `knowledge_version is empty`
(S1, `docs/orchestration/requests/s2-knowledge-version.md`). `base_revision`, `adapter_id` and `adapter_revision` are
present. QA-027 (model level, years below the minimum) stays open: the validator catches it.

Run on this branch: `pytest matcher benchmark/tests tests/qa` gives 182 passed, 6 skipped, 7 xfailed and **6 failed,
all six being the XPASS(strict) tests above**.
