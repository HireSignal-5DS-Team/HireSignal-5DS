Adds a complete recruiter-facing frontend under `frontend/`, based on the team integration branch. A recruiter can submit anonymized text CVs and requirements, run an explicitly simulated workflow, inspect verbatim evidence, record review notes, and export JSON reports.

The React/Vite/TypeScript/Tailwind interface includes dashboard, new analysis, processing, candidate results/detail, reports, and backend diagnostics. Frozen Matcher domain contracts are reused. No backend, model, training or evaluation logic changes. REAL matching stays disabled because the integration branch does not yet define the FastAPI transport contract; `INTEGRATION.md` records the exact handoff work.

Validation: unit tests, desktop/tablet/mobile end-to-end workflow checks, ESLint, TypeScript and production build. Includes environment example, lockfile, Vercel SPA routing and deployment instructions. Reviews are session-only and exported reports are clearly marked DEMO.

Target: `claude/beautiful-galileo-o36bdv`. Deploy Vercel with Root Directory `frontend`, build `npm run build`, output `dist`, `VITE_EXECUTION_MODE=MOCK`.
