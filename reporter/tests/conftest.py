import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE.parents[1], HERE):  # repo root (for `reporter`, `matcher`), this folder (for `_fixtures`)
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
