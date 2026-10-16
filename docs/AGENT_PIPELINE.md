# HireSignal Matcher agent pipeline

Branch `feature/matcher-agent-pipeline`. The order is fixed: each stage only adds findings, and the Matcher decision
is never replaced.

```
Parser (StructuredInputParser; teammates' Reader/Profile/Job agents not integrated yet)
  -> RAG knowledge per requirement (HS_RAG = none | bm25 | qdrant; CV text never sent)
  -> Matcher: fine-tuned Qwen3-4B + LoRA (primary)  --transport failure-->  original Qwen3-4B (fallback)
  -> Deterministic Validator (JSON schema, exact CV quotes + spans, years, consistency)
  -> Bias Auditor (rules on every result; counterfactual test of the deployed Matcher, inline or batch)
  -> NLI Judge (DeBERTa-v3-base, fine-tuned; pretrained fallback)
  -> Aggregator (union of review reasons, citations, which model answered)
  -> Report Writer (deterministic markdown; no new claims)
```

## Models per agent

| agent | model / configuration | status |
|---|---|---|
| Matcher, primary | `Qwen/Qwen3-4B-Instruct-2507` + LoRA `HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora@0b6925b1` (r=16, all linear projections). Served by llama.cpp `--lora_path` on the Q4_K_M base (`scripts/serve_qwen4b_lora.sh`), OpenAI-compatible | owner decision: initial model. Measured (val, 202): macro-F1 0.897 BM25 RAG / 0.908 no RAG, false-MET 0.034 / 0.026, JSON 1.000, attribution 1.000 (MATCHER_REPORT §9) |
| Matcher, fallback | the same base, no adapter (`unsloth/Qwen3-4B-Instruct-2507-GGUF@a06e946b` Q4_K_M) | measured: val macro-F1 0.630 (BM25 RAG) / 0.634 (no RAG) |
| RAG | BM25 over ESCO (`RagKnowledge`), or the RAG team's dense Qdrant (e5-small) index over ESCO + job postings (`QdrantKnowledge`, using `rag/adapters.py`) | RAG team measurement: neither beats "none" for the base Matcher. LoRA: BM25 0.897 vs none 0.908, with a lower review rate (0.574 vs 0.663). Qdrant is selectable, not the default: it ran live, but its ESCO citations were off-topic (see below) |
| Bias Auditor | no model of its own: rules plus counterfactual re-runs of the **deployed** Matcher (name, gender, nationality and age signals) | base Matcher 1/30 flips; LoRA Matcher 1/30 (name signal on a borderline partial-evidence item). No systematic effect at n=30 |
| NLI Judge | `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli`, fine-tuned on train (τ 0.85); pretrained (τ 0.65) if the checkpoint is missing | behind LoRA + BM25: error-detection AUROC 0.987; 65/202 pass unreviewed with 0 errors (2 false-METs pass without the Judge). Required, not optional |

## Run

```bash
scripts/serve_qwen4b_lora.sh <lora-adapter-dir> 8081      # primary
python -m llama_cpp.server --model <Q4_K_M.gguf> --model_alias Qwen/Qwen3-4B-Instruct-2507 --port 8080   # fallback
HIRESIGNAL_RAG_DIR=<rag dir> HS_RAG=bm25 python scripts/run_pipeline.py --case val-000 --out out/val-000
#   HS_RAG=qdrant (builds/reuses the dense index under <rag dir>/index), HS_LIVE_COUNTERFACTUAL=1, HS_FALLBACK=off, HS_JUDGE=off
```

## Guarantees and their tests

All tests are in `matcher/tests/test_agent_pipeline.py` and `test_pipeline.py`.

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

## Live integration runs (CPU, llama.cpp; outputs in `examples/live/`, synthetic benchmark CVs only)

| run | configuration | result vs gold | what it shows |
|---|---|---|---|
| `val-000-bm25-cf` | LoRA + BM25 + fine-tuned Judge + live counterfactual | 6/6 | citations on 4 requirements; no bias flip in 48 extra calls; contradiction and absence go to review |
| `val-001-fallback` | `HS_MATCHER_URL` pointing at a dead port | 3/3 | every requirement was answered by the base fallback, recorded in `matcher_call`, and routed to review (`matcher:fallback_model_used`) |
| `val-002-qdrant` | LoRA + dense Qdrant (e5-small; the index was built on first use, 7.3 MB) | 4/4 | provider works end to end, but the ESCO citations are off-topic (e.g. "SPARQL" for r1). The dense retrieval quality, not the wiring, is why Qdrant is not the default. No job chunks: the val jobs are not in the RAG index |

The Qdrant RAG needs `qdrant-client` and `sentence-transformers` (in `requirements-matcher.txt`).
`sentence-transformers` requires `huggingface_hub<2`.
