# HireSignal Matcher Agent

Requirement-level CV/job matching. It is a screening aid: every result is reviewable, and no hiring or
rejection decision is made automatically.

## Architecture (one neural model)

```
anonymized CV (matcher.schemas.CV)            job requirements (matcher.schemas.Job)
            \                                   /
             \        ESCO knowledge via BM25 (matcher.knowledge.RagKnowledge -> rag/retrieval.py,
              \       lexical only, requirement text is the query; CV text is never sent to retrieval)
               \                 |
                ONE generative SLM < 1B params (+ optional LoRA of the same base)  matcher.backends.TransformersBackend
                                 |  strict JSON {decision, basis, evidence, explanation}   (prompt: matcher/prompt.py)
                deterministic validation  matcher/validate.py
                                 |
                MET / MISSING / UNCERTAIN + verbatim CV quotes + spans + ESCO refs + review flags   (RequirementResult)
                                 |
                MatchReport (summary: counts, must-have coverage, review count)                    matcher/agent.py
```

No embedding model, reranker or classifier is used. Retrieval is BM25.

## Decisions

| decision | basis | evidence |
|---|---|---|
| MET | supported | at least one verified CV quote |
| MISSING | contradicted | CV quote showing the shortfall or negation |
| MISSING | not_documented | none; absence of evidence, not proof of absence |
| UNCERTAIN | ambiguous | optional |

## Validation rules (`matcher/validate.py`)

The model proposes; these rules decide. Evidence is always stored as the exact CV slice
(`cv.text[start:end]`); quotes are located exactly, else ignoring case and whitespace runs.

| reason | priority | effect |
|---|---|---|
| model_output_invalid | high | not parseable as the schema -> UNCERTAIN |
| inconsistent_decision_basis | high | e.g. MET + not_documented -> UNCERTAIN |
| met_without_verified_evidence | high | MET with no verified quote -> UNCERTAIN |
| negation_in_evidence | high | MET quoting "no / not / never / without / expired / in preparation ..." -> UNCERTAIN |
| duration_not_verified | high | min_years required but no years parseable from the skill's quotes -> UNCERTAIN |
| years_below_minimum_in_evidence | high | years in evidence < minimum -> UNCERTAIN |
| years_not_tied_to_skill | high | years only from quotes that do not name the skill -> MET kept, human must confirm |
| evidence_not_in_cv | medium | the quote is dropped |
| evidence_too_short | medium | quotes under 4 characters are dropped |
| contradiction_without_evidence | medium | MISSING/contradicted without quote -> not_documented |
| semantic_inference_no_term_in_quote | medium | skill MET where no skill term or matching ESCO alias is in the quote |
| no_requirement_term_in_quote | medium | non-skill MET where no requirement word is in the quote |
| uncertain_decision | medium | every UNCERTAIN is reviewed |
| must_have_absence_of_evidence / must_have_contradicted | medium | every missing must-have is reviewed |

`review_priority` is a rule signal, not a probability. When the validator changes the model's decision,
the model's explanation is replaced by the validator's reason.

Known limits (also `shortcut:` comments in the code): negation is lexical; years are attributed per quote,
so "Java (5 years), Python" credits Python.

## Run

```python
from matcher import Matcher, CV, Job
from matcher.backends import TransformersBackend
from matcher.knowledge import RagKnowledge

backend = TransformersBackend("Qwen/Qwen2.5-0.5B-Instruct", revision="7ae557604adf67be50417f59c2c2f167def9a775",
                              adapter_id="finetune/runs/qwen25_05b_lora_pilot/best")
report = Matcher(backend, RagKnowledge()).match(CV(cv_id="c1", text=cv_text), Job.model_validate(job_dict))
```

Benchmark: `python benchmark/run.py --split val --backend transformers --arm qwen2.5-0.5b --adapter <dir> --knowledge rag --out benchmark/results/<name>`.
