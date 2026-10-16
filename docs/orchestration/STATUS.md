# HireSignal session status

Maintained by Session 6. Plan and rules: `docs/orchestration/ORCHESTRATION.md`.

**Compute window: 0** (evaluation running in `session_015pC4cWnLapLopyiUgf8VmG`, 138/202 at `302a424`).
No LLM server or training in any session until the orchestrator opens window 1.

| session | branch | Claude session | deliverable | blockers | tests |
|---|---|---|---|---|---|
| 1 RAG | `session/s1-rag-optimization` | `session_013GKCTUT4EiMBH2Q8tVdquw` | RAG failure analysis; improved query, filter, chunking, citations; retrieval + end-to-end comparisons | live Matcher runs wait for window 1 | not run |
| 2 Matcher LoRA | `session/s2-matcher-lora-integration` | `session_01ReP1Qmd3Hq69cVnvLM4RZJ` | LoRA-primary Matcher wired to contracts, provenance, review routing, live E2E harness | live smoke waits for window 1 | not run |
| 3 Soft prompt | `session/s3-matcher-soft-prompt` | `session_01Uxb7wkSL8FdicKUG7jGBk8` | trainable soft-prompt code + feasibility study; 4-arm comparison if feasible | 4B training does not fit a CPU container; GPU handoff needed | not run |
| 4 Bias Auditor | `session/s4-bias-auditor` | `session_01QjD3VUqjjj6hLiUU5LegT1` | fairness test set, prompt-only vs adapter research, measured recommendation | live audit waits for window 1 | not run |
| 5 QA | `session/s5-qa-contracts` | `session_015KY6nW8NkJuGZ2rB35uZGz` | contract, regression, adversarial and live-ready test suites; failure log | none for mock work | not run |
| 6 Orchestrator | `claude/beautiful-galileo-o36bdv` | `session_01CyLv8Vej3sAYAmPbyrDsJy` | plan, contracts, reviews, merges, final real E2E | final E2E waits for window 2 | baseline mock: 50 passed, 1 skipped |

## Log

- 2026-10-16: audit done, branches and worktrees created, contracts frozen (v1).
- 2026-10-16 10:05Z: sessions S1–S5 launched as independent cloud sessions (tag `hiresignal-orchestra`), each on its own branch and container.
