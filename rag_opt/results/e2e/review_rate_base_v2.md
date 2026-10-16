# Review-rate comparison (base, validator v2; saved LIVE raw outputs replayed, no model call)

| comparison | review rate base → cand | Δ | 95% CI | reviewed only base / only cand | McNemar p | dropped reviews: correct / wrong |
|---|---|---|---|---|---|---|
| bm25 vs none | 0.802 → 0.777 | -0.025 | [-0.059, +0.010] | 10 / 5 | 0.3018 | 10 / 0 |
| gated vs none | 0.802 → 0.767 | -0.035 | [-0.064, -0.005] | 8 / 1 | 0.0391 | 8 / 0 |

Largest review-reason count changes (cand − base):

- bm25 vs none: {'model_output_invalid': 9, 'semantic_inference_no_term_in_quote': -6, 'uncertain_decision': 4, 'inconsistent_decision_basis': 4}
- gated vs none: {'semantic_inference_no_term_in_quote': -6, 'model_output_invalid': 3, 'uncertain_decision': 3, 'must_have_absence_of_evidence': -3}
