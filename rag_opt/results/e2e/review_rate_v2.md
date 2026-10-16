# Review-rate comparison (lora, validator v2 (4f38c97); saved LIVE raw outputs replayed, no model call)

| comparison | review rate base → cand | Δ | 95% CI | reviewed only base / only cand | McNemar p | dropped reviews: correct / wrong |
|---|---|---|---|---|---|---|
| bm25 vs none | 0.668 → 0.584 | -0.084 | [-0.124, -0.049] | 17 / 0 | 0.0 | 15 / 2 |
| gated vs none | 0.668 → 0.594 | -0.074 | [-0.114, -0.040] | 15 / 0 | 0.0001 | 15 / 0 |
| none-repeat vs none | 0.668 → 0.663 | -0.005 | [-0.015, +0.000] | 1 / 0 | 1.0 | 0 / 1 |
| gated vs none-repeat | 0.663 → 0.594 | -0.069 | [-0.104, -0.035] | 14 / 0 | 0.0001 | 14 / 0 |
| bm25 vs none-repeat | 0.663 → 0.584 | -0.079 | [-0.119, -0.045] | 16 / 0 | 0.0 | 14 / 2 |

Largest review-reason count changes (cand − base):

- bm25 vs none: {'semantic_inference_no_term_in_quote': -13, 'uncertain_decision': -4, 'must_have_contradicted': 1, 'must_have_absence_of_evidence': -1}
- gated vs none: {'semantic_inference_no_term_in_quote': -13, 'must_have_absence_of_evidence': -4, 'must_have_contradicted': 2, 'years_below_minimum_in_evidence': 1}
- none-repeat vs none: {'uncertain_decision': 2, 'semantic_inference_no_term_in_quote': -1, 'must_have_contradicted': -1, 'must_have_absence_of_evidence': -1}
- gated vs none-repeat: {'semantic_inference_no_term_in_quote': -12, 'must_have_contradicted': 3, 'must_have_absence_of_evidence': -3, 'uncertain_decision': -2}
- bm25 vs none-repeat: {'semantic_inference_no_term_in_quote': -12, 'uncertain_decision': -6, 'must_have_contradicted': 2, 'years_below_minimum_in_evidence': -2}
