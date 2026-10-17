"""Run the Profile Agent on a CV and save the two files.

Steps 1-3 (privacy) always run; step 4 (skills / education / experience) uses the team's plain Qwen
(HS_LLM_BASE_URL / HS_LLM_MODEL, like job-q1). Add --no-parse to skip it.

    python scripts/run_profile_agent.py eval/profile_agent/cvs/p01_en_classic.txt
    python scripts/run_profile_agent.py out/cv01.reader.json            (a saved ReaderResult)
    python scripts/run_profile_agent.py samples/cv02.pdf                (through the Reader, once merged)
    python scripts/run_profile_agent.py cv.txt --ner gliner resume-ner  (add the NER models, CPU)
    python scripts/run_profile_agent.py cv.txt --no-parse               (privacy only, no Qwen)

Writes:
    out/<cv_id>.cv.json            -> for n8n / the Matcher: anonymised text + privacy report
    private/<cv_id>.identity.json  -> stays on this machine (private/ is git-ignored)
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.job.backend import BackendError, QwenChatClient  # noqa: E402
from agents.profile import PROMPT_VERSION, make_detectors, run_profile_agent  # noqa: E402


def load(path: Path) -> tuple[str, dict | None]:
    """-> (text, reader dict or None)."""
    if path.suffix.lower() == ".json":
        reader = json.loads(path.read_text(encoding="utf-8"))
        return reader["text"], reader
    if path.suffix.lower() in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="replace"), None
    try:
        from agents.reader import read_cv
    except ImportError:
        sys.exit(f"{path.suffix} files need the Reader (feature/reader-agent). Use .txt or a Reader .json for now.")
    reader = read_cv(path).to_dict()
    return reader["text"], reader


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="HireSignal Profile Agent (privacy)")
    parser.add_argument("file", type=Path, help=".txt, a Reader .json, or a CV file (pdf/docx/image)")
    parser.add_argument("--cv-id", help="default: random (never the file name, it often holds the name)")
    parser.add_argument("--ner", nargs="*", default=[], help="resume-ner and/or gliner")
    parser.add_argument("--no-parse", action="store_true", help="skip step 4 (no Qwen needed)")
    parser.add_argument("--llm-url", help="Qwen server (default HS_LLM_BASE_URL)")
    parser.add_argument("--out", type=Path, default=Path("out"))
    parser.add_argument("--private", type=Path, default=Path("private"))
    args = parser.parse_args()

    text, reader = load(args.file)
    try:
        detectors = make_detectors(args.ner)
    except ValueError as exc:
        sys.exit(f"CONFIG ERROR: {exc}")
    backend = None
    if not args.no_parse:
        try:
            backend = QwenChatClient(base_url=args.llm_url, max_tokens=3072)
        except ValueError as exc:
            sys.exit(f"CONFIG ERROR: {exc}")
        print(f"Step 4 ({PROMPT_VERSION}) -> {backend.info()}")
    try:
        result = run_profile_agent(text, cv_id=args.cv_id, backend=backend,
                                   sections=(reader or {}).get("sections"), detectors=detectors)
    except BackendError as exc:
        sys.exit(f"MODEL ERROR: {exc}  (use --no-parse to run the privacy steps only)")

    print(result.text)
    print("\n" + "-" * 60)
    r = result.report
    print(f"cv_id {result.cv_id}   detectors {r.detectors}   hidden {r.placeholders}")
    print(f"name found: {r.name_found}   leaks fixed: {r.leaks_fixed}   leaks left: {r.leaks_left}")
    for w in r.warnings:
        print(f"  ! {w}")
    if r.needs_human_review:
        print(">> needs_human_review = True")

    if result.profile is not None:
        p = result.profile
        print(f"\nSkills ({len(p.skills)}): " + ", ".join(sk.name for sk in p.skills))
        for x in p.experience:
            print(f"  job  {x.title} @ {x.company}  {x.start} -> {x.end}")
        for e in p.education:
            print(f"  edu  {e.degree} | {e.field} | {e.institution}  {e.end}")
        for n in p.uncertain:
            print(f"  ? {n}")

    args.out.mkdir(parents=True, exist_ok=True)
    args.private.mkdir(parents=True, exist_ok=True)
    cv_path = args.out / f"{result.cv_id}.cv.json"
    id_path = args.private / f"{result.cv_id}.identity.json"
    cv_path.write_text(json.dumps(result.to_matcher_cv(reader), indent=2, ensure_ascii=False), encoding="utf-8")
    id_path.write_text(result.identity.model_dump_json(indent=2), encoding="utf-8")
    print(f"\nSaved {cv_path}  (for the Matcher)\nSaved {id_path}  (local only, never share)")


if __name__ == "__main__":
    main()
