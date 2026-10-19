# Figures (T14 Part B)

All figures are made by `scripts/make_figures.py` from the result files below. No number is typed by hand. Each figure
is saved as PNG (200 dpi) and SVG. They use grey shades and hatches, so they also read in black and white.
Rebuild them with `.venv\Scripts\python scripts\make_figures.py`. `sources.json` lists the same sources.

| figure | source | caption |
|---|---|---|
| `1_pipeline` | `n8n/hiresignal_v1.json` (node count; the script checks that every station node exists) | The n8n chain, one node per station, with the model or method of each station. Dashed boxes are where a person acts: the recruiter confirms the requirement card, and the review form decides. |
| `2_rag_retrieval` | `eval/results/2026-10-18_rag_retrieval_checked/summary.json` | ESCO retrieval MRR@10 on the checked golds (dev 24 / test 22 queries). Rows: BM25; dense with three embedders; hybrid (RRF); + rerank; + graph expansion; chunking B. Dense all-MiniLM-L6-v2 is the production setting (V6). |
| `3_multimodal_cer` | `eval/results/2026-10-18_multimodal/summary.json` | Character error rate of the Reader by setup (OCR only / vision / late fusion = production / early fusion), and on test by condition (close photo / hard photo / scan). |
| `4_bias` | `eval/results/2026-10-18_bias/summary.json` (flips, T11 production) + `data/processed/counterfactuals/` (identical share, recomputed with today's code) | Left: requirement decisions flipped by a name / origin swap, without protection (raw text, reduced subset) vs with the anonymiser + guard. Right: share of counterfactual variants whose Matcher input is byte-identical to the base, per family: anonymiser alone, T11 production (+ leakage check), and today's production (+ T11b over-mask fix + T14 injection guard). |
| `5_final_outcomes` | `eval/results/2026-10-19_final_eval/final_summary.json` | Final outcome confusion matrices through n8n (test pairs, and the photo / scan cases), with the review rate, false invites and false rejects. |
| `6_report_writer` | `eval/results/2026-10-19_report_writer/summary.json` (T12 checker) + `eval/results/2026-10-19_report_writer_t13/summary.json` (T13 checker) | Report Writer on the 28 dev records: passes on the first try, passes after one retry, and template fallback, by prompt version (v0 to v3) and model (Qwen3-4B vs Qwen3-0.6B). The dotted line marks the stricter T13 checker. |
| `7_gate_variants` | `eval/results/2026-10-18_outcome_gate/gate/summary.json` | Outcome gate variants (a) to (f) and the temporary rule on dev (26 pairs): false invites, false rejects and the review rate. (b) is chosen. |
| `8_latency` | `eval/results/2026-10-19_final_eval/final_summary.json` | Mean seconds per CV for each station in the final evaluation through n8n (real-GPU, RTX 4050 6 GB), for text CVs and for photos / scans. |
