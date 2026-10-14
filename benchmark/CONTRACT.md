# Benchmark data contract (shared by benchmark/, finetune/ and matcher/)

One JSON object per line. One line = one CV/job case; scoring is per requirement.

```json
{
  "case_id": "val-003",
  "split": "train|val|test",
  "source": "handwritten|generated",
  "cv":  {"cv_id": "...", "text": "..."},                      // matcher.schemas.CV
  "job": {"job_id": "...", "title": "...", "requirements": [...]},  // matcher.schemas.Job
  "gold": {
    "<req_id>": {
      "decision": "MET|MISSING|UNCERTAIN",
      "basis": "supported|contradicted|not_documented|ambiguous",
      "evidence": ["verbatim substring of cv.text", "..."],     // required for MET and MISSING/contradicted
      "tags": ["exact", "equivalence", "related_not_equivalent", "experience_years", "ambiguous_duration",
               "not_documented", "negation", "rag_only_term", "certification", "education", "language",
               "contradictory_requirement"]
    }
  }
}
```

Rules
- `cv.text` is synthetic and anonymized. No real person data.
- Every gold evidence string MUST be an exact substring of `cv.text` (checked by `benchmark/check_data.py`).
- Gold `decision`/`basis` pairs follow `matcher.validate.CONSISTENT`.
- Files: `benchmark/data/train.jsonl`, `val.jsonl`, `test.jsonl`.
- `test.jsonl` is LOCKED: never used for training, prompt tuning, or model selection. Only the final report reads it.
- Model selection uses `val.jsonl` only. LoRA training uses `train.jsonl` only.
- No CV text is shared between splits (checked by `check_data.py`).
