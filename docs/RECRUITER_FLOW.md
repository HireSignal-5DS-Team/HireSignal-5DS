# Recruiter flow (T19)

Page: **http://127.0.0.1:8010/ui/recruiter.html**. It is served by the station API, works offline, and links to and
from the single-CV demo page `/ui/`.

It is a view and workflow layer on the unchanged pipeline. It does not change the n8n workflow, the prompts, the
models, the gate settings, the Matcher / Judge / Report logic or the station contracts. Every candidate goes through
the same webhook run as in the demo, with the same confirmed requirement card.

## The steps

1. **Job.**
   - Paste the job text, or load a .txt file.
   - Press **Extract requirements**: the Job Agent (`/job`, prompt v2) proposes a card.
   - Or load an existing card (.json).
   - PDF / DOCX job files are not accepted: the Reader keeps document text private and does not return it.
2. **Requirements: the recruiter's card.**
   - An editable table: text, must / nice, category, minimum years, skill terms; delete and add rows.
   - **Merge selected** joins rows into one requirement: texts joined with " or ", skill terms combined. This fixes
     the Job Agent's known "Pyro / PyMC3 / JAGS or similar" split without touching the agent.
   - **Confirm** validates each row with the station's `RequirementIn` contract and gives the webhook's
     `requirements` format, with `confirmed_by: "recruiter (UI)"`.
   - The card can be downloaded.
3. **Candidates (1 to 3).** PDF, DOCX, JPG, PNG or TXT, labelled **Candidate A / B / C** in upload order. File
   names are never shown, stored or sent (they can contain names).
   - **Run** sends them one after another through the webhook with the same card.
   - Each row shows its live agent progress (the T16 progress) and there is an overall bar.
   - Photos and scans take about 3 minutes each.
   - One batch at a time: a second batch, or a single run on `/ui/`, gets 409.
   - Results and `batch_summary.json` are saved under `private/batches/<batch_id>/` (git-ignored; they hold CV quotes).
4. **Compare & decide.**
   - One column per candidate, ordered **invite → review → reject, then upload order**. Each column shows:
     - the gate outcome;
     - "decided by: gate" or "needs the recruiter";
     - counts only: must-haves met X of N, unclear, nice-to-haves met;
     - the badge "All must-haves met" when true.
   - The **evidence matrix**: requirements (must-haves first, card order) × candidates, with ✓ / ✗ / ?. A click on a
     cell shows the CV quotes, the Matcher confidence, the Judge verdict and the reasons in plain words.
   - **Needs your eyes**: every unclear cell and every flag, in one list.
   - **Details** opens the full result, with a collapsible "How it was decided" timeline. This is the only place the
     gate score appears, labelled "gate score".
5. **Decision and letter (human-approved).** For each candidate the recruiter chooses **Invite / Reject / Hold**.
   - **Same decision as the gate**: the Report Writer's checked letter.
   - **Review case**: decide in the n8n recruiter form (the existing path). Its checked letter, from
     `eval/outbox/<decision>/<execution>_<cv_id>.json`, then appears here.
   - **Override of a gate decision**: the existing human-decision path, `/report` with `decided_by: "human"` (T13),
     with the same body that n8n's "Report Writer (human decision)" node builds. The `/report` contract is unchanged.
   - **Hold**: no letter, one audit line.
   - The letter is shown in an **editable preview**. **Approve** saves it to
     `eval/outbox/<decision>/recruiter_<batch>_<label>.json` (git-ignored) and writes an audit line. Nothing is sent.
   - **Reveal identity** (only after Approve, one click per candidate) shows the name and e-mail from the identity
     store `private/<cv_id>.json`, on the page only.
   - **Open in my mail app** creates a `mailto:` link (recipient, subject, letter); the human sends it.
   - Identity values are never logged, never sent to n8n and never written outside `private/`.
   - **Audit log** `eval/outbox/decision_log.jsonl` records the time, batch_id, candidate label, cv_id, system outcome,
     recruiter decision, letter file and "identity revealed yes/no". It holds no CV text and no identity values.

## Why there is no ranking and no automatic e-mail

- **Our evaluation measured per-requirement decisions and per-candidate outcomes, not ranking quality.** A "best
  match" order would be a claim we never tested.
- **The gate score depends on how the job was split into requirements.** Merging or splitting rows changes it, so
  comparing scores across candidates or jobs is not meaningful.
- **Ranking candidates is high-risk under the EU AI Act** (AI used for recruitment, Annex III). The system supports a
  human decision; it does not make it. Columns are therefore ordered only by the gate's outcome and upload order.
- **A human decides and a human sends.** Letters are previews that the recruiter approves. There is no SMTP, no mail
  API and no stored mail credentials: the "mail app" button only opens the recruiter's own e-mail program.

## Endpoints (additive, `services/recruiter.py`)

| endpoint | what it does |
|---|---|
| `POST /ui/card/validate` | validates the card, returns the webhook format |
| `POST /ui/card/merge` | merges the selected rows |
| `POST /ui/batch` | starts a batch; `GET /ui/batch/status` gives its status; `GET /ui/batch/{id}/result/{label}` gives one result |
| `POST /ui/letter` | gives the letter preview |
| `POST /ui/approve` | saves the approved letter and writes the audit line |
| `POST /ui/identity` | reveals the identity, only after Approve |

Screenshots (demo / dataset data only): `docs/ui/recruiter/`.
