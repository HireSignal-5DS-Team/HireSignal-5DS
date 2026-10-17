"""Try the Reader on one or more CV files from the command line.

    python scripts/read_cv.py samples/cv1.pdf
    python scripts/read_cv.py samples            (every CV in the folder)
    python scripts/read_cv.py samples --json out
"""

import argparse
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.reader import ReaderError, read_cv  # noqa: E402

CV_EXTENSIONS = {".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".txt"}


def expand(inputs: list[str]) -> list[Path]:
    """Accept files, folders and patterns like *.pdf (PowerShell does not expand them)."""
    files: list[Path] = []
    for item in inputs:
        path = Path(item)
        if path.is_dir():
            files += sorted(p for p in path.iterdir()
                            if p.is_file() and p.suffix.lower() in CV_EXTENSIONS)
        elif any(c in item for c in "*?["):
            files += sorted(Path(p) for p in glob.glob(item) if Path(p).is_file())
        else:
            files.append(path)
    return files


def main() -> None:
    # Windows consoles can't print every character found in CVs; don't crash on them.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(description="Run the HireSignal Reader on CV files.")
    parser.add_argument("files", nargs="+", help="CV files or folders (PDF, DOCX, JPG, PNG)")
    parser.add_argument("--json", metavar="DIR", help="also save each result as JSON in DIR")
    args = parser.parse_args()

    files = expand(args.files)
    if not files:
        print("No CV files found.")
        return

    for file in files:
        print("=" * 70)
        print(file)
        try:
            result = read_cv(file)
        except (ReaderError, OSError) as exc:
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
