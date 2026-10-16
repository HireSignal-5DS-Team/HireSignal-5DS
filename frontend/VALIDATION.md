# Validation record

Executed 2026-10-16 on Windows, Node.js 22.16.0, npm 11.4.1.

| Check | Result |
| --- | --- |
| `npm run test` | 14 tests passed |
| `npm run lint` | Passed, zero errors |
| `npm run build` | TypeScript passed; Vite production bundle generated |
| `npm run test:e2e` | 9 tests passed: 3 each on desktop, tablet and mobile |
| `npm audit` | Zero vulnerabilities |
| `git diff --cached --check` | Passed |
| Production preview smoke | `/`, `/analysis`, `/results`, `/reports`, `/system`, `/candidates/sample-1`: HTTP 200, expected heading, zero page errors |

Browser checks used installed Microsoft Edge (Chromium), with a 1280px desktop, 820px tablet and 390px mobile viewport. Mobile tests emulate touch/device characteristics; they are not physical iOS/Safari testing. Desktop and mobile screenshots were inspected. A mobile overflow defect from an uncontained screen-reader table label was corrected; tests compare scroll width with the layout viewport client width.

Verified complete workflow: input validation, anonymization acknowledgement, TXT-only parsing, multi-candidate submission, simulated stages, exact source evidence, review status/notes, filters, navigation and JSON download contents. API failure tests cover invalid configuration, HTTP errors, network/CORS failure, timeout, empty and malformed JSON.

Not verified: live FastAPI/model execution (HTTP contracts absent), backend services, Safari/Firefox, deployed Vercel hosting. No backend/model tests were run because this change adds only `frontend/` and does not alter those components. The frontend test scripts are available for the team's CI; this change does not alter shared CI ownership.

## PDF/image upload update

- Added PDF.js text extraction and English Tesseract OCR for PNG/JPG/WebP images and scanned PDF pages.
- Added editable extracted text, progress, cancellation, sequential batch handling, file/page/text limits and a two-minute timeout.
- Validation: 14 unit tests and 15 browser tests passed across desktop/tablet/mobile; lint and production build passed; npm audit reports zero vulnerabilities.
- The production build also extracted a real PDF and recognized a PNG with zero browser runtime errors.
- OCR assets require initial network access; document content is processed in the browser. Matching remains MOCK. OCR quality and reading order require user review.
