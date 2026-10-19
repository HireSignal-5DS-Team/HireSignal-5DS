# Profile Agent parse gold (T15)

`parse_gold/` and `PARSE_RULES.md` are copied read-only from team V2: `eval/profile_agent/` (feature/agent-integration
@ a5a03ff). They hold hand-made skills / education / experience for the 10 synthetic CVs in
`tests/fixtures/profile/cvs/` (written by the team, no real person).

`scripts/eval_profile_prompts.py` uses them for skills precision / recall. Split: p01–p05 dev, p06–p10 test.
