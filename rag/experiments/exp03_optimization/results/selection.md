# exp03 — selection (pre-registered rule, PLAN.md)

## realtime (p95 ≤ 300 ms, extra RAM ≤ 1500 MB)

- Within budget: `structure@300 | e5-small`, `pc@1s | e5-small`, `pc@3s2 | e5-small`, `structure@300 | e5-base`, `pc@1s | e5-base`
- Highest dev Matcher MRR within budget: `pc@3s2 | e5-small` (MRR 0.902, p95 132.1 ms)
- Significant vs baseline on dev: False (MRR diff 0.037, CI [-0.013, 0.1], McNemar p 0.375)
- **Selected: `structure@300 | e5-small`**

## async (p95 ≤ 2000 ms, extra RAM ≤ 1500 MB)

- Within budget: `structure@300 | e5-small`, `pc@1s | e5-small`, `pc@3s2 | e5-small`, `structure@300 | e5-base`, `pc@1s | e5-base`, `structure@300 | e5-small > mmarco@5`, `structure@300 | e5-small > mmarco@10`, `structure@300 | e5-small > mmarco@20`, `pc@1s | e5-small > mmarco@10`, `pc@1s | e5-base > mmarco@10`, `structure@300 | e5-base > mmarco@10`
- Highest dev Matcher MRR within budget: `pc@1s | e5-base > mmarco@10` (MRR 0.912, p95 1058.3 ms)
- Significant vs baseline on dev: False (MRR diff 0.048, CI [-0.029, 0.135], McNemar p 0.453)
- **Selected: `structure@300 | e5-small`**

