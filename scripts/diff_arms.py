r"""Item-by-item diff of two Matcher runs (same items): decision changes, raw-output changes, gold agreement.

Usage: .venv\Scripts\python scripts\diff_arms.py <run_a.jsonl> <run_b.jsonl>
"""
import json
import sys


def load(path):
    return {(r["case_id"], r["req_id"]): r for r in map(json.loads, open(path, encoding="utf-8"))}


a, b = load(sys.argv[1]), load(sys.argv[2])
assert a.keys() == b.keys(), "runs cover different items"
same_raw = sum(a[k]["raw"] == b[k]["raw"] for k in a)
changed = [k for k in sorted(a) if a[k]["pred"] != b[k]["pred"]]
print(f"items {len(a)}; identical raw output {same_raw}/{len(a)}; decision changed {len(changed)}/{len(a)}")
for k in changed:
    g = a[k]["gold"]
    print(f"  {k[0]} {k[1]}: gold {g}  A {a[k]['pred']}{' (invalid)' if a[k]['parsed'] is None else ''}"
          f" -> B {b[k]['pred']}{' (invalid)' if b[k]['parsed'] is None else ''}"
          f"  [{'fixed' if b[k]['pred'] == g else 'broken' if a[k]['pred'] == g else 'still wrong'}]")
