# Recovery report (session started 2026-10-14 23:39 UTC)

Continuation branch: `claude/vigilant-albattani-dmn3pk` (the branch this cloud session is bound to).
The previous branch `claude/kind-albattani-k7qlt9` was NOT modified, rebased or force-pushed.

## What was verified in git

| Branch | Head | Content | Status |
|---|---|---|---|
| `main` | `0568ea8` | initial commit only | untouched |
| `claude/kind-albattani-k7qlt9` | `e584a13` | `matcher/` (schemas, prompt, validate, knowledge, backends, agent, tests), `docs/MODEL_AUDIT.md` | verified, merged here (`ff95436`) |
| `claude/gracious-fermi-ncuem4` | `1f5610b` | `rag/` (ESCO ICT 1,621 concepts, 20 USAJOBS postings, BM25/dense retriever, exp02/exp03, API, n8n) | verified, merged here (`c7fb97b`) |
| `claude/hiresignal-rag-data-audit-fbge7j` | `ae727d4` | CSV exports of RAG data | not needed by matcher; not merged |

No commit newer than `e584a13` exists on the previous branch (checked with `git ls-remote`).

## What was NOT recoverable

- The previous session (`HireSignal Matcher Agent overnight implementation`, idle, waiting for input)
  had a benchmark agent and a fine-tuning agent writing into `benchmark/` and `finetune/`. Its transcript
  shows both were stopped by the system and those files were never committed. Their contents are not in
  git or any accessible artifact, so they were rebuilt from scratch in this session, not reconstructed.
- Earlier research conversations (model selection, Kus-hal adapter, gw0/jobfit) are not accessible from
  this session. `docs/MODEL_AUDIT.md` (from `e584a13`) is the only durable record and was re-verified
  against the Hugging Face Hub in this session.
- Windows-only folders `hiresignal_benchmark`, `hiresignal_finetune`, `hiresignal_cv_reader`: not in any
  branch. `benchmark/` and `finetune/` here are new, written against `benchmark/CONTRACT.md`.
  The CV reader is represented only by the `CV` schema (`cv_id`, `text`, optional `structured`).
- O*NET: no O*NET data exists in any branch. Retrieval uses ESCO only.

## Notes
- The previous session has a self check-in scheduled for 2026-10-15T03:06Z (its own branch). Left in place.
- First test run after merge: `pytest matcher rag/tests/test_rag.py` -> 29 passed (matcher tests had never run before).
