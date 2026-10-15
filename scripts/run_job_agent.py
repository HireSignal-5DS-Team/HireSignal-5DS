"""Run the Job Agent on a job offer file and save the requirements card.

    python scripts/run_job_agent.py examples/job_post.example.txt
    python scripts/run_job_agent.py offer.txt --job-id JD-007 --out out/JD-007.json
    python scripts/run_job_agent.py offer.txt --mode inline      (if the server ignores chat_template_kwargs)
    python scripts/run_job_agent.py offer.txt --prompt job-v1    (an older prompt, for before/after)

NuExtract must be running first (see agents/job/README.md).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.job import BackendError, JobAgentError, NuExtractClient, PROMPT_VERSION, VERSIONS, run_job_agent  # noqa: E402


def read_offer(path: Path) -> str:
    if path.suffix.lower() in (".txt", ".md", ""):
        return path.read_text(encoding="utf-8", errors="replace")
    try:  # PDF / DOCX / images through the Reader, once its branch is merged
        from agents.reader import read_cv
    except ImportError:
        sys.exit(f"{path.suffix} files need the Reader (feature/reader-agent). Use a .txt file for now.")
    return read_cv(path).text


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(description="HireSignal Job Agent")
    parser.add_argument("file", type=Path, help="job offer (.txt or .md)")
    parser.add_argument("--job-id", help="default: the file name")
    parser.add_argument("--out", type=Path, help="where to save the card (default: out/<job-id>.json)")
    parser.add_argument("--base-url", help="NuExtract server, default http://127.0.0.1:8080/v1")
    parser.add_argument("--mode", choices=["kwargs", "inline"], help="how the template is sent")
    parser.add_argument("--prompt", choices=sorted(VERSIONS), default=PROMPT_VERSION,
                        help=f"prompt version (default {PROMPT_VERSION})")
    args = parser.parse_args()

    job_id = args.job_id or args.file.stem
    backend = NuExtractClient(base_url=args.base_url, mode=args.mode)
    print(f"Job Agent ({args.prompt}) -> {backend.info()}")

    try:
        card = run_job_agent(read_offer(args.file), job_id, backend, prompt_version=args.prompt)
    except BackendError as exc:
        sys.exit(f"MODEL ERROR: {exc}")
    except JobAgentError as exc:
        sys.exit(f"FAILED: {exc}")

    print(f"\n{card.title}  [{card.language}]  {len(card.requirements)} requirements"
          f"  ({backend.last_call.get('latency_s')} s)")
    for r in card.requirements:
        years = f", {r.min_years:g}y" if r.min_years is not None else ""
        print(f"  {r.req_id:>3} {r.kind:<4} {r.category:<13} {r.text}{years}")
        print(f"      quote: \"{r.evidence}\"")
    if card.warnings:
        print("\nWarnings:")
        for w in card.warnings:
            print(f"  ! {w}")
    if card.needs_human_review:
        print("\n>> needs_human_review = True")

    out = args.out or Path("out") / f"{job_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(card.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8")
    raw = out.with_name(out.stem + f".{args.prompt}.raw.txt")
    raw.write_text(backend.last_raw, encoding="utf-8")
    print(f"\nSaved {out}  (model's raw answer: {raw})")


if __name__ == "__main__":
    main()
