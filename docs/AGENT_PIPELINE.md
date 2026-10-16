# HireSignal Matcher agent pipeline

Branch `feature/matcher-agent-pipeline`; LoRA integration (provenance, review routing, live harness) on
`session/s2-matcher-lora-integration`, details in `docs/MATCHER_INTEGRATION.md`. The order is fixed: each stage only adds findings, and the Matcher decision
is never replaced.

```
Parser (StructuredInputParser; teammates' Reader/Profile/Job agents not integrated yet)
  -> RAG knowledge per requirement (HS_RAG = none | bm25 | qdrant; CV text never sent)
  -> Matcher: fine-tuned Qwen3-4B + LoRA (primary)  --transport failure-->  original Qwen3-4B (fallback)
     strict JSON parse -> form-only repair (never a new decision) ; provenance of the answering model per result
  -> Deterministic Validator (JSON schema, exact CV quotes + spans, years, consistency)
  -> Bias Auditor (rules on every result; counterfactual test of the deployed Matcher, inline or batch)
  -> NLI Judge (DeBERTa-v3-base, fine-tuned; pretrained fallback)
  -> Aggregator (union of review reasons, citations, which model answered)
  -> Report Writer (deterministic markdown; no new claims)
```

## Models per agent

| agent | model / configuration | status |
|---|---|---|
| Matcher, primary | `Qwen/Qwen3-4B-Instruct-2507@cdbee75f` + LoRA `HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora@0b6925b1` (r=16, alpha 32, all 7 linear projections). Served by llama.cpp `--lora_path` on the Q4_K_M base (`scripts/serve_qwen4b_lora.sh`), OpenAI-compatible. Pins in `config/matcher_models.json` | owner decision: initial model. Compatibility verified from Hub metadata (16/16 checks, `docs/matcher_integration/lora_compat.json`). Not yet run live in this pipeline; 202-req validation run in progress elsewhere |
| Matcher, fallback | the same base, no adapter (`unsloth/Qwen3-4B-Instruct-2507-GGUF@a06e946b` Q4_K_M) | measured: val macro-F1 0.630 (BM25 RAG) / 0.634 (no RAG) |
| RAG | BM25 over ESCO (`RagKnowledge`), or the RAG team's dense Qdrant (e5-small) index over ESCO + job postings (`QdrantKnowledge`, using `rag/adapters.py`) | RAG team measurement: neither beats "none" for the base Matcher. Qdrant is selectable, not the default |
| Bias Auditor | no model of its own: rules plus counterfactual re-runs of the **deployed** Matcher (name, gender, nationality and age signals) | measured on the base Matcher only (1/30 flips). **Must be re-run on the LoRA Matcher**; the LoRA is not assumed to change fairness either way |
| NLI Judge | `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli`, fine-tuned on train (τ 0.85); pretrained (τ 0.65) if the checkpoint is missing | measured on base-Matcher outputs. Re-check on LoRA outputs |

## Run

```bash
scripts/serve_qwen4b_lora.sh <lora-adapter-dir> 8081      # primary
python -m llama_cpp.server --model <Q4_K_M.gguf> --model_alias Qwen/Qwen3-4B-Instruct-2507 --port 8080   # fallback
HIRESIGNAL_RAG_DIR=<rag dir> HS_RAG=bm25 python scripts/run_pipeline.py --case val-000 --out out/val-000
# or, in one command (window 1): HS_COMPUTE_WINDOW=1 HIRESIGNAL_RAG_DIR=<rag dir> scripts/live_smoke.sh
#   HS_RAG=qdrant (builds/reuses the dense index under <rag dir>/index), HS_LIVE_COUNTERFACTUAL=1, HS_FALLBACK=off, HS_JUDGE=off
```

## Guarantees and their tests

Tests are in `matcher/tests/test_agent_pipeline.py`, `test_pipeline.py` and `test_matcher_integration.py` (real HTTP
backend against fake llama.cpp servers, all MOCK); live tests in `test_live_matcher.py` (skipped unless `HS_LIVE=1`).

| guarantee | test |
|---|---|
| A correct flow carries verbatim evidence, character spans and RAG citations | `test_correct_matcher_full_flow_with_citations` |
| A related skill (ESCO alias) is cited, and is not flagged as an unsupported inference | same |
| Missing evidence goes to review (not proof of absence) and is never rejected | same |
| A negation or contradiction error is flagged by the Judge and the decision is kept | `test_negation_error_is_flagged_not_overwritten` |
| Fabricated evidence or wrong years become UNCERTAIN, and the raw decision is kept | `test_fabricated_evidence_and_wrong_years` |
| An unfair (nationality-biased) Matcher is caught by the counterfactual audit | `test_unfair_matcher_caught_by_live_counterfactual` |
| LoRA down: falls back to the base model, recorded and routed to review | `test_fallback_to_base_model_when_lora_down` |
| Both models down: UNCERTAIN, never an invented decision | `test_both_models_down_never_invents_a_decision` |
| The Qdrant provider returns ESCO + job chunks and never sends CV text | `test_qdrant_knowledge_contract_with_job_chunks` |
| Configuration wiring, and the Judge falling back to pretrained | `test_factory_wiring_and_judge_fallback` |
| Every result names the model that answered (adapter repo + sha or none, base revision, weights, prompt, knowledge) | `test_lora_primary_provenance_per_result_and_report_schema` |
| The served alias is checked at `/v1/models` (llama-cpp-python echoes any alias) | `test_served_alias_mismatch_is_flagged` |
| Malformed JSON: unparseable/synonym/template labels -> UNCERTAIN + review; truncated output repaired + review | `test_malformed_json_paths`, `test_strict_repair_never_invents_a_decision` |
| Fallback answers and both-down results are provenanced and routed to review; the MatchReport stays schema-valid | `test_fallback_answer_is_provenanced_and_routed_to_review`, `test_both_down_never_invents_a_decision_and_report_stays_valid` |
| Citations are exactly the knowledge ids shown in the prompt | `test_citations_are_the_ids_shown_in_the_prompt` |
| Scripted backends are labelled MOCK in provenance and in the report | `test_scripted_backends_are_labelled_mock` |
| A live bias test whose variants were answered by another model is flagged | `test_counterfactual_answered_by_another_model_is_flagged` |
