# Notes — station API smoke 2026-10-18 (real-GPU, RTX 4050 Laptop 6 GB, llama.cpp b11139, Qwen3-4B Q4_K_M + Matcher LoRA)

Stack: `scripts/start_stack.ps1` (llama-server 8090 + station API 8010). Command:
`.venv\Scripts\python scripts\api_smoke.py --out eval\results\2026-10-18_api_smoke`

Inputs (`inputs/inputs.json`):
- Kaggle INFORMATION-TECHNOLOGY PDF `10089434.pdf` (path + sha256 only; the file stays in git-ignored `data/raw/`).
- Djinni CV of pair P11 (first J2 pair, stratum strong), copied in `inputs/`.
- `data/processed/jobs/J2.txt` (Data Engineer), copied in `inputs/`.

Flow: PDF -> /reader -> /profile; Djinni CV -> /reader -> /profile; J2 -> /job; /match for each of the 7 requirements on
the Djinni CV's anonymised text. Files: `outputs.json` (all responses; the Reader's `text`/`sections` are replaced by
length + sha256 because raw CV text holds identity; the full Reader output is in git-ignored `private/api_smoke/`),
`timings.json` (client wall time and server `elapsed_s` per call), `checks.json`, `run.log`, `config.json`.

Checks (all ok): responses validate against `services/contracts.py`; none of the identity values written to
`private/<cv_id>.json` (3 for the PDF, 0 for the Djinni CV, which the source already anonymised) appears in any
/profile, /job, /match response or in `outputs.json`; the 3 Matcher quotes equal `cv_text[start:end]`; no invalid Matcher JSON.

First run (same day, overwritten): `match_r7` was invalid JSON, cut at max_tokens 192 (`finish_reason: length`; the
LoRA quoted three whole paragraphs). Fix: station max_tokens 384 (`MATCHER_MAX_TOKENS`). `max_tokens_check.txt`: on the
30 lora_k items of `../2026-10-18_schema_check/`, raw output with 384 is identical to 192 on 30/30.

Observed (single smoke run, not a measurement):
- J2 on this CV: r1-r6 MISSING/not_documented (the CV names no DWH, SQL, Python or cloud: correct reading); r7 "Good
  spoken English" -> MET, but its 3 quotes are unrelated paragraphs (the supporting line "English level: upper" is not
  quoted). The quotes are verbatim, so validator v1 keeps it: a case for the Judge station (quotes must SUPPORT the decision).
- Kaggle PDF /profile took 146 s (11 chunks; 2 chunks cut at 768 tokens -> `profile:partial_extraction_requires_review`).
- Djinni CV /profile: `profile:name_not_found` (no name in an anonymised source CV): every Djinni CV gets this flag.
