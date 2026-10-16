# Note from S2 to S5 / S6: S2 defects fixed, strict xfail markers removed

After merging the integration branch (validator v2) into `session/s2-matcher-lora-integration`, these `tests/qa` tests
XPASSed. As `docs/qa/README.md` prescribes, and as the orchestrator asked for QA-028, S2 removed their `@defect` lines
(4 lines, plus the now-unused `defect` imports in two files). That is the only edit to S5 files. The tests stay as
regression tests. S5: please mark these defects fixed in `docs/qa/FAILURES.md`:

| defect | test(s) now passing | fix |
|---|---|---|
| QA-013 | `test_qa_contracts.py::test_match_report_routes_fallback_results_to_review` | `Matcher.build_report` routes the Matcher review reasons (`matcher:fallback_model_used`, …) into the MatchReport; per-result provenance is in `backend["results"]` |
| QA-015 | `test_qa_fallback.py::test_backend_exception_does_not_crash_the_pipeline`, `test_unhandled_malformed_server_responses_do_not_crash[*]` (3) | `OpenAICompatBackend.chat` treats `[]`, `{"choices": null}` and non-string content as a call error; `FallbackBackend._call` turns any backend exception into a recorded error, then falls back |
| QA-028 | `test_qa_val_regressions.py::test_final_report_explanations_are_requirement_specific_and_grounded` | the row's `explanation` is now the grounded explanation (requirement text + validated decision + verified quotes + cited titles); the model text is kept in `explanation_model`; the frozen MatchReport keeps the model text |
| QA-024 | (flaky, unmarked) `matcher/tests/test_pipeline.py::test_api_backend_success_timeout_and_unavailable` | stub server is now `ThreadingHTTPServer`, as proposed; 15/15 isolated runs pass |

QA-014 (`test_production_provenance_is_complete`) still xfails, now only on `knowledge_version is empty`
(S1, `docs/orchestration/requests/s2-knowledge-version.md`). `base_revision`, `adapter_id` and `adapter_revision` are
present. QA-027 (model level, years below the minimum) stays open: the validator catches it.

Run on this branch: `pytest matcher benchmark/tests tests/qa` gives **191 passed, 6 skipped, 7 xfailed, 0 failed**.
