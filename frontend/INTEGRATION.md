# Backend handoff — Semah and FastAPI developer

## Verified repository facts

Inspected 2026-10-16. Integration branch `claude/beautiful-galileo-o36bdv`, commit `fb68665b8b3586e379688c9e94e7efa0fccbd9ba`, is designated by `docs/orchestration/ORCHESTRATION.md`. `main` contains the project introduction only. The integration tree contains no frontend package and no FastAPI app implementing the four proposed endpoints.

Read before implementation:

- `matcher/schemas.py`, schema version 1.0.0
- `matcher/json_schemas/{CV,Job,MatchReport}.schema.json`
- `LOCAL_INTEGRATION_HANDOFF.md`
- `docs/orchestration/{ORCHESTRATION,STATUS}.md`

No model, agent, evaluation, training, schema or backend business logic was changed.

## Contracts preserved

`src/contracts.ts` mirrors `CV`, `Requirement`, `Job`, `RequirementResult`, `MatchSummary` (inline), and `MatchReport`. Frontend `Campaign` and review records are separate view-layer objects, not additions to the strict Pydantic models.

- CV `text` is the evidence source. Quotes are verbatim. Character offsets use Unicode code points, matching Python `[start,end)` semantics, rather than JavaScript UTF-16 offsets.
- `structured` is not evidence.
- MISSING / `not_documented` means absence of documentation, not lack of ability.
- `rag_refs` means **knowledge shown**, not sources cited by the model and never candidate evidence.
- No fit score is displayed. `must_coverage` in exported domain data is the schema's transparent count ratio; in MOCK it is simulated, not a validated scoring service.
- Judge and Bias Auditor are responsibilities, not separate model identities. They are not executed in this demo; fairness is not asserted.
- Human notes and review status never overwrite Matcher decisions.

## Transport gaps and enablement checklist

| Endpoint                    | Implemented client                  | Missing agreement                                                           |
| --------------------------- | ----------------------------------- | --------------------------------------------------------------------------- |
| GET `/health`               | `ApiClient.health()`                | JSON response shape and success semantics                                   |
| GET `/ready`                | `ApiClient.ready()`                 | Readiness schema and unavailable status codes                               |
| GET `/api/v1/models/status` | `ApiClient.models()`                | Model provenance and capability schema                                      |
| POST `/api/v1/match`        | `ApiClient.match(payload: unknown)` | Pydantic request envelope, sync/async response, batch semantics, error body |

Service checks show raw responses, labeled **Response received**, without inferring healthy/ready/model-loaded from HTTP 200. The transport handles non-2xx, missing configuration, network/CORS failure, timeout (20 seconds), empty bodies and malformed JSON. No credentials are sent or stored.

REAL matching deliberately throws a clear integration error, and the UI disables submission. `VITE_EXECUTION_MODE=REAL` alone does not enable an invented request or successful model execution.

To enable it:

1. Supply the FastAPI OpenAPI schema and examples for all four endpoints. Confirm whether POST accepts raw CV/job text, structured `{cv,job}`, multipart files, or a different envelope. The current Matcher domain schema is not enough to establish this.
2. Define text extraction/anonymization and Job Agent boundaries. The DEMO's line-per-requirement logic is not an AI job-description parser and must not silently become the real adapter.
3. Implement a `RealAnalysisAdapter` behind `AnalysisAdapter.run` in `src/api.ts`. Validate the actual response at runtime before converting it to `Campaign`. Add contract fixtures/tests. Preserve raw provenance, evidence offsets, Judge findings, fairness findings, errors and fallback signals.
4. Specify synchronous versus queued jobs. If queued, provide job IDs and polling/events with cancellation. Without telemetry, show an indeterminate pending request; never simulate real per-agent completion.
5. Confirm input limits, timeout, supported file types, authentication, consent, retention, and persistence. Do not expose server tokens through Vite variables. A browser app needs user-scoped authentication or a protected server intermediary.
6. Map actual Judge/fairness data to the detail view. These findings are not fields in the inspected MatchReport domain schema, so no external shape is guessed.
7. Add live integration smoke tests with safe fixture CVs. Only then enable real submission.

## CORS and hosting

FastAPI must allow the exact frontend origin for the deployed Vercel domain and approved preview domains. Allow GET/POST/OPTIONS and `Content-Type`/`Accept`. The frontend currently uses no cookies (`credentials` is not enabled). If cookie authentication is added, coordinate CSRF protection, explicit origins and credential settings; do not combine wildcard origins with credentials. Use an HTTPS backend for the HTTPS deployed frontend. Vercel hosts only the frontend; it does not start Python or a model server.

## Demo limitations

Deterministic lexical illustration only: exact whole-line matches can produce MET; mentions within longer lines remain UNCERTAIN; no match is MISSING/not_documented. All results require review. No semantics, duration validation, retrieval, Judge, bias audit or model generation runs. Seed records are fictional. CVs and notes stay in memory until the browser is refreshed; export JSON explicitly includes their contents. There are no autonomous hiring actions.

## Upload update

The frontend now extracts PDF text with PDF.js and recognizes PNG/JPG/WebP images and scanned PDF pages with English Tesseract OCR in the browser. src/cv-files.ts owns validation, limits, timeout, cancellation and cleanup. Users can edit extracted text before matching; evidence offsets refer to that resulting text, not PDF page coordinates. REAL matching is still disabled pending the HTTP contract, provenance mapping and live tests. This replaces the earlier TXT-only upload limitation, without modifying backend parsing or anonymization.
