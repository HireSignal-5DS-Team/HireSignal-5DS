# Upstream handoff for Ayoub (CV Reader, Profile Agent, Job Agent)

From S6. You own `agents/` and `contracts/`, and nobody else edits them. This document defines only what the
downstream pipeline consumes.

## What the downstream needs

| from | to | adapter (already written, tested against your current branches) |
|---|---|---|
| CV Reader `read_cv(...).to_dict()` (`feature/reader-agent` @ `2386e14`) | `matcher.schemas.CV` | `integration.contract.cv_from_reader(reader_dict, cv_id)` |
| Job Agent `JobRequirements` card, schema 0.1.x (`feature/job-agent` @ `985d14d`) | `matcher.schemas.Job` | `integration.contract.job_from_card(card_dict)` (same mapping as your `to_matcher_job()`) |
| Profile Agent | `CV.structured["profile"]` (optional) | not delivered yet: anything you add is kept but **never used as evidence** |

Rules that the downstream depends on:
1. `ReaderResult.text` is the only evidence source: the Matcher's quotes must be exact substrings of it. Keep it as
   clean text; do not rewrite or summarise it after extraction.
2. Requirement ids `r1, r2, ...` must be unique and stable. They are carried to the final report.
3. A Job card with `schema_version` other than `0.1.x` is refused by the adapter. If you bump it, tell S6 first.
4. Anonymise before the Matcher if a hosted model is used (see `config/matcher.env.example`, privacy note).

Samples (synthetic): `integration/examples/reader_result.json`, `job_card.json`; contract tests:
`integration/tests/test_contract.py`.

## Integration steps

1. Keep working on your own branches. When ready, merge the integration branch `claude/beautiful-galileo-o36bdv` into
   yours, check that `pytest integration tests` passes, push, and tell S6 the commit.
2. S6 fetches your branch, reviews it, and merges it into the integration branch without rewriting your code. Expected
   overlap: top-level `README.md`, `.gitignore`, `requirements.txt` (merged by hand, nothing of yours removed).
3. **Port:** your Job Agent defaults to `http://127.0.0.1:8080/v1` (NuExtract). The Matcher's fallback server also uses
   `:8080`. Dali will assign ports in Compose. Keep `HS_NUEXTRACT_BASE_URL` configurable, as it is today.
