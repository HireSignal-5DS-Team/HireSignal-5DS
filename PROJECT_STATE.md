# HireSignal: project state (Matcher line on `claude/kind-albattani-k7qlt9`)

Updated 2026-10-15. The evidence for each item is the path named next to it.

## Branches (origin)

| branch | content | relation to this branch |
|---|---|---|
| `main` | initial commit only | base |
| `claude/gracious-fermi-ncuem4` (`1f5610b`) | team RAG: ESCO ICT subset (1,621 concepts), 20 USAJOBS postings, BM25/dense/hybrid, exp02/exp03, FastAPI, n8n | **used read-only** via `HIRESIGNAL_RAG_DIR`; not merged (merge was refused by the environment's permission policy) |
| `claude/hiresignal-rag-data-audit-fbge7j` (`ae727d4`) | CSV exports of the RAG data + audit | not used |
| `claude/kind-albattani-k7qlt9` (this) | Matcher, synthetic benchmark, LoRA pipeline, docs | — |
| `claude/vigilant-albattani-dmn3pk` (`22f4654`) | **parallel session** with its own Matcher line. It has handwritten val/test data, 10 benchmarked arms, a CPU **pilot LoRA** (Qwen2.5-0.5B), and a locked-test run (macro-F1 0.563, false-MET 1.7 %) | independent. Not merged or modified. **Owner decision needed:** keep one line or reconcile them |

## Verified in this line

- Matcher package (`matcher/`): schemas, prompt, deterministic validation, BM25 RAG adapter, backends, report.
  Tests: see `OVERNIGHT_REPORT.md`.
- One-generative-model constraint: < 1B guard, adapter base check, and RAG with no neural model (asserted in tests).
- Benchmark `bench-v1` (`benchmark/data/MANIFEST.json`): synthetic, split-disjoint, test locked.
- Real CPU benchmark of sub-1B models on val: `benchmark/results/`, `benchmark/results/COMPARISON_val.md`.
- Model and adapter facts verified on the Hub at pinned revisions (`docs/MATCHER_REPORT.md` §6, `docs/MODEL_AUDIT.md`).
- LoRA trainer smoke-tested on a tiny random model only. **No HireSignal adapter trained in this line.**

## Not accessible / missing

- Local Windows components (`hiresignal_cv_reader`, `hiresignal_benchmark`, `hiresignal_finetune`):
  contracts are in `LOCAL_INTEGRATION_HANDOFF.md`.
- Other Claude conversations, including the October 14 research: not readable from this environment. The
  decisions here come from the mission prompt and the git history.
- O*NET: not in the repository.

## Next steps

See `OVERNIGHT_REPORT.md` → "Next steps".
