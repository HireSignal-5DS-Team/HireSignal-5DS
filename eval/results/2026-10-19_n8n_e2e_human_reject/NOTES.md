# T13 Part 0: e2e review -> human reject -> generated, checked letter (real-GPU)

- Execution 57 (pair P32, from the final evaluation run): the gate answered review (score 78); the recruiter form was
  submitted with Decision = reject (`field-0=reject`, `field-1` = a test note, which is not sent to any model).
- Path: Wait for recruiter (form) -> Decided by human -> **Report Writer (human decision)** (`POST /report`,
  `decided_by: human`) -> Human letter -> Outbox letter -> `eval/outbox/reject/57_*.json` (copy: `outbox_letter_exec57.json`).
- The model's letter failed the fact checker twice: it named met must-haves (r2, r3) and a nice-to-have (r5) as reasons
  (the new T13 rule). The checked template letter was used (`report:template_fallback`): "After a review by our
  team, we will not move forward with it. If you have questions about this decision, simply reply to this message."
  No "automated" wording, no GDPR sentence (a person decided).
