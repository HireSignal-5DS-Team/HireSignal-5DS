# Val error analysis (LIVE predictions, read from committed run files)

## qwen3-4b-q4-none-val

n=202, non-MET gold=116. raw false-MET 3 (0.026), final 1 (0.009), final and unreviewed by the validator 0.

| case/req | gold | final | requirement | model quote | weak cue | validator reasons | judge |
|---|---|---|---|---|---|---|---|
| val-014/r2 | MISSING/contradicted | UNCERTAIN | Node.js: 4 years of experience or more | Node.js in daily use for 3 years. |  | years_below_minimum_in_evidence, uncertain_decision | - |
| val-016/r1 | UNCERTAIN/ambiguous | MET | Angular: 2 years of experience or more | Applied Angular in various side projects over time. | yes | duration_not_verified | - |
| val-042/r1 | MISSING/contradicted | UNCERTAIN | React: 3 years of experience or more | React in daily use for 2 years. |  | years_below_minimum_in_evidence, uncertain_decision | - |

Explanations: 178 distinct over 192 parsed; on-topic 1.000; numbers grounded 0.964. Most common: 3x 'The CV explicitly mentions modelling relational tables with primary and foreign keys, which demonstrates working knowledge of database design.'; 3x "The CV does not mention any postgraduate (master) degree in a computing field. The academic background lists only a Bachelor's degree in Marketing."

## qwen3-4b-q4-rag-val

n=202, non-MET gold=116. raw false-MET 3 (0.026), final 1 (0.009), final and unreviewed by the validator 0.

| case/req | gold | final | requirement | model quote | weak cue | validator reasons | judge |
|---|---|---|---|---|---|---|---|
| val-014/r2 | MISSING/contradicted | UNCERTAIN | Node.js: 4 years of experience or more | Node.js in daily use for 3 years. |  | years_below_minimum_in_evidence, uncertain_decision | - |
| val-016/r1 | UNCERTAIN/ambiguous | MET | Angular: 2 years of experience or more | Applied Angular in various side projects over time. | yes | duration_not_verified | - |
| val-042/r1 | MISSING/contradicted | UNCERTAIN | React: 3 years of experience or more | React in daily use for 2 years. |  | years_below_minimum_in_evidence, uncertain_decision | - |

Explanations: 174 distinct over 185 parsed; on-topic 0.995; numbers grounded 0.946. Most common: 4x "The CV explicitly states the candidate was hired to 'engineer cloud architecture' for a multi-region SaaS product, which directly matches the requirement of designing cloud architecture."; 3x "The CV does not mention any responsibility related to maintaining information network hardware. The only references to maintenance are of the team's information wiki, which is unrelated to physical or network hardware."

## qwen3-4b-q4+hslora-none-val

n=202, non-MET gold=116. raw false-MET 7 (0.060), final 3 (0.026), final and unreviewed by the validator 1.

| case/req | gold | final | requirement | model quote | weak cue | validator reasons | judge |
|---|---|---|---|---|---|---|---|
| val-009/r3 | UNCERTAIN/ambiguous | MET | Node.js: 2 years of experience or more | Applied Node.js in various side projects over time. | yes | duration_not_verified | FAIL |
| val-014/r2 | MISSING/contradicted | UNCERTAIN | Node.js: 4 years of experience or more | Node.js in daily use for 3 years. |  | years_below_minimum_in_evidence, uncertain_decision | NOT_APPLICABLE |
| val-016/r1 | UNCERTAIN/ambiguous | MET | Angular: 2 years of experience or more | Applied Angular in various side projects over time. | yes | duration_not_verified | FAIL |
| val-024/r6 | MISSING/contradicted | UNCERTAIN | React: 3 years of experience or more | React in daily use for 1 year. |  | years_below_minimum_in_evidence, uncertain_decision | NOT_APPLICABLE |
| val-028/r4 | MISSING/contradicted | UNCERTAIN | Vue.js: 3 years of experience or more | Vue.js in daily use for 1 year. |  | years_below_minimum_in_evidence, uncertain_decision | NOT_APPLICABLE |
| val-029/r4 | UNCERTAIN/ambiguous | MET | Working knowledge of Angular | Watched tutorials about Angular in spare time. | yes | **none** | FAIL |
| val-037/r2 | MISSING/contradicted | UNCERTAIN | React: 4 years of experience or more | React in daily use for 2 years. |  | years_below_minimum_in_evidence, uncertain_decision | NOT_APPLICABLE |

Explanations: 4 distinct over 202 parsed; on-topic 0.000; numbers grounded 1.000. Most common: 88x 'The CV directly shows this requirement; the quote is copied from the CV.'; 52x 'The CV shows this requirement is not met; the quote is copied from the CV.'

## qwen3-4b-q4+hslora-rag-val

n=202, non-MET gold=116. raw false-MET 7 (0.060), final 4 (0.034), final and unreviewed by the validator 2.

| case/req | gold | final | requirement | model quote | weak cue | validator reasons | judge |
|---|---|---|---|---|---|---|---|
| val-009/r3 | UNCERTAIN/ambiguous | MET | Node.js: 2 years of experience or more | Applied Node.js in various side projects over time. | yes | duration_not_verified | FAIL |
| val-014/r2 | MISSING/contradicted | UNCERTAIN | Node.js: 4 years of experience or more | Node.js in daily use for 3 years. |  | years_below_minimum_in_evidence, uncertain_decision | NOT_APPLICABLE |
| val-016/r1 | UNCERTAIN/ambiguous | MET | Angular: 2 years of experience or more | Applied Angular in various side projects over time. | yes | duration_not_verified | FAIL |
| val-017/r1 | UNCERTAIN/ambiguous | MET | Working knowledge of React | Watched tutorials about React in spare time. | yes | **none** | FAIL |
| val-024/r6 | MISSING/contradicted | UNCERTAIN | React: 3 years of experience or more | React in daily use for 1 year. |  | years_below_minimum_in_evidence, uncertain_decision | NOT_APPLICABLE |
| val-028/r4 | MISSING/contradicted | UNCERTAIN | Vue.js: 3 years of experience or more | Vue.js in daily use for 1 year. |  | years_below_minimum_in_evidence, uncertain_decision | NOT_APPLICABLE |
| val-029/r4 | UNCERTAIN/ambiguous | MET | Working knowledge of Angular | Watched tutorials about Angular in spare time. | yes | **none** | FAIL |

Explanations: 4 distinct over 202 parsed; on-topic 0.000; numbers grounded 1.000. Most common: 91x 'The CV directly shows this requirement; the quote is copied from the CV.'; 55x 'The CV shows this requirement is not met; the quote is copied from the CV.'

