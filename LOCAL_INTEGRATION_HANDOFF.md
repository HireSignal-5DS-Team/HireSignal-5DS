# Local integration handoff (Windows laptop components)

The components `hiresignal_cv_reader`, `hiresignal_benchmark` and `hiresignal_finetune` exist only on the
Windows laptop. The cloud sessions never accessed them, so nothing here was tested against their real output.
This file defines the contracts they must meet to plug into the Matcher.

## 1. CV reader → `matcher.schemas.CV`

```json
{"cv_id": "cv-123", "text": "<full anonymized CV text, as one string>", "structured": {"...": "optional parsed fields"}}
```

- `text` is the only evidence source. Every quote is checked as an exact substring of it and stored with
  `[start, end)` offsets, so the reader must not normalise or rewrite text after anonymization.
- `structured` (skills lists, dates, sections) is passed through and **never** used as evidence.
- Anonymize before this point: no names, e-mails, phones or addresses.
- Validate: `CV.model_validate(obj)`. Schema file: `matcher/json_schemas/CV.schema.json`.

## 2. Job requirements → `matcher.schemas.Job`

```json
{"job_id": "usajobs-882803700", "title": "Data Scientist",
 "requirements": [{"req_id": "r1", "text": "At least 3 years of Python", "kind": "must",
                   "category": "experience", "skill_terms": ["Python"], "min_years": 3}]}
```

`skill_terms` are the retrieval queries (requirement wording only, never CV text). `min_years` enables the
duration check. Schema file: `matcher/json_schemas/Job.schema.json`.

## 3. Matcher call

```python
from matcher import CV, Job, Matcher
from matcher.backends import TransformersBackend
from matcher.knowledge import RagKnowledge          # HIRESIGNAL_RAG_DIR -> rag/ of claude/gracious-fermi-ncuem4

backend = TransformersBackend("Qwen/Qwen2.5-0.5B-Instruct", revision="7ae557604adf67be50417f59c2c2f167def9a775",
                              device="cuda")          # + adapter_id=... for a LoRA of the same base
report = Matcher(backend, RagKnowledge()).match(CV(**cv_json), Job(**job_json))
print(report.model_dump_json(indent=2))            # validates against MatchReport.schema.json
```

## 4. Local benchmark → `benchmark/`

If `hiresignal_benchmark` has its own cases, convert them to the `benchmark/data/*.jsonl` case format
(`benchmark/make_dataset.py` docstring and `benchmark/tests` show the invariants). Then run
`python -m benchmark.run ... --data-dir <folder>` with a `MANIFEST.json` that has the file sha256 values.
Keep any established protocol of the local benchmark. If the two disagree, document why before replacing it.

## 5. Local fine-tuning → `finetune/`

`finetune/train_lora.py` consumes `{"messages": [system, user, assistant]}` built by `finetune/build_sft.py`
from the same prompt as inference. An adapter trained by `hiresignal_finetune` can be benchmarked with
`--adapter <dir>`. `check_adapter_compat` refuses it if its `adapter_config.json` names another base.
Never merge an adapter trained on a different base.

## 6. Open items

- A parallel cloud session produced a separate implementation on `claude/vigilant-albattani-dmn3pk`. Its
  benchmark data is handwritten, it has a pilot LoRA and a locked-test run. Choose which line to keep, or how
  to reconcile them, before integrating the laptop components. See `PROJECT_STATE.md`.
