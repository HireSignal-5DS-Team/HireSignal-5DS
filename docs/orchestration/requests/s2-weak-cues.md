# Request from S2: extra weak-evidence cues for `matcher/validate.py::_WEAK` (validator v2, QA-025)

Status: open. S2 removed its duplicate aggregator rule (`matcher:met_weak_evidence`) after merging v2 (4f38c97).
One cue list now lives in `matcher/validate.py`.

Train-split check (`benchmark/data/train.jsonl`, never used to design the cues). For each cue, the number of gold
**MET** quotes it matches (false alarms) and the number of gold **non-MET** quotes it matches (MET quotes 305,
non-MET quotes 166; word-bounded, case-insensitive):

| cue | train MET-quote hits (false alarms) | train non-MET quote hits | recommend |
|---|---|---|---|
| `preparing` | 0 | 12 | **add** |
| `studying` | 0 | 10 | **add** |
| `plans? to` | 0 | 4 | **add** |
| `enrolled`, `preparation` | 0 | 0 | add (val-000 r4: "Enrolled in a … preparation course" is gold MISSING/contradicted) |
| `course(s|work)`, `learning`, `learned about`, `introduction to`, `basics of`, `basic knowledge`, `planning to`, `hobby`, `spare time`, `free time`, `aspiring`, `would like`, `interest in`, `familiarity with`, `attended` (bare) | 0 | 0 | no evidence either way; optional |
| `side projects?` | 0 | 0 | **do not add**: it describes use, not exposure (val-009 r3 "Applied Node.js in various side projects" is gold UNCERTAIN for duration, not for exposure) |

The held-out effect is unmeasured (test split, orchestrator's final run). The synthetic bench vocabulary limits what
the train check can show.
