# V2 real-model run: PDF CV + job paragraph through /api/v2/analyze (2026-10-17, cloud, CPU only)

All models were real; nothing was mocked:
- Reader (PyMuPDF);
- Profile Agent `profile-q1` and Job Agent `job-q1` on plain Qwen3-4B-Instruct-2507 Q4_K_M;
- Matcher Qwen3-4B + LoRA `0b6925b1` with `rag.gated.v1+bm25`;
- Bias `rules_v2`;
- Judge `cross-encoder/nli-deberta-v3-xsmall@a1508764`;
- Reporter Qwen3-0.6B Q8_0.

Serving: ONE llama-cpp-python 0.3.16 server, port 8091, `--config_file llama_multi.cloud.json`. It holds both the
plain and the `+lora` aliases and swaps them in memory (one loaded at a time). The log excerpt shows the swaps.
Hardware: 4 vCPU, 15 GiB, no GPU. Branch `feature/agent-integration`.

Input:
- CV: `eval/profile_agent/cvs/p01_en_classic.txt` (synthetic, invented person), rendered to a 1-page PDF with
  reportlab and sent as `cv_file_b64`. The PDF itself is not committed.
- Job: `job_paragraph.txt`, a single paragraph with a greeting, the title, 3 must and 2 nice requirements, and
  benefits.

Result (`response.json`): HTTP 200, 612 s.

| stage | status | s |
|---|---|---|
| reader | ok (pdf, 1 page, no OCR) | 0.3 |
| profile | ok, 0 leaks left; placeholders NAME 3, EMAIL 2, PHONE 1, URL 2, ADDRESS 1, PERSONAL 3 | 354 |
| job_agent | ok, 5 requirements (3 must, 2 nice); greeting, title and benefits not extracted | 130 |
| matcher_pipeline | ok, LoRA primary answered | 95 |
| reporter | ok, SLM 3/6 sections, 3 deterministic fallbacks | 32 |

| req | kind | min_years | decision | Judge | review |
|---|---|---|---|---|---|
| r1 Python ML experience | must | 2 | UNCERTAIN | n/a | yes |
| r2 SQL | must | — | MET (quote "- Dashboards in Power BI and SQL.") | FAIL | yes |
| r3 Docker | must | — | MET (quote "Deployed models with Docker and FastAPI.") | FAIL | yes |
| r4 Kubernetes | nice | — | MISSING | PASS | no |
| r5 Spark | nice | — | MISSING | PASS | no |

Checks:
- Every MET quote has a character span into the anonymised CV text.
- No identity value is in the response. The name, e-mail, phone, handles, address, birth date and the referee's
  name were searched for.
- The Job Agent warned "no requirement section found, the whole offer was used". The response therefore carries
  review reason `job_agent:validation_warnings`.

This is one synthetic example: it shows the flow works with real models. It is not an accuracy measurement.
GPU latency on the RTX 4050 is not measured here.
