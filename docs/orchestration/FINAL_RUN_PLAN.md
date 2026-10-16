# Final real-model end-to-end run (window 2)

Owner: Session 6. Run by `scripts/final_run.sh` in the orchestrator container, one model job under
`flock /home/user/hs_queue.lock`. Results go to `benchmark/results/final/`.

## What is frozen before the run

Configuration selected on **val only** (no choice below uses test data):

| component | production setting | evidence (val) |
|---|---|---|
| Matcher | Qwen3-4B-Instruct-2507 Q4_K_M (`unsloth/...-GGUF@a06e946b`) + LoRA `HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora@0b6925b1`, llama.cpp, prompt p1, temperature 0, 192 new tokens; base model as fallback | macro-F1 0.908 vs base 0.634 (eval session, 202 reqs) |
| RAG | `HS_RAG=gated` (`rag.gated.v1` over BM25, k = 3) | gated vs none −0.005 [−0.028, +0.014]; false-MET equal to none; alias 0.81 → 0.90 (S1) |
| Validator | v2 (`4f38c97` + `971f6fd`) | replay: false-MET 0, in-sample (rules written after val errors) |
| Bias Auditor | `rules_v2`; reviewer opt-in, not used in the scored run | blind holdout FPR 1/18 vs 9/18 (S4, orchestrator-verified) |
| Judge | pretrained `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli`, τ 0.65 (the fine-tuned checkpoint is not available in any container) | τ recheck on train-dev (S5) |

## Test split unlock

`bench-v1` test: 45 cases, 199 requirements. It is used **once**, after this plan is committed, for the arms below.
No configuration is changed after seeing test numbers. If a run fails mid-way it is resumed, not re-designed.

## Arms (all on test, same server build, same GGUF)

| arm | Matcher | knowledge | purpose |
|---|---|---|---|
| A | LoRA | gated | **headline result** for the production configuration |
| B | LoRA | none | held-out effect of RAG on the LoRA Matcher |
| C | base | gated | held-out effect of fine-tuning (run if time allows) |

Each arm's raw outputs are replayed through validator v1 (`4f38c97^`) and v2 (current), so the held-out effect of
validator v2 is reported separately from the model. Paired comparisons (A vs B, A vs C): McNemar on correctness and a
bootstrap 95 % CI of the macro-F1 difference (`rag/significance.py`).

Reported per arm: macro-F1, false-MET, unreviewed false-MET, JSON-valid, UNCERTAIN rate, human-review rate, latency
p50/p95, peak RSS, full provenance (model + adapter sha, knowledge provider version, prompt id, validator commit).

## Full-pipeline check

Three test cases through `scripts/run_pipeline.py` with the production factory defaults (LoRA primary, fallback,
gated RAG, validator v2, `rules_v2`, pretrained Judge): every MatchReport must validate against the JSON schema, carry
provenance, verbatim evidence spans, `rag_refs` equal to the refs shown, and grounded explanations. This is a
functional check, not a metric.

## Not covered

- Soft prompt tuning (S3): waits on a GPU run by the owner. Not part of production.
- Fine-tuned Judge: checkpoint not available; the pretrained Judge is used.
- Bias counterfactuals on test: S4 measures them on val (base vs LoRA); not repeated here.
- bench-v1 is synthetic. Results describe this benchmark, not real recruiting data.
