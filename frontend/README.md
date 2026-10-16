# HireSignal frontend

React + Vite + TypeScript + Tailwind CSS, with Lucide icons. A complete, explicitly simulated recruitment review workflow, deployable independently of FastAPI.

## Run locally

Use Node.js 22.16+ (22.x recommended) and npm. From the repository root:

```sh
cd frontend
npm ci
npm run dev
```

Open the printed URL (normally http://127.0.0.1:5173). MOCK is the default; no API keys or backend are required. To configure service checks, copy `.env.example` to `.env.local` and set the public backend URL.

## Demonstration walkthrough

1. The dashboard starts with one clearly labeled demonstration campaign and three fictional profiles.
2. Select **New analysis**, then **Use sample**, or enter a role and one requirement per line.
3. Paste anonymized CV text, or upload up to 10 UTF-8 `.txt` files. Each file is limited to 200 KB and 50,000 decoded characters. PDF, DOCX, images and OCR are deliberately unsupported until a verified parser is integrated.
4. Confirm personal information has been removed; select **Run demo analysis**. A non-empty paste is included automatically; use **Add this candidate** to queue additional profiles.
5. Watch the explicitly simulated workflow, then open candidate evidence. Review MET / MISSING / UNCERTAIN decisions and the exact source text.
6. Save a review status and notes. Navigate to **Reports** and export JSON to retain the report and annotations.

All state is in browser memory. A refresh clears user-created campaigns and reviews and reloads the sample campaign. There is no authentication, database, server audit trail or local-storage persistence. The UI says so. Export includes CV text; handle exported files appropriately.

## Environment

| Variable              | Default | Meaning                                                                                                                               |
| --------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `VITE_EXECUTION_MODE` | `MOCK`  | Only the exact value `REAL` selects the real configuration. REAL matching is intentionally disabled pending a verified HTTP contract. |
| `VITE_API_BASE_URL`   | empty   | Absolute HTTP(S) backend origin, optionally with a path prefix. No production localhost default.                                      |

Vite variables are public and embedded at build time. Never put private tokens into them. Rebuild/redeploy after changes. `.env*` files are ignored except `.env.example`.

## Quality checks

```sh
npm run test
npm run lint
npm run build
npm run test:e2e
npm audit
```

Windows browser tests use installed Microsoft Edge. Linux/macOS tests use Playwright Chromium; first run `npx playwright install chromium` (CI uses `--with-deps`). Tests exercise desktop, tablet and mobile layouts. Browser screenshots and traces are written under ignored `test-results/`.

Unit tests cover input limits, UTF-8 parsing, honest deterministic results, Unicode quote offsets, all four API paths, errors, empty/invalid responses and timeouts. End-to-end tests cover routing, input, file validation, multiple candidates, progress, evidence, reviewer notes, JSON download content, filters, error messages and viewport overflow. `npm run build` checks TypeScript and generates `dist/`.

## Vercel deployment (no Docker)

1. In Vercel, add a project and import `HireSignal-5DS-Team/HireSignal-5DS` using an account with repository access.
2. Select the frontend feature branch for the first preview deployment. `main` does not yet contain the frontend. For a production demo, set the project's production branch to the approved branch containing this change, or deploy after team integration.
3. Set **Root Directory** to `frontend` and **Framework Preset** to `Vite`.
4. Set **Install Command** to `npm ci`, **Build Command** to `npm run build`, and **Output Directory** to `dist`. Select Node.js 22.x.
5. Set `VITE_EXECUTION_MODE=MOCK` for Preview and Production. Leave `VITE_API_BASE_URL` empty for the standalone demonstration.
6. Deploy. The included `vercel.json` rewrites application routes to `index.html`; built assets remain served as files.
7. Open `/`, `/analysis`, and `/reports` directly, then run the demonstration walkthrough above. Refreshing a user-created candidate URL correctly shows the session-empty state.

The repository includes deployment configuration; no Vercel project or live deployment has been created by this change. Official reference: [Vite on Vercel](https://vercel.com/docs/frameworks/frontend/vite).

## Backend integration

Read [INTEGRATION.md](INTEGRATION.md). Matcher domain types mirror the inspected frozen Pydantic schemas. They are not a fabricated FastAPI request contract. All backend, agent, training and evaluation files are untouched.

## Source map

- `src/contracts.ts`: Matcher domain contracts and separate frontend view types.
- `src/api.ts`: API transport, replaceable analysis adapter, deterministic MOCK implementation, input validation.
- `src/App.tsx`: routed dashboard, analysis, workflow, results, detail, reports and diagnostics.
- `src/styles.css`: responsive visual system and Tailwind import.
- `src/api.test.ts`, `tests/workflow.spec.ts`: unit and browser checks.

## Git integration

Feature branch: `feature/hiresignal-frontend`.
Base: `claude/beautiful-galileo-o36bdv` at `fb68665b8b3586e379688c9e94e7efa0fccbd9ba`, as identified in `docs/orchestration/ORCHESTRATION.md`.
Changes are confined to `frontend/`. Merge through the team integration PR; do not push directly to `main`.
