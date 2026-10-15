"""Check the gold cards after editing them.

    python scripts/check_gold.py

For every card in eval/job_agent/gold/: valid against the contract, every evidence is an
exact quote of the offer, every skill term appears in its evidence, ids are r1, r2, ...
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from contracts.job_requirements import JobRequirements  # noqa: E402

OFFERS = ROOT / "eval/job_agent/offers"
GOLD = ROOT / "eval/job_agent/gold"


def check(path: Path) -> list[str]:
    problems = []
    try:
        card = JobRequirements.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception as exc:  # noqa: BLE001 - report any parsing or schema error
        return [f"invalid card: {exc}"]
    offer = OFFERS / f"{card.job_id}.txt"
    if not offer.exists():
        return [f"no offer file {offer.name}"]
    post = offer.read_text(encoding="utf-8")
    for i, r in enumerate(card.requirements, start=1):
        if r.req_id != f"r{i}":
            problems.append(f"{r.req_id}: ids must be r1, r2, ... in order (expected r{i})")
        if r.evidence not in post:
            problems.append(f"{r.req_id}: evidence is not an exact quote: \"{r.evidence[:70]}\"")
        for term in r.skill_terms:
            if term.lower() not in r.evidence.lower():
                problems.append(f"{r.req_id}: skill term '{term}' is not in its evidence")
    return problems


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    total, bad = 0, 0
    for path in sorted(GOLD.glob("*.json")):
        problems = check(path)
        n = len(json.loads(path.read_text(encoding="utf-8")).get("requirements", []))
        total += n
        print(f"{'OK ' if not problems else 'BAD'} {path.name}: {n} requirements")
        for p in problems:
            print(f"    - {p}")
        bad += bool(problems)
    print(f"\n{total} requirements, {bad} card(s) with problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
