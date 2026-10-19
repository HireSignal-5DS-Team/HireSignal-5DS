Station HTTP endpoints, one module per station: reader, profile, job, matcher (T04); rag, bias, judge, reporter, outcome later.

- `api.py`: FastAPI app on port 8010 (`/health`, `/ready`, `/reader`, `/profile`, `/job`, `/match`); start with `scripts/start_stack.ps1`.
- `contracts.py`: request/response models. `config.py`: settings from `.env`. `prompts.py`: loader for `prompts/<station>/v<N>.md`.
- `reader/`, `profile/`, `job/`: adapted from team V2 (header on each file). `profile/gender.py`: gendered-word fix (Decision 17).
- `matcher/`: prompt helpers, `schema.json` (constrained decoding), `validate.py` (validator v1, evidence rules only), `matcher.py`.
