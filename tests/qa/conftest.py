import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE.parents[1], HERE):  # repo root (for `matcher`), this folder (for `_qa_support`)
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
