# S8 request: job context in the Pipeline.run() output

Owner of the file: S2 (`matcher/pipeline.py`). Requested by S8 (Report Writer), 2026-10-16.

The Report Writer consumes only the `Pipeline.run()` dict. Three fields it would show are not in that dict:

1. `job_title` (top level). Today `scripts/run_pipeline.py` passes `job["title"]` to the reporter separately; a caller
   that only has the saved `report.json` cannot show it (`python -m reporter ... --job-title` is the workaround).
2. Per requirement: `category` and `min_years` (from `Requirement`). The reporter does not invent them; with them the
   per-requirement facts given to the SLM could state the required years explicitly instead of relying on the
   requirement text.

Proposal: in `Pipeline.run()` add `"job_title": job.title` and, in `aggregate()` rows, `"category"` and
`"min_years"`. Additive only; no existing key changes. The reporter already treats all three as optional.
