"""Try the Reader on one or more CV files from the command line.

    python scripts/read_cv.py samples/cv1.pdf
    python scripts/read_cv.py samples/*.pdf --json out/
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.reader import ReaderError, read_cv  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the HireSignal Reader on CV files.")
    parser.add_argument("files", nargs="+", help="CV files (PDF, DOCX, JPG, PNG)")
    parser.add_argument("--json", metavar="DIR", help="also save each result as JSON in DIR")
    args = parser.parse_args()

    for file in args.files:
        print("=" * 70)
        print(file)
        try:
            result = read_cv(file)
        except ReaderError as exc:
            print(f"  ERROR: {exc}")
            continue

        print(f"  type={result.file_type}  pages={result.pages}  routes={result.page_routes}")
        print(f"  layout={result.layout}  ocr_confidence={result.ocr_confidence}")
        print(f"  needs_human_review={result.needs_human_review}")
        for w in result.warnings:
            print(f"  ! {w}")
        print(f"  sections: {list(result.sections)}")
        for name, body in result.sections.items():
            preview = body.replace("\n", " / ")[:110]
            print(f"    [{name}] {preview}")

        if args.json:
            out = Path(args.json)
            out.mkdir(parents=True, exist_ok=True)
            target = out / (Path(file).stem + ".json")
            target.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
                              encoding="utf-8")
            print(f"  saved {target}")


if __name__ == "__main__":
    main()
