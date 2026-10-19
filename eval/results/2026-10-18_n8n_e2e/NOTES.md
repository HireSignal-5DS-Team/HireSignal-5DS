# Notes — n8n end-to-end 2026-10-18 (real-GPU, RTX 4050 Laptop 6 GB; n8n 2.43.7; llama.cpp b11139, Qwen3-4B Q4_K_M + Matcher LoRA)

Runs through the webhook of workflow `HireSignal v1` (`scripts/n8n_e2e.py`, config in `config.json`):

| run | input | n8n execution | wall s | outcome (TEMP rule) | score |
|---|---|---|---|---|---|
| P15 | Djinni CV of pair P15 + J2 | 7 | 56.8 | reject (must-have MISSING r1, r2, r3, r6) | 43 |
| P35 | Djinni CV of pair P35 + J4 | 8 | 40.5 | reject (must-have MISSING r1, r3) | 13 |
| kaggle | Kaggle IT PDF `10089434.pdf` + J4 | 9 | 196.6 | review (profile partial extraction; 2 dropped quotes) | 13 |

Files per run: `<run>_result.json` (the webhook reply), `<run>_execution.json` (execution id, n8n start/stop, per-node
timings from n8n's runData, station timings, checks). `summary.json` = all three. `manual_trigger_P15_result.json` =
the Manual demo trigger run (`n8n execute`, same decisions as webhook run P15). `error_path/` = error-workflow test.

Checks (all three runs): HTTP 200 and valid JSON; execution status success; every `/match` used LoRA scale 1 and ran
one at a time (Loop Over Items, batch size 1); 0 identity values (from `private/<cv_id>.json`: P15 2 — a false positive,
see below —, P35 0, Kaggle 3) found in the stored n8n execution data (searched as text and as decoded base64); none of
the raw CV lines that the anonymiser changed appear in the execution data (the raw text stays in
`private/<cv_id>.reader.json`). The uploaded file itself is kept by n8n's binary store
(`.n8n/storage/workflows/<id>/executions/<n>/binary_data/`, git-ignored): it is the original CV.

Earlier runs of the same day (executions 1-6) are superseded: they sent the 7-13 `/match` requests
concurrently (n8n HTTP "batching" only spaces requests out), which made server times overlap; the workflow now uses
Loop Over Items. Execution 10: error workflow not run (not published). Execution 11 + 12: error path test, see `error_path/`.

Observed (single runs, not a measurement): P15 r6 "Experience with GCP or other cloud providers" -> MISSING although the
CV says "Azure and AWS services"; P15 anonymised text has "Power [NAME]" and "ETL [NAME]" (V2 header name detector
took "BI Tools" as the candidate's name); P15 r7 "Good spoken English" MET with quotes that do not mention English.
