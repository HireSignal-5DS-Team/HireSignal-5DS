# Push checklist (T14 Part D, 2026-10-19)

Target (Approver, 2026-10-19): the team repo `https://github.com/HireSignal-5DS-Team/HireSignal-5DS.git`, new branch
**`v3-final`**, only after the secret scan is 0. No force-push, no merge.

## 1. `.gitignore` (checked by `tests/security/test_privacy.py` with `git check-ignore`)

| excluded | why | how to get it back |
|---|---|---|
| `.env`, `.env.*` (except `config/.env.example`) | secrets (webhook token, cloud key) | copy `config/.env.example` to `.env` and fill it (INSTALL.md) |
| `private/` | identity stored apart (CLAUDE.md rule 4) | written by `/profile` at run time |
| `models/*` except `models/MANIFEST.md` (15 GB) | size, licences | `scripts/download_models.py` (pinned revisions; `--verify` checks sha256), LoRA conversion steps in INSTALL.md |
| `tools/` (portable Node, n8n, llama.cpp, logs; 3.9 GB) | size | INSTALL.md |
| `.n8n/` (n8n database: executions, which hold the webhook token) | local runtime data | import `n8n/*.json` (`scripts/n8n_cli.ps1`) |
| `.venv/`, `__pycache__/`, `.pytest_cache/`, `.cache/` (n8n UI assets) | caches | `pip install -r requirements.txt`; n8n rewrites `.cache/` at start |
| `data/raw/djinni/` (366 MB), `data/raw/kaggle_resume/` (119 MB) | size; the used records are already in `data/processed/` with their NOTICE | `data/DATA_CARD.md` (Hugging Face / Kaggle API) |
| `data/raw/vanetik/` | GPL-3.0, not redistributed | `data/DATA_CARD.md` §3 |
| `data/raw/esco_tabiya/` | the ICT subset is in `rag/data/esco/` (with `NOTICE.md`, CC BY 4.0) | `data/DATA_CARD.md` §4 |
| `eval/outbox/` | letters written by the workflow | re-run the workflow |
| `eval/results/*/stores/` (Qdrant / Chroma files of the retrieval benchmark) | rebuilt | `rag/evaluate.py` |
| `*.log` | run logs (may hold local paths) | the result JSON files hold the measured values |

**Kept:** code, prompts, n8n JSON, docs and figures, `data/processed/` (Djinni MIT + Kaggle CC0 records with
`NOTICE_DJINNI.md`), `data/labels/` (gold labels), **`data/raw/scans/`** (our own photos / scans of the MIT / CC0
source PDFs, 9 MB; checked: no EXIF / GPS, no author in the PDF metadata, nothing personal in view),
`rag/data/esco/` and every `eval/results/` folder.

## 2. Secret scan — `scripts/secret_scan.py` → `eval/results/2026-10-19_secret_scan/scan.json`

Scope: exactly what `git add -A` stages (`git ls-files --cached --others --exclude-standard`), **3,281 files**.
The script prints counts and paths only, never a value.

| check | result |
|---|---|
| secret values from `.env` (`WEBHOOK_TOKEN`; `CLOUD_LLM_API_KEY` is empty) | **0** |
| key patterns (OpenAI, Hugging Face, GitHub, AWS, Google, private keys, bearer tokens) | **0** (7 hits were in `.cache/` n8n UI assets, now ignored) |
| identity values stored in `private/` (213 values ≥ 5 characters) | 64 occur in committed files; **0 unexplained** |

The 64 are explained by rule:
- 37 are public dataset text: older false detections such as "Qlik Sense" or "BI Tools", and one Kaggle handle
  written in a Djinni CV (MIT data, already public).
- 13 are synthetic test identities (the Sara Ben Ali fixture, counterfactual names and nationalities).
- 5 are the app's own messages.
- 9 are reviewed by hand and stored as sha256 hashes only (`config/secret_scan_reviewed.json`): CV lines read from
  our photos of public CVs, OCR noise, and Reader warnings with numbers filled in.
- No real person's identity: the source datasets carry no names (T13 A4).

Verdict: **PASS**.

## 3. Size

- **3,281 files, 30.9 MB in total.**
- The largest file is `rag/data/esco/esco_ict_graph.jsonl` (1.9 MB). No file is over 50 MB (0 over 50 MB, 0 over
  5 MB).
- Excluded locally: models 15 GB, tools 3.9 GB, `.venv` 5.0 GB, raw datasets about 0.5 GB.

## 4. Commit and push

- `n8n/hiresignal_v1.json` (37 nodes) and `n8n/hiresignal_errors.json` (4 nodes): no credentials, no pinned data;
  the token is read from `$env.WEBHOOK_TOKEN`.
- Tests before the commit: `pytest -q` → 502 passed, 1 skipped.
- One commit of the whole project on the local branch `v3-final`, then `git push -u origin v3-final`.
- The result is in `tasks/T14_report.md`.
