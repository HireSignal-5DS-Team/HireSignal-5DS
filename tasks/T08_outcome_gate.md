# T08 — Outcome gate (invite / review / reject) + n8n approval step

Read `CLAUDE.md` first. Answers to your T07 questions: 1) yes, see the gate rules below (flags only count where they can change the outcome). 2) yes: J2 r6 is now **nice-to-have** (Approver decision, applied in gold); re-report T07's confidence threshold with this change, and keep 0.72 unless dev clearly says otherwise. 3) Judge precision ~0.4 is acceptable for a safety check if the gate only uses outcome-relevant flags; no Judge fine-tuning now.

**Gold update (by the Brain):** `data/labels/gold/` now has **52 pairs** (40 + 12 targeted pairs with real invite cases, `data/labels/pairs_extra.csv`, CVs already in `data/processed/cvs/`). Rebuild with `python data/labels/gold/build_gold.py` and read `summary.json`. The 12 new pairs are being checked by a teammate right now (`row_sources.unchecked` > 0 until done). Splits are fixed in `build_gold.py`.

## Part A — Run the pipeline on the 12 new pairs (now)
Same harness as T06/T07 (`scripts/eval_real.py`, then Judge + confidence): `/reader` → `/profile` → `/match` per gold requirement (with confidence) → `/judge`. Append to a new results folder `eval/results/<date>_extra_pairs/` and produce one combined rows file for all 52 pairs (variant 4 = confidence + Judge). Report Matcher metrics for the 12 alone and for all 52 (dev/test).

## Part B — Gate design (offline on the 52 rows)
**Order:** write the gate code and its tests first, with provisional thresholds, and do Part C with them. **Tune and report the numbers only when `summary.json` shows `unchecked: 0`** (re-run `build_gold.py` to check). If it is still not 0 when everything else is done, stop and report; the Approver will tell you when the labels are final.
Write the gate as plain code in `services/outcome/gate.py` + `POST /outcome` (input: the pair's requirement results; output: outcome, score, reasons, which rule fired). Candidate rules (compare them; pick on **dev**, report on **test**):
1. **Score** = Decision 5 formula (must 2, nice 1; MET 1, UNCERTAIN 0.5, MISSING 0).
2. **Reject** if a must-have is MISSING with no outcome-relevant flag on it.
3. **Outcome-relevant flags** (send to review): on must-haves only — MET with `judge:disagrees` or validator evidence flags (possible false invite); MISSING where the Judge finds the CV entails the requirement (possible false reject); UNCERTAIN (incl. `match:low_confidence`). Flags on nice-to-haves and `info_flags` never block; they are listed in the result.
4. **Invite** if every must-have is MET without an outcome-relevant flag and score ≥ threshold `T_invite`; else review.
5. Pair-level profile flags (`partial_extraction_requires_review`, etc.): test both "block" and "info only", report the difference.
Targets: **0 false invites** (hard), review rate ≤ 25% of pairs, as few false rejects as possible. Report a confusion matrix (gold invite/review/reject × gate), review rate, false invites, false rejects, on dev and test, and a simple table of what each rule changes. If the targets cannot be met together, say which trade-off you chose and why.

## Part C — n8n
Replace `TEMP outcome` with: HTTP `/outcome` → Switch on outcome →
- **invite:** write the result JSON to `eval/outbox/invite/` (stands in for the email);
- **reject:** same to `eval/outbox/reject/`, including the reasons and the sentence "You can request a human review of this decision";
- **review:** an n8n **Wait node with a form** (approve-invite / reject / note) for the recruiter; after submission, write the final decision with `decided_by: human` to `eval/outbox/<decision>/`.
Re-export and clean the workflow. Run 3 real webhook runs: one expected invite (P44 or P50), one reject, one review (submit the form once, show the resumed execution).

## Report
`tasks/T08_report.md` with `SUMMARY.md` for non-experts (what the gate does, with one example per outcome). Log the gate rules in `prompts/PROMPT_LIBRARY.md` as a guardrail entry. Stop llama-server and the API at the end.
